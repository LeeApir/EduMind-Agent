"""r04 composition with synthetic authorization and mock HTTP, never real credentials."""

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
from acceptance_support.om_diagnostic import price, stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from prepare_coverage_admission import PLAN, PLAN_SHA, build, review_document  # noqa: E402
from run_coverage_review import BASE, PRIVATE, SLOTS, runtime  # noqa: E402
from test_om_admission import fake_transport  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.services.learning_contract import LearningContractError  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    return build()


def test_execution_freeze_preserves_all_four_exact_prior_wires(prepared):
    prior = json.loads((ROOT / PLAN / "proposal.json").read_text())
    assert stable(prior) == PLAN_SHA
    assert prepared["cases.json"] == json.loads(
        (ROOT / PLAN / "cases.json").read_text()
    )
    p = prepared["proposal.json"]
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert p["requests"] == 4 and p["cost_micro_cny"] == 8768806
    assert p["cost_micro_cny"] == sum(price(s["wire_bytes"]) for s in p["slots"])
    assert "implementation-only-offline" not in prepared["cases.json"]
    for c in prepared["cases.json"].values():
        body = json.loads(bytes.fromhex(c["wire_hex"]))
        assert body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == 2048 and body["temperature"] == 0
        assert "tools" not in body and "previous_response_id" not in body
        assert "expected_route" not in bytes.fromhex(c["wire_hex"]).decode()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    runner = runtime()
    values = deepcopy(prepared)
    p, data = values["proposal.json"], values["cases.json"]
    p["execution_root"] = str(tmp_path.resolve())
    names = (
        "backend/app/services/deepseek_responses.py",
        "docs/ADR/0015-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    )
    p["sources"] = {name: stable(name) for name in names}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(runner.canonical(name))
    base = tmp_path / BASE
    base.mkdir(parents=True)
    for name, value in values.items():
        (base / name).write_text(json.dumps(value))
    (base / "human-review.md").write_text(review_document(values))
    approval = {
        "version": "om-admission-human-approval-v1",
        "proposal_sha256": stable(p),
        "requests": 4,
        "cost_micro_cny": p["cost_micro_cny"],
        "labels_sha256": p["labels_sha256"],
        "confirmed_by": "Lee",
        "user_confirmation": "SYNTHETIC_TEST_ONLY",
        "source_message_id": "synthetic-budget",
        "terms_verified_on": runner.time.strftime("%Y-%m-%d"),
    }
    labels = {
        "proposal_sha256": stable(p),
        "labels_sha256": p["labels_sha256"],
        "case_digests": {name: stable(data[name]["material"]) for name in SLOTS},
        "decision": "accept_calibration_labels",
        "reviewer": "Lee",
        "source_message_id": "synthetic-labels",
        "user_confirmation": "SYNTHETIC_TEST_ONLY",
    }
    (base / "run-approval.json").write_text(json.dumps(approval))
    (base / "labels-human.json").write_text(json.dumps(labels))
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda _: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    return runner, tmp_path, values


@pytest.mark.parametrize("missing", ["run-approval.json", "labels-human.json"])
def test_both_human_gates_precede_key_dns_or_new_ledger(
    execution, monkeypatch, missing
):
    runner, root, _ = execution
    (root / BASE / missing).unlink()
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("premature key access")
    )
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|LABEL_REVIEW_REQUIRED"):
        asyncio.run(runner.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / PRIVATE).exists()


@pytest.mark.parametrize(
    "changed",
    ["source", "wire", "labels", "terms", "label_binding", "readable_material"],
)
def test_tampering_is_rejected_before_key_dns_or_ledger(
    execution, monkeypatch, changed
):
    runner, root, values = execution
    base = root / BASE
    if changed == "source":
        (root / next(iter(values["proposal.json"]["sources"]))).write_text("tampered")
    elif changed == "readable_material":
        (base / "human-review.md").write_text("tampered readable content")
    elif changed == "label_binding":
        path = base / "labels-human.json"
        value = json.loads(path.read_text())
        value["case_digests"][SLOTS[0]] = "0" * 64
        path.write_text(json.dumps(value))
    else:
        name = {
            "wire": "cases.json",
            "labels": "proposed-labels.json",
            "terms": "token-cost-proof.json",
        }[changed]
        path = base / name
        value = json.loads(path.read_text())
        value["tampered"] = True
        path.write_text(json.dumps(value))
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("premature key access")
    )
    with pytest.raises(
        GateFailure, match="FREEZE_CHANGED|LABEL_REVIEW_REQUIRED|HUMAN_REVIEW_CHANGED"
    ):
        asyncio.run(runner.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / PRIVATE).exists()


