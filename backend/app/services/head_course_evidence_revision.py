"""Exact B local revision plus versioned program evidence. No Provider or prose fallback."""

from copy import deepcopy
from pathlib import Path

from app.services import head_course_materials as m
from app.services import head_course_reuse as r
from app.services import head_course_teaching_evidence as evidence
from app.services.free_course_snapshots import SnapshotError, canonical, digest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-b-local-revision-r01"
ORIGINAL = ROOT / "docs/acceptance/phase-1.5-head-reuse-live-r01"
EVIDENCE = ROOT / "docs/acceptance/phase-1.5-head-evidence-t110/teaching-evidence.json"
VERSION = "head-evidence-local-revision-v1"
INSTRUCTION = """[ROLE] Revise only the exact parent fields allowed by this request.
[OUTPUT] Return only the supplied closed Schema: complete failure_scope, and the mapped
paragraph object with complete text and fact_ids. No full lesson, patch operations, extra keys,
fences, commentary, tools or external material. The program alone merges replacements.
[SCOPE] In failure_scope accurately state that the main lesson shows two successful allocations
and two evaluated NULL conditions, both false, followed by insertion. The mask-disabled
no-allocation branch and actual malloc failure are NOT shown in the 13 main frames. Static
code capability is not a demonstrated branch. Keep correct explanation of returning old head
when p is NULL, no p field writes on failure, assumed-success boundary and no real C execution.
[PARAGRAPH] The supplied paragraph's algorithm explanation is already correct. Prefer copying
its original text verbatim; fix its citations to the separately computed discard-return evidence
specified in required_fact_ids. Preserve its teaching duty: caller keeps old entry, allocated
nodes become unreachable, this differs from allocation failure. The comparison is not a main
animation. Do not copy a neighbour, omit explanation or add transfer answers or hints.
[OWNERSHIP] All other teaching fields including summary, questions, step notes and lifecycle
are immutable. Program code, trace, answers, original facts, plan, learner goal and basis are
immutable. New teaching_evidence is a separately versioned program supplement, not an edit
of the old catalog. Use its exact IDs and source distinctions; never invent evidence.
[REVIEW] The original stop review stays unchanged. This request authorizes only the listed
scope exception for a NEW batch; it does not reopen r01 or pre-sign teaching success. The
complete merged lesson must be independently reassessed before private application import.
"""


def read(path):
    # Local execution inputs are also frozen by the exact package manifest.
    from scripts.head_course_goal import raw_io

    return raw_io.wire.strict_json(path.read_bytes())


def build_inputs(parent, bundle, review, scope):
    r.validate_candidate(parent)
    evidence.validate(parent["payload"], bundle)
    if (
        scope["version"] != VERSION
        or scope["parent_digest"] != parent["candidate_digest"]
        or scope["evidence_digest"] != bundle["evidence_digest"]
        or review["candidate_digest"] != parent["candidate_digest"]
        or review["planning_basis_binding"] != parent["payload"]["planning_basis"]["binding"]
        or review["verdict"] != "stop"
        or not review["independent_evaluator"]
        or scope["max_http_requests"] != 1
        or scope["planning_calls"] != 0
        or scope["full_generation_calls"] != 0
    ):
        raise SnapshotError("EVIDENCE_REVISION_BINDING")
    paths = scope["allowed_paths"]
    if len(paths) != 2 or list(paths.values()).count(["failure_scope"]) != 1:
        raise SnapshotError("EVIDENCE_REVISION_SCOPE")
    for key, path in paths.items():
        if path != ["failure_scope"] and not (
            len(path) == 2
            and path[0] == "paragraphs"
            and type(path[1]) is int
            and 0 <= path[1] < len(parent["raw_output"]["paragraphs"])
        ):
            raise SnapshotError("EVIDENCE_REVISION_SCOPE")
        findings = [f for f in review["blocking_findings"] if f["path"] == path]
        old = parent["raw_output"]
        for part in path:
            old = old[part]
        text = old["text"] if isinstance(old, dict) else old
        if not findings or not all(f["quote"] in text for f in findings):
            raise SnapshotError("EVIDENCE_REVISION_REVIEW_TARGET")
        ids = scope["supporting_fact_ids"][key]
        if not ids or not set(ids) <= set(bundle["facts"]):
            raise SnapshotError("EVIDENCE_REVISION_FACTS")
        if path == ["failure_scope"] and ids != [evidence.DISPLAYED]:
            raise SnapshotError("EVIDENCE_REVISION_FACTS")
        if path != ["failure_scope"]:
            required = scope["required_fact_ids"][key]
            if (
                required != [evidence.DISCARDED]
                or bundle["facts"][required[0]]["evidence_kind"] != "computed_counterfactual"
            ):
                raise SnapshotError("EVIDENCE_REVISION_FACTS")
    return dict(
        protocol_version=VERSION,
        parent_candidate=deepcopy(parent),
        teaching_evidence=deepcopy(bundle),
        original_review=deepcopy(review),
        revision_scope=deepcopy(scope),
        allowed_paths=deepcopy(paths),
        evidence_derivation=dict(
            kind="program_evidence_supplement",
            model_calls=0,
            parent_digest=parent["candidate_digest"],
            evidence_digest=bundle["evidence_digest"],
            original_materials_digest=parent["payload"]["materials"]["materials_digest"],
            allowed_payload_addition=["teaching_evidence"],
        ),
    )


