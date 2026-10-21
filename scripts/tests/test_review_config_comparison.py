"""Isolated paired experiment; synthetic approvals never reach the real root."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "scripts/tests"),
]

import run_review_config_comparison as runner  # noqa: E402
from acceptance_support.om_diagnostic import stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from prepare_review_config_comparison import BASE, NAMES, build, review_document  # noqa: E402
from test_om_admission import fake_transport  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.services.unit_material import restore_material  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    return build()


def test_only_effort_changes_in_each_pair_and_original_four_requests_stay_fixed(
    prepared,
):
    old = json.loads(
        (ROOT / "docs/acceptance/phase-1-coverage-r05/cases.json").read_text()
    )
    data = prepared["cases.json"]
    assert len(data) == 14
    for name in NAMES:
        low, none = (data[name + ":" + arm] for arm in ("candidate", "baseline"))
        a, b = (json.loads(bytes.fromhex(c["wire_hex"])) for c in (low, none))
        assert a.pop("reasoning") == {"effort": "low"}
        assert b.pop("reasoning") == {"effort": "none"}
        assert a == b
        assert low["material"] == none["material"]
        restore_material(low["material"])
        if name in NAMES[:4]:
            assert none["wire_hex"] == old[name]["wire_hex"]
            assert none["material"] == old[name]["material"]
    p = prepared["proposal.json"]
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert p["cost_micro_cny"] == sum(
        2 * (1048576 + s["wire_bytes"]) + 8 * 2048 for s in p["slots"]
    )
    assert build() == prepared


def test_mixed_case_only_replaces_source_before_rebinding(prepared):
    data = prepared["cases.json"]
    gap, mixed = (data[n + ":candidate"] for n in ("plan-only-gap", "gap-and-safety"))
    for before, after in zip(
        gap["material"]["candidates"], mixed["material"]["candidates"], strict=True
    ):
        a, b = deepcopy(before["envelope"]), deepcopy(after["envelope"])
        if before["role"] == "code":
            assert "a[4]" in b["content"].pop("source")
            a["content"].pop("source")
        assert a == b
    assert gap["input_snapshot"] == mixed["input_snapshot"]


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    values = deepcopy(prepared)
    p, data = values["proposal.json"], values["cases.json"]
    p["execution_root"] = str(tmp_path.resolve())
    p["expiry_local"] = "2099-01-01T00:00:00+08:00"
    values["token-cost-proof.json"]["checked_on"] = runner.time.strftime("%Y-%m-%d")
    p["proof_sha256"] = stable(values["token-cost-proof.json"])
    names = (
        "backend/app/services/deepseek_responses.py",
        "docs/ADR/0015-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    )
    p["sources"] = {n: stable(n) for n in names}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(runner.canonical(name))
    base = tmp_path / BASE
    base.mkdir(parents=True)
    for name, value in values.items():
        (base / name).write_text(json.dumps(value))
    (base / "human-review.md").write_text(review_document(data))
    (base / "run-approval.json").write_text(
        json.dumps(
            {
                "version": "om-admission-human-approval-v1",
                "proposal_sha256": stable(p),
                "requests": 14,
                "cost_micro_cny": p["cost_micro_cny"],
                "labels_sha256": p["labels_sha256"],
                "confirmed_by": "Lee",
                "user_confirmation": "SYNTHETIC_ONLY",
                "source_message_id": "synthetic",
                "terms_verified_on": runner.time.strftime("%Y-%m-%d"),
            }
        )
    )
    (base / "labels-human.json").write_text(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "labels_sha256": p["labels_sha256"],
                "case_digests": {n: stable(c["material"]) for n, c in data.items()},
                "decision": "accept_calibration_labels",
                "reviewer": "Lee",
                "source_message_id": "synthetic",
            }
        )
    )
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda _: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    return tmp_path, values


@pytest.mark.parametrize(
    "change", ["approval", "labels", "source", "wire", "readable", "terms"]
)
def test_gates_precede_key_dns_and_new_real_ledger(execution, monkeypatch, change):
    root, values = execution
    base = root / BASE
    if change in ("approval", "labels"):
        (
            base
            / ("run-approval.json" if change == "approval" else "labels-human.json")
        ).unlink()
    elif change == "source":
        (root / next(iter(values["proposal.json"]["sources"]))).write_text("changed")
    elif change == "readable":
        (base / "human-review.md").write_text("changed")
    else:
        (
            base / ("cases.json" if change == "wire" else "token-cost-proof.json")
        ).write_text("{}")
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("premature key read")
    )
    with pytest.raises(GateFailure):
        asyncio.run(runner.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / runner.PRIVATE).exists()


def response(case):
    value = valid_review("unit")
    kind = case["comparison_kind"]
    if kind == "pure_gap":
        value.update(
            verdict="needs_human",
            unresolved=["Synthetic gap; manual semantics required"],
        )
    elif kind != "positive":
        value.update(
            verdict="reject",
            findings=[
                {
                    "category": "fact" if kind == "fact" else "code_safety",
                    "severity": "severe",
                    "anchors": [case["anchors"][0]["anchor_id"]],
                    "condition_or_counterexample": "Synthetic protocol counterexample only",
                    "impact": "Synthetic protocol impact only",
                }
            ],
            unresolved=["Synthetic process gap"] if kind == "mixed" else [],
        )
    return value


def confirm(root, values, slot):
    receipt = runner.read(root / runner.PRIVATE / (slot + ".json"))
    runner.private_write(
        root / runner.PRIVATE / (slot + "-human.json"),
        {
            "proposal_sha256": stable(values["proposal.json"]),
            "receipt_sha256": stable(receipt),
            "decision": "continue",
            "reviewer": "Lee",
            "source_message_id": "synthetic",
        },
    )


def test_full_fourteen_mock_steps_send_exact_low_and_none_wires_once(execution):
    root, values = execution
    sends = 0
    for slot, case in values["cases.json"].items():
        transport, calls = fake_transport(response(case))
        result = asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
        assert result["slot"] == slot and result["requests_sent_this_step"] == 1
        sends += len(calls)
        receipt = runner.read(root / runner.PRIVATE / (slot + ".json"))
        assert receipt["local_assessment"]["semantic_detection_confirmed"] is False
        confirm(root, values, slot)
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(runner.step(root))
    assert sends == 14


def test_exact_receipt_confirmation_is_required_before_second_send(execution):
    root, _ = execution
    transport, calls = fake_transport(valid_review("unit"))
    asyncio.run(runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"]))
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|HUMAN_CHECK_REQUIRED"):
        asyncio.run(runner.step(root, transport=transport))
    assert len(calls) == 1


def test_candidate_false_positive_halts_and_cannot_retry(execution):
    root, _ = execution
    value = valid_review("unit")
    value.update(verdict="needs_human", unresolved=["Synthetic ungrounded uncertainty"])
    transport, calls = fake_transport(value)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root, transport=transport))
    assert len(calls) == 1


def test_baseline_semantic_failure_is_recorded_not_relabeled_pass(prepared):
    case = prepared["cases.json"]["plan-only-gap:baseline"]
    bad = valid_review("unit")
    result = asyncio.run(runner.assess(case, bad, "plan-only-gap:baseline"))
    assert result["criterion_signal"] is False
    assert not result["semantic_detection_confirmed"]
    candidate = prepared["cases.json"]["plan-only-gap:candidate"]
    with pytest.raises(GateFailure, match="CANDIDATE_CRITERION_FAILED"):
        asyncio.run(runner.assess(candidate, bad, "plan-only-gap:candidate"))


def test_r05_actual_answer_remains_a_failed_pure_gap_observation(prepared):
    original = json.loads(
        (
            ROOT / "docs/acceptance/phase-1-coverage-r05/results/plan-only-gap-03.json"
        ).read_text()
    )
    value = original["review_result"]
    before = deepcopy(value)
    baseline = prepared["cases.json"]["plan-only-gap:baseline"]
    result = asyncio.run(runner.assess(baseline, value, "plan-only-gap:baseline"))
    assert result["criterion_signal"] is False
    candidate = prepared["cases.json"]["plan-only-gap:candidate"]
    with pytest.raises(GateFailure, match="CANDIDATE_CRITERION_FAILED"):
        asyncio.run(runner.assess(candidate, value, "plan-only-gap:candidate"))
    assert value == before


def test_mixed_case_must_not_downgrade_serious_error_to_human(prepared):
    case = prepared["cases.json"]["gap-and-safety:candidate"]
    value = valid_review("unit")
    value.update(verdict="needs_human", unresolved=["Synthetic teaching gap only"])
    with pytest.raises(GateFailure, match="CANDIDATE_CRITERION_FAILED"):
        asyncio.run(runner.assess(case, value, "gap-and-safety:candidate"))


@pytest.mark.parametrize("failure", ["truncated", "malformed_schema", "missing_usage"])
def test_incompatible_candidate_response_halts_once(execution, failure):
    import httpx

    root, _ = execution
    inner, calls = fake_transport(
        valid_review("unit"), usage=failure != "missing_usage"
    )

    async def alter(request):
        response = await inner.handle_async_request(request)
        body = json.loads(await response.aread())
        if failure == "truncated":
            body["status"] = "incomplete"
            body["incomplete_details"] = {"reason": "max_output_tokens"}
        elif failure == "malformed_schema":
            body["output"][0]["content"][0]["text"] = '{"unexpected":"field"}'
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(alter)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1


def test_reasoning_item_does_not_count_as_extra_visible_review(execution):
    import httpx

    root, _ = execution
    inner, calls = fake_transport(valid_review("unit"))

    async def alter(request):
        response = await inner.handle_async_request(request)
        body = json.loads(await response.aread())
        body["output"].insert(
            0,
            {
                "type": "reasoning",
                "id": "rs_synthetic",
                "status": "completed",
                "content": [
                    {"type": "reasoning_text", "text": "SYNTHETIC_TRANSPORT_ONLY"}
                ],
            },
        )
        body["usage"]["output_tokens_details"] = {"reasoning_tokens": 1}
        return httpx.Response(200, json=body)

    result = asyncio.run(
        runner.step(
            root, transport=httpx.MockTransport(alter), resolver=lambda *_: ["8.8.8.8"]
        )
    )
    assert result["slot"] == "trace-complete:candidate"
    assert len(calls) == 1
    receipt = runner.read(root / runner.PRIVATE / "trace-complete:candidate.json")
    assert (
        receipt["output_tokens"] == 30
    )  # Total from transport, never subtract reasoning.
    assert "SYNTHETIC_TRANSPORT_ONLY" not in json.dumps(receipt)
