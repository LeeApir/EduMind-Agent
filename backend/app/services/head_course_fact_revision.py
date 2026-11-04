"""Finite four-text fact revision of the exact recovered r03 parent. No I/O to Provider."""

from copy import deepcopy
from typing import Any

from app.services import head_course_derivation as recovery
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, canonical, digest

VERSION = "head-f01-f02-four-text-v1"
PARENT = "7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779"
PATHS = {
    "paragraph_1_text": ("paragraphs", 1, "text"),
    "paragraph_5_text": ("paragraphs", 5, "text"),
    "paragraph_6_text": ("paragraphs", 6, "text"),
    "learning_summary": ("learning_summary",),
}
SCHEMA = m.closed({key: deepcopy(m.TEXT) for key in PATHS})
INSTRUCTION = """[ROLE] Correct only F01 and F02 in the supplied exact parent Chinese lesson.
[OUTPUT] Return exactly four replacement strings under the four Schema keys. Each is the
complete replacement text for its mapped field. No full lesson, JSON Patch, commentary,
Markdown fences, extra fields, tools or alternative outputs. Preserve useful correct teaching
in those fields; do not remove scope, initialization or NULL-check explanations to evade review.
[BOUNDARY] Do not modify any other parent text, facts, code, IDs, citations, frames, exercises,
answers, plan or assumptions. The program merges four strings and reassembles every view.
[F01] The template writes data then next; that particular order is not a C requirement.
Explain initialization before a field is read; do not assert that data must precede next.
[F02] On each successful allocation, line 5 evaluates p == NULL to false. The condition is
executed; only the early return head branch is skipped. Keep successful checks consistent
with f02/f08. Real allocation failure and cleanup are not animated, and C is not executed.
[QUALITY] Use clear Simplified Chinese, preserve local/caller scope and return-value teaching.
No invented facts or learner knowledge, no new transfer answers or hints. Review the supplied
code, original facts and two findings before returning the four complete strings.
"""


def inputs() -> dict[str, Any]:
    record, _ = recovery.mapping()
    parent = record["candidate"]
    if parent["candidate_digest"] != PARENT:
        raise SnapshotError("FACT_REVISION_PARENT")
    review = record["independent_review"]
    if review["candidate_digest"] != PARENT or [i["id"] for i in review["findings"]] != [
        "F01",
        "F02",
    ]:
        raise SnapshotError("FACT_REVISION_REVIEW")
    return dict(
        protocol_version=VERSION,
        parent_candidate=parent,
        allowed_paths={k: list(v) for k, v in PATHS.items()},
        review=review,
        same_version_basis=parent["payload"]["planning_basis"],
        same_version_materials=parent["payload"]["materials"],
    )


def body() -> dict[str, Any]:
    return dict(
        model="deepseek-flash",
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        temperature=0.2,
        max_output_tokens=4000,
        input=[
            dict(role="system", content=INSTRUCTION),
            dict(role="user", content=canonical(inputs()).decode()),
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_head_fact_revision",
                strict=True,
                schema=deepcopy(SCHEMA),
            )
        ),
    )


def merge(parent: dict[str, Any], replacements: dict[str, Any]) -> dict[str, Any]:
    expected = inputs()["parent_candidate"]
    if parent != expected:
        raise SnapshotError("FACT_REVISION_PARENT")
    m.Draft202012Validator(SCHEMA).validate(replacements)
    value = deepcopy(parent["raw_output"])
    for key, path in PATHS.items():
        obj = value
        for part in path[:-1]:
            obj = obj[part]
        obj[path[-1]] = replacements[key]
    m.validate_content(parent["payload"], value)
    return dict(
        payload=deepcopy(parent["payload"]),
        raw_output=value,
        parent_digest=PARENT,
        candidate_digest=digest(
            "head-four-text-fact-revision",
            protocol=VERSION,
            parent=PARENT,
            payload=parent["payload"],
            raw=value,
        ),
    )


def assemble(candidate: dict[str, Any]) -> dict[str, Any]:
    parent = inputs()["parent_candidate"]
    replacements = {}
    for key, path in PATHS.items():
        obj = candidate["raw_output"]
        for part in path:
            obj = obj[part]
        replacements[key] = obj
    if candidate != merge(parent, replacements):
        raise SnapshotError("FACT_REVISION_CHANGED_OUTSIDE_ALLOWLIST")
    # Proposed private projection; no DB publication or pass is granted by assembly.
    source = dict(
        origin=m.ORIGIN,
        batch="head-goal-fact-r01",
        candidate_digest=candidate["candidate_digest"],
        parent_digest=PARENT,
        model="deepseek-flash",
        prompt_version=VERSION,
        plan_digest=digest("head-plan", plan=parent["payload"]["plan"]),
        materials_digest=parent["payload"]["materials"]["materials_digest"],
        evidence_kind="targeted_fact_revision",
    )
    return m.assemble(candidate["payload"], candidate["raw_output"], source)
