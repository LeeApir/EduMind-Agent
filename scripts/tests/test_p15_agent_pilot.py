"""No-network full role workflow, provenance, unknown and bounded-repair regressions."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket
import stat
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from scripts.isolated_diagnostics import p15_agent_pilot as x
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example, digest

SPEC = dict(
    version="head-insertion-spec-v1",
    initial_values=[9],
    insert_values=[1, 2],
    variant="normal",
    allocation_success=[True, True],
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No real DNS or network allowed")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def content(example):
    refs = [
        dict(path="observation." + k, value=example["observation"][k])
        for k in x.QUESTION_KEYS
    ]
    return dict(
        paragraphs=[
            dict(
                key="intro",
                text="读取返回的新头，依次插入，观察到null时终止。",
                fact_refs=refs,
            )
        ],
        questions=[
            dict(
                key="q" + str(i),
                stem="读取观察量：" + k,
                observation_key=k,
                explanation="依据当前完整模板和轨迹。",
                fact_refs=[refs[i]],
            )
            for i, k in enumerate(x.QUESTION_KEYS)
        ],
    )


def opinion(source, verdict="pass", area="difficulty", severity="minor"):
    return dict(
        source_digest=digest(source),
        verdict=verdict,
        scope_status="insufficient_evidence" if verdict == "unknown" else "complete",
        uncertain_reason="证据不足" if verdict == "unknown" else None,
        issues=[]
        if verdict in ("pass", "unknown")
        else [
            dict(
                severity=severity,
                area=area,
                source_pointer="/blocks/0/markdown",
                evidence_quote=source["blocks"][0]["markdown"].strip(),
                reason="请解释清楚",
            )
        ],
    )


def setup(mutator=None, **options):
    seen = []
    review_count = 0

    def handler(request):
        nonlocal review_count
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])
        role = body["stage"].removeprefix("pilot_")
        if role == "plan":
            value = dict(
                objectives=list(x.GOALS),
                spec=payload["allowed_spec"],
                coverage=[
                    dict(objective=k, observation_key=v) for k, v in x.GOALS.items()
                ],
            )
        elif role == "content":
            value = content(payload["example"])
        elif role == "repair":
            value = deepcopy(payload["original"])
            value["paragraphs"][0]["text"] += " 明确使用调用者头。"
        else:
            review_count += 1
            value = opinion(payload["source"])
        raw = dict(
            value=value,
            model_id="mock-pilot",
            usage=dict(input_tokens=10, output_tokens=20),
        )
        if mutator:
            mutator(role, payload, raw, review_count)
        seen.append(dict(role=role, request=body, response=deepcopy(raw)))
        return httpx.Response(200, json=raw)

    g = x.OfflineGateway(httpx.MockTransport(handler))
    pilot = x.Pilot(g, g, **options)
    return pilot, g, seen


def run(pilot, **kw):
    return asyncio.run(
        pilot.run(run_id="dev-run", slot_id="dev-slot", spec=kw.pop("spec", SPEC), **kw)
    )


def test_complete_readable_mock_course_same_source_and_no_production():
    p, g, seen = setup()
    result = run(p)
    assert result["state"] == "mock_advisory_pass"
    assert [s["role"] for s in seen] == ["plan", "content", "review"]
    assert result["calls"] == 3
    source = result["versions"][0]["payload"]
    assert source["blocks"][0]["markdown"]
    assert source["blocks"][1]["text"].startswith("#include")
    assert [b["answer_key"] for b in source["blocks"] if b["kind"] == "question"] == [
        "t1",
        "terminated",
        [2, 1, 9],
        0,
    ]
    assert result["independent_evaluation"] is False
    assert source["production_scoring"] is False
    x.validate_actions(source, build_example(SPEC))
    for event in result["events"]:
        value = deepcopy(event)
        assert value.pop("event_digest") == digest(value)
    for first, second in zip(result["events"], result["events"][1:]):
        assert second["previous_digest"] == digest(first)
    assert len(g.adapter.raw) == 3
    assert all(s["request"]["prompt"]["images"] == [] for s in seen)


def test_single_repair_retains_original_and_reaudits():
    def mutate(role, payload, raw, count):
        if role == "review" and count == 1:
            raw["value"] = opinion(payload["source"], "revise")

    p, _, seen = setup(mutate)
    result = run(p)
    assert result["state"] == "mock_advisory_pass"
    assert result["calls"] == 5
    assert [r["role"] for r in seen] == [
        "plan",
        "content",
        "review",
        "repair",
        "review",
    ]
    a, b = result["versions"]
    assert b["payload"]["parent_digest"] == digest(a)
    assert a["identity"]["revision"] == 0 and b["identity"]["revision"] == 1
    assert (
        a["payload"]["blocks"][0]["markdown"] != b["payload"]["blocks"][0]["markdown"]
    )
    assert a["payload"]["actions"] == b["payload"]["actions"]
    assert a["payload"]["blocks"][1:] == b["payload"]["blocks"][1:]


def test_second_revise_stops_without_third_attempt():
    def mutate(role, payload, raw, count):
        if role == "review":
            raw["value"] = opinion(payload["source"], "revise")

    p, _, seen = setup(mutate)
    result = run(p)
    assert result["reason"] == "REPAIR_EXHAUSTED"
    assert len(result["versions"]) == 2 and len(seen) == 5


@pytest.mark.parametrize(
    "area,severity",
    [("fact", "major"), ("difficulty", "severe"), ("code_safety", "major")],
)
def test_fact_or_safety_stops_never_sent_to_repair(area, severity):
    def mutate(role, payload, raw, count):
        if role == "review":
            raw["value"] = opinion(payload["source"], "revise", area, severity)

    p, _, seen = setup(mutate)
    assert run(p)["reason"] == "FACT_OR_SAFETY_STOP"
    assert len(seen) == 3


def test_contradictory_prose_cannot_be_proven_by_matching_fact_refs():
    def mutate(role, payload, raw, count):
        if role == "content":
            raw["value"]["paragraphs"][0]["text"] = (
                "这里错误地声称所有指针传递会自动改掉调用者头。"
            )
        if role == "review":
            raw["value"] = opinion(payload["source"], "revise", "fact", "severe")

    p, _, _ = setup(mutate)
    assert run(p)["reason"] == "FACT_OR_SAFETY_STOP"


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("missing", "ROLE_SCHEMA"),
        ("extra", "ROLE_SCHEMA"),
        ("fact", "FACT_CONFLICT"),
        ("ref", "FACT_REFERENCE"),
        ("duplicate", "DUPLICATE_KEY"),
        ("question", "QUESTION_COVERAGE"),
        ("interface", "ROLE_SCHEMA"),
    ],
)
def test_content_faults(fault, reason):
    def mutate(role, payload, raw, count):
        if role != "content":
            return
        v = raw["value"]
        if fault == "missing":
            del v["questions"]
        elif fault == "extra":
            v["actions"] = []
        elif fault == "fact":
            v["paragraphs"][0]["fact_refs"][0]["value"] = "wrong"
        elif fault == "ref":
            v["paragraphs"][0]["fact_refs"][0]["path"] = "observation.missing"
        elif fault == "duplicate":
            v["questions"][0]["key"] = "intro"
        elif fault == "question":
            v["questions"][0]["observation_key"] = "allocation_failures"
        else:
            v["code"] = "Node **head"

    p, _, seen = setup(mutate)
    assert run(p)["reason"] == reason
    assert len(seen) == 2


@pytest.mark.parametrize("fault", ["spec", "coverage"])
def test_planner_cannot_change_spec_or_invent_coverage(fault):
    def mutate(role, payload, raw, count):
        if role == "plan":
            if fault == "spec":
                raw["value"]["spec"]["insert_values"][0] = 8
            else:
                raw["value"]["coverage"][0]["observation_key"] = "allocation_failures"

    p, _, seen = setup(mutate)
    assert run(p)["reason"] == "PLAN_COVERAGE_OR_SPEC"
    assert len(seen) == 1


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("unknown", "REVIEW_UNKNOWN"),
        ("digest", "REVIEW_SOURCE"),
        ("quote", "REVIEW_EVIDENCE"),
        ("pointer", "REFERENCE_INVALID"),
        ("scope", "REVIEW_PROTOCOL"),
    ],
)
def test_review_unknown_and_exact_evidence(fault, reason):
    def mutate(role, payload, raw, count):
        if role != "review":
            return
        v = opinion(payload["source"], "revise")
        if fault == "unknown":
            v = opinion(payload["source"], "unknown")
        elif fault == "digest":
            v["source_digest"] = "0" * 64
        elif fault == "quote":
            v["issues"][0]["evidence_quote"] = "not in source"
        elif fault == "pointer":
            v["issues"][0]["source_pointer"] = "/source/blocks/0/markdown"
        else:
            v["scope_status"] = "insufficient_evidence"
        raw["value"] = v

    p, _, seen = setup(mutate)
    assert run(p)["reason"] == reason and len(seen) == 3


def test_missing_actions_keeps_static_candidate_explicitly_failed(monkeypatch):
    monkeypatch.setattr(x, "build_actions", lambda *a: [])
    p, _, seen = setup()
    result = run(p)
    assert result["reason"] == "ACTION_INCOMPLETE_OR_CONFLICT"
    assert result["versions"][0]["payload"]["degraded"] is True
    assert result["versions"][0]["payload"]["blocks"]
    assert len(seen) == 2  # No advisory pass can hide an incomplete demonstration.


def test_repair_cannot_change_question_identity():
    def mutate(role, payload, raw, count):
        if role == "review" and count == 1:
            raw["value"] = opinion(payload["source"], "revise")
        if role == "repair":
            raw["value"]["questions"][0]["key"] = "changed"

    p, _, _ = setup(mutate)
    assert run(p)["reason"] == "REPAIR_QUESTION_IDENTITY"


@pytest.mark.parametrize("calls", [0, 1, 2])
def test_budget_is_reserved_before_call_no_extra_requests(calls):
    p, _, seen = setup(max_calls=calls)
    result = run(p)
    assert result["reason"] == "BUDGET_OR_DEADLINE" and len(seen) == calls
    with pytest.raises(x.PilotError, match="SEALED_NO_RESTART"):
        run(p)


def test_expired_clock_stops_before_dispatch():
    clock = [0]
    p, _, seen = setup(clock=lambda: clock[0], seconds=1)
    clock[0] = 2
    assert run(p)["reason"] == "BUDGET_OR_DEADLINE" and not seen


def test_protocol_drift_seals_unknown_no_retry():
    def mutate(role, payload, raw, count):
        raw["model_id"] = "different"

    p, _, seen = setup(mutate)
    result = run(p)
    assert result["reason"] == "MODEL_OR_PROTOCOL_DRIFT"
    assert any(e["kind"] == "unknown" for e in result["events"])
    assert len(seen) == 1


@pytest.mark.parametrize(
    "change,question",
    [
        ({"variant": "unknown"}, None),
        ({"code": "C code"}, None),
        ({"insert_values": [1] * 5}, None),
        ({"variant": "uninitialized_next"}, "exact_traversal"),
    ],
)
def test_unsupported_rejected_without_any_gateway_call(change, question):
    s = deepcopy(SPEC)
    s.update(change)
    p, _, seen = setup()
    assert run(p, spec=s, question=question)["state"] == "refused"
    assert not seen


def test_cancellation_preserves_reservation_and_unknown():
    async def slow(request):
        await asyncio.sleep(10)

    g = x.OfflineGateway(httpx.MockTransport(slow))
    p = x.Pilot(g, g)

    async def cancel():
        task = asyncio.create_task(p.run(run_id="dev", slot_id="s", spec=SPEC))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert p.calls == 1
    assert [e["kind"] for e in p.events][-2:] == ["unknown", "stopped"]
    with pytest.raises(x.PilotError):
        run(p)


def test_only_mock_transport_and_only_mock_gateways():
    with pytest.raises(x.PilotError, match="MOCK_TRANSPORT_REQUIRED"):
        x.OfflineGateway(httpx.AsyncHTTPTransport())
    with pytest.raises(x.PilotError, match="OFFLINE_GATEWAY_REQUIRED"):
        x.Pilot(None, None)


def test_inert_markdown_preserves_original_audit():
    def mutate(role, payload, raw, count):
        if role == "content":
            raw["value"]["paragraphs"][0]["text"] = (
                "<script>evil()</script>[bad](https://x)"
            )

    p, _, _ = setup(mutate)
    result = run(p)
    markdown = result["versions"][0]["payload"]["blocks"][0]["markdown"]
    assert "<script>" not in markdown
    raw = next(
        e["payload"]["value"]
        for e in result["events"]
        if e["kind"] == "response" and e["payload"]["role"] == "content"
    )
    assert "<script>" in raw["paragraphs"][0]["text"]


def test_exclusive_evidence_and_no_symlinks(tmp_path):
    p, g, _ = setup()
    result = run(p)
    out = tmp_path / "evidence"
    x.write_mock_evidence(out, result, [g])
    assert json.loads((out / "result.json").read_text()) == result
    assert stat.S_IMODE((out / "result.json").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        x.write_mock_evidence(out, result, [g])
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(x.PilotError, match="OUTPUT_SYMLINK"):
        x.write_mock_evidence(link / "another", result, [g])
    copy = p.events
    copy[0]["kind"] = "tampered"
    assert p.events[0]["kind"] != "tampered"


def test_deadline_after_response_preserves_response_not_pass():
    clock = [0]

    def mutate(role, payload, raw, count):
        clock[0] = 2

    p, _, seen = setup(mutate, clock=lambda: clock[0], seconds=1)
    result = run(p)
    assert result["reason"] == "DEADLINE_AFTER_RESPONSE" and len(seen) == 1
    assert any(e["kind"] == "response" for e in result["events"])


def test_timeout_consumes_reservation_and_never_retries():
    async def slow(request):
        await asyncio.sleep(1)

    g = x.OfflineGateway(httpx.MockTransport(slow))
    p = x.Pilot(g, g, seconds=0.01)
    result = run(p)
    assert result["state"] == "stopped" and p.calls == 1
    assert any(e["kind"] == "unknown" for e in p.events)


@pytest.mark.parametrize("fault", ["negative", "missing", "string"])
def test_usage_protocol_cannot_hide_unknown(fault):
    def mutate(role, payload, raw, count):
        if fault == "negative":
            raw["usage"]["input_tokens"] = -1
        elif fault == "missing":
            del raw["usage"]["output_tokens"]
        else:
            raw["usage"]["input_tokens"] = "10"

    p, _, seen = setup(mutate)
    assert run(p)["reason"] == "USAGE_INVALID" and len(seen) == 1


def test_two_concurrent_runs_only_one_dispatch_chain():
    p, _, seen = setup()

    async def concurrent():
        return await asyncio.gather(
            p.run(run_id="a", slot_id="a", spec=SPEC),
            p.run(run_id="b", slot_id="b", spec=SPEC),
            return_exceptions=True,
        )

    outcomes = asyncio.run(concurrent())
    assert sum(isinstance(v, x.PilotError) for v in outcomes) == 1
    assert len(seen) == 3
