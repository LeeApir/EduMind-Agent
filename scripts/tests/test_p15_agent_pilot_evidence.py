"""Read-only evidence tamper checks and pending execution gate: all offline."""

# ruff: noqa: E402
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from scripts import check_p15_agent_pilot_evidence as checker
from scripts.isolated_diagnostics.p15_agent_pilot import write_mock_evidence
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest
from scripts.tests.test_p15_agent_pilot import run, setup


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No real network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def evidence(tmp_path):
    p, g, _ = setup()
    result = run(p)
    out = tmp_path / "evidence"
    write_mock_evidence(out, result, [g])
    return out


def rechain(result):
    previous = None
    for e in result["events"]:
        e.pop("event_digest", None)
        e["previous_digest"] = previous
        e["event_digest"] = digest(e)
        previous = digest(e)


def test_valid_readonly_no_claim_real_or_independent(evidence):
    before = {f.name: f.read_bytes() for f in evidence.iterdir()}
    result = checker.verify(evidence)
    assert result["calls"] == 3 and result["real_http"] == 0
    assert not result["independent_truth"] and not result["T069_completed"]
    assert before == {f.name: f.read_bytes() for f in evidence.iterdir()}


@pytest.mark.parametrize(
    "fault",
    [
        "chain",
        "count",
        "answer",
        "actions",
        "run",
        "wire_input",
        "wire_response",
        "wire_model",
        "authority",
        "review",
        "event_order",
        "spec",
    ],
)
def test_tamper_rejected_even_with_rehashed_event_chain(evidence, fault):
    path = evidence / "result.json"
    r = json.loads(path.read_text())
    wirepath = evidence / "mock-wire.json"
    wire = json.loads(wirepath.read_text())
    if fault == "chain":
        r["events"][1]["event_digest"] = "a" * 64
    elif fault == "count":
        r["calls"] = 2
    elif fault == "answer":
        r["versions"][0]["payload"]["blocks"][-1]["answer_key"] = 99
    elif fault == "actions":
        r["versions"][0]["payload"]["actions"] = []
    elif fault == "run":
        r["versions"][0]["identity"]["run_id"] = "different"
    elif fault == "wire_input":
        wire[0]["request"]["messages"][1]["content"] = "{}"
        wire[0]["request_digest"] = digest(wire[0]["request"])
    elif fault == "wire_response":
        wire[1]["response_text"] = "{}"
        wire[1]["response_digest"] = digest("{}")
    elif fault == "wire_model":
        value = json.loads(wire[0]["response_text"])
        value["model_id"] = "other"
        wire[0]["response_text"] = json.dumps(value)
        wire[0]["response_digest"] = digest(wire[0]["response_text"])
    elif fault == "authority":
        r["independent_evaluation"] = True
    elif fault == "review":
        r["events"][-1]["payload"]["verdict"] = "revise"
    elif fault == "event_order":
        r["events"][1], r["events"][2] = r["events"][2], r["events"][1]
        for i, e in enumerate(r["events"]):
            e["sequence"] = i
    elif fault == "spec":
        r["events"][0]["payload"]["example"]["spec"]["insert_values"][0] = 8
    if fault in ("answer", "actions", "run"):
        for e in r["events"]:
            if e["kind"] == "candidate":
                e["payload"] = deepcopy(r["versions"][0])
    if fault != "chain":
        rechain(r)
    path.write_text(json.dumps(r))
    wirepath.write_text(json.dumps(wire))
    with pytest.raises(ValueError):
        checker.verify(evidence)


def test_repair_evidence_verified(tmp_path):
    from scripts.tests.test_p15_agent_pilot import opinion

    def mutate(role, payload, raw, count):
        if role == "review" and count == 1:
            raw["value"] = opinion(payload["source"], "revise")

    p, g, _ = setup(mutate)
    out = tmp_path / "repair"
    write_mock_evidence(out, run(p), [g])
    assert checker.verify(out)["versions"] == 2


def test_symlink_rejected(evidence, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(evidence, target_is_directory=True)
    with pytest.raises(ValueError):
        checker.verify(link)


def test_preparation_never_reads_env_or_opens_network(monkeypatch):
    from scripts import prepare_p15_agent_pilot as prep

    original = Path.read_bytes

    def safe_read(path):
        assert path.name != ".env"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", safe_read)
    result = prep.check()
    assert result["candidate_verified"] and not result["credentials_loaded"]
    assert result["state"] == "preparation_only_not_executable"
    assert not result["T069_completed"]


def test_preparation_rejects_source_freeze_drift(tmp_path, monkeypatch):
    from scripts import prepare_p15_agent_pilot as prep

    manifest = json.loads((prep.BASE / "development-freeze.json").read_text())
    manifest["files"][0]["sha256"] = "0" * 64
    (tmp_path / "development-freeze.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(prep, "BASE", tmp_path)
    with pytest.raises(ValueError, match="DEVELOPMENT_FREEZE_DRIFT"):
        prep.check()
