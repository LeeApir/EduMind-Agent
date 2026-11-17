"""Whole-flow Mock regressions. Synthesized Mock responses are not model capability evidence."""

import asyncio
from copy import deepcopy
import json
import socket

import httpx
import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as p
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_example,
    build_actions,
    canonical,
    digest,
)
from scripts.tests.test_p15_minimal_contract import SPEC


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No DNS/network in Mock regressions")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def content():
    return dict(
        paragraphs=[
            dict(
                key="intro",
                text="区分调用者头、局部头和可知值前缀；循环或未知next不代表有限完整输出。",
                fact_ids=["obs_caller_head", "obs_reachable_prefix"],
            )
        ],
        questions={
            key: dict(
                stem=p.QUESTION_DEFINITIONS[key],
                explanation="依据固定模板区分观察范围。",
                fact_ids=["obs_" + key],
            )
            for key in c.QUESTION_KEYS
        },
    )


def b_fixture(spec):
    # Test reply factory intentionally uses the engine. This is NOT a baseline model or independent truth.
    example = build_example(spec)
    groups = dict(states=[], highlights=[], advances=[])
    for order, event in enumerate(build_actions(example, "slot:code")):
        step = event["step"]
        if event["kind"] == "show_state":
            groups["states"].append(
                dict(
                    order=order,
                    step=step,
                    **c.encode_state(example["trace"]["steps"][step]),
                )
            )
        elif event["kind"] == "highlight_code":
            groups["highlights"].append(
                dict(order=order, step=step, line=event["line"])
            )
        else:
            groups["advances"].append(dict(order=order, step=step))
    answers = {key: deepcopy(example["observation"][key]) for key in c.QUESTION_KEYS}
    if answers["caller_head"] is None:
        answers["caller_head"] = "none"
    return dict(
        paragraphs=[
            dict(key="intro", text="从调用者头观察可知前缀，区分未知指针与终止。")
        ],
        code=example["code"]["source"],
        questions={
            key: dict(
                stem=p.QUESTION_DEFINITIONS[key], explanation="核对固定模板对应观察。"
            )
            for key in c.QUESTION_KEYS
        },
        answers=answers,
        actions=groups,
    )


def setup(arm="C", mutate=None, **options):
    seen = []
    reviews = 0

    def handler(request):
        nonlocal reviews
        body = json.loads(request.content)
        stage = body["stage"].removeprefix("minimal_")
        payload = json.loads(body["messages"][1]["content"])
        if stage == "C_plan":
            value = dict(spec_id=payload["spec_id"], objective_ids=list(c.GOALS))
        elif stage == "C_content":
            value = content()
        elif stage == "B_generate":
            value = b_fixture(payload["spec"])
        elif stage.endswith("repair"):
            value = deepcopy(payload["original"])
            value["paragraphs"][0]["text"] += " 补充区分调用者返回值接回。"
        else:
            reviews += 1
            value = dict(
                candidate_id=payload["candidate_id"],
                verdict="pass",
                uncertainty="",
                issues=[],
            )
        envelope = dict(
            model_id="mock-minimal",
            value=value,
            usage=dict(input_tokens=10, output_tokens=20),
        )
        if mutate:
            mutate(stage, payload, envelope, reviews)
        seen.append(
            dict(
                stage=stage,
                payload=deepcopy(payload),
                envelope=deepcopy(envelope),
                request=body,
            )
        )
        return httpx.Response(200, content=canonical(envelope))

    gateway = p.MockGateway(httpx.MockTransport(handler))
    return p.Pilot(gateway, gateway, arm=arm, **options), seen


def run(pilot, spec=None, **extra):
    return asyncio.run(
        pilot.run(run_id="dev", slot_id="slot", spec=spec or SPEC, **extra)
    )


