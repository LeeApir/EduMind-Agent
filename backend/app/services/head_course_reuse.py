"""Record-bound limited head lesson pipeline, sharing T108 materials and admission.

No Provider I/O, prose fallback, course-specific digests or review findings live here.
"""

import hashlib
from copy import deepcopy
from uuid import UUID

from app.services import head_course_generation as g
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical, digest

VERSION = m.REUSE_VERSION
BATCH = "head-reuse-r01"
FIXED_BATCH = "head-fixed-r01"
REVISION_VERSION = "head-reviewed-paragraph-revision-v1"
FIXED_REVISION_VERSION = "head-reviewed-local-revision-v2"
FIXED_REVIEW_CHECKS = ("display_scope", "return_contrast", "whole_lesson_consistency")
REVISION_INSTRUCTION = """[ROLE] Revise only independently identified passages of the exact parent.
[OUTPUT] Return replacements under exactly the supplied Schema keys. A paragraph replacement
contains complete text AND fact_ids; summary is a complete string. No other fields or full lesson.
[OWNERSHIP] Program code, facts, traces, answers, question wording, step notes, prerequisites,
lifetime/failure sections, plan and payload are immutable. Only review-identified paragraphs
and learning_summary may change. Use only supplied same-version facts; citations must support
all claims. Keep each original paragraph's teaching responsibility, necessary explanations and
correct useful content. Do not copy adjacent paragraphs, remove an explanation to avoid a finding,
introduce transfer answers/hints or replace a paragraph with a summary. No invented facts, tools,
links, Markdown fences or assistant fallback. Independent full-lesson review follows merging.
"""
FIXED_REVISION_INSTRUCTION = REVISION_INSTRUCTION.replace(
    "summary is a complete string",
    "learning_summary and failure_scope are complete strings",
).replace(
    "lifetime/failure sections, plan and payload are immutable. Only review-identified paragraphs\n"
    "and learning_summary may change.",
    "lifetime, plan and payload are immutable. Only review-identified paragraphs,\n"
    "learning_summary and failure_scope may change. Respect the program evidence: the main "
    "frames show two successful allocations and both false NULL conditions. Use the separate "
    "discard-return fact for claims about the unchanged caller entry and unreachable nodes.",
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def candidate(payload, raw, *, parent=None, recovery=None, allow_terminal_lf=False):
    m.validate_content(payload, raw, allow_terminal_lf=allow_terminal_lf)
    data = dict(
        payload=deepcopy(payload),
        raw_output=deepcopy(raw),
        parent_digest=parent,
        recovery=deepcopy(recovery),
    )
    return dict(**data, candidate_digest=digest("head-reuse-candidate", **data))


def validate_candidate(c, *, allow_terminal_lf=False):
    if c != candidate(
        c["payload"],
        c["raw_output"],
        parent=c["parent_digest"],
        recovery=c["recovery"],
        allow_terminal_lf=allow_terminal_lf,
    ):
        raise SnapshotError("REUSE_CANDIDATE_CHANGED")
    return c


def review_binding(review, c, verdict, *, allow_terminal_lf=False):
    validate_candidate(c, allow_terminal_lf=allow_terminal_lf)
    if (
        review.get("candidate_digest") != c["candidate_digest"]
        or review.get("parent_digest") != c["parent_digest"]
        or review.get("planning_basis_binding") != c["payload"]["planning_basis"]["binding"]
        or review.get("verdict") != verdict
        or not isinstance(review.get("independent_evaluator"), str)
        or not review["independent_evaluator"].strip()
        or (
            c["payload"]["original_goal"] == m.FIXED_GOAL
            and review.get("evidence_digest")
            != c["payload"]["teaching_evidence"]["evidence_digest"]
        )
    ):
        raise SnapshotError("REUSE_REVIEW_BINDING")


def revision_contract(parent, review):
    """Derive a closed response schema from exact quoted findings, never F01/F02 constants."""
    review_binding(review, parent, "needs_revision")
    findings = review.get("findings", [])
    fixed = parent["payload"]["original_goal"] == m.FIXED_GOAL
    if fixed and (
        review.get("blocking_findings") != findings
        or review.get("checks", {}).get("full_lesson") is not True
    ):
        raise SnapshotError("REUSE_REVISION_SCOPE")
    if not 1 <= len(findings) <= 8 or len({f["id"] for f in findings}) != len(findings):
        raise SnapshotError("REUSE_REVISION_SCOPE")
    props, targets, responsibilities = {}, {}, {}
    for finding in findings:
        if (
            finding.get("area") not in ("fact", "citation", "teaching_expression")
            or finding.get("repairable") is not True
            or not finding.get("issue")
            or not finding.get("teaching_responsibility")
        ):
            raise SnapshotError("REUSE_REVISION_SCOPE")
        path = finding.get("path")
        if path == ["learning_summary"] or (fixed and path == ["failure_scope"]):
            key = path[0]
            old = parent["raw_output"][key]
            schema = deepcopy(m.TEXT)
        elif (
            isinstance(path, list)
            and len(path) == 2
            and path[0] == "paragraphs"
            and type(path[1]) is int
            and 0 <= path[1] < len(parent["raw_output"]["paragraphs"])
        ):
            key = f"paragraph_{path[1]}"
            old = parent["raw_output"]["paragraphs"][path[1]]["text"]
            schema = deepcopy(m.SCHEMA["properties"]["paragraphs"]["items"])
        else:
            raise SnapshotError("REUSE_REVISION_SCOPE")
        if (
            not isinstance(finding.get("quote"), str)
            or not finding["quote"]
            or finding["quote"] not in old
        ):
            raise SnapshotError("REUSE_REVISION_QUOTE")
        if key in responsibilities and responsibilities[key] != finding["teaching_responsibility"]:
            raise SnapshotError("REUSE_REVISION_RESPONSIBILITY")
        props[key], targets[key] = schema, path
        responsibilities[key] = finding["teaching_responsibility"]
    return dict(
        version=FIXED_REVISION_VERSION if fixed else REVISION_VERSION,
        parent_digest=parent["candidate_digest"],
        review_digest=digest("head-reuse-review", review=review),
        targets=targets,
        responsibilities=responsibilities,
        schema=m.closed(props),
    )


def revision_body(parent, review):
    contract = revision_contract(parent, review)
    fixed = contract["version"] == FIXED_REVISION_VERSION
    request = m.body(parent["payload"])
    revision_input = dict(parent_candidate=parent, review=review, revision_contract=contract)
    if not fixed:
        revision_input.update(
            same_version_basis=parent["payload"]["planning_basis"],
            same_version_materials=parent["payload"]["materials"],
        )
    request.update(
        max_output_tokens=4000,
        input=[
            dict(
                role="system",
                content=FIXED_REVISION_INSTRUCTION if fixed else REVISION_INSTRUCTION,
            ),
            dict(
                role="user",
                content=canonical(revision_input).decode(),
            ),
        ],
    )
    request["text"]["format"].update(
        name="edumind_head_reviewed_revision", schema=contract["schema"]
    )
    return request


def merge(parent, review, replacements):
    contract = revision_contract(parent, review)
    m.Draft202012Validator(contract["schema"]).validate(replacements)
    raw = deepcopy(parent["raw_output"])
    for key, path in contract["targets"].items():
        if len(path) == 1:
            raw[path[0]] = replacements[key]
        else:
            i = path[1]
            raw["paragraphs"][i] = deepcopy(replacements[key])
            # Exact adjacent copying is mechanically rejectable. Paraphrase/omission is reviewed.
            text = replacements[key]["text"].strip()
            adjacent = [
                parent["raw_output"]["paragraphs"][j]["text"].strip()
                for j in (i - 1, i + 1)
                if 0 <= j < len(raw["paragraphs"])
            ]
            if text in adjacent:
                raise SnapshotError("REUSE_COPIED_NEIGHBOUR")
    if contract["version"] == FIXED_REVISION_VERSION:
        paragraphs = raw["paragraphs"]
        for path in contract["targets"].values():
            if path[0] == "paragraphs":
                i = path[1]
                if any(
                    paragraphs[i]["text"].strip() == paragraphs[j]["text"].strip()
                    for j in (i - 1, i + 1)
                    if 0 <= j < len(paragraphs)
                ):
                    raise SnapshotError("REUSE_COPIED_NEIGHBOUR")
    return candidate(
        parent["payload"], raw, parent=parent["candidate_digest"], recovery=parent["recovery"]
    )


def observe(request, raw, adapter, *, allow_recovery=False, source_batch=BATCH):
    """Strict first; only an inner teaching-JSON duplicate can enter the existing recovery."""
    from app.services.head_course_duplicate_recovery import VERSION as RULE
    from app.services.head_course_duplicate_recovery import recover

    failure = None
    try:
        result, observation = adapter.observe_generation(request, raw)
        return result, observation, None, failure
    except adapter.wire.PilotError as error:
        if not allow_recovery or str(error) != "DUPLICATE_JSON_KEY":
            raise
        failure = dict(code=str(error), raw_sha256=sha(raw), first_structure_pass=False)
    # Strict envelope parsing rejects duplicate envelope fields. No unknown field is ignored.
    envelope = adapter.wire.strict_json(raw)
    try:
        text = envelope["output"][0]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise SnapshotError("REUSE_RECOVERY_ENVELOPE") from None
    recovered, duplicates = recover(text)
    if not duplicates:
        raise SnapshotError("REUSE_RECOVERY_NOT_APPLICABLE")
    view = deepcopy(envelope)
    view["output"][0]["content"][0]["text"] = canonical(recovered).decode()
    # Existing validator still checks the entire envelope, phase, schema, usage and roles.
    result, observation = adapter.observe_generation(request, canonical(view))
    recovery = dict(
        rule_version=RULE,
        source_batch=source_batch,
        original_raw_sha256=sha(raw),
        original_text_sha256=sha(text.encode()),
        derived_output_sha256=sha(canonical(recovered)),
        original_request_sha256=sha(canonical(request)),
        duplicates=duplicates,
        new_provider_calls=0,
        model_first_structure_pass=False,
        assistant_text_edits=0,
    )
    return result, observation, recovery, failure


def record(payload, request, raw, adapter, *, evidence_kind, parent=None, review=None):
    expected = m.body(payload) if parent is None else revision_body(parent, review)
    if request != expected or (parent is not None and parent["payload"] != payload):
        raise SnapshotError("REUSE_REQUEST_BINDING")
    fixed = payload["original_goal"] == m.FIXED_GOAL
    result, observation, recovery, failure = observe(
        request,
        raw,
        adapter,
        allow_recovery=parent is None,
        source_batch=getattr(adapter, "BATCH", FIXED_BATCH) if fixed else BATCH,
    )
    if (
        result.usage.input_tokens > 139264
        or result.usage.output_tokens > request["max_output_tokens"]
    ):
        raise SnapshotError("REUSE_USAGE")
    value = dict(result.value)
    c = (
        candidate(payload, value, recovery=recovery)
        if parent is None
        else merge(parent, review, value)
    )
    return dict(
        protocol_version=m.FIXED_VERSION if fixed else VERSION,
        request=deepcopy(request),
        raw_response=raw.decode(),
        raw_sha256=sha(raw),
        raw_bytes=len(raw),
        output=value,
        candidate=c,
        parent_candidate=deepcopy(parent),
        repair_review=deepcopy(review),
        strict_failure=failure,
        observation=observation,
        model=result.model_id,
        evidence_kind=evidence_kind,
        usage=dict(
            input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens
        ),
    )


def validate_record(rec, payload, adapter, *, parent=None, review=None):
    expected = record(
        payload,
        rec["request"],
        rec["raw_response"].encode(),
        adapter,
        evidence_kind=rec["evidence_kind"],
        parent=parent,
        review=review,
    )
    if rec != expected or rec["evidence_kind"] not in (
        "actual_provider_response",
        "offline_fixture",
    ):
        raise SnapshotError("REUSE_RECORD_CHANGED")
    return rec


def validate_final(records, review, payload, adapter):
    if not 1 <= len(records) <= 2:
        raise SnapshotError("REUSE_REVISION_LIMIT")
    first = validate_record(records[0], payload, adapter)
    if len(records) == 2:
        validate_record(
            records[1],
            payload,
            adapter,
            parent=first["candidate"],
            review=records[1]["repair_review"],
        )
        if records[1]["evidence_kind"] != first["evidence_kind"]:
            raise SnapshotError("REUSE_ORIGIN")
    c = records[-1]["candidate"]
    return require_full_review(review, c)


def require_full_review(review, c, *, allow_terminal_lf=False):
    review_binding(review, c, "pass", allow_terminal_lf=allow_terminal_lf)
    # A sign-off must explicitly cover scope, citations, duties, leakage and all fixed materials.
    required = (
        "full_lesson",
        "fact_citations",
        "paragraph_responsibilities",
        "no_neighbour_copy",
        "no_omitted_explanation",
        "code_trace_answers",
        "no_answer_hints",
    )
    if c["payload"]["original_goal"] == m.FIXED_GOAL:
        required += FIXED_REVIEW_CHECKS
    if review.get("blocking_findings") != [] or any(
        review.get("checks", {}).get(k) is not True for k in required
    ):
        raise SnapshotError("REUSE_FULL_REVIEW_REQUIRED")
    return c


def assembled(records, review, adapter=None):
    from app.services import head_course_aiapi_content as aiapi

    rec = records[-1]
    c = rec["candidate"]
    source = dict(
        origin=m.ORIGIN,
        batch=getattr(adapter, "BATCH", FIXED_BATCH)
        if c["payload"]["original_goal"] == m.FIXED_GOAL
        else BATCH,
        candidate_digest=c["candidate_digest"],
        parent_digest=c["parent_digest"],
        model=rec["model"],
        prompt_version=m.FIXED_VERSION
        if c["payload"]["original_goal"] == m.FIXED_GOAL
        else VERSION,
        plan_digest=digest("head-plan", plan=c["payload"]["plan"]),
        materials_digest=c["payload"]["materials"]["materials_digest"],
        evidence_kind="offline_fixture"
        if rec["evidence_kind"] == "offline_fixture"
        else "reviewed_paragraph_revision"
        if len(records) == 2
        else "program_format_recovery"
        if c["recovery"]
        else "actual_provider_response",
        teaching_review=dict(
            verdict=review["verdict"], independent_evaluator=review["independent_evaluator"]
        ),
    )
    if c["recovery"]:
        source["format_recovery"] = deepcopy(c["recovery"])
    if c["payload"]["original_goal"] == m.FIXED_GOAL:
        evidence = c["payload"]["teaching_evidence"]
        source.update(
            teaching_evidence_version=evidence["version"],
            teaching_evidence_digest=evidence["evidence_digest"],
        )
    if adapter is aiapi:
        source["unknown_echoes"] = [
            field
            for field in aiapi.ECHO_FIELDS
            if rec["observation"]["reported"].get(field) is None
        ]
    return m.assemble(c["payload"], c["raw_output"], source, allow_terminal_lf=adapter is aiapi)


def validate_chain(chain, inputs, plan, adapter):
    from app.agents import head_course_planning_wire as wire
    from app.services import head_course_aiapi_content as aiapi
    from scripts.head_course_goal import planning_body

    if adapter is aiapi:
        return aiapi.validate_chain(chain, inputs, plan)
    context = chain["context"]
    if (
        context["planning_inputs"] != inputs
        or inputs["original_goal"] not in (m.REUSE_GOAL, m.FIXED_GOAL)
        or chain["plan_request"] != planning_body(inputs)
    ):
        raise SnapshotError("REUSE_PLAN_BINDING")
    result, _ = adapter.observe_generation(
        chain["plan_request"], chain["plan_raw_response"].encode()
    )
    if inputs["original_goal"] == m.FIXED_GOAL and (
        result.usage.input_tokens > 139264 or result.usage.output_tokens > 8000
    ):
        raise SnapshotError("REUSE_USAGE")
    if wire.to_local(dict(result.value), inputs)["plan"] != plan:
        raise SnapshotError("REUSE_PLAN_BINDING")
    payload = m.content_payload(inputs, plan)
    p_review = chain["plan_review"]
    if (
        p_review.get("plan_digest") != digest("head-plan", plan=plan)
        or p_review.get("verdict") != "pass"
        or not p_review.get("independent_evaluator")
        or p_review.get("planning_basis_binding") != payload["planning_basis"]["binding"]
    ):
        raise SnapshotError("REUSE_PLAN_REVIEW")
    return validate_final(chain["records"], chain["final_review"], payload, adapter)


def publication_adapter(chain, operation):
    from app.services import head_course_aiapi_content as aiapi
    from scripts import head_course_deepseek_wire as direct
    from scripts.head_course_goal import raw_io

    if operation is not None and operation.config_snapshot.get("policy_version") == aiapi.BATCH:
        if chain["context"].get("execution_window") != aiapi.operation_window(operation):
            raise SnapshotError("HEAD_AIAPI_WINDOW_BINDING")
        return aiapi
    window = direct.operation_window(operation) if operation is not None else {}
    if "execution_window" in chain["context"] or window:
        if not window or chain["context"].get("execution_window") != window["execution_window"]:
            raise SnapshotError("HEAD_DIRECT_WINDOW_MISMATCH")
        return direct
    return raw_io


def validate_publication(row, actual, operation=None):
    chain = row.input_snapshot["reuse_chain"]
    adapter = publication_adapter(chain, operation)
    c = validate_chain(chain, actual["request"], actual["plan"]["candidate"], adapter)
    snapshot = dict(inputs=actual, reuse_chain=chain)
    final = chain["records"][-1]
    expected = assembled(chain["records"], chain["final_review"], adapter)
    if (
        row.input_snapshot != snapshot
        or row.origin_type != m.ORIGIN
        or row.state != "candidate"
        or row.reason_code is not None
        or row.sent_attempts != 1
        or row.schema_version != final["protocol_version"]
        or row.prompt_version != final["protocol_version"]
        or str(row.request_id) != actual["request"]["request_id"]
        or row.input_digest != digest("head-reuse-input", snapshot=snapshot)
        or row.request_digest != digest("head-http-request", body=final["request"])
        or row.response_json != expected
        or row.response_digest != g.fingerprint(row)
        or row.usage_json != final["usage"]
        or c["payload"] != m.content_payload(actual["request"], actual["plan"]["candidate"])
    ):
        raise SnapshotError("REUSE_PUBLICATION_BINDING")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(
                blocks=deepcopy(expected["blocks"]),
                generation_source=deepcopy(expected["generation_source"]),
            ),
            actions=deepcopy(expected["actions"]),
            dependencies=[],
        ),
    )


