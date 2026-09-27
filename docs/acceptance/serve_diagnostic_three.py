"""Isolated opt-in 3-sample diagnostics; global 36-attempt stop, metadata only."""

import argparse
import json
import os
import time
from pathlib import Path

from first_screen_diagnostics import CURRENT, Timeline, install
from serve_first_screen import instrument_route
from serve_real_browser import Budget, CountingAdapter


class DiagnosticBudget(Budget):
    def reserve(self, kind):
        from app.services.provider_gateway import ProviderError, ProviderErrorCode

        if self.metadata.get("halted"):
            raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING)
        entry = super().reserve(kind)
        entry["start_ns"] = time.monotonic_ns()
        timeline = CURRENT.get()
        entry["request"] = timeline.phase if timeline else "outside_request"
        self.save()
        return entry

    def save(self):
        for entry in self.calls:
            if entry["status"] != "started" and "end_ns" not in entry:
                entry["end_ns"] = time.monotonic_ns()
                entry["duration_ms"] = (entry["end_ns"] - entry["start_ns"]) / 1e6
            if entry.get("error_code") in {
                "AUTHENTICATION_FAILED",
                "RATE_LIMITED",
                "CAPABILITY_UNAVAILABLE",
            }:
                # 402 is normalized as CAPABILITY_UNAVAILABLE: stop conservatively.
                self.metadata["halted"] = "AUTH_QUOTA_OR_CAPABILITY"
        super().save()


class DiagnosticAdapter(CountingAdapter):
    async def stream_text(self, request):
        timeline = CURRENT.get()
        entry = {"stage": "first_screen_provider_stream", "start_ns": time.monotonic_ns()}
        if timeline:
            timeline.spans.append(entry)
        try:
            async for delta in super().stream_text(request):
                if delta.text.strip():
                    entry.setdefault("first_delta_ns", time.monotonic_ns())
                yield delta
        finally:
            entry["end_ns"] = time.monotonic_ns()
            entry["duration_ms"] = (entry["end_ns"] - entry["start_ns"]) / 1e6


class Patcher:
    @staticmethod
    def setattr(target, name, value):
        setattr(target, name, value)


class TraceMiddleware:
    def __init__(self, app, output):
        self.app = app
        self.output = output
        self.records = []
        output.open("x").close()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        timeline = Timeline()
        # No URLs, IDs, headers or query strings recorded.
        path = scope["path"]
        timeline.phase = (
            "learning"
            if path == "/api/learning-sessions"
            else "anonymous"
            if path == "/api/auth/guest"
            else "read_only"
        )
        record = {
            "number": len(self.records) + 1,
            "phase": timeline.phase,
            "started_ns": timeline.started_ns,
            "spans": timeline.spans,
            "physical_connections": 0,
            "checkouts": 0,
        }
        timeline.record = record
        self.records.append(record)
        token = CURRENT.set(timeline)

        async def measured_send(message):
            if message["type"] == "http.response.start":
                record["status"] = message["status"]
                record["headers_sent_ns"] = time.monotonic_ns()
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        finally:
            record["ended_ns"] = time.monotonic_ns()
            CURRENT.reset(token)
            self.output.write_text(json.dumps(self.records, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable or "perf_t032_diag3" not in os.getenv("EDUMIND_DATABASE_URL", ""):
        parser.error("Requires explicit billing authorization and fresh diagnostic database")
    from sqlalchemy import event

    from app.core import database, provider_factory
    from app.services import deepseek_responses

    budget = DiagnosticBudget(args.ledger, 36)
    original_status = deepseek_responses._check_status

    def checked(response):
        if response.status_code in {401, 402, 403, 429}:
            budget.metadata["halted"] = "AUTH_BALANCE_QUOTA"
            budget.save()
        return original_status(response)

    deepseek_responses._check_status = checked
    original_adapter = provider_factory.configured_provider_adapter
    provider_factory.configured_provider_adapter = lambda settings, guard: DiagnosticAdapter(
        original_adapter(settings, guard), budget
    )
    original_engine = database.create_database_engine

    def engine(*args, **kwargs):
        result = original_engine(*args, **kwargs)

        def count(label):
            def hook(*_args):
                timeline = CURRENT.get()
                if timeline:
                    timeline.record[label] += 1

            return hook

        event.listen(result.sync_engine, "connect", count("physical_connections"))
        event.listen(result.sync_engine, "checkout", count("checkouts"))
        return result

    database.create_database_engine = engine
    import uvicorn

    from app.main import app

    install(Patcher(), Timeline())
    instrument_route(app)
    app.add_middleware(TraceMiddleware, output=args.trace)
    uvicorn.run(app, host="127.0.0.1", port=8012, access_log=False, workers=1)


if __name__ == "__main__":
    main()
