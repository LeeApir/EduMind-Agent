"""Offline failure, restart and concurrency tests; callbacks never contact a Provider."""

import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support.phase1_budget import Approval, FrozenBudget, GateFailure, canonical, sha
from acceptance_support.phase1_metrics import score_review


@pytest.fixture
def envelope(tmp_path):
    (tmp_path / "approved.txt").write_text("synthetic approval evidence")
    digest = sha((tmp_path / "approved.txt").read_bytes())
    target = "b" * 64
    manifest = {
        "version": "phase1-run-v1",
        "run_id": "offline-test",
        "state": "FROZEN_RUN_READY",
        "phase": "connection",
        "files": {"approved.txt": digest},
        "targets": {
            target: {
                "provider_type": "openai-compatible",
                "model_id": "mock",
                "adapter_sha256": digest,
                "capability_sha256": digest,
                "model_revision": "unknown",
                "currency": "USD",
                "input_price_micro_per_million": 1000000,
                "output_price_micro_per_million": 1000000,
                "input_overhead_tokens": 10,
                "max_wire_bytes": 1000,
                "max_total_output_tokens": 100,
                "total_output_limit_verified": True,
                "token_byte_bound_verified": True,
                "output_limit_path": ["max_tokens"],
            }
        },
        "slots": [
            {
                "id": "case",
                "input_sha256": digest,
                "attempts": 10,
                "stages": ["review", "correction"],
                "targets": [target],
                "resources": ["dsl", "code"],
            }
        ],
        "bounds": {
            "requests": 10,
            "cost_micro": 10000,
            "max_active_attempts": 1,
            "timeout_seconds": 60,
            "corrections_per_resource": 2,
        },
        "required_evidence": ["adr"],
        "evidence": {"adr": digest},
    }

    def build(value=None, authorized=True):
        value = manifest if value is None else value
        approval = Approval(
            sha(canonical(value)),
            value["phase"],
            value["bounds"]["requests"],
            value["bounds"]["cost_micro"],
            "c" * 64,
            authorized,
        )
        return FrozenBudget(value, tmp_path / "ledger.sqlite", root=tmp_path, approval=approval)

    return manifest, target, build


def test_unapproved_never_calls_or_creates_ledger(envelope, tmp_path):
    _, target, build = envelope
    called = []
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        build(authorized=False).attempt(
            "case", "review", target, b'{"max_tokens":10}', lambda: called.append(1)
        )
    assert not called and not (tmp_path / "ledger.sqlite").exists()


@pytest.mark.parametrize("field,value", [("requests", 0), ("cost_micro", 0)])
def test_zero_cap_stops_before_callback(envelope, field, value):
    manifest, target, build = envelope
    manifest["bounds"][field] = value
    called = []
    gate = build()
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        gate.attempt("case", "review", target, b'{"max_tokens":10}', lambda: called.append(1))
    assert not called and gate.snapshot()["attempts"] == []


@pytest.mark.parametrize(
    "wire",
    [
        b'{"max_tokens":101}',
        b'{"max_tokens":true}',
        b'{"max_tokens":10.0}',
        b'{"max_tokens":1,"max_tokens":2}',
        b"{}",
        b"null",
        b"\xff",
    ],
)
def test_actual_wire_cap_is_checked_before_reservation(envelope, wire):
    _, target, build = envelope
    gate = build()
    with pytest.raises(GateFailure, match="UNKNOWN_COST_BOUND"):
        gate.reserve("case", "review", target, wire)
    assert gate.snapshot()["attempts"] == []


def test_file_change_stops_before_send(envelope, tmp_path):
    _, target, build = envelope
    gate = build()
    (tmp_path / "approved.txt").write_text("changed")
    with pytest.raises(GateFailure, match="FREEZE_CHANGED"):
        gate.reserve("case", "review", target, b'{"max_tokens":10}')
    assert not (tmp_path / "ledger.sqlite").exists()


@pytest.mark.parametrize(
    "error,usage",
    [("TIMEOUT", (None, None)), (None, (None, None)), (None, (10000, 1)), (None, (1, 101))],
)
def test_failure_unknown_or_over_bound_halts_persistently(envelope, error, usage):
    _, target, build = envelope
    gate = build()
    n = gate.reserve("case", "review", target, b'{"max_tokens":10}')
    gate.finish(n, error_code=error, input_tokens=usage[0], output_tokens=usage[1])
    restarted = build()
    assert restarted.snapshot()["halted"]
    assert restarted.snapshot()["attempts"][0][5] > 0
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        restarted.reserve("case", "review", target, b'{"max_tokens":10}')


def test_concurrent_reservation_and_restart(envelope):
    _, target, build = envelope

    def reserve():
        try:
            return build().reserve("case", "review", target, b'{"max_tokens":10}')
        except GateFailure as e:
            return e.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: reserve(), range(4)))
    assert results.count(1) == 1 and results.count("ATTEMPT_ACTIVE") == 3
    assert len(build().snapshot()["attempts"]) == 1


def test_two_corrections_per_resource_and_no_refund(envelope):
    _, target, build = envelope
    gate = build()
    for resource in ("dsl", "code"):
        for _ in range(2):
            n = gate.reserve("case", "correction", target, b'{"max_tokens":10}', resource=resource)
            gate.finish(n, input_tokens=1, output_tokens=1)
        with pytest.raises(GateFailure, match="SLOT_EXHAUSTED"):
            gate.reserve("case", "correction", target, b'{"max_tokens":10}', resource=resource)
    assert len(gate.snapshot()["attempts"]) == 4
    assert all(row[5] >= 100 for row in gate.snapshot()["attempts"])


