"""Application entry point for the EduMind MVP API."""

from fastapi import FastAPI

app = FastAPI(title="EduMind Agent API", version="0.1.0")


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return process health without contacting a model provider."""
    return {"status": "ok"}
