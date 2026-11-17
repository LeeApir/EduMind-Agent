"""Isolated dual-route orchestration, private journal and failure containment tests."""

import asyncio
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from isolated_diagnostics import p15_split_provider as p  # noqa: E402
from app.agents.free_course_planning import SCHEMA as PLAN_SCHEMA  # noqa: E402
from app.agents.review_schema import review_output_schema  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("No DNS, socket or real credentials in unit tests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    original = Path.open

    def safe_open(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", safe_open)


def json_reply(request, value):
    body = p.parse(request.content)
    return httpx.Response(
        200,
        json={
            "object": "response",
            "model": body["model"],
            "status": "completed",
            "store": False,
            "instructions": "\n\n".join(
                m["content"] for m in body["input"] if m["role"] == "system"
            ),
            "max_output_tokens": body["max_output_tokens"],
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 100, "total_tokens": 200},
        },
    )


def scene_target(identity, sid="s1"):
    return {
        "identity": identity.packed(),
        "scene_id": sid,
        "course_version_id": "v1",
        "course_digest": "test",
        "plan_id": "p1",
        "plan_digest": "test",
        "payload": p.design.review_source(
            original_goal="合成目标",
            plan_constraints={"learner_evidence": {}},
            scene={"id": sid, "text": "栈后进先出", "answer_key": "C"},
            upstream=[],
        ),
    }


def clean_opinion(source):
    return {
        "source_sha256": source["source_sha256"],
        "scope_status": "complete",
        "uncertain_reason": None,
        "verdict": "pass",
        "issues": [],
    }


@pytest.fixture
def setup(tmp_path):
    j = p.Journal.create_mock(tmp_path / "wire")
    identity = p.Identity("D01", "TEST_ONLY_OWNER", "TEST_ONLY_COURSE")
    j.bind(identity)
    try:
        yield j, identity
    finally:
        j.ledger.close()


def router(j, review_handler=None, generation_handler=None):
    return p.Router(
        j,
        {
            "generation": httpx.MockTransport(
                generation_handler or (lambda r: json_reply(r, {}))
            ),
            "review": httpx.MockTransport(
                review_handler
                or (
                    lambda r: json_reply(
                        r,
                        clean_opinion(
                            p.parse(p.parse(r.content)["input"][-1]["content"])
                        ),
                    )
                )
            ),
        },
        {"generation": "TEST_ONLY_DEEPSEEK_KEY", "review": "TEST_ONLY_AIAPI_KEY"},
    )


async def current(_):
    return True


def test_mock_only_router_cannot_become_real_by_boolean_or_credentials(setup):
    j, identity = setup
    r = router(j)
    assert r.bound(identity).policy.bounded_output_verified is False
    with pytest.raises(p.Refused, match="UNVERIFIED"):
        r.bound(identity).input_upper_bound(None)
    with pytest.raises(p.Refused, match="NO_LIVE_AUTHORITY"):
        p.refuse_live()
    with pytest.raises(p.Refused, match="EXPLICIT_DISTINCT"):
        p.Router(
            j,
            {
                "generation": httpx.AsyncHTTPTransport(),
                "review": httpx.MockTransport(lambda r: None),
            },
            r.keys,
        )
    with pytest.raises(p.Refused, match="EXPLICIT_DISTINCT"):
        p.Router(
            j,
            r.transports,
            {"generation": "a-real-looking-key", "review": "a-different-key"},
        )
    with pytest.raises(p.Refused, match="EXPLICIT_DISTINCT"):
        p.Router(
            j,
            r.transports,
            {"generation": "TEST_ONLY_SAME", "review": "TEST_ONLY_SAME"},
        )


def test_source_binding_private_answer_and_exactly_once_review(setup):
    j, identity = setup
    calls = []

    def review(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer TEST_ONLY_AIAPI_KEY"
        assert request.headers["host"] == "aiapi.world"
        assert request.extensions["sni_hostname"] == "aiapi.world"
        source = p.parse(p.parse(request.content)["input"][-1]["content"])
        assert source["source"]["scene"]["answer_key"] == "C"
        return json_reply(request, clean_opinion(source))

    r = router(j, review_handler=review)
    j.freeze(identity, [scene_target(identity)])
    assert (
        asyncio.run(p.review_pending(r, identity, verify_current=current))
        == "mock_reviews_complete"
    )
    assert (
        asyncio.run(p.review_pending(r, identity, verify_current=current))
        == "mock_reviews_complete"
    )
    assert len(calls) == 1
    assert len(j.events("scene_review_finished")) == 1
    for file in j.output.glob("*.json"):
        raw = file.read_bytes()
        assert (
            b"TEST_ONLY_AIAPI_KEY" not in raw and b"TEST_ONLY_DEEPSEEK_KEY" not in raw
        )


@pytest.mark.parametrize(
    "bad",
    [
        "quote",
        "binding",
        "pointer",
        "malformed",
        "overflow",
        "model",
        "timeout",
        "key_echo",
        "role_injection",
        "bad_total",
    ],
)
def test_bad_review_halts_without_retry_or_cross_provider_fallback(setup, bad):
    j, identity = setup
    calls = []

    def review(request):
        calls.append(request)
        source = p.parse(p.parse(request.content)["input"][-1]["content"])
        value = clean_opinion(source)
        if bad in ("quote", "pointer"):
            value.update(
                verdict="reject",
                issues=[
                    {
                        "area": "fact",
                        "severity": "severe",
                        "message": "test",
                        "source_pointer": "/scene/text"
                        if bad == "quote"
                        else "/scene/missing",
                        "evidence_quote": "NOT_IN_SOURCE",
                    }
                ],
            )
        if bad == "binding":
            value["source_sha256"] = "0" * 64
        if bad == "malformed":
            value = {}
        if bad == "timeout":
            raise httpx.ReadTimeout("synthetic")
        response = json_reply(request, value)
        data = json.loads(response.content)
        if bad == "overflow":
            data["usage"] = {
                "input_tokens": 100,
                "output_tokens": 8001,
                "total_tokens": 8101,
            }
        if bad == "bad_total":
            data["usage"]["total_tokens"] = 999
        if bad == "model":
            data["model"] = "other"
        if bad == "key_echo":
            data["instructions"] = "TEST_ONLY_AIAPI_KEY"
        if bad == "role_injection":
            data["instructions"] = "You are a coding assistant."
        return httpx.Response(200, json=data)

    def never(_):
        pytest.fail("Review cannot fall back to generation provider")

    r = router(j, review_handler=review, generation_handler=never)
    j.freeze(identity, [scene_target(identity)])
    with pytest.raises(Exception):
        asyncio.run(p.review_pending(r, identity, verify_current=current))
    with pytest.raises(p.Refused):
        asyncio.run(p.review_pending(r, identity, verify_current=current))
    assert len(calls) == 1
    assert j.ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"


def test_changed_current_source_stops_before_review_dispatch(setup):
    j, identity = setup
    r = router(j, review_handler=lambda _: pytest.fail("No outbound for stale source"))
    j.freeze(identity, [scene_target(identity)])

    async def changed(_):
        return False

    with pytest.raises(p.Refused, match="SOURCE_NO_LONGER_CURRENT"):
        asyncio.run(p.review_pending(r, identity, verify_current=changed))
    assert not j.events("mock_dispatch_reserved")


def test_interrupted_review_cannot_be_resent_after_reopen(setup):
    j, identity = setup
    target = scene_target(identity)
    j.freeze(identity, [target])
    j.record(
        "scene_review_started",
        {
            "source_sha256": target["payload"]["source_sha256"],
            "identity": identity.packed(),
        },
    )
    with pytest.raises(p.Refused, match="INTERRUPTED_REVIEW"):
        asyncio.run(p.review_pending(router(j), identity, verify_current=current))
    assert not j.events("mock_dispatch_reserved")


def test_nonpass_pauses_until_exact_manual_false_alarm_and_preserves_opinion(setup):
    j, identity = setup
    calls = []

    def reject(request):
        calls.append(request)
        source = p.parse(p.parse(request.content)["input"][-1]["content"])
        v = clean_opinion(source)
        v.update(
            verdict="reject",
            issues=[
                {
                    "area": "fact",
                    "severity": "major",
                    "message": "synthetic false alarm",
                    "source_pointer": "/scene/text",
                    "evidence_quote": "后进先出",
                }
            ],
        )
        return json_reply(request, v)

    r = router(j, review_handler=reject)
    targets = [scene_target(identity), scene_target(identity, "s2")]
    j.freeze(identity, targets)
    assert (
        asyncio.run(p.review_pending(r, identity, verify_current=current))
        == "paused_for_human"
    )
    with pytest.raises(p.Refused, match="REQUIRES_HUMAN"):
        j.guard()
    row = j.events("scene_review_finished")[0]
    report = {
        "source_sha256": row["source_sha256"],
        "opinion_sha256": p.digest(row["opinion"]),
        "decision": "false_alarm",
        "reviewer": "TEST_ONLY_HUMAN",
        "reviewed_at": "fixture",
        "evidence_ref": "fixture",
        "reason": "fixture adjudication",
    }
    with pytest.raises(p.Refused):
        j.adjudicate_false_alarm(
            identity, row["source_sha256"], {**report, "opinion_sha256": "0" * 64}
        )
    j.adjudicate_false_alarm(identity, row["source_sha256"], report)
    j.guard()
    assert j.events("scene_review_finished")[0]["opinion"]["verdict"] == "reject"
    assert len(calls) == 1  # Adjudication never sends or automatically resumes.
    r.transports["review"] = httpx.MockTransport(
        lambda req: json_reply(
            req, clean_opinion(p.parse(p.parse(req.content)["input"][-1]["content"]))
        )
    )
    asyncio.run(p.review_pending(r, identity, verify_current=current))
    assert len(j.events("mock_dispatch_reserved")) == 2
    assert len(j.events("scene_review_finished")) == 2


def test_wrong_owner_and_same_scene_source_cannot_borrow_review_or_adjudication(setup):
    j, identity = setup
    with pytest.raises(p.Refused):
        j.bind(p.Identity(identity.slot_id, "OTHER_OWNER", identity.course_id))
    target = scene_target(identity)
    j.freeze(identity, [target])
    asyncio.run(p.review_pending(router(j), identity, verify_current=current))
    other = p.Identity("OTHER_SLOT", "OTHER_OWNER", "OTHER_COURSE")
    j.bind(other)
    clone = deepcopy(target)
    clone["identity"] = other.packed()
    j.freeze(other, [clone])
    with pytest.raises(p.Refused, match="PENDING"):
        j.require_reviews_complete(other)
    assert j.review_checkpoint(identity) != j.review_checkpoint(other)


def test_unknown_stage_wrong_schema_and_retry_refuse_before_call(setup):
    j, identity = setup
    r = router(j)
    for stage, schema, retry in [
        ("unknown", PLAN_SCHEMA, False),
        ("free_course_plan_generation", {}, False),
        ("free_course_plan_generation", PLAN_SCHEMA, True),
    ]:
        request = p.StructuredRequest(
            p.TextRequest(
                (p.ChatMessage("user", "synthetic"),), max_output_tokens=8000
            ),
            schema,
            stage,
        )
        with pytest.raises(p.Refused):
            asyncio.run(r.send(identity, request, retry_safe=retry))
    assert not j.events("mock_dispatch_reserved")


def test_pending_transport_reservation_prevents_any_new_send(setup):
    j, identity = setup
    j.ledger.reserve(
        j.batch,
        j.package,
        "interrupted",
        input_max=32000,
        output_max=8000,
        fee_max=200000,
    )
    request = p.StructuredRequest(
        p.TextRequest((p.ChatMessage("user", "synthetic"),), max_output_tokens=8000),
        dict(review_output_schema()),
        "development_review_probe",
    )
    with pytest.raises(p.Refused, match="INTERRUPTED"):
        asyncio.run(router(j).send(identity, request, retry_safe=False))
    assert not j.events("mock_dispatch_reserved")


@pytest.mark.parametrize("decision", ["confirmed_severe", "unresolved"])
def test_human_severe_or_unresolved_stops_without_generating_new_opinion(
    setup, decision
):
    j, identity = setup

    def reject(req):
        source = p.parse(p.parse(req.content)["input"][-1]["content"])
        out = clean_opinion(source)
        out.update(
            verdict="reject",
            issues=[
                {
                    "area": "fact",
                    "severity": "severe",
                    "message": "fixture",
                    "source_pointer": "/scene/text",
                    "evidence_quote": "后进先出",
                }
            ],
        )
        return json_reply(req, out)

    r = router(j, review_handler=reject)
    j.freeze(identity, [scene_target(identity)])
    assert (
        asyncio.run(p.review_pending(r, identity, verify_current=current))
        == "paused_for_human"
    )
    row = j.events("scene_review_finished")[0]
    report = {
        "source_sha256": row["source_sha256"],
        "opinion_sha256": p.digest(row["opinion"]),
        "decision": decision,
        "reviewer": "TEST_ONLY_HUMAN",
        "reviewed_at": "fixture",
        "evidence_ref": "fixture",
        "reason": "synthetic adjudication",
    }
    j.adjudicate_scene(identity, row["source_sha256"], report)
    assert len(j.events("mock_dispatch_reserved")) == 1
    with pytest.raises(p.Refused, match="STOPPED"):
        j.guard()
    assert j.events("scene_review_finished")[0]["opinion"]["verdict"] == "reject"


@pytest.mark.parametrize("mode", ["request_count", "input_tokens"])
def test_course_budget_is_durable_and_stops_before_next_mock_dispatch(setup, mode):
    j, identity = setup
    calls = []

    def generation(req):
        calls.append(req)
        data = json.loads(json_reply(req, {}).content)
        if mode == "input_tokens":
            data["usage"] = {
                "input_tokens": 32000,
                "output_tokens": 0,
                "total_tokens": 32000,
            }
        return httpx.Response(200, json=data)

    r = router(j, generation_handler=generation)
    count = 13 if mode == "request_count" else 6
    for i in range(count):
        request = p.StructuredRequest(
            p.TextRequest(
                (p.ChatMessage("user", f"synthetic {i}"),), max_output_tokens=8000
            ),
            PLAN_SCHEMA,
            "free_course_plan_generation",
        )
        asyncio.run(r.send(identity, request, retry_safe=False))
    extra = p.StructuredRequest(
        p.TextRequest(
            (p.ChatMessage("user", "synthetic extra"),), max_output_tokens=8000
        ),
        PLAN_SCHEMA,
        "free_course_plan_generation",
    )
    with pytest.raises(p.Refused, match="COURSE_"):
        asyncio.run(r.send(identity, extra, retry_safe=False))
    assert len(calls) == count
    assert j.ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"


def test_clock_budget_overrun_preserves_unknown_and_refuses_further_calls(tmp_path):
    tick = [1000.0, 1000.0]
    j = p.Journal.create_mock(tmp_path / "clock", clock=lambda: tuple(tick))
    identity = p.Identity("D01", "TEST_ONLY_OWNER", "TEST_ONLY_COURSE")
    j.bind(identity)

    def slow(req):
        tick[0] += 10801
        tick[1] += 10801
        return json_reply(req, {})

    r = router(j, generation_handler=slow)
    request = p.StructuredRequest(
        p.TextRequest((p.ChatMessage("user", "synthetic"),), max_output_tokens=8000),
        PLAN_SCHEMA,
        "free_course_plan_generation",
    )
    try:
        with pytest.raises(p.Refused):
            asyncio.run(r.send(identity, request, retry_safe=False))
        assert (
            j.ledger.db.execute("SELECT state FROM attempts").fetchone()[0] == "unknown"
        )
        assert j.ledger.usage(j.batch)["input_tokens"] == 32000
        with pytest.raises(p.Refused):
            asyncio.run(r.send(identity, request, retry_safe=False))
    finally:
        j.ledger.close()


def test_source_changes_while_model_is_responding_keep_receipt_but_reject_opinion(
    setup,
):
    j, identity = setup
    j.freeze(identity, [scene_target(identity)])
    checks = []

    async def verify(_):
        checks.append(True)
        return len(checks) == 1

    with pytest.raises(p.Refused, match="SOURCE_CHANGED_DURING_REVIEW"):
        asyncio.run(p.review_pending(router(j), identity, verify_current=verify))
    assert len(j.events("mock_wire_observed")) == 1
    assert not j.events("scene_review_finished")
    assert j.ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"


@pytest.mark.parametrize("change", ["route", "key", "transport"])
def test_runtime_mutation_cannot_turn_mock_router_into_live_dispatch(setup, change):
    j, identity = setup
    r = router(j)
    if change == "route":
        r.policy["providers"]["review"]["url"] = "https://other.invalid/responses"
    if change == "key":
        r.keys["review"] = "not-an-approved-fixture-key"
    if change == "transport":
        r.transports["review"] = httpx.AsyncHTTPTransport()
    request = p.StructuredRequest(
        p.TextRequest((p.ChatMessage("user", "synthetic"),), max_output_tokens=8000),
        dict(review_output_schema()),
        "development_review_probe",
    )
    with pytest.raises(p.Refused, match="MOCK_ROUTE_KEYS_OR_TRANSPORT_CHANGED"):
        asyncio.run(r.send(identity, request, retry_safe=False))
    assert not j.events("mock_dispatch_reserved")
