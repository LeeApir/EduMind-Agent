"""One-shot control arm: structural/fault checks only, no quality claims from Mock."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from scripts.isolated_diagnostics import p15_agent_pilot as c
from scripts.isolated_diagnostics import p15_pilot_baseline as b
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example
from scripts.tests.test_p15_agent_pilot import SPEC, opinion


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No real network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def full_payload():
    # Synthetic mock only: using the engine here does not supply independent truth or model proof.
    example = build_example(SPEC)
    actions = []
    for i, s in enumerate(example["trace"]["steps"]):
        state = {k: deepcopy(s[k]) for k in ("caller_head", "local_head", "p", "nodes")}
        actions.append(
            dict(kind="show_state", anchor="slot:code", step=i, line=None, state=state)
        )
        if s["code_line"] is not None:
            actions.append(
                dict(
                    kind="highlight_code",
                    anchor="slot:code",
                    step=i,
                    line=s["code_line"],
                    state=None,
                )
            )
    return dict(
        paragraphs=[dict(key="intro", text="从调用者头沿已知next观察。")],
        code=example["code"]["source"],
        questions=[
            dict(
                key="q" + str(i),
                stem="读取" + k,
                observation_key=k,
                answer_key=example["observation"][k],
                explanation="依据准确状态。",
            )
            for i, k in enumerate(c.QUESTION_KEYS)
        ],
        actions=actions,
    )


def setup(mutator=None, **options):
    seen = []
    reviews = 0

    def handler(request):
        nonlocal reviews
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])
        role = body["stage"].removeprefix("pilot_")
        if role in ("baseline", "baseline_repair"):
            value = (
                full_payload() if role == "baseline" else deepcopy(payload["original"])
            )
            if role == "baseline_repair":
                value["paragraphs"][0]["text"] += " 明确说明返回值接回。"
        else:
            reviews += 1
            value = opinion(payload["source"])
        if mutator:
            mutator(role, payload, value, reviews)
        seen.append((role, payload, deepcopy(value)))
        return httpx.Response(
            200,
            json=dict(
                value=value,
                model_id="mock-pilot",
                usage=dict(input_tokens=10, output_tokens=20),
            ),
        )

    g = c.OfflineGateway(httpx.MockTransport(handler))
    return b.Baseline(g, g, **options), seen


def run(p):
    return asyncio.run(p.run(run_id="baseline_dev", slot_id="slot", spec=SPEC))


def test_one_shot_never_gets_engine_outputs_or_truth():
    p, seen = setup()
    result = run(p)
    assert result["state"] == "mock_advisory_pass" and result["calls"] == 2
    assert set(seen[0][1]) == {
        "spec",
        "goals",
        "question_keys",
        "code_anchor",
        "semantics",
    }
    assert seen[0][1]["semantics"] == b.SEMANTICS
    assert "p.next=head" in b.SEMANTICS
    assert seen[1][1]["reference"]["spec"] == SPEC  # Review inputs equal those for C.
    source = result["versions"][0]["payload"]
    assert source["provenance"] == dict(
        code="model", answers="model", actions="model", content="model"
    )
    assert (
        source["production_scoring"] is False and not result["independent_evaluation"]
    )


def test_ordinary_repair_whole_candidate_once():
    def mutate(role, payload, value, count):
        if role == "review" and count == 1:
            value.update(opinion(payload["source"], "revise"))

    p, seen = setup(mutate)
    result = run(p)
    assert result["calls"] == 4 and len(result["versions"]) == 2
    assert [v[0] for v in seen] == ["baseline", "review", "baseline_repair", "review"]
    assert "reference" not in seen[2][1]
    assert seen[2][1]["semantics"] == b.SEMANTICS
    assert result["versions"][0]["payload"] != result["versions"][1]["payload"]


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("missing_actions", "ROLE_SCHEMA"),
        ("answer_missing", "ROLE_SCHEMA"),
        ("anchor", "BASELINE_ACTION_REFERENCE"),
        ("dangling", "BASELINE_NODE_REFERENCE"),
        ("line", "BASELINE_ACTION_SHAPE"),
    ],
)
def test_structural_failures_stop_without_repair(fault, reason):
    def mutate(role, payload, value, count):
        if role != "baseline":
            return
        if fault == "missing_actions":
            del value["actions"]
        elif fault == "answer_missing":
            del value["questions"][0]["answer_key"]
        elif fault == "anchor":
            value["actions"][0]["anchor"] = "other"
        elif fault == "dangling":
            value["actions"][0]["state"]["nodes"]["i0"]["next"] = "t3"
        else:
            value["actions"][1]["line"] = 500

    p, seen = setup(mutate)
    result = run(p)
    assert result["reason"] == reason and len(seen) == 1


def test_error_from_review_stops_not_regenerated():
    def mutate(role, payload, value, count):
        if role == "review":
            value.update(opinion(payload["source"], "revise", "fact", "severe"))

    p, seen = setup(mutate)
    assert run(p)["reason"] == "FACT_OR_SAFETY_STOP" and len(seen) == 2


def test_budget_and_restart():
    p, seen = setup(max_calls=1)
    assert run(p)["reason"] == "BUDGET_OR_DEADLINE" and len(seen) == 1
    with pytest.raises(c.PilotError, match="SEALED_NO_RESTART"):
        run(p)
    with pytest.raises(c.PilotError, match="BASELINE_CALL_LIMIT"):
        setup(max_calls=5)


def test_unknown_review_does_not_pass():
    def mutate(role, payload, value, count):
        if role == "review":
            value.update(opinion(payload["source"], "unknown"))

    p, seen = setup(mutate)
    assert run(p)["reason"] == "REVIEW_UNKNOWN" and len(seen) == 2
