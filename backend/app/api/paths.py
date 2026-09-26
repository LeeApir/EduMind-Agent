"""Authenticated mastery reads and deterministic path commands."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.knowledge_graph import knowledge_graph_repository
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.models.learning_state import NodeMasteryCurrent, NodeMasteryRevision
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_operations import IdempotencyConflict
from app.services.path_commands import (
    PathNotFound,
    PathVersionConflict,
    execute_path_command,
    path_is_stale,
    path_payload,
)
from app.services.path_rules import PATH_RULE_VERSION, PathRuleError
from app.services.path_versions import PathVersionError, current_path_version

router = APIRouter(tags=["Learning Path"])


class PathPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_node_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")


class PathReplanRequest(PathPlanRequest):
    reason: Literal["learner_request", "mastery_changed", "profile_changed"] = "learner_request"


@router.get("/api/mastery", tags=["Assessment"])
async def get_mastery(
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with sessions() as db:
        rows = (
            await db.execute(
                select(NodeMasteryCurrent, NodeMasteryRevision)
                .join(NodeMasteryRevision, NodeMasteryRevision.id == NodeMasteryCurrent.revision_id)
                .where(NodeMasteryCurrent.user_id == current.user.id)
                .order_by(NodeMasteryCurrent.knowledge_node_id)
            )
        ).all()
        return {
            "graph_version": graph.graph_version,
            "items": [
                {
                    "knowledge_node_id": state.knowledge_node_id,
                    "previous_score": revision.previous_score,
                    "score": state.score,
                    "status": state.status,
                    "revision": state.revision,
                    "rule_version": state.rule_version,
                    "evidence_summary": revision.evidence_summary,
                }
                for state, revision in rows
            ],
        }


@router.get("/api/path/current")
async def get_current_path(
    response: Response,
    target_node_id: str = Query(pattern=r"^[a-z][a-z0-9-]{1,63}$"),
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with sessions() as db:
        version = await current_path_version(
            db, owner_id=current.user.id, target_node_id=target_node_id
        )
        if version is None:
            raise AuthFailure(404, "NOT_FOUND", "Path not found.")
        stale = (
            await path_is_stale(db, version)
            or version.graph_version != graph.graph_version
            or version.planner_rule_version != PATH_RULE_VERSION
        )
        return path_payload(version, is_stale=stale)


async def _command(
    payload: PathPlanRequest,
    *,
    response: Response,
    current: AuthenticatedSession,
    sessions: async_sessionmaker[AsyncSession],
    graph: KnowledgeGraphRepository,
    key: str,
    expected_version: int | None = None,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with sessions() as db:
        try:
            result = await execute_path_command(
                db,
                owner_id=current.user.id,
                target_node_id=payload.target_node_id,
                idempotency_key=key,
                graph=graph,
                action="replan" if isinstance(payload, PathReplanRequest) else "plan",
                reason=payload.reason if isinstance(payload, PathReplanRequest) else "initial_plan",
                expected_version=expected_version,
            )
        except IdempotencyConflict:
            raise AuthFailure(409, "IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except PathVersionConflict:
            raise AuthFailure(
                409, "PATH_VERSION_CONFLICT", "Path version no longer matches."
            ) from None
        except PathNotFound:
            raise AuthFailure(404, "NOT_FOUND", "Path not found.") from None
        except PathRuleError as error:
            if error.code == "UNKNOWN_TARGET":
                raise AuthFailure(
                    404, "GRAPH_NODE_NOT_FOUND", "Knowledge node not found."
                ) from None
            raise AuthFailure(422, "PATH_UNREACHABLE", "Target path is unavailable.") from None
        except PathVersionError:
            raise AuthFailure(422, "PATH_UNREACHABLE", "Path inputs are not available.") from None
        stale = (
            await path_is_stale(db, result)
            or result.graph_version != graph.graph_version
            or result.planner_rule_version != PATH_RULE_VERSION
        )
        return path_payload(result, is_stale=stale)


@router.post("/api/path/plan", status_code=201)
async def plan_path(
    payload: PathPlanRequest,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
    key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
) -> dict[str, object]:
    return await _command(
        payload, response=response, current=current, sessions=sessions, graph=graph, key=key
    )


@router.post("/api/path/replan")
async def replan_path(
    payload: PathReplanRequest,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
    key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    expected_version: int = Header(ge=1, alias="If-Match-Path-Version"),
) -> dict[str, object]:
    return await _command(
        payload,
        response=response,
        current=current,
        sessions=sessions,
        graph=graph,
        key=key,
        expected_version=expected_version,
    )
