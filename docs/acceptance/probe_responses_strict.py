"""Opt-in, three-call strict-flag probe; no production policy mutation."""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.provider_factory import build_server_provider_gateway
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import ChatMessage, ProviderError, StructuredRequest, TextRequest


class StrictProbeAdapter(DeepSeekResponsesAdapter):
    def __init__(self, *args, strict, ledger, **kwargs):
        super().__init__(*args, **kwargs)
        self.strict = strict
        self.ledger = ledger

    async def _response(self, body):
        if len(self.ledger) >= 3:
            raise RuntimeError("STRICT_PROBE_BUDGET_EXHAUSTED")
        if self.strict is not None:
            body["text"]["format"]["strict"] = self.strict
        self.ledger.append({"strict": self.strict})
        return await super()._response(body)


async def run():
    ledger = []
    samples = []
    # Contradict schema with harmless public text. Only conformance is exported.
    for strict, expected in ((None, "schema-only"), (True, "schema-only"), (True, "enum-only")):
        gateway = build_server_provider_gateway(
            lambda settings, guard: StrictProbeAdapter(
                settings, guard, strict=strict, ledger=ledger
            )
        )
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string", "enum": [expected]}},
            "required": ["answer"],
            "additionalProperties": False,
        }
        request = StructuredRequest(
            TextRequest(
                messages=(
                    ChatMessage("system", "Return JSON only."),
                    ChatMessage("user", 'Return exactly {"answer":"prompt-only","extra":1}.'),
                ),
                max_output_tokens=256,
            ),
            schema,
        )
        entry = {"strict": strict, "schema_conformant": False}
        try:
            result = await gateway.generate_structured(request, retry_safe=False)
            entry.update(schema_conformant=True, model=result.model_id)
        except ProviderError as error:
            entry["error_code"] = error.code.value
            for name in ("output_failure_reason", "json_syntax_reason"):
                value = getattr(error, name, None)
                if value is not None:
                    entry[name] = value.value
            if error.schema_keyword is not None:
                entry["schema_keyword"] = error.schema_keyword
        samples.append(entry)
    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "provider_calls": len(ledger),
        "retry": False,
        "production_adapter_changed": False,
        "samples": samples,
        "limit": (
            "Acceptance alone cannot prove strict enforcement; "
            "three probes are not a quality gate."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("Explicit billable confirmation required")
    if args.output.exists():
        parser.error("Refusing to overwrite evidence")
    report = asyncio.run(run())
    with args.output.open("x") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
