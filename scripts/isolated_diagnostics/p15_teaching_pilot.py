"""Version-bound v3 teaching pilot; Mock-only, frozen v2 untouched."""

import asyncio
import hashlib
import time
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Callable

import httpx

from app.services.provider_gateway import (
    ChatMessage,
    StructuredRequest,
    TaskProfile,
    TextRequest,
)
from scripts.isolated_diagnostics import p15_teaching_revision as prompts
from scripts.isolated_diagnostics import p15_review_engineering as compact
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    canonical,
    digest,
    validate_spec,
)

VERSION = "bound-teaching-pilot-v3"


def request_for(stage: str, payload: dict[str, Any]) -> StructuredRequest:
    c.require(stage in c.STAGES, "STAGE")
    instruction = prompts.instruction(stage)
    return StructuredRequest(
        TextRequest(
            (
                ChatMessage("system", instruction),
                ChatMessage("user", canonical(payload).decode()),
            ),
            TaskProfile.QUALITY,
            8000,
            0.2,
        ),
        c.schema_for(stage),
        stage="minimal_" + stage,
    )


def request_body(request: StructuredRequest) -> dict[str, Any]:
    return dict(
        stage=request.stage,
        messages=[asdict(m) for m in request.prompt.messages],
        schema=deepcopy(dict(request.json_schema)),
        max_output_tokens=request.prompt.max_output_tokens,
        temperature=request.prompt.temperature,
    )


def verify_receipt(
    receipt: dict[str, Any],
    stage: str,
    arm: str,
    payload: dict[str, Any],
    *,
    run_id: str,
    slot_id: str,
    ordinal: int,
    previous: str | None,
) -> dict[str, Any]:
    """Rebuild exact request from trusted role, payload and frozen v2 prompts, then parse response."""
    c.require(
        set(receipt)
        == {
            "version",
            "arm",
            "stage",
            "run_id",
            "slot_id",
            "ordinal",
            "previous_receipt_digest",
            "prompt_version",
            "request",
            "request_digest",
            "request_bytes_hex",
            "response_raw_hex",
            "response_digest",
            "receipt_digest",
        },
        "RECEIPT_SHAPE",
    )
    core = {k: v for k, v in receipt.items() if k != "receipt_digest"}
    c.require(receipt["receipt_digest"] == digest(core), "RECEIPT_DIGEST")
    c.require(
        receipt["version"] == VERSION
        and receipt["arm"] == arm
        and receipt["stage"] == stage
        and receipt["run_id"] == run_id
        and receipt["slot_id"] == slot_id
        and type(receipt["ordinal"]) is int
        and receipt["ordinal"] == ordinal
        and receipt["previous_receipt_digest"] == previous,
        "RECEIPT_SCOPE",
    )
    c.require(receipt["prompt_version"] == prompts.PROMPT_VERSION, "PROMPT_VERSION")
    expected = request_body(request_for(stage, payload))
    c.require(
        receipt["request"] == expected
        and receipt["request_digest"] == digest(expected)
        and receipt["request_bytes_hex"] == canonical(expected).hex(),
        "REQUEST_BINDING",
    )
    raw = bytes.fromhex(receipt["response_raw_hex"])
    c.require(
        receipt["response_digest"] == hashlib.sha256(raw).hexdigest(),
        "RESPONSE_BINDING",
    )
    envelope = c.strict_json(raw)
    c.require(
        set(envelope) == {"model_id", "value", "usage"}
        and envelope["model_id"] == "mock-minimal",
        "MOCK_ENVELOPE",
    )
    usage = envelope["usage"]
    c.require(
        type(usage) is dict and set(usage) == {"input_tokens", "output_tokens"}, "USAGE"
    )
    c.integer(usage["input_tokens"], 0, 32768)
    c.integer(usage["output_tokens"], 0, 8000)
    c.require(type(envelope["value"]) is dict, "OBJECT_REQUIRED")
    return dict(envelope["value"])


def identity(
    run_id: str,
    slot_id: str,
    arm: str,
    revision: int,
    spec: Any,
    parent: str | None,
    receipt: dict[str, Any],
    plan_receipt: str | None,
    review_receipt: str | None,
) -> dict[str, Any]:
    result = c.identity(run_id, slot_id, arm, revision, spec, parent)
    result.update(
        prompt_version=prompts.PROMPT_VERSION,
        binding_version=VERSION,
        stage=receipt["stage"],
        instruction_digest=hashlib.sha256(
            receipt["request"]["messages"][0]["content"].encode("utf-8")
        ).hexdigest(),
        request_digest=receipt["request_digest"],
        response_digest=receipt["response_digest"],
        receipt_digest=receipt["receipt_digest"],
        plan_receipt_digest=plan_receipt,
        parent_review_receipt_digest=review_receipt,
    )
    return result


