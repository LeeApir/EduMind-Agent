"""Frozen ID calibration and actual mock HTTP transport; no real key or calls."""

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
import prepare_om_admission_r03 as prepare  # noqa: E402
from acceptance_support.om_diagnostic import stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from run_om_admission_r03 import BASE, PRIVATE, runtime  # noqa: E402
from test_om_admission import fake_transport  # noqa: E402

from app.agents.hybrid_resource_review import RESOURCE_CHECKS, UNIT_CHECKS  # noqa: E402
from app.core.config import ProviderSettings  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    base = ROOT / BASE
    return {
        name: json.loads((base / name).read_text())
        for name in (
            "proposal.json",
            "cases.json",
            "proposed-labels.json",
            "token-cost-proof.json",
        )
    }


def test_freeze_has_exact_scope_check_ids_and_actual_anchor_ids(prepared):
    # Stopped r03 inputs are historical: current policy must not silently rebaseline them.
    assert prepare.build() != prepared
    p = prepared["proposal.json"]
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert set(p["implementation_changes"]) == prepare.ALLOWED_CHANGES
    for c in prepared["cases.json"].values():
        body = json.loads(bytes.fromhex(c["wire_hex"]))
        schema = body["text"]["format"]["schema"]
        checked = schema["properties"]["coverage"]["properties"]["checked"]
        expected = UNIT_CHECKS if c["scope"] == "unit" else RESOURCE_CHECKS
        assert set(checked["items"]["enum"]) == expected
        assert checked["uniqueItems"] is True
        assert checked["minItems"] < len(
            expected
        )  # Unknown coverage remains representable.
        assert schema["$defs"]["finding"]["properties"]["anchors"]["items"]["enum"] == [
            a["anchor_id"] for a in c["anchors"]
        ]


def test_missing_new_approval_refuses_before_any_real_state(
    tmp_path, prepared, monkeypatch
):
    runner = runtime()
    base = tmp_path / BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps(prepared["proposal.json"]))
    monkeypatch.setattr(runner, "credentials", lambda _: pytest.fail("key accessed"))
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        asyncio.run(runner.step(tmp_path))
    assert not (tmp_path / PRIVATE).exists()
    import run_om_admission

    assert run_om_admission.BASE.endswith("r01")


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
        lambda _: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    return runner, tmp_path, p, data


def test_valid_ids_pass_control_but_still_require_independent_human_continue(execution):
    runner, root, _, _ = execution
    transport, calls = fake_transport(valid_review("unit"))
    result = asyncio.run(
        runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
    )
    assert (
        result["slot"] == "correct-unit"
        and result["t040_passed"] is False
        and len(calls) == 1
    )
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|HUMAN_CHECK_REQUIRED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1


def test_vendor_prose_checklist_cannot_bypass_enum_or_be_retried(execution):
    runner, root, _, _ = execution
    old = json.loads(
        (
            ROOT
            / "docs/acceptance/phase-1-om-admission-r02/results/correct-unit-01.json"
        ).read_text()
    )
    transport, calls = fake_transport(old["review_result"])
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1
