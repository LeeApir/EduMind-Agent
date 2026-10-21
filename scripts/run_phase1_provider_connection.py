"""T039 fixed four public probes. Real P1 dispatch, no retries/fallback/tool execution.

Freeze offline first; run only against the private test PG after Alembic head.
Never print HTTP exceptions, headers, credentials, raw responses or database URLs.
"""

# ruff: noqa: E402

import argparse
import asyncio
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from acceptance_support.phase1_budget import Approval, FrozenBudget, canonical, sha
from app.core.credential_crypto import CredentialKeyring
from app.core.database import create_database_engine
from app.core.provider_factory import build_connection_provider_gateway
from app.core.temporary_credentials import TemporaryBinding, TemporaryCredentialRegistry
from app.models.auth import GuestSessionRecord, User
from app.models.provider_connections import ProviderConnection
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    ConnectionOperation,
    ConnectionRoute,
    DispatchRequest,
    ModelCapabilities,
)
from app.services.provider_connections import (
    CredentialIdentity,
    ProviderConnectionStore,
)
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    TextRequest,
)
from app.services.provider_protocol import strict_json
from app.services.deepseek_responses import _check_status

BASE = ROOT / "docs/acceptance/phase-1-provider-connection-v1"
RAW = ROOT / "local-materials/phase-1-t039/r01"
MODEL = "qwen3.8-max-0902"
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
PROMPTS = {
    "text": "Reply only with OK.",
    "structured": 'Return JSON {"ok":true}.',
    "tool": "Call emit_probe with ok=true. Do not write prose.",
    "stream": "Reply only with OK.",
}


def configured(name):
    # Parse only the named literal value; never execute/source .env.
    for line in (ROOT / ".env").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip('"').strip("'")
    raise ValueError("CONFIGURATION_MISSING")


def public_bodies():
    bodies = {}
    for slot, prompt in PROMPTS.items():
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": 64,
            "enable_thinking": False,
            "stream": slot == "stream",
            "temperature": 0,
        }
        if slot == "structured":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "edumind_result",
                    "strict": True,
                    "schema": SCHEMA,
                },
            }
        if slot == "tool":
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "emit_probe",
                        "description": "Return the fixed probe flag.",
                        "parameters": SCHEMA,
                    },
                }
            ]
            body["tool_choice"] = {
                "type": "function",
                "function": {"name": "emit_probe"},
            }
        bodies[slot] = body
    return bodies


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def freeze():
    if (BASE / "run-r01.json").exists():
        raise ValueError("FREEZE_ALREADY_EXISTS")
    if configured("EDUMIND_PROVIDER_MODEL") != MODEL:
        raise ValueError("TARGET_CHANGED")
    endpoint = configured("EDUMIND_PROVIDER_BASE_URL")
    bodies = public_bodies()
    dump(BASE / "public-probes.json", bodies)
    config = {
        "provider_type": "openai-compatible",
        "model_id": MODEL,
        "endpoint_sha256": sha(endpoint.encode()),
        "credential_reference": ".env:EDUMIND_PROVIDER_API_KEY",
        "credential_mode": "temporary",
        "output_token_parameter": "max_completion_tokens",
        "thinking_enabled": False,
        "streaming": True,
        "structured_output": True,
        "tool_calling": True,
        "structured_transport": "json_schema",
        "version": "t039-qwen0902-v1",
    }
    dump(BASE / "configuration.json", config)
    target_id = sha(canonical(config))
    files = list((ROOT / "backend/app").rglob("*.py")) + [
        ROOT / "backend/uv.lock",
        ROOT / "backend/pyproject.toml",
        Path(__file__),
        ROOT / "scripts/acceptance_support/phase1_budget.py",
        BASE / "authorization-20261014.json",
        BASE / "pricing-and-capabilities.json",
        BASE / "configuration.json",
        BASE / "public-probes.json",
        ROOT / "docs/ADR/0011-dynamic-approval-20261008.json",
    ]
    manifest = {
        "version": "phase1-run-v1",
        "run_id": "phase1-t039-r01",
        "state": "FROZEN_RUN_READY",
        "phase": "connection",
        "files": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in files},
        "targets": {
            target_id: {
                "provider_type": "openai-compatible",
                "model_id": MODEL,
                "adapter_sha256": sha(
                    (ROOT / "backend/app/services/openai_compatible.py").read_bytes()
                ),
                "capability_sha256": sha(canonical(config)),
                "model_revision": MODEL,
                "currency": "CNY",
                "input_price_micro_per_million": 12000000,
                "output_price_micro_per_million": 36000000,
                "input_overhead_tokens": 512,
                "max_wire_bytes": 4096,
                "max_total_output_tokens": 74,
                "total_output_limit_verified": True,
                "token_byte_bound_verified": True,
                "output_limit_path": ["max_completion_tokens"],
            }
        },
        "slots": [
            {
                "id": slot,
                "input_sha256": sha(canonical(body)),
                "attempts": 1,
                "stages": ["probe"],
                "targets": [target_id],
                "resources": ["unit"],
            }
            for slot, body in bodies.items()
        ],
        "bounds": {
            "requests": 4,
            "cost_micro": 1000000,
            "max_active_attempts": 1,
            "timeout_seconds": 10,
            "corrections_per_resource": 2,
        },
        "required_evidence": ["adr"],
        "evidence": {
            "adr": sha(
                (ROOT / "docs/ADR/0011-dynamic-approval-20261008.json").read_bytes()
            )
        },
    }
    FrozenBudget(manifest, RAW / "budget.sqlite", root=ROOT)
    dump(BASE / "run-r01.json", manifest)
    print("Frozen public probes; no model calls.")


