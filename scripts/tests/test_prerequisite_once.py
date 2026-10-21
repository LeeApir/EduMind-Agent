"""A final explicit case consumes exactly one slot and preserves the prior stop."""

# ruff: noqa: E402
import asyncio
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_prerequisite_once as run
from acceptance_support.qwen_review_budget import sha
from acceptance_support.om_diagnostic import valid_review


@pytest.mark.parametrize("failure", [False, True])
def test_one_attempt_stops_and_replay_never_calls(tmp_path, monkeypatch, failure):
    base = tmp_path / run.BASE
    base.mkdir(parents=True)
    request = json.loads((ROOT / run.parent.BASE / "requests.json").read_bytes())[
        run.SLOT
    ]
    (base / "request.json").write_text(json.dumps(request))
    materials = tmp_path / run.parent.MATERIALS
    materials.mkdir(parents=True)
    (materials / "cases.json").write_bytes(
        (ROOT / run.parent.MATERIALS / "cases.json").read_bytes()
    )
    m = dict(
        request_sha256=request["wire_sha256"], expires_at_epoch=run.time.time() + 3600
    )
    monkeypatch.setattr(run, "authorize", lambda root: (m, "a" * 64))
    monkeypatch.setattr(run, "old_stopped", lambda root: None)
    calls = []

    async def attempt(root, m, case, wire, auth):
        auth()
        calls.append(True)
        if failure:
            raise TimeoutError()
        value = valid_review("unit")
        return dict(
            sent=1,
            http_status=200,
            raw_complete=True,
            model="gpt-6-luna",
            requested_reasoning="high",
            input_tokens=10,
            output_tokens=10,
            record=dict(
                result=value,
                local_routing=dict(verdict="pass"),
                request_digest=sha(wire),
            ),
        )

    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    with pytest.raises(FileExistsError):
        asyncio.run(run.step(tmp_path, attempt))
    assert calls == [True]
    receipt = json.loads((tmp_path / run.PRIVATE / "receipt.json").read_text())
    assert receipt["stopped"] is True and receipt["old_run_resumed"] is False


def test_no_new_authority_denies_before_private_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run,
        "authorize",
        lambda root: (_ for _ in ()).throw(ValueError("NOT_AUTHORIZED")),
    )
    monkeypatch.setattr(run, "old_stopped", lambda root: pytest.fail("must deny first"))
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        asyncio.run(run.step(tmp_path))
    assert not (tmp_path / run.PRIVATE).exists()


def test_request_unchanged_and_no_old_slot_reuse():
    source = json.loads((ROOT / run.parent.BASE / "requests.json").read_bytes())[
        run.SLOT
    ]
    actual = json.loads((ROOT / run.BASE / "request.json").read_bytes())
    assert source == actual
    assert json.loads(bytes.fromhex(actual["wire_hex"]))["reasoning"] == {
        "effort": "high"
    }
    assert run.PRIVATE != run.parent.PRIVATE
