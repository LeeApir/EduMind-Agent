"""Full diagnostic routing, strict probe envelopes and truthful delegated stop imports."""

# ruff: noqa: E402
import asyncio
import hashlib
import json
import socket
import sys
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from isolated_diagnostics import p15_full_exploration_r05 as x
from isolated_diagnostics import p15_split_provider as p
from isolated_diagnostics import p15_sol_probe_compatibility as probe
from isolated_diagnostics.p15_full_review_r05 import SplitExecution, assess
from app.core.provider_target import ApprovedTarget
from app.agents.review_schema import REVIEW_PROMPT_VERSION
from test_p15_sol_compatibility_proposal import sample
from test_p15_split_provider import scene_target


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("No real network")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def probe_sample():
    req, res, _, _ = sample()
    req["text"]["format"]["schema"] = probe.schema()
    opinion = dict(
        review_version=REVIEW_PROMPT_VERSION,
        verdict="reject",
        issues=[
            dict(
                area="fact", severity="severe", message="Synthetic incorrect FIFO claim"
            )
        ],
    )
    res["output"][-1]["content"][0]["text"] = json.dumps(opinion)
    return req, res, opinion


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "schema",
        "suffix",
        "reasoning",
        "usage",
        "tool",
        "missing_usage",
        "none_effort",
    ],
)
def test_probe_uses_original_schema_and_known_compatibility_only(fault):
    req, res, opinion = probe_sample()
    if fault == "schema":
        req["text"]["format"]["schema"] = {}
    if fault == "suffix":
        res["instructions"] += " "
    if fault == "reasoning":
        res["output"][0]["content"] = [{"text": "unexpected"}]
    if fault == "usage":
        res["usage"]["total_tokens"] += 1
    if fault == "tool":
        res["output"][0]["type"] = "function_call"
    if fault == "missing_usage":
        res.pop("usage")
    if fault == "none_effort":
        req["reasoning"] = {"effort": "none"}
    if fault:
        with pytest.raises((ValueError, TypeError)):
            probe.validate_envelope(req, res)
    else:
        checked = probe.validate_envelope(req, res)
        assert (
            checked["opinion"] == opinion
            and checked["reported_output_tokens_including_reasoning"] == 100
        )
        assert not checked["production_admission"]


@pytest.fixture
def journal(tmp_path):
    grant = dict(
        scope="PHASE-1.5-T038",
        package_sha256="a" * 64,
        batch_id="p15-split-experiment-r05-mock",
        limits=asdict(x.ExplorationLimits()),
        evidence_ref="SYNTHETIC_NOT_AUTHORITY",
        fee_cap_waiver=True,
    )
    j = x.ExplorationJournal.create(
        tmp_path / "wire", grant["batch_id"], "a" * 64, grant
    )
    yield j
    j.ledger.close()


def test_actual_probe_adapter_never_sends_labels_or_reference_reasons(journal):
    slot = dict(
        slot_id="R01-severe",
        kind="probe",
        content="栈是先进先出。",
        proposed_label="severe",
        proposed_reason="PRIVATE_SYNTHETIC_GOLD",
    )
    journal.record("planned_slots", {"slots": [slot]})
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["reasoning"] == {"effort": "low"}
        assert body["input"] == [
            dict(role="system", content=x.PROBE_PROMPT),
            dict(role="user", content=slot["content"]),
        ]
        assert "PRIVATE_SYNTHETIC_GOLD" not in request.content.decode()
        _, res, opinion = probe_sample()
        res.pop("instructions")
        res["output"][0]["summary"] = [
            {"type": "summary_text", "text": "MOCK_PROBE_SUMMARY_NOT_FORWARDED"}
        ]
        return httpx.Response(200, json=res)

    adapter = x.ExplorationAdapter(
        journal,
        {"generation": "MOCK_GEN_KEY", "review": "MOCK_REVIEW_KEY"},
        lambda role: ApprovedTarget(
            "https://aiapi.world/v1", "aiapi.world", 443, ("8.8.8.8",)
        ),
        lambda: httpx.MockTransport(handler),
    )
    out = asyncio.run(x.run_experimental_slot(slot, None, adapter))
    assert (
        out["engineering_pass"]
        and out["opinion"]["verdict"] == "reject"
        and len(calls) == 1
    )
    assert journal.ledger.usage(journal.batch)["workflow_requests"] == 15
    observations = journal.events("review_protocol_observation")
    assert len(observations) == 1
    assert observations[0]["instruction_echo_status"] == "echo_unavailable"
    assert "MOCK_PROBE_SUMMARY_NOT_FORWARDED" not in json.dumps(observations)


