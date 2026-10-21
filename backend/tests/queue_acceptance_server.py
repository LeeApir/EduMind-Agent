"""Loopback-only actual API process for T036; optional deterministic classroom test adapter."""

import argparse
import ipaddress
import os
import sys

import uvicorn

from app.api.classroom import provider_gateway
from app.core import provider_factory
from app.main import app
from app.services.provider_gateway import ProviderGateway, RetryPolicy


def forbidden(*_args, **_kwargs):
    raise RuntimeError("QUEUE_ACCEPTANCE_FORBIDS_REAL_PROVIDER")


def audit(event, args):
    if event == "socket.connect" and isinstance(args[1], tuple):
        host = args[1][0]
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise RuntimeError("QUEUE_ACCEPTANCE_EXTERNAL_NETWORK_FORBIDDEN")


def main():
    if any(name.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL")) for name in os.environ):
        raise RuntimeError("QUEUE_ACCEPTANCE_SENSITIVE_ENVIRONMENT")
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--mock-classroom", action="store_true")
    args = parser.parse_args()
    provider_factory.build_default_provider_gateway = forbidden
    sys.addaudithook(audit)
    if args.mock_classroom:
        from tests.test_classroom_speech_api import FakeAdapter

        adapter = FakeAdapter()
        gateway = ProviderGateway(adapter, retry_policy=RetryPolicy(max_attempts=1))
        app.dependency_overrides[provider_gateway] = lambda: gateway

        @app.get("/test-only/mock-calls")
        async def mock_calls():
            return {"structured_turns": len(adapter.calls), "real_provider_requests": 0}

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8166,
        ssl_keyfile=args.key,
        ssl_certfile=args.cert,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
