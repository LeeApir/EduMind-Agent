"""One bounded DeepSeek Responses recheck, public probes only; no quality run."""
# ruff: noqa: E402

import argparse
import asyncio
import json
import os
import re
import time
import traceback
import zlib
from pathlib import Path
from unittest.mock import patch

from run_phase1_provider_connection import ROOT, canonical, configured, dump, sha
from acceptance_support.phase1_budget import Approval, FrozenBudget
from acceptance_support.connection_diagnostics import ProbeFailure, classify_failure
from app.core.config import ProviderSettings
from app.core.provider_factory import configured_provider_adapter
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import _check_status, _request_body, _wire_target
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest
from app.services.provider_protocol import strict_json
import httpx

BASE = ROOT / "docs/acceptance/phase-1-deepseek-connection-v1"
RAW = ROOT / "local-materials/phase-1-deepseek-connection-v1/r01"
MODEL = "deepseek-flash"
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
LIMIT = 2 * 1024 * 1024


def bodies():
    result = {}
    for slot, prompt in PROMPTS.items():
        body = _request_body(
            TextRequest(
                (ChatMessage("user", prompt),), max_output_tokens=128, temperature=0
            )
        )
        body.update(model=MODEL, stream=slot == "stream")
        if slot == "structured":
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "edumind_result",
                    "schema": SCHEMA,
                }
            }
        if slot == "tool":
            body["tools"] = [
                {
                    "type": "function",
                    "name": "emit_probe",
                    "description": "Return the fixed probe flag.",
                    "parameters": SCHEMA,
                }
            ]
            body["tool_choice"] = "auto"
        result[slot] = body
    return result


