"""Independent review and unreviewed generation probes; injected gateways, no keys/DB."""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from acceptance_support.qwen_review_budget import canonical, sha

from app.agents.hybrid_resource_review import INSTRUCTION, review_once
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.unit_material import restore_material


class IsolatedGateway:
    """Enforce lane and exact 1/4 call ceiling before delegating any network request."""

    def __init__(self, gateway, lane):
        if lane not in {"review", "generation"}:
            raise ValueError("UNKNOWN_LANE")
        self.gateway, self.lane, self.calls = gateway, lane, 0

    async def generate_structured(self, request, *, retry_safe=False):
        is_review = request.prompt.messages[0].content == INSTRUCTION
        if retry_safe or is_review != (self.lane == "review"):
            raise ValueError("LANE_OR_RETRY_VIOLATION")
        if self.calls >= (1 if is_review else 4):
            raise ValueError("LANE_CALL_LIMIT")
        self.calls += 1  # Failed sends consume slots as well.
        return await self.gateway.generate_structured(request, retry_safe=False)


async def fixed_review(gateway, case):
    """One immutable unit, one actual ReviewAgent request, no generation/corrections."""
    workspace, material = restore_material(case["material"])
    guard = IsolatedGateway(gateway, "review")
    before = sha(canonical(case))
    record = await review_once(
        guard,
        CallWindow(),
        binding=material["binding"],
        target_digest=material["unit_digest"],
        payload={"unit": material, "reference_context": material["reference_context"]},
        candidates=workspace.candidates(),
        scope="unit",
        input_snapshot=case["input_snapshot"],
    )
    if before != sha(canonical(case)):
        raise ValueError("FIXED_MATERIAL_CHANGED")
    return dict(
        lane="review",
        case_id=case["id"],
        material_sha256=before,
        review=record,
        calls=guard.calls,
        generation_calls=0,
        corrections=0,
        published=False,
    )


async def generation_draft(gateway, case, run_id):
    """Plan + three scenes, no reviewer, DB, correction or formal publication path."""
    if not run_id:
        raise ValueError("RUN_ID_REQUIRED")
    s = deepcopy(case["input_snapshot"])
    inputs = PlanInputs(
        s["metadata"],
        s["references"],
        frozenset(s["node_ids"]),
        s["learner_evidence"],
        case["reference_context"],
        teaching_context=s.get("teaching_context"),
    )
    guard = IsolatedGateway(gateway, "generation")
    window = CallWindow()
    plan = await generate_shared_plan(guard, inputs, window)

    def identity(k):
        return str(
            uuid5(
                NAMESPACE_URL,
                "edumind:unreviewed-diagnostic:" + run_id + ":" + case["id"] + ":" + k,
            )
        )

    binding = {k: identity(k) for k in ("owner_id", "unit_id", "operation_id", "plan_id")}
    binding.update(
        plan_version=1,
        plan_digest=digest("plan", "learning-plan-v1", plan=plan),
        input_digest=digest("input", "learning-input-v1", snapshot=s),
        references_digest=digest("references", "references-v1", references=inputs.references),
        policy_version="hybrid-review-v1",
        policy_digest=active_policy_digest(),
    )
    workspace = PlannedScenes(
        plan, binding, reference_context=inputs.reference_context, input_snapshot=s
    )
    for role in ("explanation", "code", "exercise"):
        c = await workspace.generate(guard, window, role)
        # Internal draft continuation only; no ReviewRecord or human decision is created.
        workspace.disposition(role, c.id, "needs_human")
    return dict(
        lane="generation",
        case_id=case["id"],
        run_id=run_id,
        input_sha256=sha(canonical(case)),
        plan=plan,
        candidates=[c.payload() for c in workspace.candidates()],
        calls=guard.calls,
        review_calls=0,
        corrections=0,
        review_status="not_reviewed",
        stage_bridge="needs_human permits downstream drafts only; not a review outcome",
        formal_success=None,
        published=False,
        production_publish_performed=False,
        new_code_executed=False,
    )