class CaptureStream(httpx.AsyncByteStream):
    def __init__(self, wrapped, audit):
        self.wrapped, self.audit = wrapped, audit

    async def __aiter__(self):
        async for chunk in self.wrapped:
            if len(self.audit.payload) + len(chunk) > 2 * 1024 * 1024:
                raise ValueError("INVALID_OUTPUT")
            self.audit.payload.extend(chunk)
            yield chunk

    async def aclose(self):
        await self.wrapped.aclose()


class AuditedTransport(httpx.AsyncBaseTransport):
    """Same approved IP, Host, SNI, TLS verification, trace and zero HTTP retries."""

    def __init__(self, body):
        self.expected = canonical(body)
        self.inner = httpx.AsyncHTTPTransport(retries=0)
        self.payload = bytearray()
        self.sent = 0
        self.status = None

    async def handle_async_request(self, request):
        if canonical(strict_json(request.content)) != self.expected or self.sent:
            raise ValueError("TARGET_CHANGED")
        self.sent += 1
        response = await self.inner.handle_async_request(request)
        self.status = response.status_code
        response.stream = CaptureStream(response.stream, self)
        return response

    async def aclose(self):
        await self.inner.aclose()

    def usage(self, streaming=False):
        objects = []
        if streaming:
            for line in bytes(self.payload).splitlines():
                if line.startswith(b"data: ") and line[6:] != b"[DONE]":
                    objects.append(strict_json(line[6:]))
        elif self.payload:
            objects.append(strict_json(bytes(self.payload)))
        for obj in reversed(objects):
            raw = obj.get("usage") if isinstance(obj, dict) else None
            if isinstance(raw, dict):
                counts = raw.get("prompt_tokens"), raw.get("completion_tokens")
                if all(type(x) is int and x >= 0 for x in counts):
                    return counts
        return None, None


def verify_tool(raw):
    if raw.get("model") not in {MODEL, "qwen3.8-max-2026-09-02"}:
        raise ValueError("TARGET_CHANGED")
    choices = raw["choices"]
    if len(choices) != 1 or choices[0]["finish_reason"] != "tool_calls":
        raise ValueError("INVALID_OUTPUT")
    calls = choices[0]["message"]["tool_calls"]
    if len(calls) != 1 or calls[0]["type"] != "function":
        raise ValueError("INVALID_OUTPUT")
    function = calls[0]["function"]
    if function["name"] != "emit_probe" or canonical(
        strict_json(function["arguments"])
    ) != canonical({"ok": True}):
        raise ValueError("INVALID_OUTPUT")


