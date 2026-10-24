"""Immutable stopped-probe result audit; no real API and no credentials."""

import hashlib
import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_p15_compatibility_probe_results import REPORT, check  # noqa: E402


@pytest.fixture(autouse=True)
def forbid_network_env(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only evidence audit only")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


def test_actual_approved_stopped_evidence_read_only():
    report = check()
    assert report["T038_status"] == "blocked"


def copy_evidence(tmp_path):
    report = json.loads((ROOT / REPORT).read_text())
    manifest = json.loads((ROOT / report["manifest"]).read_text())
    names = [
        report["manifest"],
        *manifest["sha256"],
        *[g["path"] for g in report["grants"].values()],
        *[p["path"] for p in report["previous_results"]],
    ]
    for name in names:
        dst = tmp_path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
    for item in report["raw_evidence"]:
        dst = tmp_path / "raw" / item["name"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item["path"], dst)
        item["path"] = str(dst)
    return report


@pytest.mark.parametrize(
    "mode",
    [
        "fake_pass",
        "refund",
        "fee_zero",
        "T038_done",
        "hide_old",
        "counter",
        "no_risk",
        "wal",
    ],
)
def test_tamper_or_fake_acceptance_rejected(tmp_path, mode):
    report = copy_evidence(tmp_path)
    if mode == "fake_pass":
        report["verdict"] = "pass"
    if mode == "refund":
        report["unknown_reservation"]["input_tokens"] = 0
    if mode == "fee_zero":
        report["actual_relay_fee"] = 0
    if mode == "T038_done":
        report["T038_status"] = "done"
    if mode == "hide_old":
        report["previous_results"] = []
    if mode == "counter":
        report["preflight_input_tokens"] = 4438
    if mode == "no_risk":
        info = report["grants"]["execution"]
        path = tmp_path / info["path"]
        grant = json.loads(path.read_text())
        grant["unverified_upstream_bounds_risk_accepted"] = False
        path.write_text(json.dumps(grant))
        info["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if mode == "wal":
        snapshot = next(
            i["path"]
            for i in report["raw_evidence"]
            if i["name"] == "ledger.snapshot.sqlite"
        )
        Path(snapshot + "-wal").write_bytes(b"unverified WAL")
    path = tmp_path / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report))
    with pytest.raises(AssertionError):
        check(tmp_path)
