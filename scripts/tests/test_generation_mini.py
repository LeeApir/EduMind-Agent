"""Offline limits/identity/authorization for four fresh generation cases; no model truth."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_generation_mini as mini  # noqa: E402
from check_five_hour_materials import validate_evaluation  # noqa: E402


@pytest.fixture
def selected(monkeypatch):
    monkeypatch.setattr(mini.kernel, "ORDER", list(mini.ORDER))


def finish(ledger, name, count):
    ledger.start_case(name)
    for _ in range(count):
        n = ledger.reserve(name, "a" * 64)
        ledger.complete_call(n, "b" * 64)
    ledger.finish_case(name, "c" * 64)
    ledger.assess(name, "d" * 64)


def test_exact_four_rows_no_old_review_passes(tmp_path, selected):
    ledger = mini.MiniLedger(tmp_path / "run.sqlite", "f" * 64, t0=0, now=lambda: 1)
    assert [(r[0], r[1]) for r in ledger.snapshot()["cases"]] == [
        (n, "pending") for n in mini.ORDER
    ]
    with pytest.raises(ValueError, match="UNKNOWN_CASE"):
        ledger.start_case("U01")
    with pytest.raises(ValueError, match="PREVIOUS_GPT"):
        ledger.start_case("A02")


def test_combined_48_and_16_shared_extras(tmp_path, selected):
    ledger = mini.MiniLedger(tmp_path / "run.sqlite", "f" * 64, t0=0, now=lambda: 1)
    for name, count in [("A01", 20), ("A02", 12), ("A03", 8)]:
        finish(ledger, name, count)
    ledger.start_case("A04")
    for _ in range(8):
        n = ledger.reserve("A04", "a" * 64)
        ledger.complete_call(n, "b" * 64)
    assert len(ledger.snapshot()["calls"]) == 48
    with pytest.raises(ValueError, match="MINI_TOTAL_REQUEST_LIMIT"):
        ledger.reserve("A04", "a" * 64)


def test_unused_baseline_does_not_expand_shared_extras(tmp_path, selected):
    ledger = mini.MiniLedger(tmp_path / "run.sqlite", "f" * 64, t0=0, now=lambda: 1)
    finish(ledger, "A01", 1)
    finish(ledger, "A02", 20)
    ledger.start_case("A03")
    for _ in range(12):
        n = ledger.reserve("A03", "a" * 64)
        ledger.complete_call(n, "b" * 64)
    with pytest.raises(ValueError, match="SHARED_EXTRA_LIMIT"):
        ledger.reserve("A03", "a" * 64)


@pytest.mark.parametrize("elapsed,reason", [(2700, "DEADLINE"), (-1, "BACKWARD")])
def test_new_45_minute_send_cutoff(tmp_path, selected, elapsed, reason):
    now = [1000]
    ledger = mini.MiniLedger(
        tmp_path / "run.sqlite", "f" * 64, t0=1000, now=lambda: now[0]
    )
    now[0] += elapsed
    with pytest.raises(ValueError, match=reason):
        ledger.start_case("A01")


def test_stop_is_durable_and_has_no_retry(tmp_path, selected):
    ledger = mini.MiniLedger(tmp_path / "run.sqlite", "f" * 64, t0=0, now=lambda: 1)
    ledger.stop("RED_EVENT")
    with pytest.raises(ValueError, match="RUN_STOPPED"):
        mini.MiniLedger(ledger.path, ledger.digest, now=lambda: 2).start_case("A01")
    assert not ledger.snapshot()["calls"]


@pytest.mark.parametrize(
    "model,limit,count,error",
    [
        ("gpt-6-luna", 8192, 24, "MINI_MODEL_CALL_CAP"),
        ("deepseek-flash", 2048, 4, "MINI_STAGE_CALL_CAP"),
        ("deepseek-flash", 4096, 20, "MINI_STAGE_CALL_CAP"),
    ],
)
def test_model_and_stage_caps_before_any_network(
    tmp_path, monkeypatch, model, limit, count, error
):
    monkeypatch.setattr(mini, "PRIVATE", tmp_path)
    calls = []
    for n in range(1, count + 1):
        path = tmp_path / "A01" / f"{n:02}-request.json"
        path.parent.mkdir(exist_ok=True)
        body = dict(model=model, max_output_tokens=limit)
        path.write_text(json.dumps({"wire_hex": json.dumps(body).encode().hex()}))
        calls.append([n, "A01"])
    context = dict(ledger=SimpleNamespace(snapshot=lambda: dict(calls=calls)))
    requests = []
    transport = mini.MiniTransport(
        context,
        "https://www.cbbb.fun/v1",
        model,
        "high",
        None,
        inner=httpx.MockTransport(lambda request: requests.append(request)),
    )
    request = httpx.Request(
        "POST",
        "https://8.8.8.8/v1/responses",
        json=dict(model=model, max_output_tokens=limit),
    )
    with pytest.raises(ValueError, match=error):
        asyncio.run(transport.handle_async_request(request))
    assert not requests


def test_no_execution_authority_no_private_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(mini, "PACKAGE", tmp_path)
    monkeypatch.setattr(mini, "verify", lambda: ({}, "a" * 64))
    with pytest.raises(ValueError, match="EXACT_NEW_APPROVAL_REQUIRED"):
        mini.authorize()
    assert not (tmp_path / "run.sqlite").exists()


def test_unrun_and_human_wait_cannot_enter_automatic_numerator():
    p = mini.PACKAGE
    v = json.loads((p / "evaluation-template.json").read_text())
    validate_evaluation(v, base=p)
    bad = deepcopy(v)
    bad["grades"]["core_expected"] = "pass"
    with pytest.raises((ValidationError, ValueError)):
        # Either the Schema or the stricter cross-field validator rejects the fake pass.
        validate_evaluation(bad, base=p)
    bad = deepcopy(v)
    bad["actual"].update(
        status="observed", course_state="awaiting_human", local_verdict="needs_human"
    )
    bad["grades"]["core_expected"] = "pass"
    with pytest.raises((ValidationError, ValueError)):
        # Either the Schema or the stricter cross-field validator rejects the fake pass.
        validate_evaluation(bad, base=p)


def test_all_four_inputs_and_initial_wires_keep_original_raw_text():
    old = ROOT / "docs/acceptance/phase-1-five-hour-test-plan-r01"
    for name in mini.ORDER:
        assert json.loads(
            (mini.PACKAGE / f"cases/{name}.json").read_text()
        ) == json.loads((old / f"cases/{name}.json").read_text())
        new = json.loads((mini.PACKAGE / f"requests/{name}-plan.json").read_text())
        previous = json.loads((old / f"requests/{name}-plan.json").read_text())
        assert new["wire_sha256"] == previous["wire_sha256"]


@pytest.mark.parametrize("name", mini.ORDER)
def test_new_executor_full_pipeline_with_mock_wire_and_real_pg(
    tmp_path, monkeypatch, name
):
    import os
    from urllib.parse import urlsplit

    url = os.getenv("EDUMIND_MINI_TEST_URL")
    if not url:
        pytest.skip("requires independent prepared miniature-run test PG")
    sys.path.insert(0, str(ROOT / "backend/tests"))
    from test_hybrid_learning_publication import sequence
    from app.core.provider_target import ApprovedTarget, ProviderTargetGuard

    values = deepcopy(sequence())
    case = json.loads((mini.PACKAGE / f"cases/{name}.json").read_text())
    values[0]["reference_ids"] = list(case["input_snapshot"]["references"])
    monkeypatch.setattr(mini.kernel, "ORDER", [name])
    monkeypatch.setattr(mini, "PRIVATE", tmp_path)
    monkeypatch.setattr(mini.parent, "ROOT", tmp_path)
    monkeypatch.setattr(mini.parent, "BASE", mini.PACKAGE)
    monkeypatch.setattr(mini.parent, "PACKAGE", mini.PACKAGE)
    monkeypatch.setattr(mini.parent, "PRIVATE", tmp_path)
    monkeypatch.setattr(mini.parent, "AuditTransport", mini.MiniTransport)
    monkeypatch.setattr(mini.parent, "EvidenceGateway", mini.MiniEvidenceGateway)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        ProviderTargetGuard,
        "approve_base",
        lambda self: ApprovedTarget(
            self.base_url, urlsplit(self.base_url).hostname, 443, ("8.8.8.8",)
        ),
    )
    wires = []

    def reply(request):
        body = json.loads(request.content)
        wires.append(body)
        value = values.pop(0)
        return httpx.Response(
            200,
            json=dict(
                model=body["model"],
                status="completed",
                output=[
                    dict(
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[dict(type="output_text", text=json.dumps(value))],
                    )
                ],
                usage=dict(input_tokens=100, output_tokens=100),
            ),
        )

    monkeypatch.setattr(
        httpx, "AsyncHTTPTransport", lambda **kw: httpx.MockTransport(reply)
    )
    import time

    ledger = mini.MiniLedger(tmp_path / "run.sqlite", "f" * 64, t0=time.time())
    ledger.start_case(name)
    directory = tmp_path / name
    directory.mkdir(mode=0o700)
    result = asyncio.run(
        mini.parent.execute_case(
            name, ledger, directory, url, ("OFFLINE_GEN", "OFFLINE_REVIEW")
        )
    )
    assert result["state"] == "awaiting_gpt" and result["actual_call_count"] == 8
    assert not values and len(wires) == 8
    assert sum(b["model"] == "deepseek-flash" for b in wires) == 4
    assert sum(b["model"] == "gpt-6-luna" for b in wires) == 4
    actual = json.loads((directory / "result.json").read_text())
    assert actual["course_state"] == "completed" and len(actual["reviews"]) == 4
    assert actual["production_publish_performed"] is False
    assert actual["new_code_executed"] is False
    for n in range(1, 9):
        for suffix in ["request.json", "receipt.json", "response.bin", "parsed.json"]:
            assert (directory / f"{n:02}-{suffix}").is_file()
    # Scripted scoring exercises persistence/anti-tamper only; it is NOT a real quality grade.
    from datetime import datetime, timezone
    from acceptance_support.qwen_review_budget import canonical, sha

    monkeypatch.setattr(mini, "ROOT", tmp_path)
    score = json.loads((mini.PACKAGE / "evaluation-template.json").read_text())
    index = json.loads((mini.PACKAGE / "case-index.json").read_text())["entries"]
    labels = json.loads((mini.PACKAGE / "labels.json").read_text())["labels"]
    score.update(
        run_id=mini.RUN_ID,
        case_id=name,
        case_sha256=next(e["case_sha256"] for e in index if e["id"] == name),
        label_sha256=sha(canonical(labels[name])),
    )
    score["evaluator"].update(
        identity="synthetic assessment fixture; no real GPT scoring",
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )
    score["actual"].update(
        status="observed",
        model_verdict="pass",
        local_verdict="pass",
        course_state="completed",
        actual_call_count=8,
        input_tokens=800,
        output_tokens=800,
        duration_ms=sum(
            json.loads((directory / f"{n:02}-receipt.json").read_text())["duration_ms"]
            for n in range(1, 9)
        ),
        request_receipt_paths=[
            f"{name}/{n:02}-{kind}.json"
            for n in range(1, 9)
            for kind in ["request", "receipt"]
        ],
        response_artifact_paths=[f"{name}/{n:02}-response.bin" for n in range(1, 9)],
    )
    score["grades"] = {
        k: "pass"
        for k in [
            "technical_integrity",
            "core_expected",
            "all_claims",
            "all_citations",
            "full_quality",
        ]
    }
    score["grades"].update(impact="green", final_status="pass")
    score["reviewed_all_candidates_and_audit_history"] = True
    score["evidence"] = [
        dict(
            id="e1",
            kind="database_assertion",
            artifact_path=f"{name}/result.json",
            artifact_sha256=sha((directory / "result.json").read_bytes()),
            applies_to_digest="f" * 64,
            scope_note="synthetic PG/transport fixture only; not semantic evidence",
        )
    ]
    score["conclusion"] = (
        "Synthetic assessment save/anti-tamper test only; NOT a model score"
    )
    bad = deepcopy(score)
    bad["actual"]["output_tokens"] = 801
    with pytest.raises(ValueError, match="ACTUAL_USAGE_CHANGED"):
        mini.assess(ledger, name, bad)
    assert not (directory / "evaluation.json").exists()
    mini.assess(ledger, name, score)
    assert ledger.snapshot()["cases"][0][1] == "assessed"
