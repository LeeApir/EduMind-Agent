"""Single batch mechanisms and actual adapter Mock captures, not model-quality evidence."""

# ruff: noqa: E402
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_plan_boundary_batch as batch
from prepare_plan_boundary_batch import (
    BASE,
    ORDER,
    read,
    row_for,
    expected_binding,
    materials,
    labels,
)
from app.agents.plan_check import CHECKS, inspect_plan
from app.agents.shared_learning_plan import CallWindow
from app.core.provider_target import ApprovedTarget
from app.services.learning_contract import LearningContractError


def ledger(tmp_path, clock=None):
    return batch.Ledger(
        tmp_path / "run.sqlite", "a" * 64, activate=True, now=clock or (lambda: 1000)
    )


def test_fixed_collection_never_calls_it_semantic_pass_and_cap_is_eight(tmp_path):
    run_ledger = ledger(tmp_path)
    with pytest.raises(ValueError, match="FIXED_ORDER"):
        run_ledger.start("D02")
    for name in ORDER:
        run_ledger.start(name)
        n, _ = run_ledger.reserve(name, "c" * 64)
        run_ledger.complete(n, "d" * 64)
        run_ledger.finish(name, "e" * 64)
    snap = run_ledger.snapshot()
    assert len(snap["calls"]) == 8
    assert all(r[2] == "collected" for r in snap["cases"])
    assert snap["run"][3] == "COLLECTION_COMPLETE_QUALITY_UNASSESSED"
    with pytest.raises(ValueError, match="STOPPED"):
        run_ledger.start("D01")


def test_failed_or_uncertain_send_does_not_refund_or_replay(tmp_path):
    run_ledger = ledger(tmp_path)
    run_ledger.start("D01")
    run_ledger.reserve("D01", "c" * 64)
    run_ledger.stop("TECHNICAL_FAILURE_NO_RETRY")
    reopened = batch.Ledger(run_ledger.path, "a" * 64)
    assert len(reopened.snapshot()["calls"]) == 1
    with pytest.raises(ValueError, match="STOPPED"):
        reopened.start("D02")
    with pytest.raises(FileExistsError):
        batch.Ledger(run_ledger.path, "a" * 64, activate=True)


@pytest.mark.parametrize(
    "clock_delta,reason", [(3600, "BATCH_DEADLINE"), (-1, "CLOCK_MOVED_BACKWARD")]
)
def test_absolute_deadline_and_rollback_are_irreversible(tmp_path, clock_delta, reason):
    t = [1000.0]
    run_ledger = ledger(tmp_path, lambda: t[0])
    t[0] += clock_delta
    with pytest.raises(ValueError, match=reason):
        run_ledger.start("D01")
    assert run_ledger.snapshot()["run"][3] == reason


def test_concurrent_reservations_allow_one_physical_attempt(tmp_path):
    run_ledger = ledger(tmp_path)
    run_ledger.start("D01")

    def reserve(_):
        try:
            return run_ledger.reserve("D01", "c" * 64)[0]
        except ValueError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert results.count(1) == 1 and results.count(None) == 1