def test_ledger_cannot_be_reused_for_changed_freeze(envelope):
    manifest, target, build = envelope
    build().reserve("case", "review", target, b'{"max_tokens":10}')
    changed = copy.deepcopy(manifest)
    changed["run_id"] = "different"
    with pytest.raises(GateFailure, match="LEDGER_MISMATCH"):
        build(changed).snapshot()


@pytest.mark.parametrize("verified", ["total_output_limit_verified", "token_byte_bound_verified"])
def test_unknown_fee_boundary_is_rejected(envelope, verified):
    manifest, target, build = envelope
    manifest["targets"][target][verified] = False
    with pytest.raises(GateFailure, match="UNKNOWN_COST_BOUND"):
        build()


def test_prior_phase_evidence_required(envelope):
    manifest, _, build = envelope
    manifest["phase"] = "formal"
    with pytest.raises(GateFailure, match="PREREQUISITE_MISSING"):
        build()


def test_missing_generic_reject_and_wrong_category_do_not_pass():
    cases = [
        {
            "id": "error",
            "kind": "severe_error",
            "input_sha256": "a" * 64,
            "target_defect": "double free",
            "expected_area": "code_safety",
        },
        {"id": "control", "kind": "correct_control", "input_sha256": "b" * 64},
        {"id": "long", "kind": "long_review", "input_sha256": "c" * 64},
    ]
    row = {
        "id": "error",
        "freeze": "x",
        "input_sha256": "a" * 64,
        "complete": True,
        "schema_valid": True,
        "human_annotation_bound": True,
        "verdict": "reject",
    }
    result = score_review(cases, [row], freeze="x")
    assert result["metrics"]["detection"] == {"numerator": 0, "denominator": 1}
    assert result["metrics"]["correct_pass"] == {"numerator": 0, "denominator": 1}
    assert not result["proposed_admission_met"] and result["missing"] == ["control", "long"]
    row.update(
        concrete_defect="double free",
        area="fact",
        response_sha256="d" * 64,
        annotated_response_sha256="d" * 64,
        annotation_sha256="e" * 64,
    )
    result = score_review(cases, [row], freeze="x")
    assert result["metrics"]["detection"]["numerator"] == 1
    assert result["metrics"]["classification"]["numerator"] == 0
    with pytest.raises(GateFailure, match="OBSERVATION_MISMATCH"):
        score_review(cases, [row, row], freeze="x")
    with pytest.raises(GateFailure, match="OBSERVATION_MISMATCH"):
        score_review(cases, [row], freeze="other")


def test_generation_missing_slots_and_invalid_publication_fail():
    from acceptance_support.phase1_metrics import score_generation

    slots = [{"id": f"s{i}", "input_sha256": "a" * 64} for i in range(100)]
    rows = [
        {
            "id": s["id"],
            "input_sha256": s["input_sha256"],
            "freeze": "one",
            "first_schema_valid": True,
            "published": True,
            "final_schema_valid": True,
            "all_three_reviewed": True,
        }
        for s in slots
    ]
    assert score_generation(slots, rows, freeze="one")["admission_met"]
    assert not score_generation(slots, rows[:99], freeze="one")["admission_met"]
    result = score_generation(slots, rows[:90], freeze="one")
    assert result["published"] == {"numerator": 90, "denominator": 100}
    assert not result["admission_met"] and len(result["missing"]) == 10
    rows[0]["final_schema_valid"] = False
    result = score_generation(slots, rows, freeze="one")
    assert not result["admission_met"] and result["invalid_publication"] == ["s0"]


def test_failed_admission_prevents_another_outbound_callback(envelope):
    from acceptance_support.phase1_metrics import enforce_admission

    _, target, build = envelope
    gate = build()
    cases = [
        {
            "id": "error",
            "kind": "severe_error",
            "input_sha256": "a" * 64,
            "target_defect": "double free",
            "expected_area": "code_safety",
        }
    ]
    result = score_review(cases, [], freeze=gate.freeze)
    with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
        enforce_admission(result, gate)
    called = []
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        gate.attempt("case", "review", target, b'{"max_tokens":10}', lambda: called.append(1))
    assert not called and gate.snapshot()["halted"] == "ADMISSION_FAILED"


def test_used_request_limit_survives_restart(envelope):
    manifest, target, build = envelope
    manifest["bounds"]["requests"] = 1
    gate = build()
    n = gate.reserve("case", "review", target, b'{"max_tokens":10}')
    gate.finish(n, input_tokens=1, output_tokens=1)
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        build().reserve("case", "review", target, b'{"max_tokens":10}')


def test_boolean_annotation_without_response_binding_not_detection():
    cases = [
        {
            "id": "error",
            "kind": "severe_error",
            "input_sha256": "a" * 64,
            "target_defect": "double free",
            "expected_area": "code_safety",
        }
    ]
    row = {
        "id": "error",
        "freeze": "one",
        "input_sha256": "a" * 64,
        "complete": True,
        "schema_valid": True,
        "human_annotation_bound": True,
        "concrete_defect": "double free",
        "area": "code_safety",
    }
    assert score_review(cases, [row], freeze="one")["metrics"]["detection"]["numerator"] == 0
