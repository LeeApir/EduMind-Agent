"""Single-use gate only: fake attempt cannot count as real quality evidence."""

# ruff: noqa: E402
import asyncio
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_qwen_compatibility as runner
from acceptance_support.qwen_review_attempt import AttemptFailure


def prepared(tmp_path, monkeypatch, approved=True):
    p = deepcopy(runner.old.read(ROOT / runner.BASE / "proposal.json"))
    p["execution_root"] = str(tmp_path.resolve())
    files = {
        name: digest
        for name, digest in p["budget_manifest"]["files"].items()
        if name
        in [
            "backend/app/services/openai_compatible.py",
            "docs/ADR/0015-approval-20261015.json",
            "docs/acceptance/phase-1-provider-connection-v1/results/final.json",
        ]
    }
    p["sources"] = files
    p["budget_manifest"]["files"] = files
    for name in [
        *files,
        runner.BASE + "/request.json",
        runner.old.DESIGN + "/cases.json",
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    base = tmp_path / runner.BASE
    (base / "proposal.json").write_text(json.dumps(p))
    if approved:
        a = {
            "proposal_sha256": runner.old.stable(p),
            "reviewer": "Lee",
            "requests": 1,
            "cost_micro_cny": p["cost_micro_cny"],
            "user_confirmation": "SYNTHETIC_TEST_ONLY",
            "source_message_id": "SYNTHETIC_TEST_ONLY",
        }
        (base / "run-approval.json").write_text(json.dumps(a))
        (base / ("terms-" + time.strftime("%Y-%m-%d") + ".json")).write_text(
            json.dumps(
                {
                    "checked_on": time.strftime("%Y-%m-%d"),
                    "proposal_sha256": runner.old.stable(p),
                    "prices_and_limits_unchanged": True,
                }
            )
        )
    monkeypatch.setattr(
        runner.old,
        "credentials",
        lambda *_: ("https://synthetic.test/v1", "SYNTHETIC_KEY"),
    )
    monkeypatch.setattr(runner.old, "database_url", lambda: "SYNTHETIC_DB_NOT_USED")
    return p


def test_unapproved_gate_creates_no_private_state(tmp_path, monkeypatch):
    prepared(tmp_path, monkeypatch, approved=False)
    with pytest.raises(runner.GateFailure):
        asyncio.run(runner.step(tmp_path))
    assert not (tmp_path / runner.PRIVATE).exists()


@pytest.mark.parametrize("failed", [False, True])
def test_one_attempt_only_stop_and_no_quality_pass(tmp_path, monkeypatch, failed):
    p = prepared(tmp_path, monkeypatch)
    calls = []

    async def attempt(case, wire, **kwargs):
        calls.append(wire)
        assert kwargs["schema_profile"] == p["schema_profile"]
        if failed:
            raise AttemptFailure(
                {
                    "normalized_error": "CAPABILITY_UNAVAILABLE",
                    "input_tokens": None,
                    "output_tokens": None,
                    "sent": 1,
                    "http_status": 400,
                    "provider_error": {"parse": "NON_JSON"},
                }
            )
        return {
            "sent": 1,
            "normal_finish": True,
            "schema_valid": True,
            "cleanup": {"done": True},
            "input_tokens": 100,
            "output_tokens": 100,
            "review_record": {"result": "SYNTHETIC_GATE_TEST_ONLY"},
        }

    result = asyncio.run(runner.step(tmp_path, attempt))
    assert not result["t040_passed"]
    assert result["status"] == (
        "COMPATIBILITY_FAILED_STOPPED"
        if failed
        else "COMPATIBLE_PENDING_SEMANTIC_REVIEW"
    )
    with pytest.raises(runner.GateFailure):
        asyncio.run(runner.step(tmp_path, attempt))
    assert len(calls) == 1
    receipt = json.loads((tmp_path / runner.PRIVATE / "receipt.json").read_text())
    assert receipt["proposal_sha256"] == runner.old.stable(p)