def ordinary(payload, value, *, area="difficulty", severity="minor"):
    target, row = next(
        (k, v)
        for k, v in payload["target_catalog"].items()
        if v["path"] == "/raw_output/paragraphs/0/text"
    )
    value.update(
        verdict="revise",
        issues=[
            dict(
                severity=severity,
                area=area,
                target_id=target,
                evidence_quote=row["text"],
                reason="Clarify the pedagogical wording only.",
            )
        ],
    )


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
@pytest.mark.parametrize(
    "mask", [[True, True], [False, True], [True, False], [False, False]]
)
def test_complete_mock_chain_all_variants_and_allocation_masks(arm, variant, mask):
    pilot, seen = setup(arm)
    spec = dict(
        SPEC,
        initial_values=[0],
        insert_values=[-4, 0],
        variant=variant,
        allocation_success=mask,
    )
    result = run(pilot, spec)
    assert result["state"] == "mock_advisory_pass", result.get("reason")
    assert result["calls"] == (2 if arm == "B" else 3)
    assert result["independent_evaluation"] is False
    assert result["production_scoring"] is False
    source = result["versions"][0]["source"]
    assert len([b for b in source["blocks"] if b["kind"] == "question"]) == 4
    assert source["actions"]
    assert seen[-1]["payload"]["artifact"] == result["versions"][0]
    assert seen[-1]["payload"]["reference"]["spec"] == spec
    assert "fact_catalog" not in seen[0]["payload"] if arm == "B" else True
    for event in result["events"]:
        copy = deepcopy(event)
        assert copy.pop("event_digest") == digest(copy)
    for a, b in zip(result["events"], result["events"][1:]):
        assert b["previous_digest"] == digest(a)
    with pytest.raises(c.ContractError, match="SEALED_NO_RESTART"):
        run(pilot)
    with pytest.raises(c.ContractError, match="BUDGET_OR_DEADLINE"):
        asyncio.run(pilot.call("C_plan", {}))


@pytest.mark.parametrize("arm", ["B", "C"])
def test_once_ordinary_repair_new_version_binding_and_originals(arm):
    def mutate(stage, payload, envelope, n):
        if stage.startswith("review_") and n == 1:
            ordinary(payload, envelope["value"])

    pilot, seen = setup(arm, mutate)
    result = run(pilot)
    assert result["state"] == "mock_advisory_pass"
    assert result["calls"] == (4 if arm == "B" else 5)
    first, second = result["versions"]
    assert (
        first["raw_output"]["paragraphs"][0]["text"]
        != second["raw_output"]["paragraphs"][0]["text"]
    )
    assert second["identity"]["parent_digest"] == first["artifact_digest"]
    assert second["identity"]["revision"] == 1
    reviews = [r for r in seen if r["stage"].startswith("review_")]
    assert (
        reviews[0]["payload"]["candidate_id"] != reviews[1]["payload"]["candidate_id"]
    )
    repair = next(r for r in seen if r["stage"].endswith("repair"))["payload"]
    if arm == "B":
        assert set(repair["original_input"]) == set(p.baseline_input(SPEC))
        assert "reference" not in repair and "fact_catalog" not in repair
    else:
        assert first["source"]["resolved_facts"] == second["source"]["resolved_facts"]


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "decision", ["unknown", "fact", "code_safety", "severe", "exhausted"]
)
def test_stop_opinions_do_not_trigger_unauthorized_repairs(arm, decision):
    def mutate(stage, payload, envelope, n):
        if not stage.startswith("review_"):
            return
        v = envelope["value"]
        if decision == "unknown":
            v.update(verdict="unknown", uncertainty="Insufficient evidence.")
        else:
            ordinary(
                payload,
                v,
                area=decision if decision in ("fact", "code_safety") else "difficulty",
                severity="severe" if decision == "severe" else "minor",
            )

    pilot, seen = setup(arm, mutate)
    result = run(pilot)
    assert result["state"] == "stopped"
    assert result["calls"] == (
        (4 if arm == "B" else 5)
        if decision == "exhausted"
        else (2 if arm == "B" else 3)
    )
    assert len([r for r in seen if r["stage"].endswith("repair")]) == (
        1 if decision == "exhausted" else 0
    )


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "bad", ["missing", "extra", "foreign_id", "bad_usage", "bad_model"]
)
def test_structure_protocol_and_membership_errors_stop_without_format_repair(arm, bad):
    def mutate(stage, payload, envelope, n):
        if stage not in ("B_generate", "C_content"):
            return
        if bad == "missing":
            envelope["value"].pop("questions")
        elif bad == "extra":
            envelope["value"]["unexpected"] = "value"
        elif bad == "foreign_id":
            if arm == "C":
                envelope["value"]["paragraphs"][0]["fact_ids"] = ["foreign"]
            else:
                envelope["value"]["actions"]["states"][0]["caller_head"] = "t3"
        elif bad == "bad_usage":
            envelope["usage"]["output_tokens"] = None
        else:
            envelope["model_id"] = "foreign-model"

    pilot, seen = setup(arm, mutate)
    result = run(pilot)
    assert result["state"] == "stopped"
    assert result["calls"] == (1 if arm == "B" else 2)
    assert not any(r["stage"].endswith("repair") for r in seen)


