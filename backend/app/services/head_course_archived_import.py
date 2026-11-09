"""ADR0057 private import for the single reviewed AIAPI r05 response."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.services import head_course_materials as materials
from app.services import head_course_reuse as reuse
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical, digest
from app.services.head_course_replay import ORIGIN as STORAGE_ORIGIN
from app.services.head_course_replay import fingerprint

ROOT = Path(__file__).resolve().parents[3]
ACCEPTANCE = ROOT / "docs/acceptance"
BATCH = "head-fixed-aiapi-r05"
ARCHIVE = ACCEPTANCE / f"phase-1.5-{BATCH}"
VAULT = Path.home() / ".local/share/edumind" / BATCH
RULE = "head-reviewed-archived-import-v1"
ORIGIN = "reviewed_archived_response_import"
DATABASE = "edumind_catalog_p15_t108_t112"
CANDIDATE = "b7759b9d5d7b7f0cf2fb96445e776d1fec3592dd97c1d741f1ee655a5fedcdc9"
PLAN = "0997615bbdb35b96df95904d4d4d1730d08a94a2f797091c04a48e484a6452ee"
APPROVAL_SHA = "5ab7225f16efc041b5e9cb347f19c0453c9e7719b8b010865c0975729fe7e689"
MANIFEST_SHA = "a93c421ce7743c173355620cdade713249edcfccb234f18f7f6c294d7fa92d8a"
REVIEW_SHA = "53f48b2bfec532478199fd9dc80be6ed9a4026c06b64d93aadcd390f205eefda"
CONTEXT_SHA = "0bc861d03635cb7418d7f80043d5b1a46ed36ace0de533a077dbf3ed0d931c24"
PLAN_RAW_SHA = "064a0fbc56d5f90bb2ac9a024f8e9cc7606d49b21731f0bd0a6c3b08422e1534"
PLAN_REVIEW_SHA = "0363a697c150a8443950f7cb0fc503b7aa9e22c77b9c880e192be96eca6a2367"
REQUESTED_MODEL = "gpt-6.1-sol"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    body = path.read_bytes()
    if sha(body) != expected:
        raise SnapshotError("ARCHIVED_IMPORT_SOURCE_CHANGED")
    return body


def original_payload():
    from app.agents.head_course_planning_wire import to_local
    from scripts.head_course_goal import planning_body, raw_io

    planning = ACCEPTANCE / "phase-1.5-head-fixed-live-r01"
    inputs = json.loads(pinned(planning / "context.json", CONTEXT_SHA))["planning_inputs"]
    request = planning_body(inputs)
    if canonical(request) != (planning / "plan.request.json").read_bytes():
        raise SnapshotError("ARCHIVED_IMPORT_PLAN")
    result, _ = raw_io.observe_generation(request, pinned(planning / "plan.raw.json", PLAN_RAW_SHA))
    plan = to_local(result.value, inputs)["plan"]
    payload = materials.content_payload(inputs, plan)
    review = json.loads(pinned(planning / "plan-review.json", PLAN_REVIEW_SHA))
    if (
        digest("head-plan", plan=plan) != PLAN
        or review["plan_digest"] != PLAN
        or review["verdict"] != "pass"
        or review["planning_basis_binding"] != payload["planning_basis"]["binding"]
    ):
        raise SnapshotError("ARCHIVED_IMPORT_PLAN")
    return payload


def mapping():
    from scripts.head_course_fixed_continuation import cipher, raw_io

    manifest = json.loads(pinned(ARCHIVE / "originals-manifest.json", MANIFEST_SHA))
    if VAULT.is_symlink() or VAULT.stat().st_mode & 0o077 or manifest["vault"] != str(VAULT):
        raise SnapshotError("ARCHIVED_IMPORT_VAULT")
    for name, expected in manifest["files"].items():
        pinned(VAULT / name, expected)
    approval = json.loads(pinned(ARCHIVE / "approval.json", APPROVAL_SHA))
    attempt = json.loads((VAULT / "draft.attempt.json").read_bytes())
    failure = json.loads((VAULT / "failure.json").read_bytes())
    stop = json.loads((VAULT / "STOP").read_bytes())
    receipt = json.loads((VAULT / "draft.body.json").read_bytes())
    payload = original_payload()
    request = dict(materials.body(payload), model=REQUESTED_MODEL)
    request_bytes = canonical(request)
    raw = raw_io.decrypt(VAULT / "draft.raw.enc", cipher(VAULT))
    if (
        request_bytes != (VAULT / "draft.request.json").read_bytes()
        or sha(request_bytes) != attempt["request_sha256"]
        or attempt["request_sha256"] != approval["request_sha256"]
        or attempt["approval_sha256"] != APPROVAL_SHA
        or attempt["evidence_kind"] != "actual_provider_attempt"
        or attempt["model"] != REQUESTED_MODEL
        or attempt["endpoint"] != approval["endpoint"]
        or approval["source_plan_digest"] != PLAN
        or failure["code"] != "AIAPI_ENVELOPE"
        or stop["reason"] != "failure_or_unknown"
        or receipt
        != dict(http_status=200, raw_bytes=len(raw), raw_sha256=sha(raw), body_complete=True)
    ):
        raise SnapshotError("ARCHIVED_IMPORT_RECEIPT")

    reply = raw_io.wire.strict_json(raw)
    (message,) = reply["output"]
    (part,) = message["content"]
    text = part["text"]
    if (
        reply["status"] != "completed"
        or "model" in reply
        or "store" in reply
        or (message["type"], message["role"], message["status"], message["phase"])
        != ("message", "assistant", "completed", "final_answer")
        or part["type"] != "output_text"
        or part["annotations"] != []
        or reply["output_text"] != text
    ):
        raise SnapshotError("ARCHIVED_IMPORT_TEXT")
    output = raw_io.wire.strict_json(text)
    raw_io.wire.check_schema(output, request["text"]["format"]["schema"])
    candidate = reuse.candidate(payload, output)
    review = json.loads(pinned(ARCHIVE / "teaching-review.json", REVIEW_SHA))
    inspection = json.loads(
        pinned(ARCHIVE / "text-inspection.json", review["source_inspection_sha256"])
    )
    reuse.review_binding(review, candidate, "pass")
    required = (
        "full_lesson",
        "fact_citations",
        "paragraph_responsibilities",
        "no_neighbour_copy",
        "no_omitted_explanation",
        "code_trace_answers",
        "no_answer_hints",
        *reuse.FIXED_REVIEW_CHECKS,
    )
    text_sha = sha(text.encode())
    if (
        candidate["candidate_digest"] != CANDIDATE
        or candidate != inspection["candidate"]
        or review["scope"] != "text_only_diagnostic"
        or review["admission_eligible"] is not False
        or review["strict_wire_verdict"] != failure["code"]
        or review["blocking_findings"] != []
        or any(review["checks"].get(key) is not True for key in required)
        or review["raw_response_sha256"] != receipt["raw_sha256"]
        or review["assistant_output_sha256"] != text_sha
        or review["source_request_sha256"] != attempt["request_sha256"]
        or review["provider_metadata"]
        != dict(
            requested_model=REQUESTED_MODEL,
            reported_model=None,
            reported_store=None,
            model_key_present=False,
            store_key_present=False,
        )
    ):
        raise SnapshotError("ARCHIVED_IMPORT_REVIEW")
    evidence = payload["teaching_evidence"]
    source = dict(
        origin=ORIGIN,
        evidence_kind=ORIGIN,
        batch=BATCH,
        prompt_version=materials.FIXED_VERSION,
        candidate_digest=CANDIDATE,
        parent_digest=None,
        plan_digest=PLAN,
        materials_digest=payload["materials"]["materials_digest"],
        teaching_evidence_version=evidence["version"],
        teaching_evidence_digest=evidence["evidence_digest"],
        requested_model=REQUESTED_MODEL,
        reported_model=None,
        reported_store=None,
        strict_wire_verdict=failure["code"],
        new_provider_calls=0,
        teaching_review=dict(verdict="pass", independent_evaluator=review["independent_evaluator"]),
    )
    record = dict(
        candidate=candidate,
        original_text=text,
        approval_sha256=APPROVAL_SHA,
        originals_manifest_sha256=MANIFEST_SHA,
        request_sha256=attempt["request_sha256"],
        text_sha256=text_sha,
        response_receipt=receipt,
        original_failure=failure,
        original_stop=stop,
        review=review,
        review_sha256=REVIEW_SHA,
    )
    return record, materials.assemble(payload, output, source)


def require_database(db):
    from app.services.head_course_generation import require_development_database

    bind = db.bind
    if isinstance(bind, AsyncConnection):
        bind = bind.engine
    if not isinstance(bind, AsyncEngine) or bind.url.database != DATABASE:
        raise SnapshotError("ARCHIVED_IMPORT_DATABASE")
    require_development_database(bind.url.render_as_string(hide_password=False))


def validate_import(row, actual):
    record, projection = mapping()
    snapshot = dict(inputs=actual, archived_import=record)
    payload = record["candidate"]["payload"]
    if (
        row.origin_type != STORAGE_ORIGIN
        or row.schema_version != RULE
        or row.prompt_version != materials.FIXED_VERSION
        or row.state != "candidate"
        or row.reason_code is not None
        or row.sent_attempts != 0
        or row.usage_json is not None
        or row.input_snapshot != snapshot
        or str(row.request_id) != actual["request"]["request_id"]
        or actual["request"]["original_goal"] != payload["original_goal"]
        or actual["plan"]["candidate"] != payload["plan"]
        or row.input_digest != digest(RULE, snapshot=snapshot)
        or row.request_digest != record["request_sha256"]
        or row.response_json != projection
        or row.response_digest != fingerprint(row)
    ):
        raise SnapshotError("ARCHIVED_IMPORT_BINDING")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(
                blocks=projection["blocks"], generation_source=projection["generation_source"]
            ),
            actions=projection["actions"],
            dependencies=[],
        ),
    )


async def import_course(db, owner: UUID):
    from app.models.free_scene_generation import FreeSceneGenerationResult
    from app.services.free_scene_availability import commit_outline, commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate

    require_database(db)
    record, projection = mapping()
    payload = record["candidate"]["payload"]
    repo = SnapshotRepository(db, owner)
    key = RULE + ":" + CANDIDATE
    async with db.begin_nested():
        created = await repo.create_course(
            payload["original_goal"], key=key, config={"prompt_version": materials.FIXED_VERSION}
        )
        cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
        current = await repo.get_course(cid)
        if current["head_version"] is not None:
            # The import receipt refers to the original immutable version even after edits.
            version = await repo.get_version(cid, 2)
            return dict(
                **created, version=2, scene_id=version["scenes"][0]["scene_id"], imported=False
            )
        fence = await repo.acquire_write_fence(cid, oid)
        plan = await repo.store_plan(
            cid, fence, expected_head=None, key="archive-plan", candidate=payload["plan"]
        )
        pid = UUID(plan["plan_id"])
        sid = UUID((await repo.get_plan(cid, pid))["scenes"][0]["scene_id"])
        outline = await commit_outline(db, owner, cid, fence, plan_id=pid, key="archive-outline")
        actual = await load_inputs(
            db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=outline["version"]
        )
        snapshot = dict(inputs=actual, archived_import=record)
        row = FreeSceneGenerationResult(
            user_id=owner,
            course_id=cid,
            operation_id=oid,
            lease_epoch=fence.epoch,
            request_id=UUID(actual["request"]["request_id"]),
            plan_id=pid,
            scene_id=sid,
            call_key=RULE,
            expected_head=outline["version"],
            input_snapshot=snapshot,
            input_digest=digest(RULE, snapshot=snapshot),
            request_digest=record["request_sha256"],
            response_json=projection,
            prompt_version=materials.FIXED_VERSION,
            schema_version=RULE,
            state="candidate",
            reason_code=None,
            sent_attempts=0,
            usage_json=None,
            origin_type=STORAGE_ORIGIN,
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
            key="archive-ready",
        )
        operation = await repo._operation(cid, oid)
        operation.state = "succeeded"
        operation.lease_token = None
        operation.lease_expires_at = None
        await db.flush()
        return dict(**created, version=ready["version"], scene_id=str(sid), imported=True)
