"""Application entry point for the EduMind MVP API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.knowledge_graph import router as knowledge_graph_router
from app.api.learning_reads import router as learning_reads_router
from app.api.learning_sessions import router as learning_sessions_router
from app.api.profile import router as profile_router
from app.core.auth import AuthFailure

app = FastAPI(title="EduMind Agent API", version="0.1.0")
app.include_router(auth_router)
app.include_router(knowledge_graph_router)
app.include_router(learning_reads_router)
app.include_router(learning_sessions_router)
app.include_router(profile_router)


@app.exception_handler(AuthFailure)
async def auth_failure_handler(_request: Request, error: AuthFailure) -> JSONResponse:
    """Keep authentication errors aligned with the public API contract."""
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message, "retryable": False},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, _error: RequestValidationError
) -> JSONResponse:
    """Return a stable VALIDATION_ERROR body for schema-invalid requests."""
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request did not satisfy the schema.",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return process health without contacting a model provider."""
    return {"status": "ok"}
