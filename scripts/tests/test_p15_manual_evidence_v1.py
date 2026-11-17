"""Independent witness catches missing or changed ordinary and late originals."""

from copy import deepcopy
import hashlib
import json

import pytest

from scripts.isolated_diagnostics import p15_manual_evidence_v1 as evidence


def record(state):
    raw = b'{"usage":{"input_tokens":10,"output_tokens":20,"total_tokens":30}}'
    request = b"synthetic-request"
    row = dict(number=1, slot="slot", arm="B", stage="B_generate", request_sha256=hashlib.sha256(request).hexdigest(),
               request_original="request-1", parent_receipt=None,
               state=state, original="raw-1", response_sha256=hashlib.sha256(raw).hexdigest(),
               status=200, usage={"input": 10, "output": 20})
    seal(row)
    return row, {"raw-1": raw, "request-1": request}


def seal(row):
    material = {key: value for key, value in row.items() if key != "receipt_sha256"}
    row["receipt_sha256"] = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


@pytest.mark.parametrize("state", ["responded", "late"])
def test_missing_original_and_recomputed_ledger_cannot_be_verified(state):
    witness, files = record(state)
    ledger = deepcopy(witness)
    assert evidence.verify([witness], [ledger], files.__getitem__, files.__getitem__) == "verified"
    del files["raw-1"]
    assert evidence.verify([witness], [ledger], files.__getitem__, files.__getitem__) == "unknown"
    ledger.update(original=None, response_sha256=None, status=None, usage=None)
    assert evidence.verify([witness], [ledger], files.__getitem__, files.__getitem__) == "unknown"


def test_tampered_original_missing_witness_and_unknown_are_not_verified():
    witness, files = record("late")
    ledger = deepcopy(witness)
    files["raw-1"] = b"changed"
    assert evidence.verify([witness], [ledger], files.__getitem__, files.__getitem__) == "unknown"
    assert evidence.verify([], [ledger], files.__getitem__, files.__getitem__) == "unknown"
    witness["state"] = ledger["state"] = "unknown"
    assert evidence.verify([witness], [ledger], files.__getitem__, files.__getitem__) == "unknown"
    assert evidence.verify([], [], files.__getitem__, files.__getitem__) == "unknown"


def test_duplicate_usage_keys_are_not_trusted_even_with_matching_digest():
    witness, files = record("responded")
    raw = b'{"usage":{"input_tokens":10,"input_tokens":10,"output_tokens":20,"total_tokens":30}}'
    files["raw-1"] = raw
    witness["response_sha256"] = hashlib.sha256(raw).hexdigest()
    seal(witness)
    assert evidence.verify([witness], [deepcopy(witness)], files.__getitem__, files.__getitem__) == "unknown"


def test_missing_or_tampered_request_bytes_do_not_verify():
    witness, files = record("responded")
    files["request-1"] = b"tampered"
    assert evidence.verify([witness], [deepcopy(witness)], files.__getitem__, files.__getitem__) == "unknown"