async def run():
    # Exact dedicated DB only; never use the running application's database.
    db_url = os.environ.get("EDUMIND_TEST_DATABASE_URL", "")
    if (
        not db_url.endswith("/edumind_catalog_phase1_t039_r01")
        or "@127.0.0.1:15437/" not in db_url
    ):
        raise ValueError("PRIVATE_DATABASE_REQUIRED")
    manifest = json.loads((BASE / "run-r01.json").read_text())
    auth_path = BASE / "authorization-20261014.json"
    auth = json.loads(auth_path.read_text())
    if (
        auth["requests"] != 4
        or auth["cost_micro"] != 1000000
        or auth["fallback"] is not False
    ):
        raise ValueError("NOT_AUTHORIZED")
    budget = FrozenBudget(
        manifest,
        RAW / "budget.sqlite",
        root=ROOT,
        approval=Approval(
            sha(canonical(manifest)),
            "connection",
            4,
            1000000,
            sha(auth_path.read_bytes()),
            True,
        ),
    )
    budget._authorize()
    config = json.loads((BASE / "configuration.json").read_text())
    endpoint = configured("EDUMIND_PROVIDER_BASE_URL")
    if (
        sha(endpoint.encode()) != config["endpoint_sha256"]
        or configured("EDUMIND_PROVIDER_MODEL") != MODEL
    ):
        raise ValueError("TARGET_CHANGED")
    # Register all model metadata without loading application settings or provider keys.
    import app.models  # noqa: F401
    from app.main import app  # noqa: F401

    engine = create_database_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    registry = TemporaryCredentialRegistry()
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=10)
    uid, session_hash = uuid4(), sha(secrets.token_bytes(32))
    async with factory() as db, db.begin():
        db.add(User(id=uid, is_guest=True))
        await db.flush()
        db.add(
            GuestSessionRecord(
                token_hash=session_hash, user_id=uid, created_at=now, expires_at=expiry
            )
        )
    identity = CredentialIdentity(uid, session_hash)
    store = ProviderConnectionStore(
        factory, CredentialKeyring("ephemeral", {"ephemeral": secrets.token_bytes(32)})
    )
    connection = await store.create(
        identity,
        provider_type="openai-compatible",
        display_name="T039 public probe",
        base_url=endpoint,
        mode="temporary",
    )
    cid = UUID(str(connection["id"]))
    version = int(connection["config_version"])
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
    )
    results = []
    target_id = next(iter(manifest["targets"]))
    try:
        for slot, body in public_bodies().items():
            if budget.snapshot()["halted"]:
                break
            wire = canonical(body)
            frozen_slot = next(s for s in manifest["slots"] if s["id"] == slot)
            if sha(wire) != frozen_slot["input_sha256"]:
                raise ValueError("TARGET_CHANGED")
            number = budget.reserve(slot, "probe", target_id, wire, resource="unit")
            audit = AuditedTransport(body)
            observed_targets = []
            started = time.monotonic()
            error = None
            model = None
            try:
                async with asyncio.timeout(10):
                    operation_id = uuid4()
                    binding = TemporaryBinding(
                        uid,
                        session_hash,
                        cid,
                        version,
                        operation_id,
                        "connection_test",
                        MODEL,
                    )
                    handle = await registry.register(
                        binding,
                        {"api_key": configured("EDUMIND_PROVIDER_API_KEY")},
                        session_expires_at=expiry,
                        validity=lambda: store.valid_version(identity, cid, version),
                    )
                    request = DispatchRequest(
                        identity,
                        route,
                        ConnectionConsent(route, True),
                        caps,
                        operation_id,
                        "connection_test",
                        handle,
                    )

                    async def authorize(actual):
                        if actual is not request or actual.route != route:
                            raise ValueError("TARGET_CHANGED")
                        budget._authorize()

                    def observe(target):
                        observed_targets.append(sha(repr(target).encode()))

                    if slot == "tool":
                        operation = ConnectionOperation(
                            store,
                            request,
                            authorize,
                            transport=audit,
                            target_observer=observe,
                        )
                        async with (
                            operation.activate(registry),
                            operation.send(body) as response,
                        ):
                            _check_status(response)
                            raw = strict_json(await response.aread())
                            verify_tool(raw)
                            model = raw["model"]
                    else:
                        async with build_connection_provider_gateway(
                            store,
                            request,
                            authorize,
                            registry=registry,
                            transport=audit,
                            target_observer=observe,
                        ) as gateway:
                            prompt = TextRequest(
                                (ChatMessage("user", PROMPTS[slot]),),
                                max_output_tokens=64,
                                temperature=0,
                            )
                            if slot == "structured":
                                answer = await gateway.generate_structured(
                                    StructuredRequest(prompt, SCHEMA)
                                )
                                if answer.value != {"ok": True}:
                                    raise ValueError("INVALID_OUTPUT")
                                model = answer.model_id
                            elif slot == "stream":
                                text = "".join(
                                    [d.text async for d in gateway.stream_text(prompt)]
                                )
                                if text.strip() != "OK":
                                    raise ValueError("INVALID_OUTPUT")
                                model = MODEL  # Validate the actual returned model below from captured frames.
                            else:
                                answer = await gateway.generate_text(prompt)
                                if answer.text.strip() != "OK":
                                    raise ValueError("INVALID_OUTPUT")
                                model = answer.model_id
                    if slot == "stream":
                        returned = {
                            strict_json(line[6:]).get("model")
                            for line in bytes(audit.payload).splitlines()
                            if line.startswith(b"data: ") and line[6:] != b"[DONE]"
                        }
                        if not returned or not returned <= {
                            MODEL,
                            "qwen3.8-max-2026-09-02",
                        }:
                            raise ValueError("TARGET_CHANGED")
                        model = sorted(returned)[0]
                    if model not in {MODEL, "qwen3.8-max-2026-09-02"}:
                        raise ValueError("TARGET_CHANGED")
            except TimeoutError:
                error = "TIMEOUT"
            except ProviderError as exc:
                error = exc.code.value
                if error not in {
                    "AUTHENTICATION_FAILED",
                    "RATE_LIMITED",
                    "CAPABILITY_UNAVAILABLE",
                    "INVALID_OUTPUT",
                }:
                    error = "TEMPORARILY_UNAVAILABLE"
            except Exception:
                error = "TEMPORARILY_UNAVAILABLE"
            try:
                input_tokens, output_tokens = audit.usage(slot == "stream")
            except Exception:
                input_tokens, output_tokens = None, None
            budget.finish(
                number,
                error_code=error,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            results.append(
                {
                    "slot": slot,
                    "attempt": number,
                    "passed": error is None,
                    "error_code": error,
                    "http_status": audit.status,
                    "outbound_sends": audit.sent,
                    "model": model,
                    "duration_seconds": round(time.monotonic() - started, 6),
                    "target_observations": observed_targets,
                    "request_sha256": sha(wire),
                    "response_sha256": sha(bytes(audit.payload)),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "tool_executions": 0,
                    "fallbacks": 0,
                }
            )
            dump(RAW / "observations.json", results)
            print(json.dumps(results[-1]))
    finally:
        await registry.close()
        await store.delete(identity, cid, version)
        async with factory() as db:
            row = (
                await db.execute(
                    select(ProviderConnection).where(ProviderConnection.id == cid)
                )
            ).scalar_one()
            secret_absent = (
                row.encrypted_api_key is None and row.credential_key_id is None
            )
        dump(
            RAW / "result.json",
            {
                "version": "t039-real-connection-r01",
                "configuration": config,
                "observations": results,
                "budget": budget.snapshot(),
                "persistent_secret_absent": secret_absent,
                "connection_revoked": True,
                "other_adapters": "not_authorized_not_run",
                "mock": False,
                "dynamic_opening": False,
                "t040_t041_started": False,
            },
        )
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    try:
        if args.freeze:
            freeze()
        else:
            asyncio.run(run())
    except Exception as exc:
        # Never expose exception arguments, request objects, URLs or headers.
        print("T039 stopped: " + re.sub(r"[^A-Za-z0-9_]", "", type(exc).__name__))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
