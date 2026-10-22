"""Private transactional snapshot storage. No HTTP projection, scheduler or Provider."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.free_course import (
    FreeCourse,
    FreeCourseNodeLink,
    FreeCoursePlan,
    FreeCourseRequest,
    FreeCourseScene,
    FreeCourseSceneVersion,
    FreeCourseVersion,
)
from app.models.free_course_writes import FreeCourseOperation, FreeCourseReceipt
from app.models.learning import StudentProfile
from app.services.knowledge_graph_versions import graph_repository_for_version

SCHEMA = "free-course-storage-v1"
ACTIVE = ("queued", "running", "cancel_requested")
CONFIG_KEYS = {
    "connection_id",
    "model_snapshot_id",
    "model",
    "task_tier",
    "prompt_version",
    "policy_version",
    "temperature",
    "max_output_tokens",
}
PROFILE_FIELDS = (
    "professional_background",
    "knowledge_base",
    "cognitive_style",
    "learning_goals",
    "error_preferences",
    "engineering_preference",
    "extended_dimensions",
    "evidence",
)


class SnapshotError(ValueError):
    def __init__(self, code: str = "SNAPSHOT_INVALID") -> None:
        self.code = code
        super().__init__(code)


def canonical(value: object) -> bytes:
    def check(v: object) -> None:
        if v is None or isinstance(v, (str, bool, int)):
            return
        if isinstance(v, float) and math.isfinite(v):
            return
        if isinstance(v, list):
            for item in v:
                check(item)
            return
        if isinstance(v, dict) and all(isinstance(k, str) for k in v):
            for item in v.values():
                check(item)
            return
        raise SnapshotError()

    try:
        check(value)
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise SnapshotError() from None


def parse_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise SnapshotError()
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
        canonical(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise SnapshotError() from None


def digest(domain: str, **fields: Any) -> str:
    return hashlib.sha256(
        canonical({"kind": domain, "schema_version": SCHEMA, "payload": fields})
    ).hexdigest()


@dataclass(frozen=True)
class WriteFence:
    operation_id: UUID
    epoch: int
    token: UUID


class SnapshotRepository:
    """Caller owns commit/rollback. Each mutation is also atomic within a savepoint."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db, self.owner = db, owner_id

    async def _now(self) -> datetime:
        value = await self.db.scalar(select(func.clock_timestamp()))
        if not isinstance(value, datetime):
            raise SnapshotError("CLOCK_UNAVAILABLE")
        return value

    async def _owner_lock(self) -> None:
        if (
            await self.db.scalar(select(User.id).where(User.id == self.owner).with_for_update())
            is None
        ):
            raise SnapshotError("NOT_FOUND")

    async def _course(self, course_id: UUID, *, lock: bool = False) -> FreeCourse:
        query = select(FreeCourse).where(
            FreeCourse.id == course_id, FreeCourse.user_id == self.owner
        )
        query = query.execution_options(populate_existing=True)
        if lock:
            query = query.with_for_update()
        course = await self.db.scalar(query)
        if course is None:
            raise SnapshotError("NOT_FOUND")
        return course

    async def _head(self, course: FreeCourse) -> FreeCourseVersion | None:
        return (
            await self.db.scalar(
                select(FreeCourseVersion).where(
                    FreeCourseVersion.user_id == self.owner,
                    FreeCourseVersion.course_id == course.id,
                    FreeCourseVersion.id == course.head_version_id,
                )
            )
            if course.head_version_id
            else None
        )

    async def _expected(self, course: FreeCourse, expected: int | None) -> FreeCourseVersion | None:
        current = await self._head(course)
        if (current.version if current else None) != expected:
            raise SnapshotError("STALE_COURSE_VERSION")
        return current

    async def _receipt(self, route: str, key: str, request: str) -> dict[str, Any] | None:
        if not 1 <= len(key) <= 128 or not all(32 <= ord(c) <= 126 for c in key):
            raise SnapshotError("INVALID_IDEMPOTENCY_KEY")
        row = await self.db.get(FreeCourseReceipt, (self.owner, route, key))
        if row is None:
            return None
        if row.request_digest != request:
            raise SnapshotError("IDEMPOTENCY_CONFLICT")
        return deepcopy(row.response_json)

    async def _record(
        self,
        course: UUID,
        route: str,
        key: str,
        request: str,
        result: dict[str, Any],
        *,
        status_code: int = 201,
    ) -> dict[str, Any]:
        self.db.add(
            FreeCourseReceipt(
                user_id=self.owner,
                course_id=course,
                route=route,
                idempotency_key=key,
                request_digest=request,
                status_code=status_code,
                response_json=result,
            )
        )
        await self.db.flush()
        return deepcopy(result)

    async def create_course(
        self,
        goal: str,
        *,
        key: str,
        profile_id: UUID | None = None,
        teaching_language: str = "zh-CN",
        code_language: str | None = "C",
        config: dict[str, Any] | None = None,
        policy_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = deepcopy(config or {})
        policy_snapshot = deepcopy(policy_snapshot or {})
        canonical(policy_snapshot)
        if (
            not isinstance(goal, str)
            or not goal.strip()
            or len(goal) > 4000
            or teaching_language != "zh-CN"
            or code_language not in ("C", None)
            or not config.keys() <= CONFIG_KEYS
        ):
            raise SnapshotError()
        if any(
            isinstance(v, (dict, list, bool)) or not isinstance(v, (str, int, float, type(None)))
            for v in config.values()
        ):
            raise SnapshotError()
        request = digest(
            "create",
            goal=goal,
            teaching_language=teaching_language,
            code_language=code_language,
            profile_id=str(profile_id) if profile_id else None,
            config=config,
            **({"policy_snapshot": policy_snapshot} if policy_snapshot else {}),
        )
        route = "/api/free-courses"
        async with self.db.begin_nested():
            await self._owner_lock()
            replay = await self._receipt(route, key, request)
            if replay is not None:
                return replay
            if (
                await self.db.scalar(
                    select(FreeCourseOperation.id).where(
                        FreeCourseOperation.user_id == self.owner,
                        FreeCourseOperation.state.in_(ACTIVE),
                    )
                )
                is not None
            ):
                raise SnapshotError("OPERATION_ACTIVE")
            profile = None
            if profile_id:
                profile = await self.db.scalar(
                    select(StudentProfile).where(
                        StudentProfile.user_id == self.owner, StudentProfile.id == profile_id
                    )
                )
                if profile is None:
                    raise SnapshotError("NOT_FOUND")
            evidence = (
                {field: deepcopy(getattr(profile, field)) for field in PROFILE_FIELDS}
                if profile
                else {}
            )
            canonical(evidence)
            course = FreeCourse(
                user_id=self.owner,
                original_goal=goal,
                teaching_language=teaching_language,
                code_language=code_language,
            )
            self.db.add(course)
            await self.db.flush()
            payload = dict(
                request_text=goal,
                kind="original",
                profile_id=str(profile.id) if profile else None,
                profile_version=profile.version if profile else None,
                evidence_snapshot=evidence,
                nonsecret_config_snapshot=config,
                parent_request_id=None,
            )
            req = FreeCourseRequest(
                user_id=self.owner,
                course_id=course.id,
                version=1,
                schema_version=SCHEMA,
                digest=digest("request", **payload),
                **{**payload, "profile_id": profile.id if profile else None},
            )
            self.db.add(req)
            await self.db.flush()
            operation = FreeCourseOperation(
                user_id=self.owner,
                course_id=course.id,
                request_id=req.id,
                kind="create",
                config_snapshot=config,
                policy_snapshot=policy_snapshot,
            )
            self.db.add(operation)
            await self.db.flush()
            return await self._record(
                course.id,
                route,
                key,
                request,
                {"course_id": str(course.id), "operation_id": str(operation.id)},
            )

    async def _operation(self, course_id: UUID, operation_id: UUID) -> FreeCourseOperation:
        row = await self.db.scalar(
            select(FreeCourseOperation)
            .where(
                FreeCourseOperation.user_id == self.owner,
                FreeCourseOperation.course_id == course_id,
                FreeCourseOperation.id == operation_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        return row

    async def acquire_write_fence(self, course_id: UUID, operation_id: UUID) -> WriteFence:
        async with self.db.begin_nested():
            await self._owner_lock()
            await self._course(course_id, lock=True)
            op = await self._operation(course_id, operation_id)
            now = await self._now()
            if (
                op.state not in ("queued", "running")
                or op.cancel_requested_at
                or op.deadline_at <= now
            ):
                raise SnapshotError("OPERATION_FENCED")
            if op.lease_token and op.lease_expires_at and op.lease_expires_at > now:
                raise SnapshotError("LEASE_ACTIVE")

            op.lease_epoch += 1
            op.lease_token = uuid4()
            op.lease_expires_at = min(now + timedelta(seconds=45), op.deadline_at)
            op.state = "running"
            await self.db.flush()
            return WriteFence(op.id, op.lease_epoch, op.lease_token)

    async def _fence(self, course_id: UUID, fence: WriteFence) -> FreeCourseOperation:
        op = await self._operation(course_id, fence.operation_id)
        now = await self._now()
        if (
            op.state != "running"
            or op.cancel_requested_at is not None
            or op.deadline_at <= now
            or op.lease_epoch != fence.epoch
            or op.lease_token != fence.token
            or op.lease_expires_at is None
            or op.lease_expires_at <= now
        ):
            raise SnapshotError("OPERATION_FENCED")
        return op

    async def fence_cancellation(self, course_id: UUID, operation_id: UUID) -> None:
        """Storage primitive; full cancel/events/settlement protocol belongs to T015."""
        async with self.db.begin_nested():
            await self._owner_lock()
            await self._course(course_id, lock=True)
            op = await self._operation(course_id, operation_id)
            if op.state not in ACTIVE or op.state == "cancel_requested":
                return
            op.cancel_requested_at = await self.db.scalar(select(func.clock_timestamp()))
            op.lease_epoch += 1
            op.lease_token = None
            op.lease_expires_at = None
            op.state = "cancel_requested"
            await self.db.flush()

    async def store_plan(
        self,
        course_id: UUID,
        fence: WriteFence,
        *,
        expected_head: int | None,
        key: str,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = parse_json(canonical(candidate).decode())
        request = digest(
            "plan-write",
            candidate=candidate,
            operation_id=str(fence.operation_id),
            expected_head=expected_head,
        )
        route = f"repo:plan:{course_id}"
        async with self.db.begin_nested():
            await self._owner_lock()
            course = await self._course(course_id, lock=True)
            replay = await self._receipt(route, key, request)
            if replay is not None:
                return replay
            current_head = await self._expected(course, expected_head)
            op = await self._fence(course_id, fence)
            scenes = candidate.get("scenes")
            if not isinstance(scenes, list) or not 1 <= len(scenes) <= 8:
                raise SnapshotError()
            keys = [item.get("scene_key") for item in scenes if isinstance(item, dict)]
            if (
                len(keys) != len(scenes)
                or any(not isinstance(k, str) or not k for k in keys)
                or len(set(keys)) != len(keys)
            ):
                raise SnapshotError()
            previous: dict[str, UUID] = {}
            if current_head is not None:
                previous_plan = await self.db.scalar(
                    select(FreeCoursePlan).where(
                        FreeCoursePlan.id == current_head.plan_id,
                        FreeCoursePlan.course_id == course_id,
                        FreeCoursePlan.user_id == self.owner,
                    )
                )
                if previous_plan is None:
                    raise SnapshotError("SNAPSHOT_CORRUPT")
                previous = {
                    item["scene_key"]: UUID(item["scene_id"])
                    for item in cast(list[dict[str, Any]], previous_plan.plan_json["scenes"])
                }
            identities = {k: previous.get(k, uuid4()) for k in cast(list[str], keys)}
            normalized = []
            seen: set[str] = set()
            for item in scenes:
                deps = item.get("depends_on")
                if (
                    not isinstance(deps, list)
                    or any(not isinstance(d, str) for d in deps)
                    or len(set(deps)) != len(deps)
                    or not set(deps) <= seen
                ):
                    raise SnapshotError()
                sid = identities[item["scene_key"]]
                if item["scene_key"] not in previous:
                    self.db.add(FreeCourseScene(id=sid, user_id=self.owner, course_id=course_id))
                normalized.append(
                    {**item, "scene_id": str(sid), "depends_on": [str(identities[d]) for d in deps]}
                )
                seen.add(item["scene_key"])
            value = {"candidate": candidate, "scenes": normalized}
            if len(canonical(value)) > 16384:
                raise SnapshotError()
            number = await self.db.scalar(
                select(func.max(FreeCoursePlan.version)).where(
                    FreeCoursePlan.user_id == self.owner, FreeCoursePlan.course_id == course_id
                )
            )
            await self.db.flush()
            row = FreeCoursePlan(
                user_id=self.owner,
                course_id=course_id,
                version=(number or 0) + 1,
                request_id=op.request_id,
                schema_version=SCHEMA,
                plan_json=value,
                origin_operation_id=op.id,
                origin_lease_epoch=fence.epoch,
                digest=digest("plan", plan=value),
            )
            self.db.add(row)
            await self.db.flush()
            return await self._record(course_id, route, key, request, {"plan_id": str(row.id)})

    async def store_scene(
        self,
        course_id: UUID,
        fence: WriteFence,
        *,
        expected_head: int | None,
        key: str,
        plan_id: UUID,
        scene_id: UUID,
        content: dict[str, Any],
        actions: list[Any],
        dependencies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        data = parse_json(
            canonical(dict(content=content, actions=actions, dependencies=dependencies)).decode()
        )
        if (
            not isinstance(data["content"], dict)
            or not isinstance(data["actions"], list)
            or not isinstance(data["dependencies"], list)
            or len(canonical(data)) > 65536
        ):
            raise SnapshotError()
        request = digest(
            "scene-write",
            **data,
            operation_id=str(fence.operation_id),
            plan_id=str(plan_id),
            scene_id=str(scene_id),
            expected_head=expected_head,
        )
        route = f"repo:scene:{course_id}:{scene_id}"
        async with self.db.begin_nested():
            await self._owner_lock()
            course = await self._course(course_id, lock=True)
            replay = await self._receipt(route, key, request)
            if replay is not None:
                return replay
            await self._expected(course, expected_head)
            op = await self._fence(course_id, fence)
            plan = await self.db.scalar(
                select(FreeCoursePlan).where(
                    FreeCoursePlan.id == plan_id,
                    FreeCoursePlan.user_id == self.owner,
                    FreeCoursePlan.course_id == course_id,
                )
            )
            if plan is None or plan.request_id != op.request_id:
                raise SnapshotError("NOT_FOUND")
            number = await self.db.scalar(
                select(func.max(FreeCourseSceneVersion.version)).where(
                    FreeCourseSceneVersion.user_id == self.owner,
                    FreeCourseSceneVersion.course_id == course_id,
                    FreeCourseSceneVersion.scene_id == scene_id,
                )
            )
            row = FreeCourseSceneVersion(
                user_id=self.owner,
                course_id=course_id,
                scene_id=scene_id,
                version=(number or 0) + 1,
                plan_id=plan_id,
                schema_version=SCHEMA,
                content_json=data["content"],
                actions_json=data["actions"],
                dependency_bindings=data["dependencies"],
                origin_operation_id=op.id,
                origin_lease_epoch=fence.epoch,
                content_digest=digest("scene", **data),
            )
            self.db.add(row)
            await self.db.flush()
            return await self._record(
                course_id, route, key, request, {"scene_version_id": str(row.id)}
            )

    async def commit_manifest(
        self,
        course_id: UUID,
        fence: WriteFence,
        *,
        expected_head: int | None,
        key: str,
        plan_id: UUID,
        bindings: list[UUID | None],
        node_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        links = parse_json(canonical(node_links or []).decode())
        request = digest(
            "manifest-write",
            operation_id=str(fence.operation_id),
            plan_id=str(plan_id),
            expected_head=expected_head,
            bindings=[str(b) if b else None for b in bindings],
            links=links,
        )
        route = f"repo:manifest:{course_id}"
        async with self.db.begin_nested():
            await self._owner_lock()
            course = await self._course(course_id, lock=True)
            replay = await self._receipt(route, key, request)
            if replay is not None:
                return replay
            old = await self._expected(course, expected_head)
            await self._fence(course_id, fence)
            plan = await self.db.scalar(
                select(FreeCoursePlan).where(
                    FreeCoursePlan.id == plan_id,
                    FreeCoursePlan.user_id == self.owner,
                    FreeCoursePlan.course_id == course_id,
                )
            )
            if plan is None:
                raise SnapshotError("NOT_FOUND")
            if not (old and old.plan_id == plan.id) and (
                plan.origin_operation_id != fence.operation_id
                or plan.origin_lease_epoch != fence.epoch
            ):
                raise SnapshotError("OPERATION_FENCED")
            scenes = cast(list[dict[str, Any]], plan.plan_json["scenes"])
            if len(bindings) != len(scenes):
                raise SnapshotError()
            prior = (
                {
                    item["scene_version_id"]
                    for item in cast(list[dict[str, Any]], old.manifest_json["scenes"])
                }
                if old
                else set()
            )
            for sid in bindings:
                if sid is None:
                    continue
                row = await self.db.scalar(
                    select(FreeCourseSceneVersion).where(
                        FreeCourseSceneVersion.user_id == self.owner,
                        FreeCourseSceneVersion.course_id == course_id,
                        FreeCourseSceneVersion.id == sid,
                        FreeCourseSceneVersion.plan_id == plan_id,
                    )
                )
                if row is None:
                    raise SnapshotError("NOT_FOUND")
                if str(sid) not in prior and (
                    row.origin_operation_id != fence.operation_id
                    or row.origin_lease_epoch != fence.epoch
                ):
                    raise SnapshotError("OPERATION_FENCED")
            value = {
                "node_links": links,
                "scenes": [
                    {"scene_id": item["scene_id"], "scene_version_id": str(sid) if sid else None}
                    for item, sid in zip(scenes, bindings, strict=True)
                ],
            }
            number = await self.db.scalar(
                select(func.max(FreeCourseVersion.version)).where(
                    FreeCourseVersion.user_id == self.owner,
                    FreeCourseVersion.course_id == course_id,
                )
            )
            manifest_row = FreeCourseVersion(
                user_id=self.owner,
                course_id=course_id,
                version=(number or 0) + 1,
                plan_id=plan_id,
                schema_version=SCHEMA,
                manifest_json=value,
                digest=digest("manifest", manifest=value),
            )
            self.db.add(manifest_row)
            await self.db.flush()
            for link in links:
                if not isinstance(link, dict) or set(link) - {
                    "scene_id",
                    "node_id",
                    "graph_version",
                    "relation",
                    "source",
                    "evidence_refs",
                }:
                    raise SnapshotError()
                try:
                    graph = graph_repository_for_version(link["graph_version"])
                    if graph.get_node(link["node_id"]) is None:
                        raise SnapshotError()
                    scene = UUID(link["scene_id"]) if link.get("scene_id") else None
                    self.db.add(
                        FreeCourseNodeLink(
                            user_id=self.owner,
                            course_id=course_id,
                            course_version_id=manifest_row.id,
                            scene_id=scene,
                            node_id=link["node_id"],
                            graph_version=link["graph_version"],
                            relation=link["relation"],
                            source=link["source"],
                            evidence_refs=link["evidence_refs"],
                        )
                    )
                except (KeyError, ValueError, TypeError):
                    raise SnapshotError() from None
            await self.db.flush()
            valid_fence = (
                select(FreeCourseOperation.id)
                .where(
                    FreeCourseOperation.id == fence.operation_id,
                    FreeCourseOperation.user_id == self.owner,
                    FreeCourseOperation.course_id == course_id,
                    FreeCourseOperation.state == "running",
                    FreeCourseOperation.cancel_requested_at.is_(None),
                    FreeCourseOperation.lease_epoch == fence.epoch,
                    FreeCourseOperation.lease_token == fence.token,
                    FreeCourseOperation.deadline_at > func.clock_timestamp(),
                    FreeCourseOperation.lease_expires_at > func.clock_timestamp(),
                )
                .exists()
            )
            switched = await self.db.scalar(
                update(FreeCourse)
                .where(
                    FreeCourse.id == course_id,
                    FreeCourse.user_id == self.owner,
                    FreeCourse.head_version_id == (old.id if old else None),
                    valid_fence,
                )
                .values(head_version_id=manifest_row.id)
                .returning(FreeCourse.id)
                .execution_options(synchronize_session="fetch")
            )
            if switched is None:
                raise SnapshotError("OPERATION_FENCED")
            return await self._record(
                course_id,
                route,
                key,
                request,
                {"version": manifest_row.version, "version_id": str(manifest_row.id)},
            )

    async def get_course(self, course_id: UUID) -> dict[str, Any]:
        course = await self._course(course_id)
        head = await self._head(course)
        return {
            "course_id": str(course.id),
            "original_goal": course.original_goal,
            "teaching_language": course.teaching_language,
            "code_language": course.code_language,
            "course_kind": course.course_kind,
            "endorsement": course.endorsement,
            "head_version": head.version if head else None,
        }

    async def get_version(self, course_id: UUID, version: int) -> dict[str, Any]:
        await self._course(course_id)
        row = await self.db.scalar(
            select(FreeCourseVersion).where(
                FreeCourseVersion.user_id == self.owner,
                FreeCourseVersion.course_id == course_id,
                FreeCourseVersion.version == version,
            )
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        if row.digest != digest("manifest", manifest=row.manifest_json):
            raise SnapshotError("SNAPSHOT_CORRUPT")
        return deepcopy(
            {
                "id": str(row.id),
                "version": row.version,
                "plan_id": str(row.plan_id),
                "digest": row.digest,
                **row.manifest_json,
            }
        )

    async def get_scene_snapshot(
        self, course_id: UUID, version: int, scene_id: UUID
    ) -> dict[str, Any]:
        manifest = await self.get_version(course_id, version)
        binding = next(
            (item for item in manifest["scenes"] if item["scene_id"] == str(scene_id)), None
        )
        if binding is None:
            raise SnapshotError("NOT_FOUND")
        if binding["scene_version_id"] is None:
            raise SnapshotError("SCENE_NOT_READY")
        row = await self.db.scalar(
            select(FreeCourseSceneVersion).where(
                FreeCourseSceneVersion.user_id == self.owner,
                FreeCourseSceneVersion.course_id == course_id,
                FreeCourseSceneVersion.scene_id == scene_id,
                FreeCourseSceneVersion.id == UUID(binding["scene_version_id"]),
            )
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        payload = {
            "content": row.content_json,
            "actions": row.actions_json,
            "dependencies": row.dependency_bindings,
        }
        if row.content_digest != digest("scene", **payload):
            raise SnapshotError("SNAPSHOT_CORRUPT")
        return deepcopy({"scene_version_id": str(row.id), "digest": row.content_digest, **payload})

    async def get_request(self, course_id: UUID, version: int) -> dict[str, Any]:
        await self._course(course_id)
        row = await self.db.scalar(
            select(FreeCourseRequest).where(
                FreeCourseRequest.user_id == self.owner,
                FreeCourseRequest.course_id == course_id,
                FreeCourseRequest.version == version,
            )
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        payload = dict(
            request_text=row.request_text,
            kind=row.kind,
            profile_id=str(row.profile_id) if row.profile_id else None,
            profile_version=row.profile_version,
            evidence_snapshot=row.evidence_snapshot,
            nonsecret_config_snapshot=row.nonsecret_config_snapshot,
            parent_request_id=str(row.parent_request_id) if row.parent_request_id else None,
        )
        if row.digest != digest("request", **payload):
            raise SnapshotError("SNAPSHOT_CORRUPT")
        return deepcopy(
            {"id": str(row.id), "version": row.version, "digest": row.digest, **payload}
        )

    async def get_plan(self, course_id: UUID, plan_id: UUID) -> dict[str, Any]:
        await self._course(course_id)
        row = await self.db.scalar(
            select(FreeCoursePlan).where(
                FreeCoursePlan.user_id == self.owner,
                FreeCoursePlan.course_id == course_id,
                FreeCoursePlan.id == plan_id,
            )
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        if row.digest != digest("plan", plan=row.plan_json):
            raise SnapshotError("SNAPSHOT_CORRUPT")
        return deepcopy(
            {
                "id": str(row.id),
                "request_id": str(row.request_id),
                "version": row.version,
                "digest": row.digest,
                **row.plan_json,
            }
        )
