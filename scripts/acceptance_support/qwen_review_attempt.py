"""Real selected temporary connection + exact-wire audit, no default model/credential fallback."""

import asyncio
import hashlib
import ipaddress
import re
import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from acceptance_support.connection_diagnostics import RecordingOperation
from acceptance_support.om_diagnostic import stable
from acceptance_support.qwen_review_budget import GateFailure, sha
from acceptance_support.schema_failure_observation import SAFE_SCHEMA_TOKENS, _fields, _path
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.hybrid_resource_review import INSTRUCTION, REVIEW_V4_PROMPT, review_once
from app.agents.planned_scene_generation import SceneCandidate
from app.agents.shared_learning_plan import CallWindow
from app.core.credential_crypto import CredentialKeyring
from app.core.database import create_database_engine
from app.core.provider_target import resolve_addresses
from app.core.temporary_credentials import TemporaryBinding, TemporaryCredentialRegistry
from app.models.auth import GuestSessionRecord, User
from app.models.provider_connections import ProviderConnection
from app.services.learning_policy import active_policy_digest
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    ConnectionOperation,
    ConnectionRoute,
    DispatchRequest,
    ModelCapabilities,
)
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import StructuredRequest, TaskProfile, TransportAudit
from app.services.provider_protocol import MAX_RESPONSE_BYTES, strict_json

MODEL = "qwen3.8-max-0902"
MODELS = {MODEL, "qwen3.8-max-2026-09-02"}


def require(condition, code):
    if not condition:
        raise GateFailure(code)


def reflected(value, key):
    if isinstance(value, str):
        return key in value or re.search(r"sk-[A-Za-z0-9_-]{16,}", value) is not None
    if isinstance(value, list):
        return any(reflected(v, key) for v in value)
    if isinstance(value, dict):
        return any(reflected(k, key) or reflected(v, key) for k, v in value.items())
    return False


class RawHashStream(httpx.AsyncByteStream):
    def __init__(self, inner, audit):
        self.inner, self.audit = inner, audit

    async def __aiter__(self):
        async for data in self.inner:
            self.audit.raw_bytes += len(data)
            require(self.audit.raw_bytes <= MAX_RESPONSE_BYTES, "INVALID_OUTPUT")
            self.audit.raw_hash.update(data)
            yield data
        self.audit.raw_complete = True

    async def aclose(self):
        await self.inner.aclose()


class ExactTransport(httpx.AsyncBaseTransport):
    def __init__(self, wire, base_url, inner=None):
        self.wire = wire
        self.base = urlsplit(base_url)
        self.inner = inner if inner is not None else httpx.AsyncHTTPTransport(retries=0)
        self.sent = 0
        self.status = None
        self.raw_hash = hashlib.sha256()
        self.raw_bytes = 0
        self.raw_complete = False

    async def handle_async_request(self, request):
        require(
            self.sent == 0 and request.method == "POST" and request.content == self.wire,
            "FREEZE_CHANGED",
        )
        require(
            request.headers.get("host") == self.base.netloc
            and request.extensions.get("sni_hostname") == self.base.hostname
            and request.url.path == self.base.path.rstrip("/") + "/chat/completions"
            and request.url.scheme == "https"
            and (request.url.port or 443) == (self.base.port or 443)
            and ipaddress.ip_address(request.url.host).is_global,
            "TARGET_CHANGED",
        )
        self.sent += 1
        response = await self.inner.handle_async_request(request)
        self.status = response.status_code
        response.stream = RawHashStream(response.stream, self)
        return response

    async def aclose(self):
        await self.inner.aclose()


class AuditedGateway:
    def __init__(self, recorder, audit, wire, key):
        self.recorder, self.audit, self.wire, self.key = recorder, audit, wire, key
        self.calls = 0
        self.response_model_id = None

    async def generate_structured(self, request, *, retry_safe=False):
        require(
            self.calls == 0
            and retry_safe is False
            and request.prompt.task_profile == TaskProfile.QUALITY
            and request.prompt.messages[0].content == INSTRUCTION,
            "TARGET_CHANGED",
        )
        user = strict_json(request.prompt.messages[1].content)
        require(
            user["unit"]["binding"]["policy_digest"] == active_policy_digest(), "TARGET_CHANGED"
        )
        self.calls += 1
        effective = StructuredRequest(
            replace(request.prompt, max_output_tokens=8192, temperature=0), request.json_schema
        )
        result = await OpenAICompatibleAdapter(self.recorder).generate_structured(effective)
        require(result.model_id in MODELS, "TARGET_CHANGED")
        self.response_model_id = result.model_id
        require(not reflected(dict(result.value), self.key), "SAFETY_FAILURE")
        require(self.audit.sent == 1 and self.audit.raw_complete, "INVALID_OUTPUT")
        config = {
            "model": MODEL,
            "response_model_ids": sorted(MODELS),
            "transport": "json_schema",
            "enable_thinking": False,
            "max_completion_tokens": 8192,
            "policy_digest": active_policy_digest(),
            "prompt_version": REVIEW_V4_PROMPT,
        }
        if self.recorder.request.capabilities.schema_profile != "full-v1":
            config["schema_profile"] = self.recorder.request.capabilities.schema_profile
        return replace(
            result,
            transport_audit=TransportAudit(
                sha(self.wire), sha(bytes(self.recorder.payload)), stable(config)
            ),
        )


