"""Reject false passes, refunded unknown holds and altered private evidence offline."""

import hashlib
import json
import shutil
import socket
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_p15_relay_regression_results as checker  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Result verification must not use network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


def test_actual_stopped_result():
    result = checker.check()
    assert result["model_requests"] == 0 and result["http_requests"] == 1


@pytest.mark.parametrize(
    "mode",
    [
        "fake_pass",
        "refund",
        "extra_generation",
        "http200",
        "hidden_history",
        "free_invoice",
        "ledger_refund",
        "wal",
    ],
)
def test_tampering_is_rejected(tmp_path, mode):
    base = tmp_path / "result"
    shutil.copytree(checker.BASE, base)
    result = json.loads((base / "results.json").read_bytes())
    snapshot = tmp_path / "snapshot"
    shutil.copytree(result["snapshot"], snapshot)
    result["snapshot"] = str(snapshot)
    if mode == "fake_pass":
        result["status"] = "passed"
    if mode == "refund":
        result["local_unknown_reservation"]["planning_fee_micros_usd"] = 0
    if mode == "extra_generation":
        result["model_requests"] = 1
    if mode == "hidden_history":
        result["cumulative_http_requests"] = 1
    if mode == "free_invoice":
        result["actual_invoice"] = 0
    if mode == "http200":
        p = snapshot / "S1-count-status.json"
        p.write_text('{"http_status":200}')
        result["snapshot_sha256"][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    if mode == "ledger_refund":
        p = snapshot / "ledger.sqlite"
        db = sqlite3.connect(p)
        db.execute(
            "UPDATE attempts SET state='complete',input_used=0,output_used=0,fee_used=0"
        )
        db.commit()
        db.close()
        result["snapshot_sha256"][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    if mode == "wal":
        (snapshot / "ledger.sqlite-wal").write_bytes(b"")
    (base / "results.json").write_text(json.dumps(result))
    with pytest.raises(AssertionError):
        checker.check(base)
