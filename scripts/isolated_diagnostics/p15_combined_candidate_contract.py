"""Offline construction for a proposed seven-role admission and one C-course batch."""

import hashlib
import json
from copy import deepcopy
from typing import Any

from scripts.isolated_diagnostics import p15_bound_pilot as bound
from scripts.isolated_diagnostics import p15_clean_pilot_prompts as prompts
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics import p15_minimal_probe_contract as roles
from scripts.isolated_diagnostics import p15_minimal_probe as probe
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    Refused,
    final_phase_validation_view,
)

VERSION = "combined-candidate-v1"
SCOPE = "PHASE-1.5-T095"
SPEC = dict(
    version="head-insertion-spec-v1",
    initial_values=[9],
    insert_values=[1, 2],
    variant="normal",
    allocation_success=[True, True],
)
RUN_ID = "candidate_combined_r01"
SLOT_ID = "synthetic_course_01"
LIMITS: dict[str, Any] = dict(
    requests=12,
    generation=8,
    review=4,
    input_reservation=98304,
    output_reservation=56896,
    per_request_input=8192,
    wall_seconds=1800,
    per_request_seconds=60,
    dns_seconds=9,
    request_bytes=65536,
    response_bytes=262144,
    fee_cap=None,
)
COURSE_ORDER = (
    "course_plan",
    "course_content",
    "course_review_0",
    "course_repair",
    "course_review_1",
)


def role_bodies() -> dict[str, bytes]:
    """Protocol echoes: v2 role instruction is *data*, not the echo's system instruction."""
    bodies = {}
    originals = roles.bodies()
    first = json.loads(json.loads(originals["S1"])["input"][1]["content"])[
        "expected_output"
    ]
    for slot in roles.ORDER:
        body = json.loads(originals[slot])
        stage = roles.STAGES[slot]
        payload = json.loads(body["input"][1]["content"])
        key = "review" if stage.startswith("review_") else stage
        payload["candidate_role_instruction_data"] = prompts.INSTRUCTIONS[key]
        if stage == "C_content":
            payload["role_input"]["plan"] = deepcopy(first)
        elif stage == "C_repair":
            payload["role_input"]["original_input"]["plan"] = deepcopy(first)
        body["input"][1]["content"] = canonical(payload).decode()
        raw = canonical(body)
        c.require(len(raw) <= LIMITS["request_bytes"], "ROLE_REQUEST_SIZE")
        bodies[slot] = raw
    return bodies


def course_wire(stage: str, payload: dict[str, Any]) -> bytes:
    request = bound.request_for(stage, payload)
    role = "review" if stage.startswith("review_") else "generation"
    route = wire.ROUTES[role]
    body = dict(
        model=route["model"],
        stream=False,
        store=False,
        reasoning=dict(effort=route["reasoning"]),
        max_output_tokens=8000,
        temperature=0.2,
        input=[dict(role=m.role, content=m.content) for m in request.prompt.messages],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_agent_pilot",
                strict=True,
                schema=deepcopy(dict(request.json_schema)),
            )
        ),
    )
    raw = canonical(body)
    c.require(len(raw) <= LIMITS["request_bytes"], "COURSE_REQUEST_SIZE")
    return raw


