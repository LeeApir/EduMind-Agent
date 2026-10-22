"""Owner feedback stays pending; local maintenance authority alone controls accurate facts."""

import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_quality import (
    FreeCourseFeedback,
    FreeCourseQualityDecision,
    FreeCourseVisibilityFact,
)
from app.models.free_course_revision import FreeCourseRevisionStage
from app.models.free_course_writes import FreeCourseOperation
from app.services.free_course_exercise_identity import exercise_identity
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, WriteFence, digest

ROOT = Path(__file__).resolve().parents[3]
RULE = "free-course-quality-v1"
_TOKEN = object()


@dataclass(frozen=True)
class MaintenanceAuthority:
    name: str
    token: object = field(repr=False)


def local_authority() -> MaintenanceAuthority:
    # Local OS owner is the trusted maintenance principal. No HTTP role or JSON field can
    # construct the in-process capability; no public endpoint imports this command boundary.
    if os.getuid() != ROOT.stat().st_uid:
        raise PermissionError("MAINTENANCE_AUTHORITY_REQUIRED")
    return MaintenanceAuthority("Lee", _TOKEN)


def validate_schema(name: str, value: dict[str, Any]) -> None:
    from app.services.free_course_contract import validate

    try:
        validate(name, value)
    except SnapshotError:
        raise SnapshotError("INVALID_QUALITY_INPUT") from None


async def locate(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    binding: dict[str, Any],
    *,
    anchor: str | None = None,
    exercise_id: str | None = None,
    exercise_version_id: str | None = None,
) -> tuple[dict[str, Any], FreeCourseSceneVersion, dict[str, Any], dict[str, Any] | None]:
    repo = SnapshotRepository(db, owner)
    if type(binding.get("course_version")) is not int or binding["course_version"] < 1:
        raise SnapshotError("NOT_FOUND")
    manifest = await repo.get_version(cid, binding["course_version"])
    item = next(
        (
            s
            for s in manifest["scenes"]
            if s["scene_id"] == binding["scene_id"]
            and s["scene_version_id"] == binding["scene_version_id"]
        ),
        None,
    )
    if item is None or item["scene_version_id"] is None:
        raise SnapshotError("NOT_FOUND")
    raw = await repo.get_scene_snapshot(cid, binding["course_version"], UUID(binding["scene_id"]))
    row = await db.get(FreeCourseSceneVersion, UUID(binding["scene_version_id"]))
    if row is None or row.user_id != owner or row.course_id != cid:
        raise SnapshotError("NOT_FOUND")
    blocks = raw["content"].get("blocks", [])
    selected = next((b for b in blocks if b.get("anchor_id") == anchor), None) if anchor else None
    if anchor is not None and selected is None:
        raise SnapshotError("NOT_FOUND")
    if (exercise_id is None) != (exercise_version_id is None):
        raise SnapshotError("NOT_FOUND")
    if exercise_id is not None:
        found = None
        for block in blocks:
            if block.get("kind") != "exercise":
                continue
            ids = exercise_identity(owner, cid, row.scene_id, row.id, block["exercise_key"])
            if tuple(map(str, ids)) == (exercise_id, exercise_version_id):
                found = block
        if found is None or (anchor is not None and found != selected):
            raise SnapshotError("NOT_FOUND")
        selected = found
    return manifest, row, raw, selected


async def visibility_state(
    db: AsyncSession, owner: UUID, cid: UUID, sv: UUID, anchor: str | None = None
) -> bool:
    facts = (
        await db.scalars(
            select(FreeCourseVisibilityFact)
            .where(
                FreeCourseVisibilityFact.user_id == owner,
                FreeCourseVisibilityFact.course_id == cid,
                FreeCourseVisibilityFact.scene_version_id == sv,
            )
            .order_by(
                FreeCourseVisibilityFact.created_at.desc(), FreeCourseVisibilityFact.id.desc()
            )
        )
    ).all()
    latest: dict[tuple[str, str | None], str] = {}
    for f in facts:
        key = (f.scope, f.anchor_id)
        if key not in latest:
            latest[key] = f.action
    return latest.get(("scene", None)) == "disable" or (
        anchor is not None and latest.get(("exercise", anchor)) == "disable"
    )


async def assert_visible(
    db: AsyncSession, owner: UUID, cid: UUID, sv: UUID, anchor: str | None = None
) -> None:
    if await visibility_state(db, owner, cid, sv, anchor):
        raise SnapshotError("CONTENT_UNAVAILABLE")


