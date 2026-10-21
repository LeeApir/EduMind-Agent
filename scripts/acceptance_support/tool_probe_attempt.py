"""One guarded public tool probe; only trusted frozen composition supplies this context."""
# ruff: noqa: E402

import asyncio
import json
import secrets
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from acceptance_support.connection_diagnostics import (
    ProbeFailure,
    RecordingOperation,
    classify_failure,
)
from acceptance_support.tool_probe_observation import tool_metadata, tool_shape
from run_phase1_provider_connection import (
    MODEL,
    ROOT,
    AuditedTransport,
    ConnectionConsent,
    ConnectionOperation,
    ConnectionRoute,
    CredentialIdentity,
    CredentialKeyring,
    DispatchRequest,
    GuestSessionRecord,
    ModelCapabilities,
    ProviderConnection,
    ProviderConnectionStore,
    TemporaryBinding,
    TemporaryCredentialRegistry,
    User,
    _check_status,
    async_sessionmaker,
    canonical,
    configured,
    create_database_engine,
    dump,
    os,
    select,
    sha,
    strict_json,
    verify_tool,
)


async def run_probe(*, budget, evidence_dir, body, config, prior_check):
    slot = "tool"
    prior_count, prior_cost = prior_check()
    import app.main  # noqa: F401

    db_url = os.environ.get("EDUMIND_TEST_DATABASE_URL", "")
    if not db_url.endswith("/edumind_catalog_phase1_t039_r01") or "@127.0.0.1:15437/" not in db_url:
        raise ValueError("PRIVATE_DATABASE_REQUIRED")
    budget._authorize()
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
            GuestSessionRecord(token_hash=token, user_id=uid, created_at=now, expires_at=expires)
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
    tool_checks = {}
    tool_fields = {}
    stage = "credential"
    model = None
    exact_ok = None
    started = time.monotonic()
    number = budget.reserve(slot, "probe", target_id, canonical(body), resource="unit")
    try:
        async with asyncio.timeout(10):
            op_id = uuid4()
            handle = await registry.register(
                TemporaryBinding(uid, token, cid, version, op_id, "connection_test", MODEL),
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
                if prior_check() != (prior_count, prior_cost):
                    raise ValueError("PRIOR_BUDGET_CHANGED")
                budget._authorize()
                used = True

            operation = ConnectionOperation(store, request, authorize, transport=audit)
            recorder = RecordingOperation(operation)
            stage = "dispatch_and_production_parser"
            async with operation.activate(registry):
                async with recorder.send(body) as response:
                    _check_status(response)
                    async for _ in response.aiter_bytes():
                        operation._check()
                    raw = strict_json(bytes(recorder.payload))
                    tool_checks = tool_shape(raw, models={MODEL, "qwen3.8-max-2026-09-02"})
                    tool_fields = tool_metadata(raw)
                    if not all(tool_checks.values()):
                        raise ProbeFailure("tool_response_schema")
                    verify_tool(raw)
                    model = raw["model"]
                    stage = "model_identity"
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
                await db.execute(select(ProviderConnection).where(ProviderConnection.id == cid))
            ).scalar_one()
            no_secret = row.encrypted_api_key is None and row.credential_key_id is None
        result = {
            "version": config["version"],
            "slot": slot,
            "real_cloud": True,
            "mock": False,
            "http_status": audit.status,
            "outbound_sends": audit.sent,
            "parser_passed": error is None,
            "error_code": error,
            "diagnostic": diagnostic,
            "tool_checks": tool_checks,
            "tool_fields": tool_fields,
            "model": model,
            "matches_original_exact_OK": exact_ok,
            "response": summary,
            "response_wire_sha256": sha(bytes(audit.payload)),
            "response_decoded_sha256": sha(bytes(recorder.payload)) if recorder else None,
            "duration_seconds": round(time.monotonic() - started, 6),
            "budget": budget.snapshot(),
            "aggregate_attempts_including_r01": prior_count + len(budget.snapshot()["attempts"]),
            "aggregate_reserved_cost_micro": prior_cost
            + sum(r[5] for r in budget.snapshot()["attempts"]),
            "persistent_secret_absent": no_secret,
            "connection_revoked": True,
            "retries": 0,
            "fallbacks": 0,
            "tool_executions": 0,
            "t040_t041_started": False,
        }
        dump(evidence_dir / (slot + ".json"), result)
        print(json.dumps(result))
        await engine.dispose()
