"""Read-only actual r03 mismatch evidence and isolated tamper rejection."""

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_p15_r03_diagnostic_results import REPORT, check  # noqa: E402


@pytest.fixture
def copied_report(tmp_path):
    report = json.loads((ROOT / REPORT).read_text())
    for item in report["raw_evidence"]:
        original = Path(item["path"])
        target = tmp_path / original.name
        shutil.copyfile(original, target)
        item["path"] = str(target)
    approval = tmp_path / "approval.json"
    shutil.copyfile(ROOT / report["approval_registry"], approval)
    report["approval_registry"] = str(approval)
    path = tmp_path / "report.json"

    def save():
        path.write_text(json.dumps(report))
        return path

    return report, save


def test_exact_terminal_failure_is_verified_without_network_or_credentials(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only checker must not open sockets or load credentials")

    original = Path.read_text

    def read(path, *args, **kwargs):
        if path.name == ".env":
            forbidden()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "read_text", read)
    assert check()["verdict"] == "blocked_not_admitted"


@pytest.mark.parametrize(
    "mode",
    [
        "fake_pass",
        "missing_slot",
        "fake_quality",
        "zero_usage",
        "lost_request",
        "raw_tamper",
        "missing_raw",
        "changed_authority",
        "reopened_batch",
        "claim_count_equal",
        "refund_hold",
        "hide_previous_failure",
    ],
)
def test_rejects_loss_tampering_and_manufactured_success(copied_report, mode):
    report, save = copied_report
    paths = {r["role"]: Path(r["path"]) for r in report["raw_evidence"]}
    if mode == "fake_pass":
        report["verdict"] = "done"
    elif mode == "missing_slot":
        report["slots"].pop()
    elif mode == "fake_quality":
        report["quality_evaluated"] = True
    elif mode == "zero_usage":
        report["model_usage_actual"] = {"input_tokens": 0, "output_tokens": 0}
    elif mode == "lost_request":
        report["http_attempts"] = 1
    elif mode == "raw_tamper":
        paths["model_response"].write_text("{}")
    elif mode == "missing_raw":
        paths["model_response"].unlink()
    elif mode == "changed_authority":
        path = Path(report["approval_registry"])
        value = json.loads(path.read_text())
        value["received_at"] = "CHANGED_SYNTHETIC_VALUE"
        path.write_text(json.dumps(value))
        report["approval_registry_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    elif mode == "claim_count_equal":
        report["provider_reported_usage"]["input_tokens"] = 1677
    elif mode == "refund_hold":
        report["unknown_reservation"]["input_tokens"] = 6507
    elif mode == "hide_previous_failure":
        report["cumulative_http_attempts"] = 2
        report["cumulative_model_requests"] = 1
    elif mode == "reopened_batch":
        db = sqlite3.connect(paths["ledger_snapshot"])
        try:
            db.execute("UPDATE batches SET state='running',reason=NULL")
            db.commit()
        finally:
            db.close()
        for item in report["raw_evidence"]:
            if item["role"] == "ledger_snapshot":
                item["sha256"] = hashlib.sha256(
                    paths["ledger_snapshot"].read_bytes()
                ).hexdigest()
    with pytest.raises(AssertionError):
        check(report_path=save())


def test_live_wal_cannot_be_ignored_by_immutable_snapshot_read(copied_report):
    report, save = copied_report
    path = next(
        Path(r["path"])
        for r in report["raw_evidence"]
        if r["role"] == "ledger_snapshot"
    )
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("UPDATE batches SET state='running',reason=NULL")
        db.commit()
        assert Path(str(path) + "-wal").exists()
        with pytest.raises(AssertionError):
            check(report_path=save())
    finally:
        db.close()
