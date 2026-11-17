"""Offline measurement of the complete proposed Responses request.

This is development instrumentation, not a provider grant, tokenizer, or an
upstream limit.  It never creates a transport or reads credentials.
"""

from dataclasses import dataclass
import hashlib
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as contract
from scripts.isolated_diagnostics import p15_bounded_json_v1 as bounded
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_teaching_revision as prompts
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

VERSION = "visible-request-budget-v1-development"
REVIEW_PROMPT_VERSION = "visible-review-instruction-v1"


def instruction(stage: str) -> tuple[str, str]:
    original = prompts.instruction(stage)
    if not stage.startswith("review_"):
        return original, prompts.PROMPT_VERSION
    old = "its target_id from the supplied target_catalog for this artifact, copy a nonempty\nexact evidence_quote substring from that target's canonical text"
    new = "its target_id from the id field of an actually supplied cells item, copy a nonempty\nexact evidence_quote substring from that same item's text field"
    contract.require(original.count(old) == 1, "REVIEW_INSTRUCTION_SOURCE")
    original = original.replace(old, new)
    old_source = "including raw natural language and rendered\nsource"
    contract.require(original.count(old_source) == 1, "REVIEW_INSTRUCTION_SOURCE")
    original = original.replace(
        old_source, "including directly visible original natural language and\nsource"
    )
    contract.require("target_catalog" not in original, "REVIEW_INSTRUCTION_SOURCE")
    return original, REVIEW_PROMPT_VERSION


@dataclass(frozen=True)
class DevelopmentPolicy:
    request_bytes: int
    input_reservation: int
    output_reservation: int
    allowance: int = 8192

    def __post_init__(self) -> None:
        contract.require(
            all(
                type(x) is int and x > 0
                for x in (
                    self.request_bytes,
                    self.input_reservation,
                    self.output_reservation,
                    self.allowance,
                )
            ),
            "BUDGET_POLICY",
        )


def build(
    stage: str, user_payload: dict[str, Any], policy: DevelopmentPolicy
) -> tuple[bytes, dict[str, Any]]:
    """Serialize final outer request before applying both independent local gates."""
    contract.require(
        stage in contract.STAGES and type(user_payload) is dict, "REQUEST_INPUT"
    )
    role = "review" if stage.startswith("review_") else "generation"
    route = wire.ROUTES[role]
    instruction_text, prompt_version = instruction(stage)
    schema = contract.schema_for(stage)
    user_content = bounded.encode(
        user_payload, policy.request_bytes, "REQUEST_BYTES_LIMIT"
    ).decode("utf-8")
    body = {
        "model": route["model"],
        "stream": False,
        "store": False,
        "reasoning": {"effort": route["reasoning"]},
        "max_output_tokens": policy.output_reservation,
        "temperature": 0.2,
        "input": [
            {"role": "system", "content": instruction_text},
            {"role": "user", "content": user_content},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "edumind_agent_pilot",
                "strict": True,
                "schema": schema,
            }
        },
    }
    request = bounded.encode(body, policy.request_bytes, "REQUEST_BYTES_LIMIT")
    # This heuristic intentionally does not assert a token upper bound. Its
    # policy and provider usage must be evaluated for each authorized package.
    estimated = len(request) + policy.allowance
    contract.require(len(request) <= policy.request_bytes, "REQUEST_BYTES_LIMIT")
    contract.require(
        estimated <= policy.input_reservation, "LOCAL_INPUT_RESERVATION_LIMIT"
    )
    return request, {
        "version": VERSION,
        "stage": stage,
        "body_sha256": hashlib.sha256(request).hexdigest(),
        "body_bytes": len(request),
        "user_json_bytes": len(user_content.encode("utf-8")),
        "system_utf8_bytes": len(instruction_text.encode("utf-8")),
        "prompt_version": prompt_version,
        "schema_json_bytes": len(canonical(schema)),
        "local_input_reservation": estimated,
        "local_output_reservation": policy.output_reservation,
        "token_estimate_is_provider_bound": False,
    }
