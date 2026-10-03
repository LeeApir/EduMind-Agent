"""Run the actual Uvicorn app with a global, single-worker real Provider budget."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core import provider_factory
from app.core.config import get_provider_settings
from app.services.provider_gateway import ProviderError, ProviderErrorCode


class Budget:
    def __init__(self, output: Path, limit: int):
        self.output = output
        self.limit = limit
        self.calls = []
        self.metadata = {
            "configured_model": get_provider_settings().model,
            "structured_transport": os.getenv(
                "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema"
            ),
            "limit": limit,
            "provider_calls": self.calls,
        }
        with output.open("x") as handle:
            json.dump(self.metadata, handle)

    def save(self):
        self.output.write_text(json.dumps(self.metadata, indent=2) + "\n")

    def reserve(self, kind):
        if len(self.calls) >= self.limit:
            raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING)
        entry = {"number": len(self.calls) + 1, "kind": kind, "status": "started"}
        self.calls.append(entry)
        self.save()
        return entry


class CountingAdapter:
    def __init__(self, adapter, budget):
        self.adapter = adapter
        self.budget = budget

    async def call(self, kind, request):
        entry = self.budget.reserve(kind)
        try:
            method = getattr(self.adapter, f"generate_{kind}")
            result = await method(request)
            entry.update(status="completed", returned_model=result.model_id)
            if result.usage is not None:
                entry["usage"] = {
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                }
            return result
        except ProviderError as error:
            entry.update(status="failed", error_code=error.code.value)
            raise
        finally:
            self.budget.save()

    async def generate_structured(self, request):
        return await self.call("structured", request)

    async def generate_text(self, request):
        return await self.call("text", request)

    async def stream_text(self, request):
        entry = self.budget.reserve("stream")
        try:
            async for delta in self.adapter.stream_text(request):
                yield delta
            entry["status"] = "completed"
        except ProviderError as error:
            entry.update(status="failed", error_code=error.code.value)
            raise
        finally:
            self.budget.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=30, choices=range(1, 31))
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("Real Provider server requires --confirm-billable")
    if "browser_t031" not in os.getenv("EDUMIND_DATABASE_URL", ""):
        parser.error("A dedicated browser_t031 acceptance database is required")
    budget = Budget(args.ledger, args.limit)
    original = provider_factory.configured_provider_adapter
    provider_factory.configured_provider_adapter = lambda settings, guard: CountingAdapter(
        original(settings, guard), budget
    )
    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, workers=1)


if __name__ == "__main__":
    main()
