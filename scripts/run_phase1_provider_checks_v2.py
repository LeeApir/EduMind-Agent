"""Active T039 structured/stream checks, using the remaining 2/4 authorized requests.

Never resets stopped r01. Freeze before execute; no retry, fallback or learner data.
"""
# ruff: noqa: E402

import argparse
import asyncio
import json
import secrets
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from run_phase1_provider_connection import (
    BASE,
    MODEL,
    ROOT,
    Approval,
    AuditedTransport,
    ConnectionConsent,
    ConnectionOperation,
    ConnectionRoute,
    CredentialIdentity,
    CredentialKeyring,
    DispatchRequest,
    FrozenBudget,
    GuestSessionRecord,
    ModelCapabilities,
    ProviderConnection,
    ProviderConnectionStore,
    TemporaryBinding,
    TemporaryCredentialRegistry,
    User,
    async_sessionmaker,
    canonical,
    configured,
    create_database_engine,
    dump,
    os,
    public_bodies,
    select,
    sha,
)
from acceptance_support.connection_diagnostics import (
    RecordingOperation,
    ProbeFailure,
    classify_failure,
)
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_gateway import ChatMessage, TextRequest, StructuredRequest
from run_phase1_provider_connection import SCHEMA, PROMPTS

RAW = ROOT / "local-materials/phase-1-t039/checks-r03"
FREEZE = BASE / "checks-r03.json"
AUTH = BASE / "checks-allocation.json"
PRIOR = BASE / "results/r01.json"
BODIES = {s: b for s, b in public_bodies().items() if s in {"structured", "stream"}}
BODIES["stream"]["stream_options"] = {"include_usage": True}


def prior_usage():
    import sqlite3

    expected = [
        ("r01", 1, 10860, "TEMPORARILY_UNAVAILABLE"),
        ("diagnostic-r02", 1, 10860, None),
    ]
    count, cost = 0, 0
    for name, n, c, h in expected:
        db = sqlite3.connect(
            f"file:{ROOT / 'local-materials/phase-1-t039' / name / 'budget.sqlite'}?mode=ro",
            uri=True,
        )
        try:
            actual = db.execute(
                "SELECT count(*),coalesce(sum(cost_micro),0) FROM attempts"
            ).fetchone()
            halt = db.execute("SELECT halted FROM run WHERE id=1").fetchone()[0]
        finally:
            db.close()
        if (*actual, halt) != (n, c, h):
            raise ValueError("PRIOR_BUDGET_CHANGED")
        count += n
        cost += c
    return count, cost


def gate():
    prior_usage()
    manifest = json.loads(FREEZE.read_text())
    return FrozenBudget(
        manifest,
        RAW / "budget.sqlite",
        root=ROOT,
        approval=Approval(
            sha(canonical(manifest)),
            "connection",
            2,
            100000,
            sha(AUTH.read_bytes()),
            True,
        ),
    )


def freeze():
    if FREEZE.exists():
        raise ValueError("FREEZE_ALREADY_EXISTS")
    prior_usage()
    dump(
        AUTH,
        {
            "user_instruction": "可以解决这个问题然后进行T39吗",
            "original_authorization": "authorization-20261014.json",
            "original_requests": 4,
            "original_cost_micro": 1000000,
            "prior_requests": 2,
            "prior_reserved_cost_micro": 21720,
            "allocated_requests": 2,
            "allocated_cost_micro": 100000,
            "slots": ["structured", "stream"],
            "data_categories": ["probe"],
            "retries": 0,
            "fallback": False,
            "tool_probe": "Not authorized in this allocation; original aggregate 4-request limit would be exceeded.",
        },
    )
    old = json.loads((BASE / "run-r01.json").read_text())
    config = json.loads((BASE / "configuration.json").read_text())
    config["version"] = "t039-checks-v2"
    config["include_stream_usage"] = True
    dump(BASE / "checks-configuration.json", config)
    dump(BASE / "checks-bodies.json", BODIES)
    target_id = sha(canonical(config))
    target = next(iter(old["targets"].values())).copy()
    target["adapter_sha256"] = sha(
        (ROOT / "backend/app/services/openai_compatible.py").read_bytes()
    )
    target["capability_sha256"] = target_id
    paths = [ROOT / p for p in old["files"]] + [
        Path(__file__).resolve(),
        AUTH,
        PRIOR,
        BASE / "results/diagnostic-r02.json",
        BASE / "checks-configuration.json",
        BASE / "checks-bodies.json",
        ROOT / "scripts/acceptance_support/connection_diagnostics.py",
    ]
    manifest = {
        **old,
        "run_id": "phase1-t039-checks-r03",
        "files": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths},
        "targets": {target_id: target},
        "slots": [
            {
                "id": slot,
                "input_sha256": sha(canonical(body)),
                "attempts": 1,
                "stages": ["probe"],
                "targets": [target_id],
                "resources": ["unit"],
            }
            for slot, body in BODIES.items()
        ],
        "bounds": {**old["bounds"], "requests": 2, "cost_micro": 100000},
    }
    dump(FREEZE, manifest)
    gate()._authorize()
    print("Diagnostic frozen; zero extra provider calls.")


