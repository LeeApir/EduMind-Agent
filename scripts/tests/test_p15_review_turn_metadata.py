"""ADR0040 synthetic proposal tests: exact opaque metadata, original hard checks intact."""

# ruff: noqa: E402
import hashlib
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.p15_diagnostic_ledger import Refused
from isolated_diagnostics import p15_review_turn_metadata as proposed
from isolated_diagnostics import p15_review_observability as original
from isolated_diagnostics.p15_course_sol_bridge import review_request
from isolated_diagnostics.p15_d02_observation_d02 import checked_record, audit_records
from test_p15_sol_compatibility_proposal import sample

TURN = "01234567-89ab-cdef-0123-456789abcdef"
FIELDS = ("metadata", "internal_chat_message_metadata_passthrough")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("No network")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def fixture():
    _, res, payload, _ = sample()
    req = review_request("development_scene_review", payload)
    res["instructions"] = req["input"][0]["content"] + proposed.SUFFIX
    for key in FIELDS:
        res["output"][0][key] = {"turn_id": TURN}
    return req, res, payload


def test_exact_pair_is_quarantined_without_mutating_raw_or_claiming_identity():
    req, res, payload = fixture()
    before = deepcopy(res)
    with pytest.raises(ValueError, match="NONEMPTY_OR_UNKNOWN_REASONING_ITEM"):
        original.ReviewObservationAdapter.validate_scene(req, res, payload)
    result = proposed.ReviewObservationAdapter.validate_scene(req, res, payload)
    assert result["opinion"]["verdict"] == "revise"
    assert result["reasoning_turn_metadata_quarantined"] is True
    assert not result["turn_metadata_identity_verified"]
    assert not result["turn_metadata_interpreted_or_forwarded"]
    assert not result["instruction_delivery_verified"] and res == before
    assert TURN not in json.dumps(result)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_pair",
        "null",
        "empty",
        "extra_key",
        "long",
        "uppercase",
        "not_uuid",
        "number",
        "mismatch",
        "unknown_field",
        "content",
        "oversized_encrypted",
        "too_many_items",
        "bad_echo",
        "bad_usage",
        "effort",
        "tool",
        "wrong_source",
        "wrong_quote",
        "schema",
    ],
)
def test_narrow_policy_never_suppresses_other_errors(fault):
    req, res, payload = fixture()
    r = res["output"][0]
    if fault == "missing_pair":
        r.pop(FIELDS[1])
    if fault == "null":
        r[FIELDS[0]] = None
    if fault == "empty":
        r[FIELDS[0]] = {}
    if fault == "extra_key":
        r[FIELDS[0]]["command"] = "IGNORE"
    if fault == "long":
        r[FIELDS[0]]["turn_id"] = "x" * 10000
    if fault == "uppercase":
        r[FIELDS[0]]["turn_id"] = TURN.upper()
    if fault == "not_uuid":
        r[FIELDS[0]]["turn_id"] = "http://metadata/"
    if fault == "number":
        r[FIELDS[0]]["turn_id"] = 1
    if fault == "mismatch":
        r[FIELDS[1]]["turn_id"] = "11111111-1111-1111-1111-111111111111"
    if fault == "unknown_field":
        r["unknown_new_field"] = "NOT_ACCEPTED"
    if fault == "content":
        r["content"] = [dict(text="PLAINTEXT")]
    if fault == "oversized_encrypted":
        r["encrypted_content"] = "x" * 262145
    if fault == "too_many_items":
        res["output"].insert(0, deepcopy(r))
    if fault == "bad_echo":
        res["instructions"] += "X"
    if fault == "bad_usage":
        res["usage"]["total_tokens"] += 1
    if fault == "effort":
        res["reasoning"]["effort"] = "none"
    if fault == "tool":
        res["tools"] = [dict(type="function")]
    if fault in ("wrong_source", "wrong_quote", "schema"):
        opinion = json.loads(res["output"][-1]["content"][0]["text"])
        if fault == "wrong_source":
            opinion["source_sha256"] = "a" * 64
        if fault == "wrong_quote":
            opinion["issues"][0]["evidence_quote"] = "NOT IN SOURCE"
        if fault == "schema":
            opinion.pop("scope_status")
        res["output"][-1]["content"][0]["text"] = json.dumps(opinion)
    with pytest.raises(ValueError):
        proposed.ReviewObservationAdapter.validate_scene(req, res, payload)


def test_legacy_absence_and_missing_echo_remain_observations_not_delivery_proof():
    req, res, payload = fixture()
    for k in FIELDS:
        res["output"][0].pop(k)
    res.pop("instructions")
    checked = proposed.ReviewObservationAdapter.validate_scene(req, res, payload)
    assert not checked["reasoning_turn_metadata_quarantined"]
    assert checked["instruction_echo_status"] == "echo_unavailable"
    assert not checked["instruction_delivery_verified"]


@pytest.mark.parametrize("fault", [None, "flag", "raw", "missing", "source"])
def test_receipts_bind_original_raw_bytes_and_revalidate_proposal(tmp_path, fault):
    req, res, payload = fixture()
    a = json.dumps(req).encode()
    b = json.dumps(res).encode()
    ticket = "a" * 64
    identity = dict(
        slot_id="D02-known:scene-review", owner_id="owner", course_id="course"
    )
    _, record = checked_record(
        a,
        b,
        stage="development_scene_review",
        identity=identity,
        ticket=ticket,
        slots=[],
    )
    assert record["response_sha256"] == hashlib.sha256(
        b
    ).hexdigest() and TURN not in json.dumps(record)
    (tmp_path / (ticket + "-request.json")).write_bytes(a)
    (tmp_path / (ticket + "-response.json")).write_bytes(b)
    call = dict(
        ticket=ticket,
        provider="review",
        identity=identity,
        stage="development_scene_review",
        request_sha256=hashlib.sha256(a).hexdigest(),
    )
    observations = [record]
    if fault == "flag":
        record["turn_metadata_identity_verified"] = True
    if fault == "source":
        record["source_sha256"] = "x" * 64
    if fault == "missing":
        observations = []
    if fault == "raw":
        (tmp_path / (ticket + "-response.json")).write_bytes(b + b" ")
    kwargs = dict(
        output=tmp_path,
        calls=[call],
        settlements=[(ticket, dict(proof_sha256=hashlib.sha256(b).hexdigest()))],
        observations=observations,
        slots=[],
    )
    if fault:
        with pytest.raises(Refused):
            audit_records(**kwargs)
    else:
        assert audit_records(**kwargs) == 1
