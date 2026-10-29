"""Offline synthetic role/course transitions; never sends to a provider."""

import json
import socket
from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_combined_candidate_contract as cc
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_probe_contract as roles
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_minimal_pilot import content, ordinary


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def response(body, value):
    request = json.loads(body)
    review = request["model"] == "gpt-6.1-sol"
    return canonical(
        dict(
            model=request["model"],
            status="completed",
            store=False,
            error=None,
            reasoning=request["reasoning"],
            text=dict(format=request["text"]["format"]),
            usage=dict(
                input_tokens=100,
                output_tokens=60,
                total_tokens=160,
                output_tokens_details=dict(reasoning_tokens=5 if review else 0),
            ),
            output=[
                dict(
                    id="synthetic",
                    type="message",
                    role="assistant",
                    status="completed",
                    phase="final_answer",
                    content=[
                        dict(
                            type="output_text",
                            text=json.dumps(value, ensure_ascii=False),
                        )
                    ],
                )
            ],
        )
    )


def value_for(workflow, name, body, repair=False):
    request = json.loads(body)
    payload = json.loads(request["input"][1]["content"])
    if name.startswith("S"):
        return payload["expected_output"]
    if name == "course_plan":
        return dict(spec_id=payload["spec_id"], objective_ids=list(c.GOALS))
    if name == "course_content":
        return content()
    if name == "course_repair":
        item = deepcopy(payload["original"])
        item["paragraphs"][0]["text"] += " 解释调用者接回返回值。"
        return item
    output = dict(
        candidate_id=payload["candidate_id"], verdict="pass", uncertainty="", issues=[]
    )
    if repair and name == "course_review_0":
        ordinary(payload, output)
    return output


def advance(workflow, repair=False):
    name, _, body = workflow.next_request()
    output = value_for(workflow, name, body, repair)
    workflow.accept(name, body, response(body, output))
    return name, body


@pytest.mark.parametrize("repair", [False, True])
def test_seven_roles_then_one_complete_course_pending_user_review(repair):
    w = cc.Workflow()
    sent = []
    while w.next_request() is not None:
        sent.append(advance(w, repair)[0])
    assert sent == list(roles.ORDER) + (
        [
            "course_plan",
            "course_content",
            "course_review_0",
            "course_repair",
            "course_review_1",
        ]
        if repair
        else ["course_plan", "course_content", "course_review_0"]
    )
    assert w.stage == "pending_user_review"
    assert len(w.versions) == len(w.opinions) == (2 if repair else 1)
    assert w.versions[0]["identity"]["prompt_version"] == cc.prompts.PROMPT_VERSION
    if repair:
        assert (
            w.versions[1]["identity"]["parent_digest"]
            == w.versions[0]["artifact_digest"]
        )
        assert (
            w.versions[1]["identity"]["parent_review_receipt_digest"]
            == w.course_receipts[2]["binding"]
        )


@pytest.mark.parametrize("failure_slot", range(7))
def test_each_role_protocol_failure_is_terminal(failure_slot):
    w = cc.Workflow()
    for _ in range(failure_slot):
        advance(w)
    name, _, body = w.next_request()
    bad = json.loads(response(body, value_for(w, name, body)))
    bad["output"][0]["content"][0]["text"] = "{}"
    with pytest.raises(Exception):
        w.accept(name, body, canonical(bad))
    assert w.stage == "stopped" and w.next_request() is None
    assert not w.versions


def test_wrong_dynamic_request_fails_closed():
    w = cc.Workflow()
    for _ in range(7):
        advance(w)
    name, _, body = w.next_request()
    with pytest.raises(c.ContractError):
        w.accept(name, body + b" ", response(body, value_for(w, name, body)))
    assert w.next_request() is None


@pytest.mark.parametrize("outcome", ["unknown", "severe", "fact"])
def test_course_review_nonordinary_stops_without_repair(outcome):
    w = cc.Workflow()
    for _ in range(9):
        advance(w)
    name, _, body = w.next_request()
    value = value_for(w, name, body)
    payload = json.loads(json.loads(body)["input"][1]["content"])
    if outcome == "unknown":
        value.update(verdict="unknown", uncertainty="insufficient context")
    else:
        ordinary(
            payload,
            value,
            severity="severe" if outcome == "severe" else "minor",
            area="fact" if outcome == "fact" else "difficulty",
        )
    w.accept(name, body, response(body, value))
    assert w.stage == "stopped" and w.next_request() is None


def test_missing_schema_echo_stops_course():
    w = cc.Workflow()
    for _ in range(7):
        advance(w)
    name, _, body = w.next_request()
    bad = json.loads(response(body, value_for(w, name, body)))
    del bad["text"]
    with pytest.raises(cc.Refused, match="COURSE_SCHEMA_ECHO"):
        w.accept(name, body, canonical(bad))
    assert w.next_request() is None