@pytest.mark.parametrize("arm", ["B", "C"])
def test_stale_review_candidate_after_repair_rejected(arm):
    first = None

    def mutate(stage, payload, envelope, n):
        nonlocal first
        if stage.startswith("review_"):
            if n == 1:
                first = payload["candidate_id"]
                ordinary(payload, envelope["value"])
            else:
                envelope["value"]["candidate_id"] = first

    pilot, _ = setup(arm, mutate)
    result = run(pilot)
    assert result["state"] == "stopped"
    assert result["reason"] == "CANDIDATE_ID"


def test_b_generation_and_repair_input_excludes_reference_by_allowlist():
    raw = p.baseline_input(SPEC)
    assert set(raw) == {
        "spec",
        "semantics",
        "goals",
        "question_definitions",
        "node_id_conventions",
    }
    for name in [
        "expected_answers",
        "fact_catalog",
        "reference",
        "independent_truth",
        "example",
        "engine_actions",
    ]:
        assert name not in raw


def test_b_wrong_answer_preserved_through_review_not_repaired_by_program():
    def mutate(stage, payload, envelope, n):
        if stage == "B_generate":
            envelope["value"]["answers"]["caller_head"] = "none"

    pilot, seen = setup("B", mutate)
    result = run(pilot)
    assert (
        result["state"] == "mock_advisory_pass"
    )  # A deliberately blind Mock reviewer is not truth.
    candidate = result["versions"][0]
    assert candidate["raw_output"]["answers"]["caller_head"] == "none"
    assert (
        next(
            b
            for b in candidate["source"]["blocks"]
            if b.get("observation_key") == "caller_head"
        )["answer_key"]
        is None
    )
    assert seen[-1]["payload"]["reference"]["observation"]["caller_head"] == "t0"
    assert result["independent_evaluation"] is False


def test_correct_ids_wrong_prose_still_reaches_full_reviewer():
    bad = "A successful insertion leaves the caller head empty."

    def mutate(stage, payload, envelope, n):
        if stage == "C_content":
            envelope["value"]["paragraphs"][0]["text"] = bad

    pilot, seen = setup("C", mutate)
    result = run(pilot)
    assert result["state"] == "mock_advisory_pass"
    assert seen[-1]["payload"]["artifact"]["raw_output"]["paragraphs"][0]["text"] == bad
    assert any(bad in t["text"] for t in seen[-1]["payload"]["target_catalog"].values())
    assert result["independent_evaluation"] is False


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "case", ["variant", "length", "arbitrary_code", "unknown_question"]
)
def test_all_refusal_categories_are_local_zero_call(arm, case):
    pilot, seen = setup(arm)
    spec = deepcopy(SPEC)
    extra = {}
    if case == "variant":
        spec["variant"] = "unknown"
    elif case == "length":
        spec["insert_values"] = [1] * 5
    elif case == "arbitrary_code":
        spec["code"] = "arbitrary C"
    else:
        extra["question"] = "exact_full_traversal"
    result = run(pilot, spec, **extra)
    assert result["state"] == "stopped"
    assert result["calls"] == 0 and seen == []


def test_deadline_before_dispatch_and_late_response_stop():
    values = iter([0.0, 100.0])
    pilot, seen = setup("B", clock=lambda: next(values))
    result = run(pilot)
    assert result["calls"] == 0 and seen == []
    clock = [0.0]

    def mutate(stage, payload, envelope, n):
        clock[0] = 100.0

    pilot, seen = setup("B", mutate, clock=lambda: clock[0])
    result = run(pilot)
    assert result["reason"] == "DEADLINE_AFTER_RESPONSE"
    assert result["calls"] == 1
    assert result["versions"] == []


def test_unknown_transport_does_not_retry_and_seals():
    def handler(request):
        raise httpx.ReadTimeout("synthetic unknown")

    g = p.MockGateway(httpx.MockTransport(handler))
    pilot = p.Pilot(g, g, arm="B")
    result = run(pilot)
    assert result["state"] == "stopped" and result["calls"] == 1
    assert len(g.audit) == 1
    assert any(e["kind"] == "unknown" for e in result["events"])
    with pytest.raises(c.ContractError):
        run(pilot)


