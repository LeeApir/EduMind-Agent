"""Isolated backend for the real-HTTP debate browser check with a mock Provider."""

import sys
from pathlib import Path

import uvicorn

backend = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(backend))
sys.path.insert(0, str(backend / "tests"))

from test_debate_api import FakeAdapter  # noqa: E402

from app.api.classroom import provider_gateway  # noqa: E402
from app.main import app  # noqa: E402
from app.services.provider_gateway import ProviderGateway, RetryPolicy  # noqa: E402

app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(
    FakeAdapter(), retry_policy=RetryPolicy(max_attempts=1)
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