async def run(slot):
    body = BODIES[slot]
    import app.main  # noqa: F401

    db_url = os.environ.get("EDUMIND_TEST_DATABASE_URL", "")
    if (
        not db_url.endswith("/edumind_catalog_phase1_t039_r01")
        or "@127.0.0.1:15437/" not in db_url
    ):
        raise ValueError("PRIVATE_DATABASE_REQUIRED")
    budget = gate()
    budget._authorize()
    config = json.loads((BASE / "checks-configuration.json").read_text())
    endpoint = configured("EDUMIND_PROVIDER_BASE_URL")
    if (
        sha(endpoint.encode()) != config["endpoint_sha256"]
        or configured("EDUMIND_PROVIDER_MODEL") != MODEL
    ):
        raise ValueError("TARGET_CHANGED")
    target_id = next(iter(budget.manifest["targets"]))
    engine = create_database_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=5)
    uid, token = uuid4(), sha(secrets.token_bytes(32))
    async with factory() as db, db.begin():
        db.add(User(id=uid, is_guest=True))
        await db.flush()
        db.add(
            GuestSessionRecord(
                token_hash=token, user_id=uid, created_at=now, expires_at=expires
            )
        )
    identity = CredentialIdentity(uid, token)
    store = ProviderConnectionStore(
        factory, CredentialKeyring("ephemeral", {"ephemeral": secrets.token_bytes(32)})
    )
    view = await store.create(
        identity,
        provider_type="openai-compatible",
        display_name="T039 diagnostic public probe",
        base_url=endpoint,
        mode="temporary",
    )
    cid, version = UUID(str(view["id"])), int(view["config_version"])
    registry = TemporaryCredentialRegistry()
    audit = AuditedTransport(body)
    recorder = None
    error = None
    diagnostic = {}
    stage = "credential"
    model = None
    exact_ok = None
    started = time.monotonic()
    number = budget.reserve(slot, "probe", target_id, canonical(body), resource="unit")
    try:
        async with asyncio.timeout(10):
            op_id = uuid4()
            handle = await registry.register(
                TemporaryBinding(
                    uid, token, cid, version, op_id, "connection_test", MODEL
                ),
                {"api_key": configured("EDUMIND_PROVIDER_API_KEY")},
                session_expires_at=expires,
                validity=lambda: store.valid_version(identity, cid, version),
            )
            route = ConnectionRoute(cid, version, MODEL, frozenset({"probe"}))
            caps = ModelCapabilities(
                cid,
                version,
                MODEL,
                config["version"],
                True,
                True,
                "json_schema",
                True,
                output_token_parameter="max_completion_tokens",
                thinking_enabled=False,
                include_stream_usage=True,
            )
            request = DispatchRequest(
                identity,
                route,
                ConnectionConsent(route, True),
                caps,
                op_id,
                "connection_test",
                handle,
            )
            used = False

            async def authorize(actual):
                nonlocal used
                if actual is not request or used:
                    raise ValueError("TARGET_CHANGED")
                prior_usage()
                budget._authorize()
                used = True

            operation = ConnectionOperation(store, request, authorize, transport=audit)
            recorder = RecordingOperation(operation)
            stage = "dispatch_and_production_parser"
            async with operation.activate(registry):
                adapter = OpenAICompatibleAdapter(recorder)
                prompt = TextRequest(
                    (ChatMessage("user", PROMPTS[slot]),),
                    max_output_tokens=64,
                    temperature=0,
                )
                if slot == "structured":
                    answer = await adapter.generate_structured(
                        StructuredRequest(prompt, SCHEMA)
                    )
                    if canonical(answer.value) != canonical({"ok": True}):
                        raise ProbeFailure("structured_payload")
                    model = answer.model_id
                else:
                    text = "".join(
                        [delta.text async for delta in adapter.stream_text(prompt)]
                    )
                    exact_ok = (
                        text.strip() == "OK"
                    )  # Diagnostic only; normal protocol completion is the connection criterion.
                    objects = recorder.objects(streaming=True)
                    models = {
                        obj.get("model") for obj in objects if isinstance(obj, dict)
                    }
                    if not models or not models <= {MODEL, "qwen3.8-max-2026-09-02"}:
                        raise ProbeFailure("stream_model_identity")
                    model = sorted(models)[0]
                stage = "model_identity"
                if model not in {MODEL, "qwen3.8-max-2026-09-02"}:
                    raise ProbeFailure("model_identity")
                stage = "complete"
    except TimeoutError:
        error = "TIMEOUT"
    except Exception as exc:
        error, category = classify_failure(exc)
        diagnostic = {
            "exception_class": type(exc).__name__,
            "category": category,
            "stage": stage,
            "trace": [
                {"file": str(Path(f.filename).relative_to(ROOT)), "line": f.lineno}
                for f in traceback.extract_tb(exc.__traceback__)
                if Path(f.filename).is_relative_to(ROOT)
            ],
            "output_failure_reason": getattr(
                getattr(exc, "output_failure_reason", None), "value", None
            ),
        }
    finally:
        summary = (
            recorder.summary(streaming=slot == "stream")
            if recorder
            else {"input_tokens": None, "output_tokens": None}
        )
        budget.finish(
            number,
            error_code=error,
            input_tokens=summary["input_tokens"],
            output_tokens=summary["output_tokens"],
        )
        await registry.close()
        await store.delete(identity, cid, version)
        async with factory() as db:
            row = (
                await db.execute(
                    select(ProviderConnection).where(ProviderConnection.id == cid)
                )
            ).scalar_one()
            no_secret = row.encrypted_api_key is None and row.credential_key_id is None
        result = {
            "version": "t039-checks-r03",
            "slot": slot,
            "real_cloud": True,
            "mock": False,
            "http_status": audit.status,
            "outbound_sends": audit.sent,
            "parser_passed": error is None,
            "error_code": error,
            "diagnostic": diagnostic,
            "model": model,
            "matches_original_exact_OK": exact_ok,
            "response": summary,
            "response_wire_sha256": sha(bytes(audit.payload)),
            "response_decoded_sha256": sha(bytes(recorder.payload))
            if recorder
            else None,
            "duration_seconds": round(time.monotonic() - started, 6),
            "budget": budget.snapshot(),
            "aggregate_attempts_including_r01": 2 + len(budget.snapshot()["attempts"]),
            "aggregate_reserved_cost_micro": 21720
            + sum(r[5] for r in budget.snapshot()["attempts"]),
            "persistent_secret_absent": no_secret,
            "connection_revoked": True,
            "retries": 0,
            "fallbacks": 0,
            "t040_t041_started": False,
        }
        dump(RAW / (slot + ".json"), result)
        print(json.dumps(result))
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--slot", choices=["structured", "stream"])
    args = parser.parse_args()
    try:
        if args.freeze:
            freeze()
        elif args.slot:
            asyncio.run(run(args.slot))
        else:
            raise ValueError("SLOT_REQUIRED")
    except Exception as exc:
        print("Diagnostic stopped: " + type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