def test_nonmock_transport_and_gateway_refused_before_io():
    with pytest.raises(c.ContractError, match="MOCK_TRANSPORT_REQUIRED"):
        p.MockGateway(object())
    with pytest.raises(c.ContractError, match="MOCK_GATEWAY_REQUIRED"):
        p.Pilot(object(), object(), arm="C")


def test_all_seven_synthetic_wire_bodies_use_exact_approved_schemas_and_caps():
    bodies = p.protocol_bodies()
    plan = json.loads((c.DESIGN / "compatibility-plan.json").read_text())
    assert len(bodies) == 7
    assert sum(json.loads(raw)["max_output_tokens"] for raw in bodies.values()) == 16896
    for slot in plan["requests"]:
        body = json.loads(bodies[slot["slot"]])
        assert body["text"]["format"]["schema"] == c.schema_for(slot["stage"])
        assert body["text"]["format"]["strict"] is True
        assert body["model"] == slot["model"]
        assert body["reasoning"]["effort"] == slot["reasoning"]
        assert body["store"] is False and body["stream"] is False
        assert len(bodies[slot["slot"]]) <= 65536
        assert "expected_output" in json.loads(body["input"][1]["content"])


def test_teaching_standard_is_unchanged_and_explicitly_reused():
    standard = (
        c.ROOT
        / "docs/acceptance/phase-1.5-sol-compatibility-plan-r01/scene-review-prompt.txt"
    ).read_text()
    assert p.INSTRUCTIONS["review"].startswith(standard)
    assert p.INSTRUCTIONS["B_generate"].startswith(p.old_b.INSTRUCTION)


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
def test_maximum_supported_spec_still_fits_complete_review_without_omissions(
    arm, variant
):
    spec = dict(
        SPEC,
        initial_values=[-99, 0, 99],
        insert_values=[-99, 0, 99, 0],
        allocation_success=[True] * 4,
        variant=variant,
    )
    pilot, seen = setup(arm)
    result = run(pilot, spec)
    assert result["state"] == "mock_advisory_pass", result.get("reason")
    review = seen[-1]["payload"]
    assert len(canonical(review)) <= c.MAX_PAYLOAD
    assert review["artifact"] == result["versions"][0]
    assert review["reference"]["spec"] == spec
    actions = review["artifact"]["source"]["actions"]
    targets = list(review["target_catalog"].values())
    for i, event in enumerate(actions):
        assert any(
            t["path"] == f"/source/actions/{i}"
            and t["text"] == canonical(event).decode()
            for t in targets
        )


def test_seven_protocol_cases_use_real_local_binding_and_repair_wrappers():
    catalog = c.make_catalog(SPEC)
    plan = json.loads((c.DESIGN / "compatibility-plan.json").read_text())
    bodies = p.protocol_bodies()
    for slot in plan["requests"]:
        stage = slot["stage"]
        payload = json.loads(json.loads(bodies[slot["slot"]])["input"][1]["content"])
        role_input = payload["role_input"]
        if stage.startswith("review_"):
            binding = c.make_binding(role_input["artifact"])
            assert binding["targets"] == role_input["target_catalog"]
            c.validate(stage, payload["expected_output"], binding=binding)
            assert payload["expected_output"]["verdict"] == "unknown"
        else:
            c.validate(
                stage,
                payload["expected_output"],
                catalog=catalog if stage.startswith("C_") else None,
            )
        if stage.endswith("repair"):
            assert {
                "original_input",
                "original",
                "issues",
                "previous_candidate_digest",
            } <= set(role_input)
        if stage.startswith("B_"):
            b_input = (
                role_input["original_input"] if stage.endswith("repair") else role_input
            )
            assert set(b_input) == set(p.baseline_input(SPEC))
            assert "fact_catalog" not in b_input


def test_cancelled_inflight_mock_is_unknown_and_sealed_without_resend():
    async def scenario():
        entered = asyncio.Event()

        async def handler(request):
            entered.set()
            await asyncio.Event().wait()

        g = p.MockGateway(httpx.MockTransport(handler))
        pilot = p.Pilot(g, g, arm="B")
        task = asyncio.create_task(pilot.run(run_id="dev", slot_id="slot", spec=SPEC))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(g.audit) == 1
        assert any(e["kind"] == "unknown" for e in pilot.events)
        assert pilot.events[-1]["payload"]["state"] == "cancelled"
        with pytest.raises(c.ContractError, match="BUDGET_OR_DEADLINE"):
            await pilot.call("B_generate", p.baseline_input(SPEC))

    asyncio.run(scenario())