@pytest.mark.parametrize("name", ORDER)
def test_actual_semantic_wire_equals_frozen_probe_and_no_labels(tmp_path, name):
    # Material inputs are frozen developer controls, not H or prior actual responses.
    ccase = read(BASE / f"materials/{name}.json")
    row = row_for(ccase)
    run_ledger = ledger(tmp_path)
    with run_ledger.db() as db:
        db.execute(
            'UPDATE cases SET state="collected" WHERE pos<?', (ORDER.index(name),)
        )
    run_ledger.start(name)
    directory = tmp_path / name
    directory.mkdir(mode=0o700)
    c = dict(name=name, ledger=run_ledger, directory=directory)
    base = batch.CONFIG["review"]["base_url"]
    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            base, urlsplit(base).hostname, 443, ("8.8.8.8",)
        )
    )

    def respond(request):
        assert batch.sha(request.content) == batch.wire_digest(name)
        value = dict(
            schema_version="plan-review-result-v1",
            verdict="pass",
            coverage=dict(checked=CHECKS, unchecked=[]),
            findings=[],
            unresolved=[],
        )
        return httpx.Response(
            200,
            json=dict(
                model="gpt-6-luna",
                status="completed",
                output=[
                    dict(
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[dict(type="output_text", text=json.dumps(value))],
                    )
                ],
                usage=dict(input_tokens=2, output_tokens=2),
            ),
        )

    g, transport = batch.gateway(
        c,
        keys=("TEST_GENERATION_SECRET", "TEST_REVIEW_SECRET"),
        inner=httpx.MockTransport(respond),
        guard=guard,
    )
    result = asyncio.run(
        inspect_plan(
            g,
            CallWindow(),
            row,
            row.origin_operation_id,
            expected_binding=expected_binding(ccase),
        )
    )
    asyncio.run(transport.aclose())
    assert (
        result["schema_version"] == "plan-check-record-v2"
        and len(run_ledger.snapshot()["calls"]) == 1
    )
    wire = read(directory / "01-request.json")["wire"]
    payload = json.loads(wire["input"][-1]["content"])
    assert (
        "prelabel" not in payload
        and "server_binding" not in payload
        and "source_digest" not in json.dumps(payload)
    )
    assert payload["authoritative_teaching_goal"]["user_request"] == ccase[
        "input_snapshot"
    ].get("teaching_context", {}).get(
        "original_request", ccase["input_snapshot"]["metadata"]["goal"]
    )
    assert result["anchor_catalog"] and c["review_sources"]


def test_wrong_frozen_wire_is_blocked_without_network():
    calls = []
    w = batch.ExactWire("D01", httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(ValueError, match="WIRE"):
        asyncio.run(
            w.handle_async_request(
                httpx.Request("POST", "https://example.com", content=b"changed")
            )
        )
    assert not calls


def test_eight_labels_and_semantic_negative_controls_are_precommitted():
    cases = {c["id"]: c for c in materials()}
    lab = labels()
    assert (
        len(cases) == len(lab) == 8
        and [k for k, v in lab.items() if v["model_verdicts"] == ["pass"]] == ORDER[:4]
    )
    assert (
        cases["D01"]["plan"]
        == read(
            ROOT
            / "docs/acceptance/phase-1-plan-admission-preparation-r01/materials/plan/P01.json"
        )["plan"]
    )
    assert (
        "17" in cases["D05"]["plan"]["objectives"][0]["text"]
        and cases["D05"]["input_snapshot"] == cases["D01"]["input_snapshot"]
    )
    assert (
        cases["D06"]["plan"]["shared_example"]["steps"][-1]["expected_output"]
        == "返回a[0]=4"
    )
    assert "a[4]" in cases["D07"]["plan"]["shared_example"]["steps"][0]["operation"]
    assert "未提供" in cases["D08"]["plan"]["shared_example"]["input_description"]
    assert "reject" in lab["D07"]["model_verdicts"]


def test_binding_error_with_recomputed_content_still_zero_review_calls():
    case = deepcopy(read(BASE / "materials/D02.json"))
    case["plan"]["references"][0]["version"] = "invalid"
    # Even trusting a new plan digest cannot override the separate frozen reference snapshot.
    case["server_binding"]["plan_digest"] = batch.sha(b"incorrect-authority")

    class Never:
        calls = 0

        async def generate_structured(self, *a, **kw):
            self.calls += 1
            raise AssertionError("must not send")

    g = Never()
    row = row_for(case)
    with pytest.raises(LearningContractError):
        asyncio.run(
            inspect_plan(
                g,
                CallWindow(),
                row,
                row.origin_operation_id,
                expected_binding=expected_binding(case),
            )
        )
    assert g.calls == 0


def test_missing_approval_and_no_prepare_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "BASE", tmp_path)
    with pytest.raises(FileNotFoundError):
        batch.authorize("a" * 64)
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="CANNOT_REWRITE"):
        batch.freeze()