def course_pending(j, partial=False):
    identity = p.Identity("course:scene-review", "owner", "course")
    j.bind(identity)
    target = scene_target(identity)
    target["payload"] = p.design.review_source(
        original_goal="synthetic goal",
        plan_constraints={},
        scene=dict(
            content=dict(
                blocks=[
                    dict(
                        kind="text", anchor_id="a", markdown="Array synthetic statement"
                    )
                ]
            )
        ),
        upstream=[],
    )
    targets = [target]
    if partial:
        extra = scene_target(identity, "second")
        extra["payload"] = p.design.review_source(
            original_goal="synthetic goal",
            plan_constraints={},
            scene=dict(
                content=dict(
                    blocks=[
                        dict(
                            kind="text",
                            anchor_id="b",
                            markdown="Second synthetic statement",
                        )
                    ]
                )
            ),
            upstream=[],
        )
        targets.append(extra)
    j.freeze(identity, targets)
    payload = target["payload"]
    opinion = dict(
        source_sha256=payload["source_sha256"],
        scope_status="complete",
        uncertain_reason=None,
        verdict="revise",
        issues=[
            dict(
                area="fact",
                severity="minor",
                source_pointer="/scene/content/blocks/0/markdown",
                evidence_quote="Array",
                message="Synthetic finding",
            )
        ],
    )
    j.record(
        "scene_review_finished",
        dict(
            identity=identity.packed(),
            source_sha256=payload["source_sha256"],
            opinion=opinion,
        ),
    )
    j.record(
        "scene_advisory_pause",
        dict(
            identity=identity.packed(),
            source_sha256=payload["source_sha256"],
            verdict="revise",
        ),
    )
    slot = dict(slot_id="course", kind="course")
    raw = json.dumps(
        dict(engineering_pass=True, scene_review_identity=identity.packed())
    ).encode()
    (j.output / "course.json").write_bytes(raw)
    j.record(
        "slot_output", dict(slot_id="course", sha256=hashlib.sha256(raw).hexdigest())
    )
    report = dict(
        slot_id="course",
        output_sha256=hashlib.sha256(raw).hexdigest(),
        reviewer="Codex assistant",
        review_type="delegated_assistant",
        independent_human_truth=False,
        reviewed_at="SYNTHETIC",
        evidence_ref="SYNTHETIC_NOT_TRUTH",
        exhaustive_coverage_attested=True,
        natural_severe_errors=0,
        scene_review_checkpoint_sha256=j.review_checkpoint(identity),
        items=[
            dict(
                area=a,
                location="/scene",
                reason="Synthetic reviewed content",
                verdict="fail" if a == "facts" else "pass",
            )
            for a in ["requirements", "learnability", "facts", "answers", "profile"]
        ],
        atomic_facts=[
            dict(
                source_sha256=payload["source_sha256"],
                anchor_id="a",
                source_pointer="/scene/content/blocks/0/markdown",
                evidence_quote="Array",
                statement="Synthetic checked claim",
                reason="Synthetic reasoning",
                verdict="fail",
            )
        ],
        answer_checks=[],
        model_adjudications=[
            dict(
                source_sha256=payload["source_sha256"],
                opinion_sha256=p.digest(opinion),
                decision="confirmed_nonsevere",
                reason="Synthetic confirmed precision issue",
            )
        ],
    )
    if partial:
        report["atomic_facts"].append(
            dict(
                source_sha256=targets[1]["payload"]["source_sha256"],
                anchor_id="b",
                source_pointer="/scene/content/blocks/0/markdown",
                evidence_quote="Second",
                statement="Synthetic second reviewed claim",
                reason="Synthetic reviewed evidence",
                verdict="pass",
            )
        )
    return SplitExecution(j, [slot]), report


