"""Exercise actual v2 Mock requests, version links and independent replay guards."""

import asyncio
from copy import deepcopy
import json
import socket

import pytest

from scripts.isolated_diagnostics import p15_teaching_pilot as p
from scripts.isolated_diagnostics import p15_teaching_revision as prompts
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest
from scripts.tests.test_p15_minimal_pilot import SPEC, ordinary, setup


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("real network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def run_case(arm, repair=False):
    def mutate(stage, payload, envelope, reviews):
        if repair and stage.startswith("review_") and reviews == 1:
            ordinary(payload, envelope["value"])

    legacy, seen = setup(arm, mutate)
    gateway = p.MockGateway(legacy.generation.transport)
    pilot = p.Pilot(
        gateway,
        gateway,
        arm=arm,
        feedback_guard=lambda candidate, opinion: all(
            i["reason"] == "Clarify the pedagogical wording only."
            for i in opinion["issues"]
        ),
        feedback_reviewer="mock-fixture-review",
    )
    result = asyncio.run(pilot.run(run_id="dev", slot_id="slot", spec=SPEC))
    assert result["state"] == "mock_advisory_pass", result
    return result, seen


def verify(result, arm):
    p.verify_complete(result, run_id="dev", slot_id="slot", arm=arm, spec=SPEC)


def reseal(receipt):
    receipt["request_digest"] = digest(receipt["request"])
    receipt["request_bytes_hex"] = p.canonical(receipt["request"]).hex()
    receipt["receipt_digest"] = digest(
        {k: v for k, v in receipt.items() if k != "receipt_digest"}
    )


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize("repair", [False, True])
def test_actual_full_workflow_uses_clean_instruction_and_preserves_parent(arm, repair):
    result, seen = run_case(arm, repair)
    verify(result, arm)
    assert result["calls"] == (2 if arm == "B" else 3) + 2 * repair
    for row, receipt in zip(seen, result["receipts"]):
        stage = row["stage"]
        assert row["request"] == receipt["request"]
        assert row["request"]["messages"][0]["content"] == prompts.instruction(stage)
        assert json.loads(row["request"]["messages"][1]["content"]) == row["payload"]
        assert receipt["prompt_version"] == prompts.PROMPT_VERSION
    for revision, artifact in enumerate(result["versions"]):
        ident = artifact["identity"]
        stage = arm + (
            "_repair" if revision else ("_content" if arm == "C" else "_generate")
        )
        receipt = next(row for row in result["receipts"] if row["stage"] == stage)
        assert ident["prompt_version"] == prompts.PROMPT_VERSION
        assert ident["request_digest"] == receipt["request_digest"]
        assert ident["response_digest"] == receipt["response_digest"]
        assert ident["receipt_digest"] == receipt["receipt_digest"]
    if repair:
        first, second = result["versions"]
        assert second["identity"]["parent_digest"] == first["artifact_digest"]
        assert (
            second["identity"]["parent_review_receipt_digest"]
            == next(
                row for row in result["receipts"] if row["stage"].startswith("review_")
            )["receipt_digest"]
        )
    if arm == "B":
        for row in seen:
            if row["stage"].startswith("B_"):
                allowed = (
                    row["payload"]["original_input"]
                    if row["stage"] == "B_repair"
                    else row["payload"]
                )
                assert set(allowed) == set(p.old.baseline_input(SPEC))
                assert "fact_catalog" not in allowed and "reference" not in allowed


@pytest.mark.parametrize("arm", ["B", "C"])
def test_version_request_and_response_tampering_rejected_even_when_rehashed(arm):
    result, _ = run_case(arm)
    stage = arm + ("_content" if arm == "C" else "_generate")
    index = next(i for i, row in enumerate(result["receipts"]) if row["stage"] == stage)
    for mutation in ("version", "system", "payload", "response"):
        changed = deepcopy(result)
        receipt = changed["receipts"][index]
        if mutation == "version":
            receipt["prompt_version"] = "minimal-pilot-prompt-v1"
        elif mutation == "system":
            receipt["request"]["messages"][0]["content"] += " changed"
        elif mutation == "payload":
            receipt["request"]["messages"][1]["content"] = "{}"
        else:
            receipt["response_raw_hex"] += "20"
        reseal(receipt)
        with pytest.raises(c.ContractError):
            verify(changed, arm)


@pytest.mark.parametrize("arm", ["B", "C"])
def test_stale_review_wrong_parent_and_cross_arm_material_rejected(arm):
    result, _ = run_case(arm, True)
    review_indices = [
        i
        for i, row in enumerate(result["receipts"])
        if row["stage"].startswith("review_")
    ]
    repair_index = next(
        i for i, row in enumerate(result["receipts"]) if row["stage"].endswith("repair")
    )
    changed = deepcopy(result)
    changed["receipts"][review_indices[1]] = deepcopy(
        changed["receipts"][review_indices[0]]
    )
    with pytest.raises(c.ContractError):
        verify(changed, arm)
    changed = deepcopy(result)
    payload = json.loads(
        changed["receipts"][repair_index]["request"]["messages"][1]["content"]
    )
    payload["previous_candidate_digest"] = "0" * 64
    changed["receipts"][repair_index]["request"]["messages"][1]["content"] = (
        p.canonical(payload).decode()
    )
    reseal(changed["receipts"][repair_index])
    with pytest.raises(c.ContractError):
        verify(changed, arm)
    changed = deepcopy(result)
    changed["receipts"][repair_index]["arm"] = "C" if arm == "B" else "B"
    reseal(changed["receipts"][repair_index])
    with pytest.raises(c.ContractError):
        verify(changed, arm)


def test_cross_arm_review_and_candidate_are_not_interchangeable():
    b, _ = run_case("B")
    c_result, _ = run_case("C")
    b["versions"][0] = deepcopy(c_result["versions"][0])
    with pytest.raises(c.ContractError):
        verify(b, "B")


@pytest.mark.parametrize(
    "field",
    [
        "prompt_version",
        "instruction_digest",
        "request_digest",
        "response_digest",
        "parent_digest",
        "parent_review_receipt_digest",
    ],
)
def test_rehashed_artifact_cannot_forge_identity_links(field):
    result, _ = run_case("C", True)
    artifact = result["versions"][1]
    artifact["identity"][field] = "0" * 64
    artifact["artifact_digest"] = digest(
        {k: v for k, v in artifact.items() if k != "artifact_digest"}
    )
    with pytest.raises(c.ContractError, match="CANDIDATE_BINDING"):
        verify(result, "C")


def test_rehashed_receipt_from_different_run_is_rejected():
    result, _ = run_case("B")
    receipt = result["receipts"][0]
    receipt["run_id"] = "different_run"
    reseal(receipt)
    with pytest.raises(c.ContractError, match="RECEIPT_SCOPE"):
        verify(result, "B")


@pytest.mark.parametrize("outcome", ["unknown", "severe", "fact", "repeat"])
def test_nonordinary_or_second_review_never_creates_an_extra_repair(outcome):
    def mutate(stage, payload, envelope, reviews):
        if not stage.startswith("review_"):
            return
        value = envelope["value"]
        if outcome == "unknown":
            value.update(verdict="unknown", uncertainty="insufficient context")
        elif outcome == "severe":
            ordinary(payload, value, severity="severe")
        elif outcome == "fact":
            ordinary(payload, value, area="fact")
        else:
            ordinary(payload, value)

    legacy, seen = setup("B", mutate)
    gateway = p.MockGateway(legacy.generation.transport)
    result = asyncio.run(
        p.Pilot(
            gateway,
            gateway,
            arm="B",
            feedback_guard=lambda candidate, opinion: all(
                i["reason"] == "Clarify the pedagogical wording only."
                for i in opinion["issues"]
            ),
            feedback_reviewer="mock-fixture-review",
        ).run(run_id="dev", slot_id="slot", spec=SPEC)
    )
    assert result["state"] == "stopped"
    assert sum(row["stage"] == "B_repair" for row in seen) == (
        1 if outcome == "repeat" else 0
    )


@pytest.mark.parametrize("arm", ["B", "C"])
def test_replacing_repair_response_with_prior_response_and_rehashing_is_rejected(arm):
    result, _ = run_case(arm, True)
    first_stage = arm + ("_content" if arm == "C" else "_generate")
    first = next(row for row in result["receipts"] if row["stage"] == first_stage)
    repair = next(row for row in result["receipts"] if row["stage"] == arm + "_repair")
    repair["response_raw_hex"] = first["response_raw_hex"]
    repair["response_digest"] = first["response_digest"]
    reseal(repair)
    with pytest.raises(c.ContractError):
        verify(result, arm)


def test_mock_transport_is_required():
    import httpx

    with pytest.raises(c.ContractError, match="MOCK_TRANSPORT_REQUIRED"):
        p.MockGateway(httpx.AsyncHTTPTransport())


def test_b_feedback_that_contains_answer_stops_before_repair():
    def mutate(stage, payload, envelope, reviews):
        if stage == "review_B" and reviews == 1:
            ordinary(payload, envelope["value"])
            envelope["value"]["issues"][0]["reason"] = "The correct caller head is t0."

    legacy, seen = setup("B", mutate)
    gateway = p.MockGateway(legacy.generation.transport)
    # No adjudicator configured: even a mechanically ordinary opinion cannot be sent on.
    result = asyncio.run(
        p.Pilot(gateway, gateway, arm="B").run(run_id="dev", slot_id="slot", spec=SPEC)
    )
    assert result["state"] == "stopped"
    assert result["reason"] == "B_FEEDBACK_REVIEW_REQUIRED"
    assert [row["stage"] for row in seen] == ["B_generate", "review_B"]


@pytest.mark.parametrize(
    "change", ["events", "independent", "production", "real_calls"]
)
def test_missing_events_and_false_qualification_claims_rejected(change):
    result, _ = run_case("B", True)
    if change == "events":
        result["events"] = []
    elif change == "independent":
        result["independent_evaluation"] = True
    elif change == "production":
        result["production_scoring"] = True
    else:
        result["real_provider_calls"] = 999
    with pytest.raises(c.ContractError):
        verify(result, "B")


def test_c_plan_is_in_exact_content_request():
    _, seen = run_case("C")
    plan = next(row for row in seen if row["stage"] == "C_plan")["envelope"]["value"]
    content = next(row for row in seen if row["stage"] == "C_content")["payload"]
    assert content["plan"] == plan
