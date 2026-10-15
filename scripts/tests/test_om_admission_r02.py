"""Zero-network regression for repaired scope calibration and independent run gates."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "scripts/tests"),
]
import prepare_om_admission_r02 as prepare  # noqa: E402
from acceptance_support.om_admission_r02 import BASE, PRIVATE, SLOTS  # noqa: E402
from acceptance_support.om_diagnostic import stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from app.core.config import ProviderSettings  # noqa: E402
from app.services.learning_contract import LearningContractError  # noqa: E402
from app.services.unit_material import restore_material  # noqa: E402
from run_om_admission_r02 import runtime  # noqa: E402
from test_om_admission import fake_transport  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    return prepare.build()


def test_repair_freeze_is_reproducible_and_keeps_old_results(prepared):
    assert prepare.build() == prepared
    p = prepared["proposal.json"]
    assert set(p["implementation_changes"]) == prepare.ALLOWED_CHANGES
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert (
        p["prior_proposal_sha256"]
        == "28e25a016c1689c8b27ae52284edb91244fec85b4f24c19297673377a2b17057"
    )
    assert list(prepared["cases.json"]) == list(SLOTS)
    for case in prepared["cases.json"].values():
        restore_material(case["material"])
        body = json.loads(bytes.fromhex(case["wire_hex"]))
        schema = body["text"]["format"]["schema"]
        Draft202012Validator.check_schema(schema)
        assert schema["properties"]["scope"] == {"const": case["scope"]}
        assert ("revise" in schema["properties"]["verdict"]["enum"]) == (
            case["scope"] == "resource"
        )
    data = prepared["cases.json"]
    good = data["correct-unit"]["material"]
    bad = data["missing-unit-objective"]["material"]
    assert good["plan"]["objectives"] == bad["plan"]["objectives"]
    assert good["reference_context"] == bad["reference_context"]
    assert "total=7" in good["candidates"][0]["envelope"]["content"]["markdown"]
    assert "total=7" not in bad["candidates"][0]["envelope"]["content"]["markdown"]
    assert "i=1" in good["candidates"][2]["envelope"]["content"]["items"][0]["question"]


def test_missing_new_approval_stops_before_key_or_old_ledger(
    tmp_path, prepared, monkeypatch
):
    runner = runtime()
    base = tmp_path / BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps(prepared["proposal.json"]))
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("premature key read")
    )
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        asyncio.run(runner.step(tmp_path))
    assert not (tmp_path / PRIVATE).exists()
    import run_om_admission

    assert run_om_admission.BASE.endswith("r01")
    assert run_om_admission.PRIVATE.endswith("r01")


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    runner = runtime()
    p, data = deepcopy(prepared["proposal.json"]), deepcopy(prepared["cases.json"])
    p["execution_root"] = str(tmp_path.resolve())
    p["sources"] = {
        name: stable(name)
        for name in p["sources"]
        if name
        in (
            "backend/app/services/deepseek_responses.py",
            "docs/ADR/0015-approval-20261015.json",
            "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
        )
    }
    for name in p["sources"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(runner.canonical(name))
    base = tmp_path / BASE
    base.mkdir(parents=True)
    for name, value in prepared.items():
        (base / name).write_text(json.dumps(p if name == "proposal.json" else value))
    monkeypatch.setattr(runner, "load", lambda root: (p, {"synthetic": True}, data))
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda root: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    return runner, tmp_path, p, data


def test_new_runtime_runs_each_slot_only_after_exact_synthetic_human_continue(
    execution,
):
    runner, root, p, data = execution
    for slot in SLOTS:
        value = valid_review(data[slot]["scope"])
        if slot == "missing-unit-objective":
            value["verdict"] = "needs_human"
            value["unresolved"] = [
                "Synthetic missing direct trace instruction requires review."
            ]
        elif slot != "correct-unit":
            value.update(
                verdict="reject",
                findings=[
                    {
                        "category": "code_safety"
                        if slot == "reachable-safety"
                        else "fact",
                        "severity": "major",
                        "anchors": [data[slot]["anchors"][0]["anchor_id"]],
                        "condition_or_counterexample": "Synthetic routing condition, not semantic proof.",
                        "impact": "Synthetic impact, not human-approved evidence.",
                    }
                ],
            )
        transport, calls = fake_transport(value)
        result = asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
        assert (
            result["slot"] == slot
            and len(calls) == 1
            and result["t040_passed"] is False
        )
        receipt = runner.read(root / PRIVATE / (slot + ".json"))
        runner.private_write(
            root / PRIVATE / (slot + "-human.json"),
            {
                "proposal_sha256": stable(p),
                "receipt_sha256": stable(receipt),
                "decision": "continue",
                "reviewer": "Lee",
                "source_message_id": "synthetic-only-not-actual-review",
            },
        )
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(runner.step(root))


def test_new_error_mapping_does_not_misreport_contract_fault_as_credential_leak():
    runner = runtime()
    assert runner.classify_failure(
        LearningContractError("REVIEW_PROTOCOL_INVALID")
    ) == ("INVALID_OUTPUT", "review_contract")
    assert runner.classify_failure(GateFailure("SAFETY_FAILURE"))[0] == "SAFETY_FAILURE"


def test_provider_ignoring_unit_schema_halts_new_run_without_refund(execution):
    runner, root, _, _ = execution
    value = valid_review("unit")
    value["verdict"] = "revise"
    transport, calls = fake_transport(value)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1