def test_confirmed_nonsevere_import_stops_without_false_alarm_or_human_forgery(journal):
    execution, report = course_pending(journal)
    execution.review(report)
    assert journal.events("assistant_review") == [report] and not journal.events(
        "human_review"
    )
    assert not journal.events("scene_false_alarm_adjudicated")
    assert (
        journal.ledger.db.execute("SELECT reason FROM batches").fetchone()[0]
        == "threshold_unreachable"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "missing_atoms",
        "hidden_fact_failure",
        "missing_adjudication",
        "false_alarm_without_record",
        "human",
    ],
)
def test_failure_reports_cannot_skip_sources_or_disguise_model_findings(journal, fault):
    execution, report = course_pending(journal)
    if fault == "source":
        report["atomic_facts"][0]["evidence_quote"] = "not present"
    if fault == "missing_atoms":
        report["atomic_facts"] = []
    if fault == "hidden_fact_failure":
        report["items"][2]["verdict"] = "pass"
    if fault == "missing_adjudication":
        report["model_adjudications"] = []
    if fault == "false_alarm_without_record":
        report["model_adjudications"][0]["decision"] = "false_alarm"
    if fault == "human":
        report["independent_human_truth"] = True
    with pytest.raises(p.Refused):
        execution.review(report)
    assert not journal.events("assistant_review")


def test_unrun_slots_and_no_probe_findings_cannot_admit():
    slots = json.loads(
        (ROOT / "docs/acceptance/phase-1.5-full-diagnostic-r05/slots.json").read_bytes()
    )
    out = assess(slots, [], [], [])
    assert not out["development_admitted"] and not out["gates"]["complete"]
    assert out["counts"]["planned"] == 34 and out["counts"]["severe_denominator"] == 10
    assert not out["gates"]["probe_precision"]


def passing_fixture():
    slots = json.loads(
        (ROOT / "docs/acceptance/phase-1.5-full-diagnostic-r05/slots.json").read_bytes()
    )
    outputs = [dict(slot_id=s["slot_id"], engineering_pass=True) for s in slots]
    reports = []
    for s in slots:
        areas = {
            "course": [
                "requirements",
                "learnability",
                "facts",
                "answers",
                "profile",
                "pair",
            ],
            "negative": ["unsupported_or_conflict_boundary"],
            "probe": ["true_positive_or_false_block"],
        }[s["kind"]]
        report = dict(
            slot_id=s["slot_id"],
            natural_severe_errors=0,
            items=[dict(area=a, verdict="pass") for a in areas],
        )
        if s["kind"] == "course":
            report.update(
                atomic_facts=[dict(verdict="pass")],
                answer_checks=[dict(verdict="pass")],
            )
        if s["kind"] == "probe":
            label = s["proposed_label"]
            report.update(
                accepted_label=label,
                severe_detected=label == "severe",
                flagged_correct_control=False,
                findings_total=int(label == "severe"),
                findings_true=int(label == "severe"),
            )
        reports.append(report)
    return slots, outputs, reports, [dict(valid=True) for _ in range(58)]