def observe(raw):
    """Safe fields only; never retain output content, arbitrary arguments or errors."""
    result = {
        "completed": False,
        "model_matches": False,
        "function_count": 0,
        "function_name_matches": False,
        "arguments_schema_valid": False,
        "input_tokens": None,
        "output_tokens": None,
    }
    if not isinstance(raw, dict):
        return result
    result["completed"] = (
        raw.get("status") == "completed"
        and not raw.get("error")
        and not raw.get("incomplete_details")
    )
    result["model_matches"] = raw.get("model") == MODEL
    usage = raw.get("usage")
    if isinstance(usage, dict):
        for key in ("input_tokens", "output_tokens"):
            count = usage.get(key)
            if type(count) is int and count >= 0:
                result[key] = count
    output = raw.get("output")
    if isinstance(output, list):
        calls = [
            item
            for item in output
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        result["function_count"] = len(calls)
        if len(calls) == 1:
            call = calls[0]
            result["function_name_matches"] = call.get("name") == "emit_probe"
            try:
                args = strict_json(call.get("arguments"))
                result["arguments_schema_valid"] = canonical(args) == canonical(
                    {"ok": True}
                )
            except Exception:
                pass
    return result


class Capture(httpx.AsyncByteStream):
    def __init__(self, inner, audit):
        self.inner, self.audit = inner, audit

    async def __aiter__(self):
        async for chunk in self.inner:
            if len(self.audit.payload) + len(chunk) > LIMIT:
                raise ProbeFailure("wire_size")
            self.audit.payload.extend(chunk)
            yield chunk

    async def aclose(self):
        await self.inner.aclose()


class Audit(httpx.AsyncBaseTransport):
    def __init__(self, body):
        self.body = canonical(body)
        self.inner = httpx.AsyncHTTPTransport(retries=0)
        self.payload = bytearray()
        self.sent, self.status, self.encoding = 0, None, "identity"

    async def handle_async_request(self, request):
        if (
            self.sent
            or canonical(strict_json(request.content)) != self.body
            or request.headers.get("host") != "api.deepseek.com"
            or request.extensions.get("sni_hostname") != "api.deepseek.com"
        ):
            raise ProbeFailure("wire_target_or_input")
        self.sent += 1
        response = await self.inner.handle_async_request(request)
        request.headers.pop("Authorization", None)
        self.status = response.status_code
        self.encoding = response.headers.get("content-encoding", "identity").lower()
        response.stream = Capture(response.stream, self)
        return response

    async def aclose(self):
        await self.inner.aclose()

    def decoded(self):
        data = bytes(self.payload)
        if self.encoding == "identity":
            return data
        if self.encoding not in {"gzip", "deflate"}:
            raise ProbeFailure("unsupported_capture_encoding")
        decoder = zlib.decompressobj(
            16 + zlib.MAX_WBITS if self.encoding == "gzip" else zlib.MAX_WBITS
        )
        decoded = decoder.decompress(data, LIMIT + 1)
        if len(decoded) > LIMIT or decoder.unconsumed_tail:
            raise ProbeFailure("decoded_size")
        return decoded

    def observation(self, streaming=False):
        data = self.decoded()
        if not streaming:
            return observe(strict_json(data))
        final = None
        fields = []
        for line in data.replace(b"\r\n", b"\n").split(b"\n"):
            if line.startswith(b"data:"):
                fields.append(line[5:].removeprefix(b" "))
            elif not line and fields:
                obj = strict_json(b"\n".join(fields))
                fields = []
                if isinstance(obj, dict) and obj.get("type") == "response.completed":
                    final = obj.get("response")
        return observe(final)


def freeze():
    if (BASE / "run-r01.json").exists():
        raise ValueError("FREEZE_ALREADY_EXISTS")
    assert configured("EDUMIND_PROVIDER_BASE_URL") == "https://api.deepseek.com"
    assert configured("EDUMIND_PROVIDER_MODEL") == MODEL
    assert (
        configured("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT") == "responses_json_schema"
    )
    config = {
        "provider_type": "openai-compatible",
        "provider": "deepseek",
        "model_id": MODEL,
        "base_url": "https://api.deepseek.com",
        "transport": "Responses /responses",
        "credential_reference": ".env:EDUMIND_PROVIDER_API_KEY",
        "reasoning_effort": "none",
        "max_output_tokens": 128,
        "retries": 0,
        "fallback": False,
    }
    dump(BASE / "configuration.json", config)
    dump(BASE / "public-probes.json", bodies())
    old = json.loads(
        (
            ROOT / "docs/acceptance/phase-1-provider-connection-v1/run-r01.json"
        ).read_text()
    )
    target_id = sha(canonical(config))
    target = {
        "provider_type": "openai-compatible",
        "model_id": MODEL,
        "model_revision": "DeepSeek-V4.1-Flash",
        "adapter_sha256": sha(
            (ROOT / "backend/app/services/deepseek_responses.py").read_bytes()
        ),
        "capability_sha256": target_id,
        "currency": "CNY",
        "input_price_micro_per_million": 2000000,
        "output_price_micro_per_million": 8000000,
        "input_overhead_tokens": 1024,
        "max_wire_bytes": 4096,
        "max_total_output_tokens": 128,
        "total_output_limit_verified": True,
        "token_byte_bound_verified": True,
        "output_limit_path": ["max_output_tokens"],
    }
    paths = list((ROOT / "backend/app").rglob("*.py")) + [
        Path(__file__).resolve(),
        ROOT / "scripts/acceptance_support/phase1_budget.py",
        ROOT / "scripts/acceptance_support/connection_diagnostics.py",
        ROOT / "scripts/run_phase1_provider_connection.py",
        ROOT / "backend/uv.lock",
        ROOT / "backend/pyproject.toml",
        BASE / "approval.json",
        BASE / "pricing.json",
        BASE / "configuration.json",
        BASE / "public-probes.json",
        ROOT / "docs/ADR/0011-dynamic-approval-20261008.json",
    ]
    manifest = {
        **old,
        "run_id": "deepseek-connection-r01",
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
            for slot, body in bodies().items()
        ],
        "bounds": {
            "requests": 4,
            "cost_micro": 100000,
            "max_active_attempts": 1,
            "timeout_seconds": 15,
            "corrections_per_resource": 2,
        },
    }
    dump(BASE / "run-r01.json", manifest)
    gate()._authorize()
    print("DeepSeek public recheck frozen; no model requests.")


def gate():
    manifest = json.loads((BASE / "run-r01.json").read_text())
    approval = BASE / "approval.json"
    return FrozenBudget(
        manifest,
        RAW / "budget.sqlite",
        root=ROOT,
        approval=Approval(
            sha(canonical(manifest)),
            "connection",
            4,
            100000,
            sha(approval.read_bytes()),
            True,
        ),
    )