async def publish(db, owner, cid, oid, chain):
    from app.models.free_scene_generation import FreeSceneGenerationResult
    from app.services import head_course_aiapi_content as aiapi
    from app.services.free_scene_availability import commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate as admit
    from scripts import head_course_deepseek_wire as direct

    g.require_development_database(db.bind.url.render_as_string(hide_password=False))
    repo = SnapshotRepository(db, owner)
    fence = await repo.acquire_write_fence(cid, oid)
    op = await repo._fence(cid, fence)
    adapter = publication_adapter(chain, op)
    if adapter is aiapi:
        aiapi.require_database(db)
        context = await aiapi.outline(repo, cid)
        window = {"execution_window": aiapi.operation_window(op)}
    else:
        context = await g.generation_context(db, owner, cid, oid)
        window = direct.operation_window(op)
    if chain["context"] != dict(
        owner=str(owner),
        course_id=str(cid),
        operation_id=str(oid),
        planning_inputs=chain["context"]["planning_inputs"],
        **window,
    ):
        raise SnapshotError("REUSE_OWNER_BINDING")
    actual = await load_inputs(
        db,
        owner,
        cid,
        oid,
        plan_id=UUID(context["plan_id"]),
        scene_id=UUID(context["scene_id"]),
        expected_head=1,
    )
    c = validate_chain(chain, actual["request"], actual["plan"]["candidate"], adapter)
    records, final = chain["records"], chain["records"][-1]
    snapshot = dict(inputs=actual, reuse_chain=chain)
    row = FreeSceneGenerationResult(
        user_id=owner,
        course_id=cid,
        operation_id=oid,
        request_id=UUID(actual["request"]["request_id"]),
        lease_epoch=fence.epoch,
        call_key="head-reuse-final",
        expected_head=1,
        input_snapshot=snapshot,
        input_digest=digest("head-reuse-input", snapshot=snapshot),
        request_digest=digest("head-http-request", body=final["request"]),
        response_json=assembled(records, chain["final_review"], adapter),
        prompt_version=final["protocol_version"],
        schema_version=final["protocol_version"],
        state="candidate",
        reason_code=None,
        plan_id=UUID(context["plan_id"]),
        scene_id=UUID(context["scene_id"]),
        sent_attempts=1,
        usage_json=deepcopy(final["usage"]),
        origin_type=m.ORIGIN,
    )
    row.response_digest = g.fingerprint(row)
    db.add(row)
    await db.flush()
    checked = await admit(db, owner, cid, fence, result_id=row.id)
    ready = await commit_scene(
        db,
        owner,
        cid,
        fence,
        validation_id=UUID(checked["validation_id"]),
        expected_head=1,
        key="head-reuse-ready:" + c["candidate_digest"],
    )
    op = await repo._operation(cid, oid)
    op.state, op.lease_token, op.lease_expires_at = "succeeded", None, None
    return dict(
        course_id=str(cid),
        operation_id=str(oid),
        version=ready["version"],
        scene_id=context["scene_id"],
        candidate_digest=c["candidate_digest"],
    )
