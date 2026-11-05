"""Record-bound reviewed evidence revision, imported as a new private child course."""

import hashlib
from copy import deepcopy
from uuid import UUID

from app.services import head_course_evidence_revision as f
from app.services import head_course_generation as g
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical, digest


def validate_record(record):
    from scripts.head_course_goal import raw_io

    data = f.inputs()
    raw = record["raw_response"].encode()
    result, _ = raw_io.observe_generation(f.body(), raw)
    expected = f.merge(data["parent_candidate"], dict(result.value))
    approval = record["approval"]
    if (
        record["protocol_version"] != f.VERSION
        or canonical(record["input"]) != canonical(data)
        or record["request"] != f.body()
        or record["output"] != dict(result.value)
        or canonical(record["candidate"]) != canonical(expected)
        or record["model"] != result.model_id
        or record["usage"]
        != dict(input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens)
        or result.usage.input_tokens > 139264
        or result.usage.output_tokens > 4000
        or record["receipt"]
        != dict(
            http_status=200,
            raw_bytes=len(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            body_complete=True,
        )
        or approval.get("explicit_user_authorization") is not True
        or approval.get("accept_ADR0054_scope_and_batch_C2") is not True
        or approval.get("protocol_version") != f.VERSION
        or approval.get("parent_digest") != expected["parent_digest"]
        or approval.get("evidence_digest") != data["teaching_evidence"]["evidence_digest"]
        or type(approval.get("max_http_requests")) is not int
        or approval["max_http_requests"] != 1
        or approval["manifest_sha256"]
        != hashlib.sha256((f.PACKAGE / "manifest.json").read_bytes()).hexdigest()
        or type(approval.get("starts_epoch")) is not int
        or type(approval.get("expires_epoch")) is not int
        or approval["expires_epoch"] - approval["starts_epoch"] != 600
        or record["attempt"]["manifest_sha256"] != approval["manifest_sha256"]
        or record["attempt"]["parent_digest"] != expected["parent_digest"]
        or record["attempt"]["request_sha256"] != hashlib.sha256(canonical(f.body())).hexdigest()
        or record["attempt"]["evidence_kind"] not in ("offline_fixture", "actual_provider_response")
    ):
        raise SnapshotError("EVIDENCE_PUBLICATION_RECORD")
    return expected


def validate_review(c, review):
    r = f.r
    r.review_binding(review, c, "pass")
    required = (
        "full_lesson",
        "fact_citations",
        "paragraph_responsibilities",
        "no_neighbour_copy",
        "no_omitted_explanation",
        "code_trace_answers",
        "no_answer_hints",
        "display_scope",
        "paragraph_algorithm_preserved",
    )
    if (
        review.get("evidence_digest") != c["payload"]["teaching_evidence"]["evidence_digest"]
        or review.get("blocking_findings") != []
        or any(review.get("checks", {}).get(key) is not True for key in required)
    ):
        raise SnapshotError("EVIDENCE_PUBLICATION_REVIEW")


def assembled(record, review):
    c = validate_record(record)
    validate_review(c, review)
    return m.assemble(
        c["payload"],
        c["raw_output"],
        f.source(
            c,
            record["model"],
            review,
            fixture=record["attempt"]["evidence_kind"] == "offline_fixture",
        ),
    )


def validate_publication(row, actual):
    stored = row.input_snapshot["evidence_revision"]
    record, review = stored["record"], stored["review"]
    projection = assembled(record, review)
    snapshot = dict(inputs=actual, evidence_revision=stored)
    if (
        row.state != "candidate"
        or row.reason_code is not None
        or row.origin_type != m.ORIGIN
        or row.schema_version != f.VERSION
        or row.prompt_version != f.VERSION
        or row.sent_attempts != 1
        or str(row.request_id) != actual["request"]["request_id"]
        or actual["request"]["original_goal"] != record["candidate"]["payload"]["original_goal"]
        or actual["plan"]["candidate"] != record["candidate"]["payload"]["plan"]
        or row.input_snapshot != snapshot
        or row.input_digest != digest("head-evidence-revision-input", snapshot=snapshot)
        or row.request_digest != digest("head-http-request", body=record["request"])
        or row.response_json != projection
        or row.response_digest != g.fingerprint(row)
        or row.usage_json != record["usage"]
    ):
        raise SnapshotError("EVIDENCE_PUBLICATION_BINDING")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(
                blocks=deepcopy(projection["blocks"]),
                generation_source=deepcopy(projection["generation_source"]),
            ),
            actions=deepcopy(projection["actions"]),
            dependencies=[],
        ),
    )


async def import_course(db, owner, record, review):
    from app.models.free_scene_generation import FreeSceneGenerationResult
    from app.services.free_scene_availability import commit_outline, commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate

    g.require_development_database(db.bind.url.render_as_string(hide_password=False))
    projection = assembled(record, review)
    c = record["candidate"]
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        c["payload"]["original_goal"],
        key="head-evidence-revision:" + c["candidate_digest"],
        config={"prompt_version": m.REUSE_VERSION},
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
        )
    fence = await repo.acquire_write_fence(cid, oid)
    plan = await repo.store_plan(
        cid,
        fence,
        expected_head=None,
        key="evidence-revision-original-real-plan",
        candidate=c["payload"]["plan"],
    )
    pid = UUID(plan["plan_id"])
    sid = UUID((await repo.get_plan(cid, pid))["scenes"][0]["scene_id"])
    await commit_outline(db, owner, cid, fence, plan_id=pid, key="evidence-revision-outline")
    actual = await load_inputs(db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=1)
    snapshot = dict(inputs=actual, evidence_revision=dict(record=record, review=review))
    row = FreeSceneGenerationResult(
        user_id=owner,
        course_id=cid,
        operation_id=oid,
        request_id=UUID(actual["request"]["request_id"]),
        lease_epoch=fence.epoch,
        call_key="head-evidence-local-revision",
        expected_head=1,
        input_snapshot=snapshot,
        input_digest=digest("head-evidence-revision-input", snapshot=snapshot),
        request_digest=digest("head-http-request", body=record["request"]),
        response_json=projection,
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
    row.response_digest = g.fingerprint(row)
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
        key="head-evidence-ready:" + c["candidate_digest"],
    )
    op = await repo._operation(cid, oid)
    op.state = "succeeded"
    op.lease_token = op.lease_expires_at = None
    return dict(
        **created,
        version=ready["version"],
        scene_id=str(sid),
        candidate_digest=c["candidate_digest"],
    )