@pytest.mark.parametrize("all_pass", [True, False])
def test_only_all_eight_human_records_form_admission_and_failure_converges(
    tmp_path, all_pass
):
    run_ledger = ledger(tmp_path)
    for name in ORDER:
        run_ledger.start(name)
        n, _ = run_ledger.reserve(name, "c" * 64)
        run_ledger.complete(n, "d" * 64)
        run_ledger.finish(name, "e" * 64)
    assert batch.quality_summary(run_ledger)["development_admission_pass"] is None
    for i, name in enumerate(ORDER):
        run_ledger.record_evaluation(name, "f" * 64, all_pass or i != 0)
    summary = batch.quality_summary(run_ledger)
    assert (
        summary["development_admission_pass"] == all_pass
        and summary["T040"] == "blocked"
    )
    assert run_ledger.snapshot()["run"][3] == (
        "DEVELOPMENT_CHECKS_PASSED_NO_H_AUTH"
        if all_pass
        else "DEVELOPMENT_FAILED_CONVERGE_TO_DRAFTS"
    )
    with pytest.raises(ValueError):
        run_ledger.start("D01")


def test_gpt_draft_cannot_be_used_as_independent_evaluation(tmp_path):
    value = read(BASE / "evaluation-template.json")
    run_ledger = ledger(tmp_path)
    with pytest.raises(ValueError, match="INDEPENDENT_HUMAN_REQUIRED"):
        batch.evaluate("D01", run_ledger, value, "a" * 64)


def test_late_human_review_cannot_complete_admission(tmp_path):
    t = [1000.0]
    run_ledger = ledger(tmp_path, lambda: t[0])
    run_ledger.start("D01")
    n, _ = run_ledger.reserve("D01", "c" * 64)
    run_ledger.complete(n, "d" * 64)
    run_ledger.finish("D01", "e" * 64)
    t[0] += 3600
    with pytest.raises(ValueError, match="OUTSIDE_FROZEN_WINDOW"):
        run_ledger.record_evaluation("D01", "f" * 64, True)
    assert batch.quality_summary(run_ledger)["signed_evaluations"] == 0


def test_http_failure_consumes_single_attempt_and_stops_collection(tmp_path):
    case = read(BASE / "materials/D01.json")
    row = row_for(case)
    run_ledger = ledger(tmp_path)
    run_ledger.start("D01")
    directory = tmp_path / "D01"
    directory.mkdir(mode=0o700)
    c = dict(name="D01", ledger=run_ledger, directory=directory)
    base = batch.CONFIG["review"]["base_url"]
    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            base, urlsplit(base).hostname, 443, ("8.8.8.8",)
        )
    )
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {"message": "unsupported schema"}})

    g, transport = batch.gateway(
        c,
        keys=("TEST_GENERATION_SECRET", "TEST_REVIEW_SECRET"),
        inner=httpx.MockTransport(respond),
        guard=guard,
    )
    with pytest.raises(Exception):
        asyncio.run(
            inspect_plan(
                g,
                CallWindow(),
                row,
                row.origin_operation_id,
                expected_binding=expected_binding(case),
            )
        )
    asyncio.run(transport.aclose())
    assert (
        len(calls) == 1
        and len(run_ledger.snapshot()["calls"]) == 1
        and run_ledger.snapshot()["run"][3]
    )
    assert (directory / "01-response.bin").exists()
    with pytest.raises(ValueError, match="STOPPED"):
        run_ledger.start("D02")


def mock_collection(tmp_path, monkeypatch, count):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(batch, "PRIVATE", private)
    run_ledger = batch.Ledger(
        private / "run.sqlite", "a" * 64, activate=True, now=lambda: 1000
    )
    original = batch.gateway

    def factory(c, *, keys):
        base = batch.CONFIG["review"]["base_url"]
        guard = SimpleNamespace(
            approve_base=lambda: ApprovedTarget(
                base, urlsplit(base).hostname, 443, ("8.8.8.8",)
            )
        )

        def respond(request):
            value = dict(
                schema_version="plan-review-result-v1",
                verdict="pass",
                coverage=dict(checked=CHECKS, unchecked=[]),
                findings=[],
                unresolved=[],
            )
            return httpx.Response(
                200,
                json=dict(
                    model="gpt-6-luna",
                    status="completed",
                    output=[
                        dict(
                            type="message",
                            role="assistant",
                            status="completed",
                            content=[dict(type="output_text", text=json.dumps(value))],
                        )
                    ],
                    usage=dict(input_tokens=2, output_tokens=2),
                ),
            )

        return original(c, keys=keys, inner=httpx.MockTransport(respond), guard=guard)

    monkeypatch.setattr(batch, "gateway", factory)
    for name in ORDER[:count]:
        asyncio.run(
            batch.execute_case(name, run_ledger, keys=("TEST_GEN", "TEST_REVIEW"))
        )
    return run_ledger, private