def failure_observation(exc, recorder, audit, wire, stage):
    """Only allowlisted fields/counts/schema locations; no raw vendor text or values."""
    code = getattr(getattr(exc, "code", None), "value", getattr(exc, "code", None))
    known = {
        "AUTHENTICATION_FAILED",
        "RATE_LIMITED",
        "CAPABILITY_UNAVAILABLE",
        "TIMEOUT",
        "INVALID_OUTPUT",
        "TEMPORARILY_UNAVAILABLE",
        "TARGET_CHANGED",
        "SAFETY_FAILURE",
    }
    normalized = (
        "TIMEOUT"
        if isinstance(exc, (TimeoutError, asyncio.CancelledError))
        else code
        if code in known
        else "INVALID_OUTPUT"
    )
    result = {
        "version": "qwen-safe-failure-v1",
        "normalized_error": normalized,
        "stage": stage,
        "http_status": audit.status if audit else None,
        "sent": audit.sent if audit else 0,
        "raw_capture_complete": audit.raw_complete if audit else False,
        "raw_response_sha256": audit.raw_hash.hexdigest() if audit else None,
        "input_tokens": None,
        "output_tokens": None,
        "finish_reason": None,
        "schema_location": {"status": "NOT_AVAILABLE"},
    }
    if recorder is None:
        return result
    try:
        summary = recorder.summary()
        result["input_tokens"] = summary["input_tokens"]
        result["output_tokens"] = summary["output_tokens"]
        raw = strict_json(bytes(recorder.payload))
        choices = raw.get("choices", [])
        if len(choices) != 1:
            return result
        reason = choices[0].get("finish_reason")
        result["finish_reason"] = (
            reason if reason in {"stop", "length", "tool_calls", "content_filter"} else "other"
        )
        if reason != "stop":
            return result
        value = strict_json(choices[0]["message"]["content"])
        schema = strict_json(wire)["response_format"]["json_schema"]["schema"]
        try:
            Draft202012Validator(schema).validate(value)
        except ValidationError as error:
            result["schema_location"] = {
                "status": "LOCATED",
                "keyword": error.validator if error.validator in SAFE_SCHEMA_TOKENS else "other",
                "instance_path": _path(error.absolute_path, SAFE_SCHEMA_TOKENS),
                "schema_path": _path(error.absolute_schema_path, SAFE_SCHEMA_TOKENS),
            }
            if error.validator == "additionalProperties" and isinstance(error.instance, dict):
                result["schema_location"]["extra_fields"] = _fields(
                    set(error.instance) - set(error.schema.get("properties", {}))
                )
    except Exception:
        pass
    return result


class AttemptFailure(Exception):
    def __init__(self, observation):
        super().__init__("QWEN_ATTEMPT_FAILED")
        self.observation = observation


