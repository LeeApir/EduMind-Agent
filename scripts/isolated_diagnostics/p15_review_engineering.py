"""Offline isolated review adapter; historical batches and provider calls remain untouched."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.isolated_diagnostics import p15_bound_pilot as bound
from scripts.isolated_diagnostics import p15_clean_pilot_prompts as prompts
from scripts.isolated_diagnostics import p15_combined_candidate_runner as old_runner
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    final_phase_validation_view,
)


@dataclass(frozen=True)
class ReviewPolicy:
    request_bytes: int = 65536
    input_tokens: int = 32768
    output_tokens: int = 8000
    response_bytes: int = 65536
    encrypted_reasoning_chars: int = 8192


POLICY = ReviewPolicy()
VERSION = "isolated-review-engineering-v1"


def compact_payload(
    artifact: dict[str, Any], catalog: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep the full artifact/reference and every quoteable target path and text."""
    old = bound.review_input(artifact, catalog)
    targets = old["target_catalog"]
    compact = {
        key: {"path": row["path"], "text": row["text"]} for key, row in targets.items()
    }
    old["target_catalog"] = compact
    return old, c.make_binding(artifact)


def build_review(
    artifact: dict[str, Any], catalog: dict[str, Any], policy: ReviewPolicy = POLICY
) -> tuple[bytes, dict[str, Any]]:
    payload, binding = compact_payload(artifact, catalog)
    body = dict(
        model=wire.ROUTES["review"]["model"],
        stream=False,
        store=False,
        reasoning=dict(effort=wire.ROUTES["review"]["reasoning"]),
        max_output_tokens=policy.output_tokens,
        temperature=0.2,
        input=[
            dict(role="system", content=prompts.INSTRUCTIONS["review"]),
            dict(role="user", content=canonical(payload).decode()),
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_agent_pilot",
                strict=True,
                schema=c.schema_for("review_C"),
            )
        ),
    )
    raw = canonical(body)
    c.require(len(raw) <= policy.request_bytes, "REVIEW_REQUEST_SIZE")
    return raw, binding


def observe_review(
    body: bytes, raw: bytes, binding: dict[str, Any], policy: ReviewPolicy = POLICY
) -> tuple[dict[str, Any], dict[str, Any]]:
    c.require(
        len(body) <= policy.request_bytes and len(raw) <= policy.response_bytes,
        "REVIEW_BYTE_BOUND",
    )
    request = wire.strict_json(body)
    c.require(
        request.get("max_output_tokens") == policy.output_tokens,
        "OUTPUT_RESERVATION_MISMATCH",
    )
    original = wire.strict_json(raw)
    fmt = (
        original.get("text", {}).get("format")
        if isinstance(original.get("text"), dict)
        else None
    )
    expected = request["text"]["format"]
    c.require(
        isinstance(fmt, dict)
        and fmt.get("schema") == expected["schema"]
        and fmt.get("type", "json_schema") == "json_schema"
        and fmt.get("name", expected["name"]) == expected["name"]
        and fmt.get("strict", True) is True,
        "SCHEMA_ECHO",
    )
    normalized, phase = final_phase_validation_view(raw)
    view = wire.strict_json(normalized)
    quarantined = False
    for item in view.get("output", []):
        if (
            isinstance(item, dict)
            and item.get("type") == "reasoning"
            and item.get("encrypted_content") not in (None, "")
        ):
            value = item["encrypted_content"]
            c.require(
                type(value) is str
                and 1 <= len(value) <= policy.encrypted_reasoning_chars,
                "ENCRYPTED_REASONING_BOUND",
            )
            item["encrypted_content"] = None
            quarantined = True
    result, observation = wire.validate(request, canonical(view), "review")
    value = dict(result.value)
    c.validate("review_C", value, binding=binding)
    c.require(
        observation["reported_input_tokens"] <= policy.input_tokens
        and observation["reported_total_output_tokens"] <= policy.output_tokens,
        "REVIEW_TOKEN_BOUND",
    )
    return value, {
        **observation,
        "phase": phase,
        "encrypted_content_quarantined": quarantined,
        "original_preserved": True,
        "semantic_pass": False,
    }


def stopped_summary(
    output: Path, package: str, grant: dict[str, Any]
) -> dict[str, Any]:
    """Replay a stopped batch without constructing or sending any next request."""
    events = [
        wire.strict_json(f.read_bytes()) for f in sorted(output.glob("event-*.json"))
    ]
    state, workflow = old_runner.replay(events, output, package, grant)
    c.require(
        not output.is_symlink()
        and all(not file.is_symlink() and file.is_file() for file in output.iterdir()),
        "RESULT_FILE_SAFETY",
    )
    allowed = {"grant.json", "summary.json"} | {
        f"event-{i:03}.json" for i in range(len(events))
    }
    allowed |= {f"{name}-request.json" for name in state["reserved"]}
    allowed |= {
        f"{name}-{suffix}"
        for name in state["sent"]
        for suffix in ("status.json", "response.bin")
    }
    c.require(
        all(file.name in allowed for file in output.iterdir()), "UNBOUND_RESULT_FILE"
    )
    for name in state["observed"]:
        c.require(
            (output / f"{name}-response.bin").is_file()
            and (output / f"{name}-status.json").is_file(),
            "OBSERVED_FILE_MISSING",
        )
    c.require(
        state["phase"] == "terminal" and events[-1]["data"]["outcome"] == "stopped",
        "NOT_STOPPED",
    )
    return dict(
        outcome="stopped",
        terminal=deepcopy(events[-1]["data"]),
        reserved=state["reserved"],
        sent=state["sent"],
        observed=state["observed"],
        validated=state["validated"],
        unknown_sent=len(state["sent"]) - len(state["validated"]),
        workflow_stage_at_stop=workflow.stage,
        versions=len(workflow.versions),
        opinions=len(workflow.opinions),
        teaching_evaluated=False,
        resumed=False,
    )


class ReviewAttempt:
    """One offline request/response binding; never initiates a provider request."""

    def __init__(
        self,
        artifact: dict[str, Any],
        catalog: dict[str, Any],
        policy: ReviewPolicy = POLICY,
    ):
        c.require(
            type(policy) is ReviewPolicy
            and all(
                type(v) is int and v > 0
                for v in (
                    policy.request_bytes,
                    policy.input_tokens,
                    policy.output_tokens,
                    policy.response_bytes,
                    policy.encrypted_reasoning_chars,
                )
            ),
            "POLICY_INVALID",
        )
        c.require(
            policy.response_bytes <= 65536 and policy.output_tokens <= 8000,
            "UNDERLYING_WIRE_LIMIT",
        )
        self.policy = policy
        self.request, self.binding = build_review(artifact, catalog, policy)
        self.reservation = dict(
            input_tokens=policy.input_tokens,
            output_tokens=policy.output_tokens,
            request_bytes=policy.request_bytes,
            response_bytes=policy.response_bytes,
        )
        self.closed = False

    def observe(self, response: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
        c.require(not self.closed, "ATTEMPT_CLOSED")
        self.closed = True
        return observe_review(self.request, response, self.binding, self.policy)