def evaluation_for_fixture(private, name, *, missed=False):
    # Synthetic signature exercises validation only; never saved to a real-run directory.
    e = read(private / name / "result.json")
    v = read(BASE / "evaluation-template.json")
    item = next(x for x in read(BASE / "index.json")["items"] if x["id"] == name)
    v.update(
        lane="plan_review",
        case_id=name,
        slot_id=name,
        mode="real",
        status="evaluated",
        run_id=batch.RUN_ID,
        package_manifest_sha256="a" * 64,
        evaluator=dict(name="Lee", role="independent_human", signed=True),
        inventories_complete=dict(all_assertions=True, all_citations=True),
        artifacts=dict(
            material_sha256=item["sha256"],
            request_sha256=batch.sha(
                batch.canonical([c["logical_request_sha256"] for c in e["calls"]])
            ),
            response_sha256=batch.sha(
                batch.canonical([c["parsed_sha256"] for c in e["calls"]])
            ),
        ),
        dimensions=dict(
            core_detection="missed" if missed else "not_applicable",
            false_block=None if missed else False,
        ),
    )
    v["scores"] = dict(
        technical_integrity="pass",
        severe_detection="not_applicable",
        incidental_falsehoods="none",
        teaching_coverage="not_applicable",
        citation_quality="not_applicable",
        quality_success=not missed,
        matches_frozen_label=not missed,
    )
    fields = batch.output_fields(e["parsed_calls"][0]["value"], "/parsed_calls/0/value")
    v["claims"] = [
        dict(
            id=f"c{i}",
            text=f"Test-only field {p}",
            verdict="contradicted"
            if missed and p.endswith("/verdict")
            else "supported",
            evidence_pointers=[p, "/material/plan/goal"],
            reason="Synthetic validation fixture, not independent semantic truth",
        )
        for i, p in enumerate(sorted(fields))
    ]
    return v


def test_evaluation_bound_to_real_artifacts_all_fields_and_observed_false_block(
    tmp_path, monkeypatch
):
    run_ledger, private = mock_collection(tmp_path, monkeypatch, 1)
    good = evaluation_for_fixture(private, "D01")
    for mutate, reason in [
        (lambda v: v["artifacts"].update(request_sha256="0" * 64), "ARTIFACT_BINDING"),
        (lambda v: v.update(claims=v["claims"][:-1]), "TEXT_FIELDS"),
        (
            lambda v: v.update(
                dimensions=dict(core_detection="not_applicable", false_block=True)
            ),
            "FALSE_BLOCK",
        ),
    ]:
        bad = deepcopy(good)
        mutate(bad)
        with pytest.raises(ValueError, match=reason):
            batch.evaluate("D01", run_ledger, bad, "a" * 64)
    batch.evaluate("D01", run_ledger, good, "a" * 64)
    summary = batch.quality_summary(run_ledger)
    assert (
        summary["signed_evaluations"] == 1
        and summary["development_admission_pass"] is None
    )
    assert summary["judged_false_blocks"] == 0 and summary["judged_core_misses"] == 0


def test_true_negative_miss_is_separate_from_incidental_errors_and_collection_can_finish(
    tmp_path, monkeypatch
):
    run_ledger, private = mock_collection(tmp_path, monkeypatch, 5)
    v = evaluation_for_fixture(private, "D05", missed=True)
    batch.evaluate("D05", run_ledger, v, "a" * 64)
    summary = batch.quality_summary(run_ledger)
    assert (
        summary["judged_core_misses"] == 1 and summary["incidental_error_records"] == 0
    )
    assert summary["development_admission_pass"] is False
    # Continue only the originally frozen next control; no repaired sample or repeat.
    asyncio.run(batch.execute_case("D06", run_ledger, keys=("TEST_GEN", "TEST_REVIEW")))
    assert (
        len(run_ledger.snapshot()["calls"]) == 6
        and run_ledger.snapshot()["run"][3] is None
    )
