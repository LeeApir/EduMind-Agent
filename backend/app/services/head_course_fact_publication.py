"""Fixed, independently reviewed real fact revision; existing private snapshot chain only."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from app.services import head_course_fact_revision as f
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-fact-live-r01"
CANDIDATE_SHA = "16db731f7b5df5d84adb86e725af661192a5b17bc6b538ca421b4b86571cbd69"

FILES = {
    "revision.output.json": "a3665eccce0373e528f9c22693036bd226bdcafb1696c5c6a2d3044c41aab156",
    "revision.request.json": "0320d95d3c502c02cff48b41e4a0e2995c6d77fbfaba3b6d8a027f04d9c96486",
    "revision.body.json": "4052bb8ac8a57daf908ca8f028c72cf572584ff8c43b8f04d101bd0f835fa320",
    "mechanical-check.json": "58eb4089b582d68ca3e8de3ddd47a691dd0afd31dc22ff5f108f0bf33b2f1245",
    "final-review.json": "24255c6ac09fe2f11bad9c3c1453251f471732218198289a3633807752a89598",
}


def mapping():
    for name, sha in FILES.items():
        if hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() != sha:
            raise SnapshotError("FACT_PUBLICATION_INPUT_CHANGED")
    body = (PACKAGE / "revision.candidate.json").read_bytes()
    if hashlib.sha256(body).hexdigest() != CANDIDATE_SHA:
        raise SnapshotError("FACT_CANDIDATE_CHANGED")
    c = json.loads(body)
    out = json.loads((PACKAGE / "revision.output.json").read_text())
    if c != f.merge(f.inputs()["parent_candidate"], out):
        raise SnapshotError("FACT_MERGE_CHANGED")
    review = json.loads((PACKAGE / "final-review.json").read_text())
    if (
        review.get("candidate_digest") != c["candidate_digest"]
        or review.get("parent_digest") != f.PARENT
        or review.get("verdict") != "pass"
        or not review.get("independent_evaluator")
        or review.get("planning_basis_binding") != c["payload"]["planning_basis"]["binding"]
    ):
        raise SnapshotError("FACT_REVIEW_REQUIRED")
    request = json.loads((PACKAGE / "revision.request.json").read_text())
    if request != f.body():
        raise SnapshotError("FACT_REQUEST_CHANGED")
    meta = json.loads((PACKAGE / "mechanical-check.json").read_text())
    receipt = json.loads((PACKAGE / "revision.body.json").read_text())
    if receipt["raw_sha256"] != "fbaeb8c2b1a0acffeddaee8e5fccbd2d00e42c77450d348d3df8a6e0b946f6f7":
        raise SnapshotError("FACT_RECEIPT_CHANGED")
    record = dict(
        candidate=c,
        output=out,
        request=request,
        receipt=receipt,
        usage=meta["usage"],
        review=review,
    )
    assembled = f.assemble(c)
    assembled["generation_source"]["teaching_review"] = dict(
        verdict="pass", independent_evaluator=review["independent_evaluator"]
    )
    return record, assembled


def fingerprint(row):
    return digest(
        "head-fact-outcome",
        input_digest=row.input_digest,
        request_digest=row.request_digest,
        response=row.response_json,
        usage=row.usage_json,
        sent_attempts=row.sent_attempts,
        origin=row.origin_type,
    )


def validate_publication(row, actual):
    record, assembled = mapping()
    snapshot = dict(inputs=actual, fact_revision=record)
    if (
        row.origin_type != m.ORIGIN
        or row.schema_version != f.VERSION
        or row.prompt_version != f.VERSION
        or row.sent_attempts != 1
        or row.state != "candidate"
        or row.reason_code is not None
        or row.input_snapshot != snapshot
        or row.input_digest != digest("head-fact-input", snapshot=snapshot)
        or row.request_digest != digest("head-http-request", body=record["request"])
        or row.response_json != assembled
        or row.response_digest != fingerprint(row)
        or row.usage_json != record["usage"]
        or str(row.request_id) != actual["request"]["request_id"]
        or actual["request"]["original_goal"] != m.GOAL
        or actual["plan"]["candidate"] != record["candidate"]["payload"]["plan"]
    ):
        raise SnapshotError("FACT_PUBLICATION_BINDING")
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


async def import_course(db, owner: UUID):
    from app.models.free_scene_generation import FreeSceneGenerationResult
    from app.services.free_scene_availability import commit_outline, commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate
    from app.services.head_course_generation import require_development_database

    require_development_database(db.bind.url.render_as_string(hide_password=False))
    record, assembled = mapping()
    c = record["candidate"]
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        m.GOAL,
        key="head-fact-revision:" + c["candidate_digest"],
        config={"prompt_version": m.VERSION},
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    current = await repo.get_course(cid)
    if current["head_version"] is not None:
        version = await repo.get_version(cid, current["head_version"])
        return dict(
            **created,
            version=current["head_version"],
            scene_id=version["scenes"][0]["scene_id"],
            candidate_digest=c["candidate_digest"],
            imported=False,
        )
    fence = await repo.acquire_write_fence(cid, oid)
    plan = await repo.store_plan(
        cid,
        fence,
        expected_head=None,
        key="fact-original-real-plan",
        candidate=c["payload"]["plan"],
    )
    pid = UUID(plan["plan_id"])
    sid = UUID((await repo.get_plan(cid, pid))["scenes"][0]["scene_id"])
    await commit_outline(db, owner, cid, fence, plan_id=pid, key="fact-outline")
    actual = await load_inputs(db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=1)
    snapshot = dict(inputs=actual, fact_revision=record)
    row = FreeSceneGenerationResult(
        user_id=owner,
        course_id=cid,
        operation_id=oid,
        request_id=UUID(actual["request"]["request_id"]),
        lease_epoch=fence.epoch,
        call_key="fact-revision-reviewed",
        expected_head=1,
        input_snapshot=snapshot,
        input_digest=digest("head-fact-input", snapshot=snapshot),
        request_digest=digest("head-http-request", body=record["request"]),
        response_json=assembled,
        prompt_version=f.VERSION,
        schema_version=f.VERSION,
        state="candidate",
        reason_code=None,
        plan_id=pid,
        scene_id=sid,
        sent_attempts=1,
        usage_json=record["usage"],
        origin_type=m.ORIGIN,
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
        expected_head=1,
        key="fact-ready",
    )
    op = await repo._operation(cid, oid)
    op.state = "succeeded"
    op.lease_token = None
    op.lease_expires_at = None
    # The new private child course records the accurate parent candidate; no parent
    # course/version/attempt is updated or re-scored, and no planning call is made.
    return dict(
        **created,
        version=ready["version"],
        scene_id=str(sid),
        candidate_digest=c["candidate_digest"],
        imported=True,
    )