async def compute_impact(
    db: AsyncSession, owner: UUID, cid: UUID, draft: dict[str, Any]
) -> dict[str, Any]:
    manifest, row, raw, block = await locate(
        db,
        owner,
        cid,
        draft["binding"],
        exercise_id=draft["exercise_id"],
        exercise_version_id=draft["exercise_version_id"],
    )
    scope = draft["scope"]
    if scope == "exercise" and (block is None or block["kind"] != "exercise"):
        raise SnapshotError("INVALID_QUALITY_INPUT")
    roots = (
        [s["scene_version_id"] for s in manifest["scenes"] if s["scene_version_id"]]
        if scope == "course"
        else [str(row.id)]
    )
    targets = {
        sv: dict(
            scene_version_id=sv,
            scope="exercise" if scope == "exercise" else "scene",
            anchor_id=block["anchor_id"] if scope == "exercise" and block is not None else None,
        )
        for sv in roots
    }
    versions = (
        await db.scalars(
            select(FreeCourseSceneVersion).where(
                FreeCourseSceneVersion.user_id == owner, FreeCourseSceneVersion.course_id == cid
            )
        )
    ).all()
    copies = (
        await db.scalars(
            select(FreeCourseRevisionStage).where(
                FreeCourseRevisionStage.user_id == owner,
                FreeCourseRevisionStage.course_id == cid,
                FreeCourseRevisionStage.source_version_id.is_not(None),
            )
        )
    ).all()
    changed = True
    while changed:
        changed = False
        for copy in copies:
            source = targets.get(str(copy.source_version_id))
            key = str(copy.scene_version_id)
            if source and (
                key not in targets
                or (source["scope"] == "scene" and targets[key]["scope"] != "scene")
            ):
                targets[key] = {**source, "scene_version_id": key}
                changed = True
        for v in versions:
            if any(
                d["scene_version_id"] in targets
                for d in cast(list[dict[str, Any]], v.dependency_bindings)
            ):
                key = str(v.id)
                if key not in targets or targets[key]["scope"] != "scene":
                    targets[key] = dict(scene_version_id=key, scope="scene", anchor_id=None)
                    changed = True
    if draft["action"] == "restore":
        targets = {str(row.id): targets[str(row.id)]}
    active = (
        await db.scalars(
            select(FreeCourseOperation).where(
                FreeCourseOperation.user_id == owner,
                FreeCourseOperation.course_id == cid,
                FreeCourseOperation.state.in_(("queued", "running", "cancel_requested")),
            )
        )
    ).all()
    current = await SnapshotRepository(db, owner).get_course(cid)
    current_ids = set()
    if current["head_version"]:
        head = await SnapshotRepository(db, owner).get_version(cid, current["head_version"])
        current_ids = {s["scene_version_id"] for s in head["scenes"] if s["scene_version_id"]}
    affected_ops = (
        [str(o.id) for o in active]
        if draft["action"] == "confirm_defect" and current_ids & set(targets)
        else []
    )
    value = dict(
        binding=deepcopy(draft["binding"]),
        content_digest=row.content_digest,
        scope=scope,
        targets=sorted(targets.values(), key=lambda v: v["scene_version_id"]),
        operation_ids=sorted(affected_ops),
        action=draft["action"],
        target_decision_id=draft["target_decision_id"],
        basis=deepcopy(draft["basis"]),
        reason=draft["reason"],
    )
    return {**value, "impact_digest": digest("quality-impact-v1", **value)}