async def run():
    budget = gate()
    budget._authorize()
    assert configured("EDUMIND_PROVIDER_BASE_URL") == "https://api.deepseek.com"
    assert configured("EDUMIND_PROVIDER_MODEL") == MODEL
    assert (
        configured("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT") == "responses_json_schema"
    )
    results = []
    target_id = next(iter(budget.manifest["targets"]))
    for slot, body in bodies().items():
        if budget.snapshot()["halted"]:
            break
        expected = next(item for item in budget.manifest["slots"] if item["id"] == slot)
        assert sha(canonical(body)) == expected["input_sha256"]
        number = budget.reserve(
            slot, "probe", target_id, canonical(body), resource="unit"
        )
        audit = Audit(body)
        error = category = None
        started = time.monotonic()
        diagnostic = {}
        try:
            async with asyncio.timeout(15):
                settings = ProviderSettings(
                    "https://api.deepseek.com",
                    configured("EDUMIND_PROVIDER_API_KEY"),
                    MODEL,
                )
                guard = ProviderTargetGuard(settings.base_url, TargetPolicy())
                with patch.dict(
                    os.environ,
                    {"EDUMIND_PROVIDER_STRUCTURED_TRANSPORT": "responses_json_schema"},
                ):
                    adapter = configured_provider_adapter(settings, guard)
                adapter._transport = audit
                prompt = TextRequest(
                    (ChatMessage("user", PROMPTS[slot]),),
                    max_output_tokens=128,
                    temperature=0,
                )
                if slot == "text":
                    answer = await adapter.generate_text(prompt)
                    if answer.model_id != MODEL or not answer.text.strip():
                        raise ProbeFailure("text_identity_or_empty")
                elif slot == "structured":
                    answer = await adapter.generate_structured(
                        StructuredRequest(prompt, SCHEMA)
                    )
                    if answer.model_id != MODEL or canonical(answer.value) != canonical(
                        {"ok": True}
                    ):
                        raise ProbeFailure("structured_identity_or_payload")
                elif slot == "stream":
                    text = "".join([d.text async for d in adapter.stream_text(prompt)])
                    if not text.strip():
                        raise ProbeFailure("stream_empty")
                else:
                    target = guard.approve_base()
                    url, host = _wire_target(target)
                    async with httpx.AsyncClient(
                        transport=audit,
                        trust_env=False,
                        follow_redirects=False,
                        timeout=10,
                    ) as client:
                        wire = client.build_request(
                            "POST",
                            url,
                            json=body,
                            headers={
                                "Host": host,
                                "Authorization": "Bearer " + settings.api_key,
                            },
                        )
                        wire.extensions["sni_hostname"] = target.hostname
                        response = await client.send(wire, stream=True)
                        try:
                            _check_status(response)
                            async for _ in response.aiter_bytes():
                                pass
                        finally:
                            await response.aclose()
                fields = audit.observation(slot == "stream")
                if not fields["completed"] or not fields["model_matches"]:
                    raise ProbeFailure("response_completion_or_identity")
                if slot == "tool" and not (
                    fields["function_count"] == 1
                    and fields["function_name_matches"]
                    and fields["arguments_schema_valid"]
                ):
                    raise ProbeFailure("tool_schema")
        except Exception as exc:
            error, category = classify_failure(exc)
            diagnostic = {
                "exception_class": type(exc).__name__,
                "category": category,
                "failed_check": getattr(exc, "check", None),
                "trace": [
                    {"file": str(Path(f.filename).relative_to(ROOT)), "line": f.lineno}
                    for f in traceback.extract_tb(exc.__traceback__)
                    if Path(f.filename).is_relative_to(ROOT)
                ],
            }
        try:
            fields = audit.observation(slot == "stream")
        except Exception:
            fields = observe(None)
        budget.finish(
            number,
            error_code=error,
            input_tokens=fields["input_tokens"],
            output_tokens=fields["output_tokens"],
        )
        result = {
            "slot": slot,
            "attempt": number,
            "passed": error is None,
            "error_code": error,
            "diagnostic": diagnostic,
            "http_status": audit.status,
            "outbound_sends": audit.sent,
            "response": fields,
            "response_sha256": sha(bytes(audit.payload)),
            "request_sha256": sha(canonical(body)),
            "duration_seconds": round(time.monotonic() - started, 6),
            "tool_executions": 0,
            "fallbacks": 0,
        }
        results.append(result)
        dump(
            RAW / "result.json",
            {
                "real_cloud": True,
                "mock": False,
                "observations": results,
                "budget": budget.snapshot(),
                "t040_t041_started": False,
            },
        )
        print(json.dumps(result))
        if error:
            break
    print(
        json.dumps(
            {
                "requests": len(budget.snapshot()["attempts"]),
                "halted": budget.snapshot()["halted"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    try:
        freeze() if args.freeze else asyncio.run(run())
    except Exception as exc:
        print(
            "DeepSeek recheck stopped: "
            + re.sub(r"[^A-Za-z0-9_]", "", type(exc).__name__)
        )
        raise SystemExit(1) from None
