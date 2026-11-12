"""Versioned evidence rules for the fixed-capacity stack selector."""

from dataclasses import replace
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.agents import free_course_planning as planning
from app.services import stack_goal_selection as previous
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.provider_gateway import ChatMessage, StructuredRequest

VERSION = "stack-goal-evidence-v2"
CHECKS = ("selection_semantics", "original_evidence", "scope_complete")
OPTIONAL = previous.REQUIRED["operations_and_rejections"]
INSTRUCTION = """For out_of_scope, include exactly one unsupported citation for a positive
learning requirement outside the supported units. You may also cite supported positive
requirements as normal, full_push or empty_pop, at most once per kind. Do not duplicate
citations. Read each quote in its full source context. A request to omit a topic is not
evidence of a positive requirement, even when the quote itself leaves out the negation.
If any positive requirement is unsupported, keep out_of_scope even with supported evidence."""


def build_request(inputs: dict[str, Any]) -> StructuredRequest:
    base = previous.build_request(inputs)
    snapshot = previous._snapshot(inputs)
    payload = {
        "prompt_version": VERSION,
        "original_goal": snapshot["original_goal"],
        "request_sources": {key: row["text"] for key, row in snapshot["request_sources"].items()},
        "required_evidence": {key: list(kinds) for key, kinds in previous.REQUIRED.items()},
        "optional_evidence": {"out_of_scope": list(OPTIONAL)},
    }
    return replace(base, json_schema=_schema(snapshot), prompt=replace(
        base.prompt, messages=(
            ChatMessage("system", previous.INSTRUCTION + "\n\n" + INSTRUCTION),
            ChatMessage("user", canonical(payload).decode()),
        ),
    ))


def _schema(snapshot: dict[str, Any]) -> dict[str, Any]:
    schema = previous._schema(snapshot)
    schema["properties"]["evidence"]["maxItems"] = 1 + len(OPTIONAL)
    return schema


def inspect_scope(
    raw: Any, inputs: dict[str, Any], *, request_sha256: str, response_sha256: str,
) -> dict[str, Any]:
    """Check the original bytes' extracted evidence. Semantics still need independent review."""
    snapshot = previous._snapshot(inputs)
    if not Draft202012Validator(_schema(snapshot)).is_valid(raw):
        raise SnapshotError("STACK_SELECTION_SCHEMA")
    if raw["selection"] != "out_of_scope":
        raise SnapshotError("STACK_SELECTION_SCOPE")
    kinds = set()
    excerpts = set()
    for item in raw["evidence"]:
        kind, key, excerpt = item["kind"], item["source_key"], item["source_excerpt"]
        if (
            kind in kinds or excerpt.strip() in excerpts or not excerpt.strip()
            or excerpt not in snapshot["request_sources"][key]["text"]
        ):
            raise SnapshotError("STACK_SELECTION_EVIDENCE")
        kinds.add(kind)
        excerpts.add(excerpt.strip())
    if "unsupported" not in kinds:
        raise SnapshotError("STACK_SELECTION_EVIDENCE")
    record = dict(
        rule=VERSION, request_sha256=request_sha256, response_sha256=response_sha256,
        original_goal=snapshot["original_goal"],
        request_sources={key: row["text"] for key, row in snapshot["request_sources"].items()},
        raw_output=raw,
    )
    return dict(**record, replay_digest=digest("stack-goal-scope-replay", record=record))


def reviewed_scope(
    raw: Any, inputs: dict[str, Any], *, request_sha256: str, response_sha256: str,
    review: dict[str, Any],
) -> dict[str, Any]:
    record = inspect_scope(
        raw, inputs, request_sha256=request_sha256, response_sha256=response_sha256,
    )
    if (
        set(review) != {"replay_digest", "verdict", "reviewer", "checks", "notes"}
        or review["replay_digest"] != record["replay_digest"]
        or review["verdict"] != "pass"
        or review["checks"] != dict.fromkeys(CHECKS, "pass")
        or not isinstance(review["reviewer"], str) or not review["reviewer"].strip()
        or not isinstance(review["notes"], str) or not review["notes"].strip()
    ):
        raise SnapshotError("STACK_REVIEW_REQUIRED")
    source = next(item["source_key"] for item in raw["evidence"] if item["kind"] == "unsupported")
    outcome = planning.validate_response(dict(
        needs_clarification=True, plan=None, questions=[previous.OUT_OF_SCOPE],
        reason="out_of_scope",
        source_keys=[source],
    ), inputs)
    return dict(**record, outcome=outcome, body_allowed=False, review=review)
