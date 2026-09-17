"""Application entry point for the EduMind MVP API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.learning_reads import router as learning_reads_router
from app.core.auth import AuthFailure

app = FastAPI(title="EduMind Agent API", version="0.1.0")
app.include_router(auth_router)
app.include_router(learning_reads_router)


@app.exception_handler(AuthFailure)
async def auth_failure_handler(_request: Request, error: AuthFailure) -> JSONResponse:
    """Keep authentication errors aligned with the public API contract."""
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message, "retryable": False},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return process health without contacting a model provider."""
    return {"status": "ok"}