class Feedback:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def submit(
        self, owner: UUID, cid: UUID, body: dict[str, Any], *, key: str
    ) -> dict[str, str]:
        validate_schema("FeedbackRequest", body)
        if not body["description"].strip():
            raise SnapshotError("INVALID_QUALITY_INPUT")
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            route = f"/api/free-courses/{cid}/feedback"
            fingerprint = digest("feedback-v1", body=body)
            replay = await repo._receipt(route, key, fingerprint)
            if replay is not None:
                return replay
            binding = {k: body[k] for k in ("course_version", "scene_id", "scene_version_id")}
            manifest, row, _, _ = await locate(
                db,
                owner,
                cid,
                binding,
                anchor=body["anchor_id"],
                exercise_id=body["exercise_id"],
                exercise_version_id=body["exercise_version_id"],
            )
            feedback = FreeCourseFeedback(
                user_id=owner,
                course_id=cid,
                course_version_id=UUID(manifest["id"]),
                scene_version_id=row.id,
                location_json={
                    **binding,
                    "anchor_id": body["anchor_id"],
                    "exercise_id": body["exercise_id"],
                    "exercise_version_id": body["exercise_version_id"],
                },
                description=body["description"],
                source="student",
            )
            db.add(feedback)
            await db.flush()
            return await repo._record(
                cid, route, key, fingerprint, dict(feedback_id=str(feedback.id))
            )

    async def read(self, owner: UUID, cid: UUID, fid: UUID) -> dict[str, Any]:
        async with self.sessions() as db:
            await SnapshotRepository(db, owner).get_course(cid)
            row = await db.scalar(
                select(FreeCourseFeedback).where(
                    FreeCourseFeedback.user_id == owner,
                    FreeCourseFeedback.course_id == cid,
                    FreeCourseFeedback.id == fid,
                )
            )
            if row is None:
                raise SnapshotError("NOT_FOUND")
            decisions = (
                await db.scalars(
                    select(FreeCourseQualityDecision)
                    .where(
                        FreeCourseQualityDecision.user_id == owner,
                        FreeCourseQualityDecision.course_id == cid,
                        FreeCourseQualityDecision.scene_version_id == row.scene_version_id,
                    )
                    .order_by(
                        FreeCourseQualityDecision.created_at.desc(),
                        FreeCourseQualityDecision.id.desc(),
                    )
                )
            ).all()
            decisions = [
                d
                for d in decisions
                if any(
                    t["scene_version_id"] == str(row.scene_version_id)
                    and (t["scope"] == "scene" or t["anchor_id"] == row.location_json["anchor_id"])
                    for t in d.impact_json["targets"]
                )
            ]
            status = "pending"
            if decisions:
                status = {
                    "confirm_defect": "confirmed",
                    "not_confirmed": "not_confirmed",
                    "decision_correction": "corrected",
                    "restore": "corrected",
                }[decisions[0].action]
            return dict(
                feedback_id=str(fid),
                binding={
                    k: row.location_json[k]
                    for k in ("course_version", "scene_id", "scene_version_id")
                },
                anchor_id=row.location_json["anchor_id"],
                description=row.description,
                status=status,
                reason_code="CONTENT_UNAVAILABLE" if status == "confirmed" else None,
            )


