"""Application entry point for the EduMind MVP API."""

from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.animation_events import router as animation_events_router
from app.api.animation_generation import router as animation_generation_router
from app.api.animation_jobs import router as animation_jobs_router
from app.api.animation_media import router as animation_media_router
from app.api.auth import router as auth_router
from app.api.catalog import router as catalog_router
from app.api.classroom import router as classroom_router
from app.api.debate import router as debate_router
from app.api.free_courses import router as free_courses_router
from app.api.knowledge_graph import router as knowledge_graph_router
from app.api.learning_events import router as learning_events_router
from app.api.learning_reads import router as learning_reads_router
from app.api.learning_sessions import router as learning_sessions_router
from app.api.markdown_notes import router as markdown_notes_router
from app.api.model_preferences import router as model_preferences_router
from app.api.paths import router as paths_router
from app.api.profile import router as profile_router
from app.api.provider_connections import router as provider_connections_router
from app.api.provider_model_catalog import router as provider_model_catalog_router
from app.api.provider_probe import router as provider_probe_router
from app.api.quiz import router as quiz_router
from app.core.auth import AuthFailure
from app.core.database import database_lifespan
from app.core.product_mode import catalog_only, require_dynamic_mode
from app.services.free_course_contract import public_openapi
from app.services.free_course_snapshots import SnapshotError
from app.services.knowledge_graph import KnowledgeGraphValidationError

app = FastAPI(title="EduMind Agent API", version="0.1.0", lifespan=database_lifespan)
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(classroom_router)
app.include_router(debate_router, dependencies=[Depends(require_dynamic_mode)])
app.include_router(animation_jobs_router)
app.include_router(animation_generation_router)
app.include_router(animation_media_router)
app.include_router(animation_events_router)
app.include_router(knowledge_graph_router)
app.include_router(learning_reads_router)
app.include_router(learning_events_router)
app.include_router(learning_sessions_router, dependencies=[Depends(require_dynamic_mode)])
app.include_router(markdown_notes_router)
app.include_router(model_preferences_router)
app.include_router(profile_router)
app.include_router(provider_connections_router)
app.include_router(provider_model_catalog_router)
app.include_router(provider_probe_router)
app.include_router(paths_router)
app.include_router(quiz_router)
app.include_router(free_courses_router)


@app.exception_handler(KnowledgeGraphValidationError)
async def graph_failure_handler(
    _request: Request, _error: KnowledgeGraphValidationError
) -> JSONResponse:
    """Fail closed for every graph consumer, without exposing source/configuration paths."""
    return JSONResponse(
        status_code=503,
        content={
            "code": "GRAPH_UNAVAILABLE",
            "message": "Knowledge graph unavailable.",
            "retryable": False,
        },
        headers={"Cache-Control": "no-store"},
    )


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


@app.get("/api/runtime", tags=["system"])
async def runtime_scope() -> dict[str, str]:
    return {"mode": "catalog_only" if catalog_only() else "dynamic"}


@app.exception_handler(SnapshotError)
async def free_course_failure(_request: Request, error: SnapshotError) -> JSONResponse:
    invalid = error.code.startswith("INVALID_") or error.code in {
        "EVENT_CURSOR_INVALID",
        "OPERATION_KIND_INVALID",
    }
    code = "VALIDATION_ERROR" if invalid else error.code
    status = (
        404
        if error.code == "NOT_FOUND"
        else 422
        if invalid
        else 503
        if error.code == "PUBLIC_PROJECTION_INVALID"
        else 409
    )
    return JSONResponse(
        status_code=status,
        content=dict(
            code=code, message="Free course request could not be completed.", retryable=False
        ),
        headers={"Cache-Control": "no-store"},
    )


def free_course_openapi() -> dict[str, Any]:
    if app.openapi_schema is None:
        app.openapi_schema = public_openapi(
            get_openapi(title=app.title, version=app.version, routes=app.routes)
        )
    return app.openapi_schema


app.openapi = free_course_openapi  # type: ignore[method-assign]
