"""Opt-in real server: validated endpoint clock and global Provider attempt cap."""

import argparse
import os
import time
from pathlib import Path

from serve_real_browser import Budget, CountingAdapter

HEADER = "X-Acceptance-Validated-At-Ns"


def instrument_route(app):
    """Wrap only the resolved call, after FastAPI schema/auth dependency validation."""
    route = next(r for r in app.routes if r.path == "/api/learning-sessions")
    original = route.dependant.call

    async def measured(**kwargs):
        started = time.monotonic_ns()
        response = await original(**kwargs)
        response.headers[HEADER] = str(started)
        return response

    route.dependant.call = measured


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("Requires --confirm-billable")
    if "perf_t032" not in os.getenv("EDUMIND_DATABASE_URL", ""):
        parser.error("Requires dedicated perf_t032 database")

    from app.core import provider_factory

    budget = Budget(args.ledger, 240)
    original = provider_factory.configured_provider_adapter
    provider_factory.configured_provider_adapter = lambda settings, guard: CountingAdapter(
        original(settings, guard), budget
    )
    import uvicorn

    from app.main import app

    instrument_route(app)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, workers=1)


if __name__ == "__main__":
    main()
