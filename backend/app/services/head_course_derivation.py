"""Offline r03 derived candidate admission through the existing private course chain."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical, digest
from app.services.head_course_duplicate_recovery import VERSION, recover

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-goal-r03-recovery"
ARTIFACTS_SHA = "1b85bdde797beb08f663404ade5eda041b9efc07845600e26b0836d811535592"
HISTORICAL_REVIEW_RECORD_SHA = "90d70178019f814c2240027821125afb8f1924d778cb06c33833a721f6ca8951"
RAW_SHA = "4f05e35015c83b5660c3508e3b7e63671036ece326637ffeb56d5cf9d9f169ee"


def source(record):
    c = record["candidate"]
    r = record["recovery"]
    return dict(
        origin=m.ORIGIN,
        batch="head-goal-r03-derived",
        candidate_digest=c["candidate_digest"],
        parent_digest=None,
        model=record["model"],
        prompt_version=m.VERSION,
        plan_digest=digest("head-plan", plan=c["payload"]["plan"]),
        materials_digest=c["payload"]["materials"]["materials_digest"],
        evidence_kind="program_format_recovery",
        format_recovery=deepcopy(r),
        teaching_review=dict(
            verdict=record.get("independent_review", {}).get("verdict", "pending"),
            independent_evaluator=record.get("independent_review", {}).get(
                "independent_evaluator", "pending"
            ),
        ),
    )


def mapping():
    from app.services.head_course_generation import candidate

    # This package contains no Provider credential or body-encryption key.
    manifest_bytes = (PACKAGE / "artifacts.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != ARTIFACTS_SHA:
        raise SnapshotError("HEAD_RECOVERY_ARTIFACT_CHANGED")
    manifest = json.loads(manifest_bytes)
    if manifest["rule_version"] != VERSION:
        raise SnapshotError("HEAD_RECOVERY_RULE")
    for name, sha in manifest["files"].items():
        if hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() != sha:
            raise SnapshotError("HEAD_RECOVERY_ARTIFACT_CHANGED")
    record = json.loads((PACKAGE / "recovered.record.json").read_text())
    text = (PACKAGE / "original-output.txt").read_text()
    raw, changes = recover(text)
    c = record["candidate"]
    r = record["recovery"]
    expected = m.content_payload(
        record["original_context"]["planning_inputs"], c["payload"]["plan"]
    )
    candidate(expected, raw)  # Complete Schema / fact / frame / scenario checks again.
    if (
        raw != c["raw_output"]
        or c["payload"] != expected
        or r["rule_version"] != VERSION
        or r["original_raw_sha256"] != RAW_SHA
        or r["duplicates"] != changes
        or r["original_text_sha256"] != hashlib.sha256(text.encode()).hexdigest()
        or r["derived_output_sha256"] != hashlib.sha256(canonical(raw)).hexdigest()
        or r["original_request_sha256"] != hashlib.sha256(canonical(record["request"])).hexdigest()
        or record["request"] != m.body(expected)
        or c["candidate_digest"]
        != digest("head-format-recovered-candidate", payload=expected, raw=raw, recovery=r)
        or r["new_provider_calls"] != 0
        or r["model_first_structure_pass"] is not False
        or r["assistant_text_edits"] != 0
        or record["plan_review"]["verdict"] != "pass"
        or record["plan_review"]["planning_basis_binding"] != expected["planning_basis"]["binding"]
    ):
        raise SnapshotError("HEAD_RECOVERY_BINDING")
    assembled = m.assemble(expected, raw, source(record))
    if assembled != json.loads((PACKAGE / "assembled.private.json").read_text()):
        raise SnapshotError("HEAD_RECOVERY_ASSEMBLY")
    return record, assembled


def fingerprint(row):
    return digest(
        "head-recovery-outcome",
        input_digest=row.input_digest,
        request_digest=row.request_digest,
        response=row.response_json,
        usage=row.usage_json,
        sent_attempts=row.sent_attempts,
        origin=row.origin_type,
    )


def validate_derivation(row, actual):
    record, assembled = mapping()
    stored = row.input_snapshot.get("derivation")
    # Preserve the already-written preview audit when the independent report corrects
    # only its locator metadata. The entire historical record is pinned, not normalized.
    if (
        stored != record
        and hashlib.sha256(canonical(stored)).hexdigest() != HISTORICAL_REVIEW_RECORD_SHA
    ):
        raise SnapshotError("HEAD_RECOVERY_ADMISSION")
    snapshot = dict(inputs=actual, derivation=stored)
    if (
        row.origin_type != m.ORIGIN
        or row.sent_attempts != 1
        or row.state != "candidate"
        or row.reason_code is not None
        or row.input_snapshot != snapshot
        or actual["request"]["original_goal"] != m.GOAL
        or actual["plan"]["candidate"] != record["candidate"]["payload"]["plan"]
        or row.input_digest != digest("head-recovery-input", snapshot=snapshot)
        or row.request_digest != digest("head-http-request", body=record["request"])
        or row.response_json != assembled
        or row.response_digest != fingerprint(row)
        or row.usage_json != record["usage"]
        or row.prompt_version != m.VERSION
        or row.schema_version != VERSION
        or str(row.request_id) != actual["request"]["request_id"]
    ):
        raise SnapshotError("HEAD_RECOVERY_ADMISSION")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(
                blocks=deepcopy(assembled["blocks"]),
                generation_source=deepcopy(assembled["generation_source"]),
            ),
            actions=deepcopy(assembled["actions"]),
            dependencies=[],
        ),
    )


async def import_course(db, owner: UUID, review: dict[str, Any]):
    from app.models.free_scene_generation import FreeSceneGenerationResult
    from app.services.free_scene_availability import commit_outline, commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate
    from app.services.head_course_generation import require_development_database

    record, assembled = mapping()
    c = record["candidate"]
    require_development_database(db.bind.url.render_as_string(hide_password=False))
    if (
        review.get("candidate_digest") != c["candidate_digest"]
        or review.get("verdict") not in ("pass", "needs_revision")
        or review != record.get("independent_review")
        or not review.get("independent_evaluator")
        or review.get("planning_basis_binding") != c["payload"]["planning_basis"]["binding"]
    ):
        raise SnapshotError("HEAD_REVIEW_REQUIRED")
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        m.GOAL,
        key="head-format-recovery:" + c["candidate_digest"],
        config={"prompt_version": m.VERSION},
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    current = await repo.get_course(cid)
    if current["head_version"] is not None:
        version = await repo.get_version(cid, current["head_version"])
        return dict(
            **created,
            imported=False,
            version=current["head_version"],
            scene_id=version["scenes"][0]["scene_id"],
            candidate_digest=c["candidate_digest"],
        )
    fence = await repo.acquire_write_fence(cid, oid)
    # Exact existing real model plan is copied; this is not a new planning success.
    saved = await repo.store_plan(
        cid, fence, expected_head=None, key="derived-original-plan", candidate=c["payload"]["plan"]
    )
    pid = UUID(saved["plan_id"])
    sid = UUID((await repo.get_plan(cid, pid))["scenes"][0]["scene_id"])
    await commit_outline(db, owner, cid, fence, plan_id=pid, key="derived-outline")
    actual = await load_inputs(db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=1)
    snapshot = dict(inputs=actual, derivation=record)
    row = FreeSceneGenerationResult(
        user_id=owner,
        course_id=cid,
        operation_id=oid,
        request_id=UUID(actual["request"]["request_id"]),
        lease_epoch=fence.epoch,
        call_key="r03-local-format-recovery",
        expected_head=1,
        input_snapshot=snapshot,
        input_digest=digest("head-recovery-input", snapshot=snapshot),
        request_digest=digest("head-http-request", body=record["request"]),
        response_json=assembled,
        prompt_version=m.VERSION,
        schema_version=VERSION,
        state="candidate",
        reason_code=None,
        plan_id=pid,
        scene_id=sid,
        sent_attempts=1,
        usage_json=record["usage"],
        origin_type=m.ORIGIN,
    )
    # sent_attempts and usage attribute the one historical r03 teaching response,
    # not a new dispatch. The explicit recovery source carries new_provider_calls=0.
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
        expected_head=1,
        key="derived-ready",
    )
    op = await repo._operation(cid, oid)
    op.state = "succeeded"
    op.lease_token = None
    op.lease_expires_at = None
    return dict(
        **created,
        version=ready["version"],
        scene_id=str(sid),
        candidate_digest=c["candidate_digest"],
        imported=True,
    )