def inputs():
    return build_inputs(
        read(ORIGINAL / "candidate.json"),
        read(EVIDENCE),
        read(ORIGINAL / "final-review.json"),
        read(PACKAGE / "scope.json"),
    )


def schema(data):
    props = {}
    for key, path in data["allowed_paths"].items():
        if path == ["failure_scope"]:
            props[key] = deepcopy(m.TEXT)
        else:
            props[key] = deepcopy(m.SCHEMA["properties"]["paragraphs"]["items"])
            ids = data["revision_scope"]["required_fact_ids"][key]
            props[key]["properties"]["fact_ids"] = dict(
                type="array",
                minItems=len(ids),
                maxItems=len(ids),
                uniqueItems=True,
                items=dict(type="string", enum=ids),
            )
    return m.closed(props)


def body():
    data = inputs()
    return dict(
        model="deepseek-flash",
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        temperature=0.2,
        max_output_tokens=4000,
        input=[
            dict(role="system", content=INSTRUCTION),
            dict(role="user", content=canonical(data).decode()),
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_head_evidence_revision",
                strict=True,
                schema=schema(data),
            )
        ),
    )


def merge(parent, replacements):
    data = inputs()
    if canonical(parent) != canonical(data["parent_candidate"]):
        raise SnapshotError("EVIDENCE_REVISION_PARENT")
    m.Draft202012Validator(schema(data)).validate(replacements)
    raw = deepcopy(parent["raw_output"])
    for key, path in data["allowed_paths"].items():
        if path == ["failure_scope"]:
            raw[path[0]] = replacements[key]
        else:
            i = path[1]
            if replacements[key]["text"].strip() in [
                parent["raw_output"]["paragraphs"][j]["text"].strip()
                for j in (i - 1, i + 1)
                if 0 <= j < len(raw["paragraphs"])
            ]:
                raise SnapshotError("EVIDENCE_REVISION_NEIGHBOUR_COPY")
            raw["paragraphs"][i] = deepcopy(replacements[key])
    payload = evidence.with_evidence(parent["payload"])
    result = r.candidate(payload, raw, parent=parent["candidate_digest"])
    validate_immutable(parent, result, data)
    return result


def validate_immutable(parent, result, data):
    restored = deepcopy(result["raw_output"])
    for path in data["allowed_paths"].values():
        if path == ["failure_scope"]:
            restored[path[0]] = parent["raw_output"][path[0]]
        else:
            restored["paragraphs"][path[1]] = parent["raw_output"]["paragraphs"][path[1]]
    payload = deepcopy(result["payload"])
    supplement = payload.pop("teaching_evidence")
    evidence.validate(parent["payload"], supplement)
    if canonical(restored) != canonical(parent["raw_output"]) or canonical(payload) != canonical(
        parent["payload"]
    ):
        raise SnapshotError("EVIDENCE_REVISION_OUTSIDE_ALLOWLIST")


def source(candidate, model="deepseek-flash", review=None, fixture=False):
    p = candidate["payload"]
    value = dict(
        origin=m.ORIGIN,
        batch=inputs()["revision_scope"]["batch"],
        candidate_digest=candidate["candidate_digest"],
        parent_digest=candidate["parent_digest"],
        model=model,
        prompt_version=VERSION,
        plan_digest=digest("head-plan", plan=p["plan"]),
        materials_digest=p["materials"]["materials_digest"],
        evidence_kind="offline_fixture" if fixture else "evidence_bound_local_revision",
        teaching_evidence_version=evidence.VERSION,
        teaching_evidence_digest=p["teaching_evidence"]["evidence_digest"],
    )
    if review is not None:
        value["teaching_review"] = dict(
            verdict=review["verdict"], independent_evaluator=review["independent_evaluator"]
        )
    return value


def assemble(candidate):
    data = inputs()
    replacements = {}
    for key, path in data["allowed_paths"].items():
        value = candidate["raw_output"]
        for part in path:
            value = value[part]
        replacements[key] = value
    if canonical(candidate) != canonical(merge(data["parent_candidate"], replacements)):
        raise SnapshotError("EVIDENCE_REVISION_CANDIDATE")
    return m.assemble(candidate["payload"], candidate["raw_output"], source(candidate))