def test_actual_composition_sends_once_and_waits_for_exact_receipt(execution):
    runner, root, _ = execution
    transport, calls = fake_transport(valid_review("unit"))
    result = asyncio.run(
        runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
    )
    assert result["slot"] == "trace-complete" and len(calls) == 1
    assert result["t040_passed"] is False
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|HUMAN_CHECK_REQUIRED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1
    import run_om_admission

    assert run_om_admission.BASE.endswith("r01")


def test_wrong_control_route_halts_and_cannot_retry(execution):
    runner, root, _ = execution
    value = valid_review("unit")
    value.update(verdict="needs_human", unresolved=["Synthetic ungrounded uncertainty"])
    transport, calls = fake_transport(value)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1
    failed = runner.read(root / PRIVATE / "trace-complete-failed.json")
    assert failed["value"] == value and not failed["human_confirmed"]


@pytest.mark.parametrize("slot", SLOTS)
def test_expected_routes_never_claim_semantic_success(prepared, slot):
    runner = runtime()
    value = valid_review("unit")
    if slot in SLOTS[2:]:
        value.update(
            verdict="needs_human",
            unresolved=["Generic uncertainty cannot prove detection."],
        )
    result = asyncio.run(runner.assess(prepared["cases.json"][slot], value, slot))
    assert result["human_concrete_detection_check_required"] is True
    assert result["semantic_detection_confirmed"] is False


@pytest.mark.parametrize("slot", SLOTS[2:])
def test_pure_gap_does_not_pass_on_wrong_route_or_fabricated_fact(prepared, slot):
    runner = runtime()
    case = prepared["cases.json"][slot]
    with pytest.raises(GateFailure, match="COVERAGE_ROUTE_MISMATCH"):
        asyncio.run(runner.assess(case, valid_review("unit"), slot))
    value = valid_review("unit")
    value.update(
        verdict="needs_human",
        unresolved=["Coverage gap"],
        findings=[
            {
                "category": "fact",
                "severity": "minor",
                "anchors": [case["anchors"][0]["anchor_id"]],
                "condition_or_counterexample": (
                    "Synthetic fabricated fact category for a pure omission"
                ),
                "impact": "Synthetic coverage gap",
            }
        ],
    )
    with pytest.raises((GateFailure, LearningContractError)):
        asyncio.run(runner.assess(case, value, slot))


def test_exact_human_continuations_can_only_consume_four_frozen_slots(execution):
    runner, root, values = execution
    p = values["proposal.json"]
    sends = 0
    for slot in SLOTS:
        value = valid_review("unit")
        if slot in SLOTS[2:]:
            value.update(
                verdict="needs_human",
                unresolved=["Synthetic gap; semantic review still required"],
            )
        transport, calls = fake_transport(value)
        result = asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
        assert result["slot"] == slot and result["requests_sent_this_step"] == 1
        sends += len(calls)
        receipt = runner.read(root / PRIVATE / (slot + ".json"))
        assert not receipt["local_assessment"]["semantic_detection_confirmed"]
        runner.private_write(
            root / PRIVATE / (slot + "-human.json"),
            {
                "proposal_sha256": stable(p),
                "receipt_sha256": stable(receipt),
                "decision": "continue",
                "reviewer": "Lee",
                "source_message_id": "synthetic-only",
            },
        )
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(runner.step(root))
    assert sends == 4


def test_mismatched_receipt_human_record_cannot_authorize_second_send(execution):
    runner, root, values = execution
    transport, calls = fake_transport(valid_review("unit"))
    asyncio.run(runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"]))
    runner.private_write(
        root / PRIVATE / "trace-complete-human.json",
        {
            "proposal_sha256": stable(values["proposal.json"]),
            "receipt_sha256": "0" * 64,
            "decision": "continue",
            "reviewer": "Lee",
            "source_message_id": "synthetic-only",
        },
    )
    with pytest.raises(GateFailure, match="HUMAN_CHECK_REQUIRED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    assert len(calls) == 1