class Maintenance:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], authority: MaintenanceAuthority):
        if authority.token is not _TOKEN or authority.name != "Lee":
            raise PermissionError("MAINTENANCE_AUTHORITY_REQUIRED")
        self.sessions, self.authority = sessions, authority

    def validate(self, draft: dict[str, Any]) -> None:
        validate_schema("QualityDecisionDraft", draft)
        if not draft["reason"].strip() or any(
            not b[k].strip() for b in draft["basis"] for k in ("source_ref", "excerpt", "reason")
        ):
            raise SnapshotError("QUALITY_BASIS_REQUIRED")
        # Labeling a model opinion as a source cannot confer local maintenance authority.
        if (
            draft["action"] in ("decision_correction", "restore")
            and draft["target_decision_id"] is None
        ):
            raise SnapshotError("TARGET_DECISION_REQUIRED")

    async def dry_run(self, owner: UUID, draft: dict[str, Any]) -> dict[str, Any]:
        self.validate(draft)
        async with self.sessions() as db:
            return await compute_impact(db, owner, UUID(draft["course_id"]), draft)

    async def apply(self, owner: UUID, draft: dict[str, Any]) -> dict[str, str]:
        self.validate(draft)
        cid = UUID(draft["course_id"])
        fingerprint = digest("quality-decision-v1", draft=draft)
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            old = await db.scalar(
                select(FreeCourseQualityDecision).where(
                    FreeCourseQualityDecision.user_id == owner,
                    FreeCourseQualityDecision.decision_key == draft["decision_key"],
                )
            )
            if old:
                if old.request_digest != fingerprint:
                    raise SnapshotError("IDEMPOTENCY_CONFLICT")
                return dict(decision_id=str(old.id))
            impact = await compute_impact(db, owner, cid, draft)
            if impact["impact_digest"] != draft["impact_digest"]:
                raise SnapshotError("IMPACT_CHANGED")
            manifest, row, _, selected = await locate(
                db,
                owner,
                cid,
                draft["binding"],
                exercise_id=draft["exercise_id"],
                exercise_version_id=draft["exercise_version_id"],
            )
            if draft["target_decision_id"] is not None:
                target = await db.scalar(
                    select(FreeCourseQualityDecision).where(
                        FreeCourseQualityDecision.user_id == owner,
                        FreeCourseQualityDecision.course_id == cid,
                        FreeCourseQualityDecision.id == UUID(draft["target_decision_id"]),
                    )
                )
                if target is None:
                    raise SnapshotError("NOT_FOUND")
                if not any(
                    t["scene_version_id"] == str(row.id)
                    and (
                        t["scope"] == "scene"
                        or (selected is not None and t["anchor_id"] == selected["anchor_id"])
                    )
                    for t in target.impact_json["targets"]
                ):
                    raise SnapshotError("DECISION_BINDING_MISMATCH")
            if any(b["kind"] == "mechanical_rule" for b in draft["basis"]):
                # Actual mechanical findings, never caller-supplied severity or rule labels.
                from app.models.free_scene_generation import FreeSceneGenerationResult
                from app.services.free_scene_validation import check_scene

                source = await db.scalar(
                    select(FreeSceneGenerationResult).where(
                        FreeSceneGenerationResult.scene_id == row.scene_id,
                        FreeSceneGenerationResult.operation_id == row.origin_operation_id,
                    )
                )
                if (
                    source is None
                    or check_scene(
                        dict(blocks=row.content_json.get("blocks"), actions=row.actions_json),
                        source.input_snapshot,
                    )["state"]
                    != "rejected"
                ):
                    raise SnapshotError("MECHANICAL_FAILURE_NOT_FOUND")
            decision = FreeCourseQualityDecision(
                user_id=owner,
                course_id=cid,
                course_version_id=UUID(manifest["id"]),
                scene_version_id=row.id,
                decision_key=draft["decision_key"],
                request_digest=fingerprint,
                action=draft["action"],
                authority=self.authority.name,
                rule_version=RULE,
                evidence_json=deepcopy(draft),
                impact_json=impact,
            )
            db.add(decision)
            await db.flush()
            action = draft["action"]
            if action == "restore":
                from app.models.free_course_progress import FreeCourseStep
                from app.models.free_scene_actions import FreeScenePresentation
                from app.services.free_scene_actions import initial_state

                presentation = await db.scalar(
                    select(FreeScenePresentation)
                    .join(
                        FreeCourseStep, FreeCourseStep.presentation_id == FreeScenePresentation.id
                    )
                    .where(
                        FreeCourseStep.user_id == owner,
                        FreeCourseStep.course_id == cid,
                        FreeCourseStep.scene_version_id == row.id,
                        FreeCourseStep.state == "ready",
                    )
                )
                if presentation is None:
                    raise SnapshotError("RESTORE_HARD_GATE_REQUIRED")
                initial_state(presentation.presentation_json)
                copies = (
                    await db.scalars(
                        select(FreeCourseRevisionStage).where(
                            FreeCourseRevisionStage.scene_version_id == row.id,
                            FreeCourseRevisionStage.user_id == owner,
                        )
                    )
                ).all()
                for copy in copies:
                    if copy.source_version_id:
                        await assert_visible(db, owner, cid, copy.source_version_id)
                # Restore only the exact selected version/group.
                for dep in cast(list[dict[str, Any]], row.dependency_bindings):
                    await assert_visible(db, owner, cid, UUID(dep["scene_version_id"]))
                targets = [t for t in impact["targets"] if t["scene_version_id"] == str(row.id)]
            else:
                targets = impact["targets"]
            if action in ("confirm_defect", "restore"):
                for item in targets:
                    db.add(
                        FreeCourseVisibilityFact(
                            user_id=owner,
                            course_id=cid,
                            decision_id=decision.id,
                            scene_version_id=UUID(item["scene_version_id"]),
                            scope=item["scope"],
                            anchor_id=item["anchor_id"],
                            action="disable" if action == "confirm_defect" else "restore",
                            reason_code="CONFIRMED_DEFECT"
                            if action == "confirm_defect"
                            else "TRUSTED_RESTORE",
                        )
                    )
                if action == "confirm_defect":
                    from app.services.free_course_scheduler import Lease, Scheduler

                    for oid in impact["operation_ids"]:
                        op = await repo._operation(cid, UUID(oid))
                        if op.state not in ("queued", "running"):
                            continue
                        op.state, op.reason_code = "cancel_requested", "CONTENT_UNAVAILABLE"
                        op.cancel_requested_at = await repo._now()
                        op.lease_epoch += 1
                        op.lease_token = op.lease_expires_at = None
                        await Scheduler(self.sessions)._event(
                            db,
                            Lease(owner, cid, WriteFence(op.id, op.lease_epoch, uuid4())),
                            "cancel_requested",
                            dict(state="cancel_requested", reason_code="CONTENT_UNAVAILABLE"),
                        )
                from app.services.free_course_effects import quality_effects

                await quality_effects(db, owner, cid, decision.id, targets, action)
            await db.flush()
            return dict(decision_id=str(decision.id))