def check_review_audit(row, case, request):
    """Check exhaustive quoted evidence locations, leaving semantic truth to evaluator."""
    audit = row["audit"]
    if set(audit) != {"evaluator", "assertions", "citations"} or not audit["evaluator"]:
        raise ValueError("AUDITOR_REQUIRED")
    result = row["model_result"]
    expected = set()
    for i, finding in enumerate(result["findings"]):
        for key in ("condition_or_counterexample", "impact"):
            expected.add((f"/findings/{i}/{key}", finding[key]))
    for key, entries in [
        ("unresolved", result["unresolved"]),
        ("coverage/unchecked", result["coverage"]["unchecked"]),
    ]:
        expected.update((f"/{key}/{i}", text) for i, text in enumerate(entries))
    assertions = audit["assertions"]
    if (
        len(assertions) != len(expected)
        or {(a["json_pointer"], a["quoted_text"]) for a in assertions} != expected
    ):
        raise ValueError("ALL_ASSERTIONS_REQUIRED")
    catalog = {a["anchor_id"]: a for a in request["anchor_catalog"]}
    citations = audit["citations"]
    expected_citations = {(i, a) for i, f in enumerate(result["findings"]) for a in f["anchors"]}
    if (
        len(citations) != len(expected_citations)
        or {(c["finding_index"], c["anchor_id"]) for c in citations} != expected_citations
    ):
        raise ValueError("ALL_CITATIONS_REQUIRED")
    resources = {c["resource_id"]: c["envelope"]["content"] for c in case["material"]["candidates"]}
    for c in citations:
        anchor = catalog[c["anchor_id"]]
        value = resources[anchor["resource_id"]]
        for part in anchor["json_pointer"].lstrip("/").split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if isinstance(value, list) else value[part]
        raw = value.encode() if isinstance(value, str) else canonical(value)
        if raw[anchor["start_utf8"] : anchor["end_utf8"]].decode() != c["quoted_text"]:
            raise ValueError("CITATION_QUOTE_CHANGED")
    for entry in assertions + citations:
        if entry.get("result") not in {"supported", "contradicted", "unresolved"} or not entry.get(
            "reason"
        ):
            raise ValueError("SEMANTIC_EVIDENCE_NOTE_REQUIRED")
    checks = row["semantic_checks"]
    for field, entries in [("all_assertions", assertions), ("all_citations", citations)]:
        if checks[field] == "pass" and any(e["result"] != "supported" for e in entries):
            raise ValueError("UNSUPPORTED_CANNOT_PASS")


