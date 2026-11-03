"""ADR0051 fixed-source development replay. No Provider, scheduler or HTTP import."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.database import get_database_url
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-replay-t107"
ORIGIN = "existing_real_candidate_replay"
RULE = "head-replay-map-v1"
APPROVED_MANIFEST = "d1d394bbd08851da8b2a813d0ddeabcb5767b2ac63005029c364debcf315fd93"


def require_development_database(url: str | None = None) -> None:
    value = make_url(url or get_database_url())
    if (
        value.drivername != "postgresql+asyncpg"
        or value.host != "127.0.0.1"
        or value.port != 15437
        or not (value.database or "").startswith("edumind_catalog_p15_t107_")
    ):
        raise SnapshotError("REPLAY_DEVELOPMENT_DATABASE_REQUIRED")


def mapping(slot: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if slot not in {"C01", "C02"}:
        raise SnapshotError("REPLAY_SOURCE_INVALID")
    manifest_bytes = (PACKAGE / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != APPROVED_MANIFEST:
        raise SnapshotError("REPLAY_SOURCE_CHANGED")
    manifest = json.loads(manifest_bytes)
    # Approval/frozen input bytes never change when the implementation changes.
    for name, expected in manifest["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise SnapshotError("REPLAY_SOURCE_CHANGED")
    spec = importlib.util.spec_from_file_location(
        "head_replay_approved_mapping", PACKAGE / "prepare_mapping.py"
    )
    if spec is None or spec.loader is None:
        raise SnapshotError("REPLAY_SOURCE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    public, private = module.map_case(slot)
    # Compare regenerated mapping to the actual approved examples too.
    if public != json.loads(
        (PACKAGE / f"{slot}.public.proposed.json").read_text()
    ) or private != json.loads((PACKAGE / f"{slot}.private.proposed.json").read_text()):
        raise SnapshotError("REPLAY_MAPPING_CHANGED")
    return public, private


def candidate(slot: str) -> tuple[dict[str, Any], dict[str, Any]]:
    public, private = mapping(slot)
    blocks = deepcopy(public["blocks"])
    exercise = next(b for b in blocks if b["kind"] == "exercise")
    exercise.pop("exercise_id")
    exercise.pop("exercise_version_id")
    exercise.update(exercise_key="head-questions", items=deepcopy(private["exercise"]["items"]))
    return dict(
        blocks=blocks,
        actions=deepcopy(public["actions"]),
        replay_source=deepcopy(public["replay_source"]),
    ), private


def fingerprint(row: FreeSceneGenerationResult) -> str:
    return digest(
        "head-replay-outcome",
        origin=row.origin_type,
        input_digest=row.input_digest,
        request_digest=row.request_digest,
        response=row.response_json,
        sent_attempts=row.sent_attempts,
        usage=row.usage_json,
    )


def validate_replay(row: FreeSceneGenerationResult, actual: dict[str, Any]) -> dict[str, Any]:
    source = (row.response_json or {}).get("replay_source", {})
    if not isinstance(source, dict):
        raise SnapshotError("REPLAY_SOURCE_INVALID")
    slot = source.get("slot")
    if not isinstance(slot, str):
        raise SnapshotError("REPLAY_SOURCE_INVALID")
    expected, private = candidate(slot)
    snapshot = dict(inputs=actual, replay=private)
    if (
        row.origin_type != ORIGIN
        or row.sent_attempts != 0
        or row.usage_json is not None
        or row.state != "candidate"
        or row.reason_code is not None
        or row.input_snapshot != snapshot
        or row.input_digest != digest("head-replay-input", snapshot=snapshot)
        or row.request_digest != digest("head-replay-request", source=expected["replay_source"])
        or row.response_json != expected
        or row.response_digest != fingerprint(row)
        or str(row.request_id) != actual["request"]["request_id"]
        or row.prompt_version != expected["replay_source"]["prompt_version"]
        or row.schema_version != RULE
    ):
        raise SnapshotError("REPLAY_MAPPING_MISMATCH")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(blocks=expected["blocks"], replay_source=expected["replay_source"]),
            actions=expected["actions"],
            dependencies=[],
        ),
    )


async def import_course(db: AsyncSession, owner: UUID, slot: str) -> dict[str, Any]:
    bind = db.bind
    if isinstance(bind, AsyncConnection):
        bind = bind.engine
    if not isinstance(bind, AsyncEngine):
        raise SnapshotError("REPLAY_DEVELOPMENT_DATABASE_REQUIRED")
    require_development_database(bind.url.render_as_string(hide_password=False))
    from app.services.free_scene_availability import commit_outline, commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate

    raw, private = candidate(slot)
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        f"单链表头插：既有真实候选回放 {slot}",
        key="head-replay:" + raw["replay_source"]["candidate_digest"],
        config={"prompt_version": raw["replay_source"]["prompt_version"]},
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    current = await repo.get_course(cid)
    if current["head_version"] is not None:
        # Receipt replay: never overwrite a subsequent head or create a second operation.
        return dict(**created, version=current["head_version"], imported=False)
    fence = await repo.acquire_write_fence(cid, oid)
    plan = dict(
        title=f"单链表头插 · {slot} 回放",
        objectives=[
            dict(
                id="head",
                description="阅读既有头插课程并作答",
                source="user_requirement",
                source_key="request_1",
                source_excerpt=current["original_goal"],
            )
        ],
        shared_example=raw["replay_source"]["candidate_digest"],
        terminology=[dict(term="caller_head", meaning="调用者头指针")],
        conventions=["保持原模型教学文本和固定程序轨迹"],
        scenes=[
            dict(
                scene_key="head",
                title=f"头插完整课程 · {slot}",
                purpose="讲解、代码、状态与练习",
                forms=["text", "code", "visualization", "exercise"],
                objective_ids=["head"],
                depends_on=[],
            )
        ],
    )
    saved = await repo.store_plan(cid, fence, expected_head=None, key="replay-plan", candidate=plan)
    pid = UUID(saved["plan_id"])
    sid = UUID((await repo.get_plan(cid, pid))["scenes"][0]["scene_id"])
    outline = await commit_outline(db, owner, cid, fence, plan_id=pid, key="replay-outline")
    actual = await load_inputs(
        db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=outline["version"]
    )
    snapshot = dict(inputs=actual, replay=private)
    row = FreeSceneGenerationResult(
        user_id=owner,
        course_id=cid,
        operation_id=oid,
        request_id=UUID(actual["request"]["request_id"]),
        lease_epoch=fence.epoch,
        call_key="replay:" + slot,
        expected_head=outline["version"],
        input_digest=digest("head-replay-input", snapshot=snapshot),
        request_digest=digest("head-replay-request", source=raw["replay_source"]),
        input_snapshot=snapshot,
        response_json=raw,
        prompt_version=raw["replay_source"]["prompt_version"],
        schema_version=RULE,
        state="candidate",
        reason_code=None,
        plan_id=pid,
        scene_id=sid,
        sent_attempts=0,
        usage_json=None,
        origin_type=ORIGIN,
    )
    row.response_digest = fingerprint(row)
    db.add(row)
    await db.flush()
    checked = await validate_candidate(db, owner, cid, fence, result_id=row.id)
    ready = await commit_scene(
        db,
        owner,
        cid,
        fence,
        validation_id=UUID(checked["validation_id"]),
        expected_head=outline["version"],
        key="replay-ready",
    )
    operation = await db.get(FreeCourseOperation, oid)
    if operation is None:
        raise SnapshotError("SNAPSHOT_CORRUPT")
    operation.state = "succeeded"
    operation.lease_token = None
    operation.lease_expires_at = None
    await db.flush()
    return dict(**created, version=ready["version"], scene_id=str(sid), imported=True)