def test_complete_fixed_set_can_admit_development_but_not_independent_acceptance():
    out = assess(*passing_fixture())
    assert out["development_admitted"] and all(out["gates"].values())
    assert (
        not out["independent_quality_pass"]
        and not out["performance_admitted"]
        and not out["production_admission"]
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_course",
        "bad_answer",
        "bad_fact",
        "unresolved_fact",
        "two_schema_failures",
        "one_schema_failure",
        "miss_one",
        "miss_two",
        "correct_false_block",
        "empty_findings",
        "missing_pair",
    ],
)
def test_exact_small_denominators_and_zero_tolerance_gates(fault):
    slots, outputs, reports, primary = passing_fixture()
    if fault == "missing_course":
        reports.pop(0)
    if fault == "bad_answer":
        reports[0]["answer_checks"][0]["verdict"] = "fail"
    if fault in ["bad_fact", "unresolved_fact"]:
        reports[0]["atomic_facts"][0]["verdict"] = (
            "unresolved" if fault == "unresolved_fact" else "fail"
        )
    if fault in ["two_schema_failures", "one_schema_failure"]:
        primary[0]["valid"] = False
        if fault == "two_schema_failures":
            primary[1]["valid"] = False
    if fault in ["miss_one", "miss_two"]:
        severe = [r for r in reports if r.get("accepted_label") == "severe"]
        severe[0]["severe_detected"] = False
        if fault == "miss_two":
            severe[1]["severe_detected"] = False
    if fault == "correct_false_block":
        next(r for r in reports if r.get("accepted_label") == "correct")[
            "flagged_correct_control"
        ] = True
    if fault == "empty_findings":
        for r in reports:
            r.update(findings_total=0, findings_true=0)
    if fault == "missing_pair":
        for s, r in zip(slots, reports):
            if s.get("pair_id") == "D01":
                r["items"] = [i for i in r["items"] if i["area"] != "pair"]
    assert assess(slots, outputs, reports, primary)["development_admitted"] == (
        fault in ["one_schema_failure", "miss_one"]
    )


def test_full_window_and_250_request_cap_do_not_reuse_old_ledgers(tmp_path):
    ticks = [100.0, 100.0]
    grant = dict(
        scope="PHASE-1.5-T038",
        package_sha256="a" * 64,
        batch_id="p15-split-experiment-r05-clock",
        limits=asdict(x.ExplorationLimits()),
        evidence_ref="SYNTHETIC",
        fee_cap_waiver=True,
        window_deadline_epoch=105.0,
    )
    j = x.ExplorationJournal.create(
        tmp_path / "clock",
        grant["batch_id"],
        "a" * 64,
        grant,
        clock=lambda: tuple(ticks),
    )
    try:
        for n in range(250):
            j.ledger.reserve(
                j.batch, j.package, str(n), input_max=0, output_max=0, fee_max=0
            )
        assert j.ledger.usage(j.batch)["workflow_requests"] == 264
        with pytest.raises(p.Refused, match="BUDGET_EXHAUSTED"):
            j.ledger.reserve(
                j.batch, j.package, "extra", input_max=0, output_max=0, fee_max=0
            )
    finally:
        j.ledger.close()
    grant["batch_id"] = "p15-split-experiment-r05-expiry"
    j = x.ExplorationJournal.create(
        tmp_path / "expiry",
        grant["batch_id"],
        "a" * 64,
        grant,
        clock=lambda: tuple(ticks),
    )
    try:
        ticks[:] = [106.0, 106.0]
        with pytest.raises(p.Refused, match="EXPLICIT_WINDOW_EXPIRED"):
            j.guard()
        assert j.ledger.usage(j.batch)["requests"] == 0
    finally:
        j.ledger.close()


def test_failed_partial_review_keeps_missing_model_scene_explicitly_unrun(journal):
    execution, report = course_pending(journal, partial=True)
    execution.review(report)
    assert len(journal.events("scene_source_frozen")) == 2
    assert len(journal.events("scene_review_finished")) == 1
    assert len(journal.events("assistant_review")) == 1
    assert (
        journal.ledger.db.execute("SELECT reason FROM batches").fetchone()[0]
        == "threshold_unreachable"
    )