def review_summary(rows, fixed, *, repeats=3):
    """Summarize externally audited observations; not a semantic judge or authorization."""
    if repeats != 3:
        raise ValueError("FIXED_REPEAT_PLAN_REQUIRED")
    seen = set()
    groups = {name: [] for name in fixed}
    keys = (
        "case_id",
        "repeat",
        "material_sha256",
        "wire_sha256",
        "model_result",
        "semantic_checks",
        "evidence_kind",
        "audit",
        "technical_status",
        "technical_error",
    )
    for row in rows:
        if set(row) != set(keys) or row["case_id"] not in fixed:
            raise ValueError("OBSERVATION_SHAPE")
        name = row["case_id"]
        case, request, label = fixed[name]
        slot = (name, row["repeat"])
        if type(row["repeat"]) is not int or not 1 <= row["repeat"] <= 3 or slot in seen:
            raise ValueError("DUPLICATE_OR_UNKNOWN_REPEAT")
        seen.add(slot)
        if (
            row["material_sha256"] != sha(canonical(case))
            or row["wire_sha256"] != request["wire_sha256"]
        ):
            raise ValueError("FIXED_INPUT_CHANGED")
        if row["evidence_kind"] not in {"synthetic", "externally_audited_provider"}:
            raise ValueError("EVIDENCE_KIND_REQUIRED")
        checks = row["semantic_checks"]
        if set(checks) != {"required_claims", "all_assertions", "all_citations"} or any(
            x not in {"pass", "fail", "unassessed"} for x in checks.values()
        ):
            raise ValueError("SEPARATE_SEMANTIC_CHECKS_REQUIRED")
        if row["technical_status"] == "failed":
            if not row["technical_error"] or any(x != "unassessed" for x in checks.values()):
                raise ValueError("TECHNICAL_FAILURE_NOT_SEMANTIC_PASS")
            if (
                row["audit"]
                != {"evaluator": row["audit"].get("evaluator"), "assertions": [], "citations": []}
                or not row["audit"]["evaluator"]
            ):
                raise ValueError("TECHNICAL_FAILURE_AUDIT_REQUIRED")
            groups[name].append(row)
            continue
        if row["technical_status"] != "complete" or row["technical_error"] is not None:
            raise ValueError("TECHNICAL_STATUS_REQUIRED")
        from jsonschema import Draft202012Validator

        Draft202012Validator(request["business_schema"]).validate(row["model_result"])
        check_review_audit(row, case, request)
        groups[name].append(row)
    kinds = {r["evidence_kind"] for r in rows}
    if len(kinds) > 1:
        raise ValueError("DO_NOT_POOL_SYNTHETIC_AND_PROVIDER")
    result = []
    for name, observed in groups.items():
        complete = [r for r in observed if r["technical_status"] == "complete"]
        verdicts = {
            v: sum(r["model_result"]["verdict"] == v for r in complete)
            for v in ["pass", "reject", "needs_human"]
        }
        expected = fixed[name][2]["expected_verdict"]
        full = sum(
            r["model_result"]["verdict"] == expected
            and all(x == "pass" for x in r["semantic_checks"].values())
            for r in complete
        )
        result.append(
            dict(
                case_id=name,
                observed=len(observed),
                technical_failures=len(observed) - len(complete),
                not_run=repeats - len(observed),
                verdict_counts=verdicts,
                expected_verdict=expected,
                verdict_matches=sum(r["model_result"]["verdict"] == expected for r in complete),
                full_audited_matches=full,
                verdict_varies=len({r["model_result"]["verdict"] for r in complete}) > 1,
                semantic_failures=sum(
                    any(x == "fail" for x in r["semantic_checks"].values()) for r in complete
                ),
                unassessed=sum("unassessed" in r["semantic_checks"].values() for r in complete),
            )
        )
    return dict(
        lane="review",
        planned=len(fixed) * repeats,
        observed=len(rows),
        not_run=len(fixed) * repeats - len(rows),
        evidence_kind=next(iter(kinds), None),
        cases=result,
        quality_claim=(
            "No inference of population stability; external audit must inspect "
            "all assertions and citations; this function checks bindings/counts only."
        ),
    )


def generator_assessment(draft, checks):
    expected = {
        "plan_internal_consistency",
        "original_request_fidelity",
        "student_content_facts_and_safety",
        "teaching_delivery",
        "exercise_measurement",
    }
    if (
        draft.get("lane") != "generation"
        or draft.get("review_calls") != 0
        or draft.get("published") is not False
        or draft.get("production_publish_performed") is not False
        or draft.get("review_status") != "not_reviewed"
    ):
        raise ValueError("GENERATION_IS_NOT_FORMAL_REVIEW")
    if set(checks) != expected:
        raise ValueError("GENERATION_DIMENSIONS_REQUIRED")
    for check in checks.values():
        if set(check) != {"status", "reason", "source_pointers"} or check["status"] not in {
            "pass",
            "fail",
            "unassessed",
        }:
            raise ValueError("GENERATION_DIMENSIONS_REQUIRED")
        if check["status"] != "unassessed" and (
            not check["reason"] or not check["source_pointers"]
        ):
            raise ValueError("GENERATION_EVIDENCE_REQUIRED")
        for pointer in check["source_pointers"]:
            if not isinstance(pointer, str) or not pointer.startswith("/"):
                raise ValueError("GENERATION_EVIDENCE_POINTER")
            value = draft
            for part in pointer.lstrip("/").split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                value = value[int(part)] if isinstance(value, list) else value[part]
    return dict(
        lane="generation",
        case_id=draft["case_id"],
        draft_sha256=sha(canonical(draft)),
        checks=deepcopy(checks),
        formal_success=None,
        reviewer_quality_score=None,
        all_dimensions_audited=all(x["status"] != "unassessed" for x in checks.values()),
        quality_pass=all(x["status"] == "pass" for x in checks.values()),
        note=(
            "Externally supplied semantic judgments; not inferred from model self-report, "
            "schema validity or ReviewAgent verdict."
        ),
    )
