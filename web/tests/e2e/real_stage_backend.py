"""FastAPI with deterministic model replies for the integrated MVP 0.3 browser flow."""

import sys
from pathlib import Path

import uvicorn

backend = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(backend))
sys.path.insert(0, str(backend / "tests"))

from test_classroom_speech_api import FakeAdapter as SpeechAdapter  # noqa: E402
from test_debate_api import FakeAdapter as DebateAdapter  # noqa: E402

from app.api.classroom import provider_gateway  # noqa: E402
from app.main import app  # noqa: E402
from app.services.provider_gateway import ProviderGateway, RetryPolicy  # noqa: E402


class StageAdapter:
    def __init__(self) -> None:
        self.speech = SpeechAdapter()
        self.debate = DebateAdapter()

    async def generate_structured(self, request):  # type: ignore[no-untyped-def]
        properties = request.json_schema.get("properties", {})
        if "turn_version" in properties:
            return await self.speech.generate_structured(request)
        if properties.get("review_version", {}).get("const") == "resource-review-v3":
            return await self.speech.generate_structured(request)
        return await self.debate.generate_structured(request)

    async def generate_text(self, request):  # type: ignore[no-untyped-def]
        raise AssertionError("No free-form model call is expected")

    def stream_text(self, request):  # type: ignore[no-untyped-def]
        raise AssertionError("No model text stream is expected")


app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(
    StageAdapter(), retry_policy=RetryPolicy(max_attempts=1)
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8003, log_level="warning")