async def perform(
    case,
    wire,
    *,
    endpoint,
    key,
    database_url,
    authorize,
    transport=None,
    resolver=None,
    schema_profile="full-v1",
    audit_factory=None,
):
    """Caller must have durably reserved before calling. Connection authority is real."""
    # app.main registers all ORM relationships, never starts an app or reads a Provider key.
    import app.main  # noqa: F401

    engine = create_database_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    registry = TemporaryCredentialRegistry()
    store = None
    cid = None
    version = None
    owner = None
    audit = None
    recorder = None
    stage = "connection_setup"
    result = None
    failure = None
    cleanup = None
    try:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=5)
        uid = uuid4()
        session_hash = sha(secrets.token_bytes(32))
        async with factory() as db, db.begin():
            db.add(User(id=uid, is_guest=True))
            await db.flush()
            db.add(
                GuestSessionRecord(
                    token_hash=session_hash, user_id=uid, created_at=now, expires_at=expires
                )
            )
        owner = CredentialIdentity(uid, session_hash)
        store = ProviderConnectionStore(
            factory,
            CredentialKeyring("ephemeral", {"ephemeral": secrets.token_bytes(32)}),
            resolver=resolver or resolve_addresses,
        )
        view = await store.create(
            owner,
            provider_type="openai-compatible",
            display_name="Qwen review diagnostic public fixture",
            base_url=endpoint,
            mode="temporary",
        )
        cid = UUID(str(view["id"]))
        version = int(view["config_version"])
        # Normalized target is used by the real ConnectionOperation, and by exact-wire validation.
        normalized = str(view["base_url"])
        audit = (audit_factory or ExactTransport)(wire, normalized, transport)
        op_id = uuid4()
        handle = await registry.register(
            TemporaryBinding(uid, session_hash, cid, version, op_id, "connection_test", MODEL),
            {"api_key": key},
            session_expires_at=expires,
            validity=lambda: store.valid_version(owner, cid, version),
        )
        route = ConnectionRoute(cid, version, MODEL, frozenset({"probe"}))
        capabilities = ModelCapabilities(
            cid,
            version,
            MODEL,
            "qwen-review-v45-8192-v1",
            structured_output=True,
            structured_transport="json_schema",
            output_token_parameter="max_completion_tokens",
            thinking_enabled=False,
            schema_profile=schema_profile,
        )
        request = DispatchRequest(
            owner,
            route,
            ConnectionConsent(route, True),
            capabilities,
            op_id,
            "connection_test",
            handle,
        )
        used = False

        async def checked_authorize(actual):
            nonlocal used
            require(actual is request and not used, "TARGET_CHANGED")
            await authorize(actual)
            used = True

        operation = ConnectionOperation(store, request, checked_authorize, transport=audit)
        recorder = RecordingOperation(operation)
        gateway = AuditedGateway(recorder, audit, wire, key)
        m = case["material"]
        candidates = tuple(
            SceneCandidate(
                c["resource_id"],
                c["role"],
                c["envelope"],
                c["content_digest"],
                c["dependency_digest"],
                tuple(c["upstream"]),
            )
            for c in m["candidates"]
        )
        stage = "provider"
        async with operation.activate(registry):
            record = await review_once(
                gateway,
                CallWindow(),
                binding=m["binding"],
                target_digest=m["unit_digest"],
                payload={"unit": m, "reference_context": m["reference_context"]},
                candidates=candidates,
                scope="unit",
                input_snapshot=case["input_snapshot"],
            )
        require(used and gateway.calls == 1 and audit.sent == 1, "TARGET_CHANGED")
        summary = recorder.summary()
        raw = strict_json(bytes(recorder.payload))
        require(not reflected(raw, key), "SAFETY_FAILURE")
        result = {
            "review_record": record,
            "model_id": gateway.response_model_id,
            "input_tokens": summary["input_tokens"],
            "output_tokens": summary["output_tokens"],
            "sent": audit.sent,
            "raw_response_sha256": audit.raw_hash.hexdigest(),
            "decoded_response_sha256": sha(bytes(recorder.payload)),
            "schema_valid": True,
            "normal_finish": True,
        }
    except BaseException as exc:
        failure = failure_observation(exc, recorder, audit, wire, stage)
    finally:
        cleanup_deadline = asyncio.get_running_loop().time() + 10
        try:
            async with asyncio.timeout_at(cleanup_deadline):
                await registry.close()
                if store is not None and cid is not None:
                    await store.delete(owner, cid, version)
                    async with factory() as db:
                        row = (
                            await db.execute(
                                select(ProviderConnection).where(ProviderConnection.id == cid)
                            )
                        ).scalar_one()
                        cleanup = {
                            "connection_disabled": not row.enabled,
                            "persistent_secret_absent": row.encrypted_api_key is None
                            and row.credential_key_id is None,
                            "config_version_invalidated": row.config_version > version,
                        }
                    require(all(cleanup.values()), "SAFETY_FAILURE")
        except BaseException:
            if failure is None:
                failure = failure_observation(
                    GateFailure("SAFETY_FAILURE"), recorder, audit, wire, "cleanup"
                )
        finally:
            try:
                async with asyncio.timeout_at(cleanup_deadline):
                    await engine.dispose()
            except BaseException:
                if failure is None:
                    failure = failure_observation(
                        GateFailure("SAFETY_FAILURE"), recorder, audit, wire, "cleanup"
                    )
    if failure is not None:
        failure["cleanup"] = cleanup
        if audit is not None and hasattr(audit, "error_diagnosis"):
            failure["provider_error"] = audit.error_diagnosis
        raise AttemptFailure(failure) from None
    result["cleanup"] = cleanup
    return result
