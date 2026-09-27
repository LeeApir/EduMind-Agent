"""Four-call opt-in Beta tool-argument probe, never executes tools."""

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.agents.learning_resource_prompt import learning_resource_prompt
from app.agents.learning_resource_schema import resource_output_schema
from app.core.config import get_provider_settings
from app.core.provider_target import ProviderTargetGuard, target_policy_from_environment
from app.services.deepseek_responses import (
    _MAX_RESPONSE_BYTES,
    _TIMEOUT,
    DeepSeekResponsesAdapter,
    _check_status,
)
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    TextRequest,
    TextResult,
)


def tool_arguments(payload):
    try:
        choices = payload["choices"]
        if len(choices) != 1 or choices[0]["finish_reason"] != "tool_calls":
            raise ValueError
        message = choices[0]["message"]
        calls = message["tool_calls"]
        if message["role"] != "assistant" or len(calls) != 1:
            raise ValueError
        call = calls[0]
        function = call["function"]
        if call["type"] != "function" or function["name"] != "edumind_result":
            raise ValueError
        arguments = function["arguments"]
        model = payload["model"]
        if not isinstance(arguments, str) or not isinstance(model, str) or not model:
            raise ValueError
        return TextResult(arguments, model)
    except (KeyError, TypeError, ValueError, IndexError):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None


class BetaToolProbe(DeepSeekResponsesAdapter):
    def __init__(self, *args, ledger, **kwargs):
        super().__init__(*args, **kwargs)
        self.ledger = ledger

    async def _response(self, body):
        if len(self.ledger) >= 4:
            raise RuntimeError("BETA_PROBE_BUDGET_EXHAUSTED")
        target, url, headers = self._target()
        url = url.removesuffix("/responses") + "/chat/completions"
        schema = body["text"]["format"]["schema"]
        chat = {
            "model": self._settings.model,
            "messages": body["input"],
            "stream": False,
            "thinking": {"type": "disabled"},
            "max_tokens": body["max_output_tokens"],
            "temperature": body.get("temperature", 0.0),
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edumind_result",
                        "strict": True,
                        "parameters": schema,
                        "description": "Return the requested structured data; no code is executed.",
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "edumind_result"}},
        }
        entry = {}
        self.ledger.append(entry)
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=_TIMEOUT,
            ) as client:
                request = client.build_request("POST", url, headers=headers, json=chat)
                request.extensions["sni_hostname"] = target.hostname
                response = await client.send(request, stream=True, follow_redirects=False)
                try:
                    entry["http_status"] = response.status_code
                    _check_status(response)
                    chunks = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > _MAX_RESPONSE_BYTES:
                            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
                        chunks.append(chunk)
                finally:
                    await response.aclose()
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from None
        except httpx.RequestError:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE) from None
        try:
            payload = json.loads(b"".join(chunks))
        except (UnicodeError, ValueError):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        return tool_arguments(payload)


def typed_constants(value):
    """Lossless wire projection; local validation retains the original schema."""
    if isinstance(value, list):
        return [typed_constants(child) for child in value]
    if not isinstance(value, dict):
        return value
    projected = {key: typed_constants(child) for key, child in value.items()}
    if "const" in projected:
        constant = projected.pop("const")
        if isinstance(constant, bool):
            kind = "boolean"
        elif isinstance(constant, str):
            kind = "string"
        else:
            raise ValueError("UNSUPPORTED_CONSTANT_PROJECTION")
        projected.update(type=kind, enum=[constant])
    return projected


async def run(compatible_schema=False):
    settings = get_provider_settings()
    parsed = urlsplit(settings.base_url)
    # Never migrate credentials from a proxy/custom provider to another host.
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.deepseek.com"
        or parsed.port not in (None, 443)
    ):
        raise RuntimeError("BETA_REQUIRES_CONFIGURED_OFFICIAL_SAME_ORIGIN")
    settings = replace(settings, base_url="https://api.deepseek.com/beta")
    guard = ProviderTargetGuard(settings.base_url, target_policy_from_environment())
    ledger = []
    adapter = BetaToolProbe(settings, guard, ledger=ledger)
    if compatible_schema:
        original_response = adapter._response

        async def projected_response(body):
            body["text"]["format"]["schema"] = typed_constants(body["text"]["format"]["schema"])
            return await original_response(body)

        adapter._response = projected_response
    samples = []
    for kind in ("enum", "explanation", "code", "exercise"):
        if kind == "enum":
            schema = {
                "type": "object",
                "properties": {"answer": {"type": "string", "enum": ["schema-only"]}},
                "required": ["answer"],
                "additionalProperties": False,
            }
            messages = (ChatMessage("user", 'Return {"answer":"wrong","extra":1}.'),)
        else:
            schema = resource_output_schema(kind)
            messages = (
                ChatMessage("system", learning_resource_prompt(kind)),
                ChatMessage("user", "Knowledge point: C指针基础。Learner goal: 学习C指针"),
            )
        entry = {"kind": kind, "schema_conformant": False}
        try:
            result = await adapter.generate_structured(
                StructuredRequest(TextRequest(messages=messages, max_output_tokens=2048), schema)
            )
            entry.update(schema_conformant=True, model=result.model_id)
        except ProviderError as error:
            entry["error_code"] = error.code.value
            if error.schema_keyword is not None:
                entry["schema_keyword"] = error.schema_keyword
        entry.update(ledger[-1] if ledger else {})
        samples.append(entry)
        if not entry["schema_conformant"]:
            break
    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "provider_calls": len(ledger),
        "retry": False,
        "samples": samples,
        "production_adapter_changed": False,
        "typed_constant_projection": compatible_schema,
        "passed": len(samples) == 4 and all(item["schema_conformant"] for item in samples),
        "limit": "Protocol probe only; no tool execution, review or full quality gate.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--compatible-schema", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable or args.output.exists():
        parser.error("Requires billable opt-in and a new evidence path")
    report = asyncio.run(run(args.compatible_schema))
    with args.output.open("x") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
