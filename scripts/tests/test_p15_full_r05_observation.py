"""Wire-bound r05 observation receipts cannot invent delivery or hide raw evidence."""

# ruff: noqa: E402
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from isolated_diagnostics import p15_full_observation_r05 as p
from isolated_diagnostics.p15_course_sol_bridge import review_request
from test_p15_sol_compatibility_proposal import sample


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("No network"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a: pytest.fail("No DNS"))


def record_fixture(tmp_path):
    _, res, source, opinion = sample()
    req = review_request("development_scene_review", source)
    res.pop("instructions")
    res["output"][0]["summary"] = [
        {"type": "summary_text", "text": "PRIVATE_SYNTHETIC_META"}
    ]
    res["output"][0]["encrypted_content"] = "OPAQUE_NOT_FORWARDED"
    raw = json.dumps(req).encode()
    response = json.dumps(res).encode()
    ticket = "a" * 64
    identity = dict(slot_id="D01:scene-review", owner_id="owner", course_id="course")
    result, record = p.checked_record(
        raw,
        response,
        stage="development_scene_review",
        identity=identity,
        ticket=ticket,
        slots=[],
    )
    assert result == opinion
    (tmp_path / (ticket + "-request.json")).write_bytes(raw)
    (tmp_path / (ticket + "-response.json")).write_bytes(response)
    call = {k: record[k] for k in ("ticket", "stage", "identity", "request_sha256")}
    call["provider"] = "review"
    settlement = (ticket, dict(proof_sha256=record["response_sha256"]))
    return call, settlement, record


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing",
        "duplicate",
        "false_delivery",
        "false_context",
        "export_summary",
        "different_source",
        "different_identity",
        "different_usage",
        "raw_request",
        "raw_response",
        "settlement_proof",
        "unknown_ticket",
    ],
)
def test_read_only_assessment_replays_original_bytes_and_rejects_forged_observations(
    tmp_path, fault
):
    call, settlement, record = record_fixture(tmp_path)
    observations = [deepcopy(record)]
    if fault == "missing":
        observations = []
    if fault == "duplicate":
        observations *= 2
    if fault == "false_delivery":
        observations[0]["instruction_delivery_verified"] = True
    if fault == "false_context":
        observations[0]["upstream_context_verified"] = True
    if fault == "export_summary":
        observations[0]["summary"] = "PRIVATE_SYNTHETIC_META"
    if fault == "different_source":
        observations[0]["source_sha256"] = "f" * 64
    if fault == "different_identity":
        observations[0]["identity"]["owner_id"] = "other"
    if fault == "different_usage":
        observations[0]["reported_output_tokens_including_reasoning"] += 1
    if fault in ("raw_request", "raw_response"):
        name = "request" if fault == "raw_request" else "response"
        (tmp_path / (call["ticket"] + "-" + name + ".json")).write_text("{}")
    if fault == "settlement_proof":
        settlement[1]["proof_sha256"] = "f" * 64
    if fault == "unknown_ticket":
        observations[0]["ticket"] = "b" * 64
    kwargs = dict(
        output=tmp_path,
        calls=[call],
        settlements=[settlement],
        observations=observations,
        slots=[],
    )
    if fault:
        with pytest.raises((ValueError, KeyError)):
            p.audit_records(**kwargs)
    else:
        before = {x.name: x.read_bytes() for x in tmp_path.iterdir()}
        assert p.audit_records(**kwargs) == 1
        assert not record["instruction_delivery_verified"]
        assert not record["upstream_context_verified"]
        assert "PRIVATE_SYNTHETIC_META" not in json.dumps(record)
        assert "OPAQUE_NOT_FORWARDED" not in json.dumps(record)
        assert before == {x.name: x.read_bytes() for x in tmp_path.iterdir()}