def observe_course(
    stage: str,
    body: bytes,
    raw: bytes,
    *,
    catalog: dict[str, Any],
    binding: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    c.require(len(raw) <= LIMITS["response_bytes"], "COURSE_RESPONSE_SIZE")
    parsed = wire.strict_json(raw)
    echo = (
        parsed.get("text", {}).get("format")
        if isinstance(parsed, dict) and isinstance(parsed.get("text"), dict)
        else None
    )
    expected = wire.strict_json(body)["text"]["format"]
    if (
        not isinstance(echo, dict)
        or echo.get("schema") != expected["schema"]
        or echo.get("type", "json_schema") != "json_schema"
        or echo.get("name", expected["name"]) != expected["name"]
        or echo.get("strict", True) is not True
    ):
        raise Refused("COURSE_SCHEMA_ECHO_MISSING_OR_MISMATCH")
    view, phase = final_phase_validation_view(raw)
    role = "review" if stage.startswith("review_") else "generation"
    result, observation = wire.validate(wire.strict_json(body), view, role)
    value = dict(result.value)
    c.validate(
        stage,
        value,
        catalog=catalog if stage.startswith("C_") else None,
        binding=binding,
    )
    if (
        observation["reported_input_tokens"] > 8192
        or observation["reported_total_output_tokens"] > 8000
    ):
        raise Refused("COURSE_REPORTED_TOKEN_BUDGET")
    return value, {
        **observation,
        "phase": phase,
        "schema_echo": "recognized",
        "source_identity_verified": False,
    }


def real_identity(
    stage: str,
    request: bytes,
    response: bytes,
    *,
    revision: int,
    parent: str | None,
    plan_receipt: str,
    review_receipt: str | None,
) -> dict[str, Any]:
    body = wire.strict_json(request)
    instruction = body["input"][0]["content"]
    ident = c.identity(RUN_ID, SLOT_ID, "C", revision, SPEC, parent)
    ident.update(
        prompt_version=prompts.PROMPT_VERSION,
        binding_version=VERSION,
        stage=stage,
        instruction_digest=hashlib.sha256(instruction.encode()).hexdigest(),
        request_digest=hashlib.sha256(request).hexdigest(),
        response_digest=hashlib.sha256(response).hexdigest(),
        plan_receipt_digest=plan_receipt,
        parent_review_receipt_digest=review_receipt,
    )
    return ident


def role_observe(name: str, body: bytes, response: bytes) -> dict[str, Any]:
    return probe.observe(name, wire.strict_json(body), response)


def response_binding(name: str, body: bytes, response: bytes) -> str:
    return digest(
        dict(
            version=VERSION,
            name=name,
            request_sha256=hashlib.sha256(body).hexdigest(),
            response_sha256=hashlib.sha256(response).hexdigest(),
        )
    )


class Workflow:
    """Derive the only allowed next request from previously validated raw responses."""

    def __init__(self) -> None:
        self.role_requests = role_bodies()
        self.catalog = c.make_catalog(SPEC)
        self.common = old.baseline_input(SPEC)
        self.index = 0
        self.stage = "roles"
        self.plan: dict[str, Any] | None = None
        self.plan_receipt: str | None = None
        self.current_input: dict[str, Any] | None = None
        self.versions: list[dict[str, Any]] = []
        self.opinions: list[dict[str, Any]] = []
        self.course_receipts: list[dict[str, Any]] = []
        self.stop_reason: str | None = None

    def next_request(self) -> tuple[str, str, bytes] | None:
        if self.stage == "roles":
            slot = roles.ORDER[self.index]
            return slot, roles.ROLES[slot], self.role_requests[slot]
        if self.stage == "course_plan":
            return (
                self.stage,
                "generation",
                course_wire("C_plan", bound.plan_input(SPEC, self.catalog)),
            )
        if self.stage == "course_content":
            assert self.current_input is not None
            return (
                self.stage,
                "generation",
                course_wire("C_content", self.current_input),
            )
        if self.stage in ("course_review_0", "course_review_1"):
            return (
                self.stage,
                "review",
                course_wire(
                    "review_C", bound.review_input(self.versions[-1], self.catalog)
                ),
            )
        if self.stage == "course_repair":
            assert self.current_input is not None
            payload = bound.repair_input(
                self.current_input, self.versions[-1], self.opinions[-1]
            )
            return self.stage, "generation", course_wire("C_repair", payload)
        return None

    def accept(self, name: str, request: bytes, response: bytes) -> dict[str, Any]:
        try:
            return self._accept(name, request, response)
        except Exception as exc:
            self.stage = "stopped"
            self.stop_reason = (
                str(exc)
                if isinstance(exc, (Refused, c.ContractError))
                else "INVALID_RESPONSE"
            )
            raise

    def _accept(self, name: str, request: bytes, response: bytes) -> dict[str, Any]:
        expected = self.next_request()
        c.require(
            expected is not None and name == expected[0] and request == expected[2],
            "NEXT_REQUEST_BINDING",
        )
        if self.stage == "roles":
            observation = role_observe(name, request, response)
            self.index += 1
            if self.index == len(roles.ORDER):
                self.stage = "course_plan"
            return observation
        if self.stage == "course_plan":
            value, observation = observe_course(
                "C_plan", request, response, catalog=self.catalog
            )
            self.plan = value
            self.plan_receipt = response_binding(name, request, response)
            self.current_input = bound.content_input(self.common, self.catalog, value)
            self.stage = "course_content"
        elif self.stage in ("course_content", "course_repair"):
            stage = "C_content" if self.stage == "course_content" else "C_repair"
            value, observation = observe_course(
                stage, request, response, catalog=self.catalog
            )
            revision = len(self.versions)
            parent = self.versions[-1]["artifact_digest"] if revision else None
            previous_review = self.course_receipts[-1]["binding"] if revision else None
            assert self.plan_receipt is not None
            ident = real_identity(
                stage,
                request,
                response,
                revision=revision,
                parent=parent,
                plan_receipt=self.plan_receipt,
                review_receipt=previous_review,
            )
            self.versions.append(c.assemble(value, ident, self.catalog))
            self.stage = f"course_review_{revision}"
        elif self.stage in ("course_review_0", "course_review_1"):
            value, observation = observe_course(
                "review_C",
                request,
                response,
                catalog=self.catalog,
                binding=c.make_binding(self.versions[-1]),
            )
            self.opinions.append(value)
            decision = c.review_disposition(value)
            if decision == "advisory_pass":
                self.stage = "pending_user_review"
            elif decision == "ordinary_revise" and self.stage == "course_review_0":
                self.stage = "course_repair"
            else:
                self.stage, self.stop_reason = "stopped", decision
        else:
            raise Refused("COURSE_ILLEGAL_STATE")
        self.course_receipts.append(
            dict(
                name=name,
                binding=response_binding(name, request, response),
                observation=observation,
            )
        )
        return observation