def plan_input(spec: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    return dict(
        spec_id=catalog["spec_id"],
        spec=spec,
        goals=list(c.GOALS),
        question_definitions=old.QUESTION_DEFINITIONS,
    )


def content_input(
    common: dict[str, Any], catalog: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    return dict(
        original_goal=common["goals"],
        plan=deepcopy(plan),
        example=catalog["example"],
        fact_catalog=catalog["facts"],
        catalog_digest=catalog["catalog_digest"],
        question_definitions=old.QUESTION_DEFINITIONS,
    )


def review_input(candidate: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Keep full artifact/reference; compact only reconstructible target metadata."""
    return compact.compact_payload(candidate, catalog)[0]


def repair_input(
    original_input: dict[str, Any], candidate: dict[str, Any], opinion: dict[str, Any]
) -> dict[str, Any]:
    return dict(
        original_input=original_input,
        original=candidate["raw_output"],
        issues=opinion["issues"],
        immutable_question_types=list(c.QUESTION_KEYS),
        previous_candidate_digest=candidate["artifact_digest"],
    )


def verify_events(result: dict[str, Any], arm: str) -> None:
    """Verify sequence, hash chain and event/receipt/versions correspondence."""
    receipts = iter(result["receipts"])
    expected: list[tuple[str, dict[str, Any]]] = []

    def exchange() -> None:
        try:
            receipt = next(receipts)
        except StopIteration as exc:
            raise c.ContractError("EVENT_RECEIPT_MISSING") from exc
        expected.append(
            (
                "dispatch",
                dict(
                    stage=receipt["stage"],
                    request=receipt["request"],
                    prompt_version=receipt["prompt_version"],
                    request_digest=receipt["request_digest"],
                ),
            )
        )
        expected.append(("response", dict(receipt=receipt)))

    if arm == "C":
        exchange()
    exchange()
    versions, opinions = result["versions"], result["opinions"]
    c.require(
        len(versions) in (1, 2) and len(versions) == len(opinions),
        "EVENT_VERSION_COUNT",
    )
    for index, (candidate, opinion) in enumerate(zip(versions, opinions)):
        if index:
            if arm == "B":
                expected.append(("feedback_review", result["feedback_attestation"]))
            exchange()
        expected.append(("candidate", candidate))
        exchange()
        expected.append(("review", opinion))
    expected.append(("terminal", {"state": "mock_advisory_pass"}))
    c.require(next(receipts, None) is None, "EVENT_EXTRA_RECEIPT")
    events = result["events"]
    c.require(type(events) is list and len(events) == len(expected), "EVENT_COUNT")
    previous = None
    for sequence, (row, (kind, payload)) in enumerate(zip(events, expected)):
        c.require(
            type(row) is dict
            and set(row)
            == {"sequence", "kind", "payload", "previous_digest", "event_digest"},
            "EVENT_SHAPE",
        )
        core = {k: v for k, v in row.items() if k != "event_digest"}
        c.require(
            type(row["sequence"]) is int
            and row["sequence"] == sequence
            and row["kind"] == kind
            and row["payload"] == payload
            and row["previous_digest"] == previous
            and row["event_digest"] == digest(core),
            "EVENT_BINDING",
        )
        previous = digest(row)


def verify_complete(
    result: dict[str, Any], *, run_id: str, slot_id: str, arm: str, spec: Any
) -> None:
    """Independently reconstruct every request, response, candidate, review and parent link."""
    spec = validate_spec(spec)
    c.require(
        arm in ("B", "C") and result["state"] == "mock_advisory_pass", "RESULT_SCOPE"
    )
    c.require(
        result.get("independent_evaluation") is False
        and result.get("production_scoring") is False
        and type(result.get("real_provider_calls")) is int
        and result["real_provider_calls"] == 0,
        "RESULT_FLAGS",
    )
    receipts = iter(result["receipts"])
    previous_receipt = None
    ordinal = 0

    def consume(
        stage: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal previous_receipt, ordinal
        try:
            receipt = next(receipts)
        except StopIteration as exc:
            raise c.ContractError("RECEIPT_MISSING") from exc
        value = verify_receipt(
            receipt,
            stage,
            arm,
            payload,
            run_id=run_id,
            slot_id=slot_id,
            ordinal=ordinal,
            previous=previous_receipt,
        )
        previous_receipt = receipt["receipt_digest"]
        ordinal += 1
        return receipt, value

    common = old.baseline_input(spec)
    catalog = c.make_catalog(spec)
    plan_digest = None
    if arm == "C":
        plan, value = consume("C_plan", plan_input(spec, catalog))
        c.validate("C_plan", value, catalog=catalog)
        plan_digest = plan["receipt_digest"]
        initial_input = content_input(common, catalog, value)
    else:
        initial_input = common
    current_input = initial_input
    prior = None
    previous_review = None
    versions = result["versions"]
    opinions = result["opinions"]
    c.require(
        len(versions) in (1, 2) and len(opinions) == len(versions), "VERSION_COUNT"
    )
    for revision, (candidate, opinion) in enumerate(zip(versions, opinions)):
        stage = arm + (
            "_repair" if revision else ("_content" if arm == "C" else "_generate")
        )
        receipt, value = consume(stage, current_input)
        c.validate(stage, value, catalog=catalog if arm == "C" else None)
        ident = identity(
            run_id,
            slot_id,
            arm,
            revision,
            spec,
            prior["artifact_digest"] if prior else None,
            receipt,
            plan_digest,
            previous_review["receipt_digest"] if previous_review else None,
        )
        rebuilt = c.assemble(value, ident, catalog if arm == "C" else None)
        c.require(candidate == rebuilt, "CANDIDATE_BINDING")
        review, value = consume("review_" + arm, review_input(candidate, catalog))
        c.validate("review_" + arm, value, binding=c.make_binding(candidate))
        c.require(value == opinion, "OPINION_BINDING")
        disposition = c.review_disposition(value)
        if revision + 1 < len(versions):
            c.require(
                revision == 0 and disposition == "ordinary_revise", "REPAIR_PERMISSION"
            )
            if arm == "B":
                attestation = result.get("feedback_attestation")
                c.require(
                    type(attestation) is dict
                    and set(attestation)
                    == {
                        "candidate_digest",
                        "review_receipt_digest",
                        "issues_digest",
                        "reviewer",
                        "approved",
                    }
                    and attestation["candidate_digest"] == candidate["artifact_digest"]
                    and attestation["review_receipt_digest"] == review["receipt_digest"]
                    and attestation["issues_digest"] == digest(value["issues"])
                    and type(attestation["reviewer"]) is str
                    and bool(attestation["reviewer"])
                    and attestation["approved"] is True,
                    "B_FEEDBACK_ATTESTATION",
                )
            current_input = repair_input(initial_input, candidate, value)
        else:
            c.require(disposition == "advisory_pass", "FINAL_REVIEW")
        prior, previous_review = candidate, review
    c.require(
        next(receipts, None) is None and result["calls"] == len(result["receipts"]),
        "RECEIPT_COUNT",
    )
    c.require(
        (arm == "B" and len(versions) == 2)
        or result.get("feedback_attestation") is None,
        "EXTRANEOUS_ATTESTATION",
    )
    verify_events(result, arm)


class MockGateway:
    """Capture exact HTTP bytes, with networking limited to httpx.MockTransport."""

    def __init__(self, transport: httpx.MockTransport):
        c.require(type(transport) is httpx.MockTransport, "MOCK_TRANSPORT_REQUIRED")
        self.transport = transport
        self.audit: list[dict[str, Any]] = []

    async def generate(
        self, request: StructuredRequest
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        body = request_body(request)
        sent = canonical(body)
        row: dict[str, Any] = dict(
            request=deepcopy(body),
            request_digest=hashlib.sha256(sent).hexdigest(),
            request_bytes_hex=sent.hex(),
        )
        self.audit.append(row)
        async with httpx.AsyncClient(
            transport=self.transport, trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                "https://offline-minimal-pilot.invalid/mock", content=sent
            )
        row.update(
            status=response.status_code,
            response_raw_hex=response.content.hex(),
            response_digest=hashlib.sha256(response.content).hexdigest(),
        )
        c.require(response.status_code == 200, "MOCK_HTTP_STATUS")
        envelope = c.strict_json(response.content)
        c.require(
            set(envelope) == {"model_id", "value", "usage"}
            and envelope["model_id"] == "mock-minimal",
            "MOCK_ENVELOPE",
        )
        c.require(type(envelope["value"]) is dict, "OBJECT_REQUIRED")
        return dict(envelope["value"]), row


class Pilot:
    """Only supports exact MockGateway; preserves old stop, deadline and budget policy."""

    def __init__(
        self,
        generation: MockGateway,
        review: MockGateway,
        *,
        arm: str,
        seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
        feedback_guard: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
        feedback_reviewer: str = "",
    ):
        c.require(
            type(generation) is MockGateway and type(review) is MockGateway,
            "MOCK_GATEWAY_REQUIRED",
        )
        c.require(arm in ("B", "C"), "ARM")
        c.require(type(seconds) in (int, float) and 0 < seconds <= 1800, "DEADLINE")
        self.generation, self.review, self.arm = generation, review, arm
        self.clock, self.seconds = clock, seconds
        self.started = False
        self._active = False
        self.deadline = 0.0
        self.calls = 0
        self.limit = 4 if arm == "B" else 5
        self._events: list[dict[str, Any]] = []
        self.receipts: list[dict[str, Any]] = []
        self.run_id = ""
        self.slot_id = ""
        self.feedback_guard = feedback_guard
        self.feedback_reviewer = feedback_reviewer
        self.feedback_attestation: dict[str, Any] | None = None

    @property
    def events(self) -> list[dict[str, Any]]:
        return deepcopy(self._events)

    def record(self, kind: str, payload: dict[str, Any]) -> None:
        row = dict(
            sequence=len(self._events),
            kind=kind,
            payload=deepcopy(payload),
            previous_digest=digest(self._events[-1]) if self._events else None,
        )
        row["event_digest"] = digest(row)
        self._events.append(row)

    async def call(
        self,
        stage: str,
        payload: dict[str, Any],
        *,
        catalog: dict[str, Any] | None = None,
        binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        c.require(
            self._active and self.calls < self.limit and self.clock() < self.deadline,
            "BUDGET_OR_DEADLINE",
        )
        c.require(len(canonical(payload)) <= c.MAX_PAYLOAD, "INPUT_SIZE")
        if stage.startswith("review_"):
            c.require(binding is not None, "BINDING_REQUIRED")
            assert binding is not None
            review_catalog = c.make_catalog(payload["reference"]["spec"])
            review_wire, rebuilt_binding = prompts.review_body(
                binding["artifact"], review_catalog
            )
            c.require(rebuilt_binding == binding, "REVIEW_BINDING")
            c.require(
                wire.strict_json(wire.strict_json(review_wire)["input"][1]["content"])
                == payload,
                "REVIEW_REQUEST_BINDING",
            )
        request = request_for(stage, payload)
        expected = request_body(request)
        gateway = self.review if stage.startswith("review_") else self.generation
        self.calls += 1
        self.record(
            "dispatch",
            dict(
                stage=stage,
                request=expected,
                prompt_version=prompts.PROMPT_VERSION,
                request_digest=digest(expected),
            ),
        )
        try:
            result, row = await asyncio.wait_for(
                gateway.generate(request), self.deadline - self.clock()
            )
        except BaseException:
            self.record("unknown", dict(stage=stage, attempt=self.calls))
            raise
        c.require(self.clock() < self.deadline, "DEADLINE_AFTER_RESPONSE")
        c.require(
            row["request"] == expected and row["request_digest"] == digest(expected),
            "ACTUAL_REQUEST_BINDING",
        )
        receipt = dict(
            version=VERSION,
            arm=self.arm,
            stage=stage,
            run_id=self.run_id,
            slot_id=self.slot_id,
            ordinal=len(self.receipts),
            previous_receipt_digest=self.receipts[-1]["receipt_digest"]
            if self.receipts
            else None,
            prompt_version=prompts.PROMPT_VERSION,
            request=deepcopy(row["request"]),
            request_digest=row["request_digest"],
            request_bytes_hex=row["request_bytes_hex"],
            response_raw_hex=row["response_raw_hex"],
            response_digest=row["response_digest"],
        )
        receipt["receipt_digest"] = digest(receipt)
        value = verify_receipt(
            receipt,
            stage,
            self.arm,
            payload,
            run_id=self.run_id,
            slot_id=self.slot_id,
            ordinal=len(self.receipts),
            previous=self.receipts[-1]["receipt_digest"] if self.receipts else None,
        )
        c.require(value == result, "ACTUAL_RESPONSE_BINDING")
        c.validate(stage, value, catalog=catalog, binding=binding)
        self.receipts.append(receipt)
        self.record("response", dict(receipt=receipt))
        return value

    async def run(
        self, *, run_id: str, slot_id: str, spec: Any, question: str | None = None
    ) -> dict[str, Any]:
        c.require(not self.started, "SEALED_NO_RESTART")
        self.started = True
        self._active = True
        self.deadline = self.clock() + self.seconds
        versions: list[dict[str, Any]] = []
        opinions: list[dict[str, Any]] = []
        try:
            spec = validate_spec(spec)
            c.identity(run_id, slot_id, self.arm, 0, spec, None)
            self.run_id, self.slot_id = run_id, slot_id
            c.require(
                question is None or question in c.QUESTION_KEYS, "unsupported_question"
            )
            common = old.baseline_input(spec)
            plan_digest = None
            if self.arm == "C":
                catalog = c.make_catalog(spec)
                plan = await self.call(
                    "C_plan", plan_input(spec, catalog), catalog=catalog
                )
                plan_digest = self.receipts[-1]["receipt_digest"]
                original_input = content_input(common, catalog, plan)
                value = await self.call("C_content", original_input, catalog=catalog)
            else:
                original_input = common
                value = await self.call("B_generate", original_input)
                catalog = c.make_catalog(spec)
            previous_review = None
            for revision in range(2):
                parent = versions[-1]["artifact_digest"] if versions else None
                ident = identity(
                    run_id,
                    slot_id,
                    self.arm,
                    revision,
                    spec,
                    parent,
                    self.receipts[-1],
                    plan_digest,
                    previous_review,
                )
                candidate = c.assemble(
                    value, ident, catalog if self.arm == "C" else None
                )
                versions.append(deepcopy(candidate))
                self.record("candidate", candidate)
                opinion = await self.call(
                    "review_" + self.arm,
                    review_input(candidate, catalog),
                    binding=c.make_binding(candidate),
                )
                previous_review = self.receipts[-1]["receipt_digest"]
                opinions.append(deepcopy(opinion))
                self.record("review", opinion)
                decision = c.review_disposition(opinion)
                if decision == "advisory_pass":
                    result = dict(
                        state="mock_advisory_pass",
                        versions=versions,
                        opinions=opinions,
                        calls=self.calls,
                        events=self.events,
                        receipts=deepcopy(self.receipts),
                        feedback_attestation=deepcopy(self.feedback_attestation),
                        independent_evaluation=False,
                        production_scoring=False,
                        real_provider_calls=0,
                    )
                    terminal = dict(
                        sequence=len(self._events),
                        kind="terminal",
                        payload={"state": "mock_advisory_pass"},
                        previous_digest=digest(self._events[-1])
                        if self._events
                        else None,
                    )
                    terminal["event_digest"] = digest(terminal)
                    result["events"] = [*self.events, terminal]
                    verify_complete(
                        result, run_id=run_id, slot_id=slot_id, arm=self.arm, spec=spec
                    )
                    self.record("terminal", dict(state="mock_advisory_pass"))
                    c.require(result["events"] == self.events, "EVENT_COMMIT")
                    return result
                c.require(decision == "ordinary_revise", decision)
                c.require(revision == 0, "REPAIR_EXHAUSTED")
                if self.arm == "B":
                    c.require(
                        self.feedback_guard is not None
                        and bool(self.feedback_reviewer),
                        "B_FEEDBACK_REVIEW_REQUIRED",
                    )
                    assert self.feedback_guard is not None
                    c.require(
                        self.feedback_guard(deepcopy(candidate), deepcopy(opinion))
                        is True,
                        "B_FEEDBACK_REVIEW_REJECTED",
                    )
                    self.feedback_attestation = dict(
                        candidate_digest=candidate["artifact_digest"],
                        review_receipt_digest=previous_review,
                        issues_digest=digest(opinion["issues"]),
                        reviewer=self.feedback_reviewer,
                        approved=True,
                    )
                    self.record("feedback_review", self.feedback_attestation)
                value = await self.call(
                    self.arm + "_repair",
                    repair_input(original_input, candidate, opinion),
                    catalog=catalog if self.arm == "C" else None,
                )
            raise c.ContractError("UNREACHABLE")
        except asyncio.CancelledError:
            self.record("terminal", dict(state="cancelled"))
            raise
        except Exception as exc:
            code = (
                str(exc)
                if isinstance(exc, (c.ContractError, ValueError))
                else type(exc).__name__
            )
            self.record("terminal", dict(state="stopped", reason=code))
            return dict(
                state="stopped",
                reason=code,
                versions=versions,
                opinions=opinions,
                calls=self.calls,
                events=self.events,
                receipts=deepcopy(self.receipts),
                generation_audit=deepcopy(self.generation.audit),
                review_audit=deepcopy(self.review.audit),
                independent_evaluation=False,
                production_scoring=False,
                real_provider_calls=0,
            )
        finally:
            self._active = False