def test_true_false_alarm_resumes_only_remaining_scene_without_regeneration(journal):
    from test_p15_split_provider import clean_opinion

    identity = p.Identity("course:scene-review", "owner", "course")
    journal.bind(identity)
    targets = [scene_target(identity, "first"), scene_target(identity, "second")]
    journal.freeze(identity, targets)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        source = json.loads(body["input"][-1]["content"])
        calls.append(source["source_sha256"])
        value = clean_opinion(source)
        if len(calls) == 1:
            value.update(
                verdict="revise",
                issues=[
                    dict(
                        area="fact",
                        severity="minor",
                        source_pointer="/scene/text",
                        evidence_quote="栈",
                        message="Synthetic false alarm",
                    )
                ],
            )
        _, response, _, _ = sample()
        response["instructions"] = body["input"][0]["content"] + x.compat.SUFFIX
        response["output"][-1]["content"][0]["text"] = json.dumps(value)
        return httpx.Response(200, json=response)

    adapter = x.ExplorationAdapter(
        journal,
        {"generation": "MOCK_GEN_KEY", "review": "MOCK_REVIEW_KEY"},
        lambda role: ApprovedTarget(
            "https://aiapi.world/v1", "aiapi.world", 443, ("8.8.8.8",)
        ),
        lambda: httpx.MockTransport(handler),
    )

    async def current(target):
        return True

    assert (
        asyncio.run(x.review_pending(adapter, identity, verify_current=current))
        == "paused_for_delegated_assistant"
    )
    assert len(calls) == 1
    old = journal.events("scene_review_finished")[0]
    journal.adjudicate_false_alarm(
        identity,
        old["source_sha256"],
        dict(
            source_sha256=old["source_sha256"],
            opinion_sha256=p.digest(old["opinion"]),
            decision="false_alarm",
            reviewer="Codex assistant",
            review_type="delegated_assistant",
            independent_human_truth=False,
            reviewed_at="SYNTHETIC",
            evidence_ref="SYNTHETIC",
            reason="Synthetic false alarm demonstration",
        ),
    )
    assert (
        asyncio.run(x.review_pending(adapter, identity, verify_current=current))
        == "live_reviews_complete"
    )
    assert calls == [t["payload"]["source_sha256"] for t in targets]
    assert len(journal.events("scene_false_alarm_adjudicated")) == 1


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing_question",
        "wrong_key",
        "wrong_accepted",
        "wrong_rejected",
        "unreliable",
        "missing_fact",
        "wrong_quote",
    ],
)
def test_every_generated_answer_and_exact_comparison_requires_source_evidence(fault):
    from types import SimpleNamespace
    from isolated_diagnostics.p15_full_review_r05 import course_inventory

    payload = p.design.review_source(
        original_goal="synthetic goal",
        plan_constraints={},
        scene=dict(
            content=dict(
                blocks=[
                    dict(
                        kind="exercise",
                        anchor_id="e",
                        items=[
                            dict(question_id="q", question="Offset?", answer_key="12")
                        ],
                    )
                ]
            )
        ),
        upstream=[],
    )
    report = dict(
        items=[
            dict(area="facts", verdict="pass"),
            dict(area="answers", verdict="pass"),
        ],
        atomic_facts=[
            dict(
                source_sha256=payload["source_sha256"],
                anchor_id="e",
                source_pointer="/scene/content/blocks/0/items/0/question",
                evidence_quote="Offset",
                statement="Synthetic question claim",
                verdict="pass",
                reason="Synthetic reasoning",
            )
        ],
        answer_checks=[
            dict(
                source_sha256=payload["source_sha256"],
                anchor_id="e",
                question_id="q",
                answer_key="12",
                verdict="pass",
                reason="3 * 4 = 12",
                safe_for_exact_scoring=True,
                accepted_inputs=["12"],
                rejected_inputs=["13"],
            )
        ],
    )
    if fault == "missing_question":
        report["answer_checks"] = []
    if fault == "wrong_key":
        report["answer_checks"][0]["answer_key"] = "13"
    if fault == "wrong_accepted":
        report["answer_checks"][0]["accepted_inputs"] = ["13"]
    if fault == "wrong_rejected":
        report["answer_checks"][0]["rejected_inputs"] = ["12"]
    if fault == "unreliable":
        report["answer_checks"][0]["safe_for_exact_scoring"] = False
    if fault == "missing_fact":
        report["atomic_facts"] = []
    if fault == "wrong_quote":
        report["atomic_facts"][0]["evidence_quote"] = "not here"
    j = SimpleNamespace(sources=lambda identity: [dict(payload=payload)])
    if fault:
        with pytest.raises(p.Refused):
            course_inventory(j, None, report)
    else:
        course_inventory(j, None, report)
