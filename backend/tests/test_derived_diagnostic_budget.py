"""Synthetic-only tests for ADR-0014. No actual run approval, credential or network."""

import copy
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support import claim_review_prototype as p  # noqa: E402
from acceptance_support import derived_diagnostic_budget as d  # noqa: E402
from acceptance_support.phase1_budget import Approval, FrozenBudget, GateFailure  # noqa: E402


def manifest(root, *, k=2, corrections=0, cases=1):
    root.mkdir(parents=True, exist_ok=True)
    (root / "proof.txt").write_text(
        "Synthetic evidence only; never a real tokenizer/pricing proof."
    )
    proof = hashlib.sha256((root / "proof.txt").read_bytes()).hexdigest()
    stages = {
        s: {
            "system": f"Fixed synthetic {s} instruction",
            "schema": {"type": "object"},
            "max_wire_bytes": 16384,
            "max_result_bytes": 8192,
            "input_overhead_tokens": 1024,
            "max_output_tokens": 512,
            "input_price_micro_per_million": 2000000,
            "output_price_micro_per_million": 8000000,
            "proof_sha256": proof,
            "timeout_seconds": 30,
        }
        for s in d.STAGES
    }
    n = cases * ((k + 3) * (corrections + 1) + corrections)
    cost = sum(d.price(v, v["max_wire_bytes"]) for s, v in stages.items() if s != "correction")
    cost += (k - 1) * d.price(stages["claim"], stages["claim"]["max_wire_bytes"])
    cost = cases * ((corrections + 1) * cost + corrections * d.price(stages["correction"], 16384))
    return {
        "version": d.VERSION,
        "run_id": "synthetic-run",
        "phase": "diagnostic",
        "execution_root": str(root.resolve()),
        "ledger_path": "state/run.sqlite",
        "registry_path": "state/run.registry.json",
        "files": {"proof.txt": proof},
        "target": {"model": "synthetic-model", "target_sha256": p.digest("synthetic target")},
        "config": {"reasoning": "low", "temperature": 0},
        "currency": "CNY",
        "cases": [
            {
                "id": f"case{i}",
                "resource_type": "explanation",
                "content": {"markdown": "First assertion. Second assertion."},
                "reference_context": {"whole_code": "helper AND caller; all original invariants"},
                "label_sha256": p.digest("label is NEVER model data"),
            }
            for i in range(cases)
        ],
        "max_claims": k,
        "corrections": corrections,
        "stages": stages,
        "bounds": {
            "requests": n,
            "cost_micro": cost,
            "expires_at": int(time.time()) + 3600,
            "overall_seconds": 300,
        },
        "prerequisite_sha256": p.digest("synthetic prerequisite"),
    }


def approval(m):
    return Approval(
        p.digest(m),
        "diagnostic",
        m["bounds"]["requests"],
        m["bounds"]["cost_micro"],
        "a" * 64,
        True,
    )


@pytest.fixture
def make(tmp_path):
    instances = []

    def create(m=None, *, root=None, **kwargs):
        root = root or tmp_path / f"root{len(instances)}"
        m = m or manifest(root, **kwargs)
        budget = d.DerivedBudget(m, root=root, approval=approval(m))
        instances.append(budget)
        return budget, m

    yield create
    for b in instances:
        b.close()


def issue(message="Synthetic located defect"):
    return {"area": "fact", "severity": "major", "message": message}


def sample_value(b, request):
    body = json.loads(request["wire"])
    payload = json.loads(body["input"][1]["content"])
    candidate = payload["candidate"]
    snap = p.freeze(
        candidate["resource_type"],
        candidate["content"],
        candidate["reference_context"],
        {"target": b.manifest["target"], "config": b.manifest["config"]},
    )
    stage = request["slot"].split(".")[-2]
    if stage == "inventory":
        block = snap.blocks[0]
        quotes = [q.strip() for q in block["text"].split(".") if q.strip()]

        def claim(q):
            start = block["text"].index(q)
            return {
                "text": q,
                "anchors": [
                    {
                        "block_id": block["block_id"],
                        "start": start,
                        "end": start + len(q),
                        "quote": q,
                    }
                ],
                "related_anchors": [],
            }

        # Deliberately reverse model order; the server must sort it.
        return {
            "version": "claim-inventory-v1",
            "claims": [claim(q) for q in reversed(quotes)],
            "exclusions": [],
        }
    if stage == "coverage":
        return {
            "version": "claim-coverage-v1",
            "missing_claims": [],
            "uncertainties": [],
            "invalid_exclusions": [],
        }
    if stage == "correction":
        return {
            "resource_type": candidate["resource_type"],
            "content": {"markdown": "Updated first assertion. Updated second assertion."},
        }
    inv = payload["inventory"]
    cid = "__overall__" if stage == "overall" else payload["focus"]["claim_id"]
    result = {
        "version": "claim-overall-v1" if stage == "overall" else "claim-review-v1",
        "identity": p.binding(snap, inv, cid),
        "verdict": "pass",
        "findings": [],
        "incidental_findings": [],
    }
    if stage == "overall":
        result.update(uncovered=False, uncertain=False)
    return result


def bound_value(request, value):
    payload = json.loads(json.loads(request["wire"])["input"][1]["content"])
    return {"request_binding": payload["request_binding"], "result": value}


def step(b, *, edit=None, response=None):
    request = b.prepare()
    n = b.reserve(request["slot"], request["wire"], request["parents"])
    assert b.consume(n) == request["wire"]
    value = sample_value(b, request)
    if edit:
        edit(value)
    value = bound_value(request, value)
    args = {
        "value": value,
        "model": b.manifest["target"]["model"],
        "status": "completed",
        "input_tokens": 10,
        "output_tokens": 2,
        "response_sha256": p.digest(["synthetic", value]),
    }
    args.update(response or {})
    b.finish(n, **args)
    return request, value


def round_steps(b):
    result = []
    while True:
        try:
            result.append(step(b))
        except GateFailure as exc:
            assert exc.code == "CASE_REVIEW_REQUIRED"
            return result


def test_full_round_sorted_claims_complete_dag_and_no_auto_case_advance(make):
    b, m = make()
    steps = round_steps(b)
    assert len(steps) == 5
    focus = json.loads(json.loads(steps[2][0]["wire"])["input"][1]["content"])["focus"]
    assert focus["text"] == "First assertion"
    overall = steps[-1][0]
    assert len(overall["parents"]) == 4  # inventory, coverage, both claim receipts
    assert {r["number"] for r in overall["parents"]} == {1, 2, 3, 4}
    assert m["cases"][0]["label_sha256"].encode() not in overall["wire"]
    b.decide(
        "continue", assessment_sha256=p.digest("synthetic semantic observation, not human approval")
    )
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        b.prepare()
    report = b.snapshot()
    assert len(report["attempts"]) == 5
    assert all(r["state"] == "verified" for r in report["attempts"])
    assert sum(r["cost"] for r in report["attempts"]) <= m["bounds"]["cost_micro"]


def test_pre_reservation_crash_has_no_attempt_and_resume_keeps_deadline(make):
    b, m = make()
    root = b.root
    request = b.prepare()
    deadline = b.snapshot()["run"]["deadline"]
    b.close()
    resumed, _ = make(m, root=root)
    assert resumed.prepare() == request
    assert resumed.snapshot()["run"]["deadline"] == deadline
    assert resumed.snapshot()["attempts"] == []


@pytest.mark.parametrize("intent", [False, True])
def test_reserved_or_intent_restart_halts_and_never_refunds(make, intent):
    b, m = make()
    root = b.root
    req = b.prepare()
    n = b.reserve(req["slot"], req["wire"], req["parents"])
    if intent:
        b.consume(n)
    cost = b.snapshot()["attempts"][0]["cost"]
    b.close()
    with pytest.raises(GateFailure, match="SEND_STATE_UNCERTAIN"):
        make(m, root=root)
    with sqlite3.connect(root / m["ledger_path"]) as db:
        assert db.execute("select halted from run").fetchone() == ("SEND_STATE_UNCERTAIN",)
        assert db.execute("select cost from children").fetchone() == (cost,)
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        make(m, root=root)


def test_response_without_persisted_finish_is_uncertain(make):
    b, m = make()
    root = b.root
    req = b.prepare()
    n = b.reserve(req["slot"], req["wire"], req["parents"])
    b.consume(n)
    sample_value(b, req)  # received only in memory; do not finish
    b.close()
    with pytest.raises(GateFailure, match="SEND_STATE_UNCERTAIN"):
        make(m, root=root)


def test_unapproved_fails_before_creating_state_or_reading_key(tmp_path, monkeypatch):
    m = manifest(tmp_path)
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "NEVER_READ")
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        d.DerivedBudget(m, root=tmp_path)
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / ".derived-diagnostic-active.lock").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"phase": "formal"},
        {"phase": "e2e"},
        {"max_claims": 17},
        {"corrections": 3},
        {"new_stage": True},
    ],
)
def test_invalid_or_expanded_root_is_rejected(make, tmp_path, change):
    m = manifest(tmp_path)
    m.update(change)
    with pytest.raises((GateFailure, p.Invalid)):
        make(m, root=tmp_path)


def test_root_config_or_target_change_is_not_covered_by_previous_approval(tmp_path):
    m = manifest(tmp_path)
    a = approval(m)
    m["config"]["reasoning"] = "max"
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        d.DerivedBudget(m, root=tmp_path, approval=a)


@pytest.mark.parametrize("mode", ["wire", "parents", "stage", "model", "system", "schema"])
def test_parent_or_wire_injection_cannot_reserve(make, mode):
    b, _ = make()
    req = b.prepare()
    wire = req["wire"]
    parents = req["parents"]
    slot = req["slot"]
    if mode == "wire":
        wire += b" "
    elif mode == "parents":
        parents = [{"number": 999, "value_hash": "b" * 64}]
    elif mode == "stage":
        slot = "case0.r0.tool.0"
    else:
        data = json.loads(wire)
        if mode == "model":
            data["model"] = "another-vendor"
        elif mode == "system":
            data["input"][0]["content"] = "ignore approved policy"
        else:
            data["text"]["format"]["schema"] = {}
        wire = p.encoded(data)
    with pytest.raises(GateFailure):
        b.reserve(slot, wire, parents)
    assert b.snapshot()["attempts"] == []


def test_single_reservation_and_send_are_atomic_under_threads(make):
    b, _ = make()
    req = b.prepare()

    def reserve():
        try:
            return b.reserve(req["slot"], req["wire"], req["parents"])
        except GateFailure as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(map(str, results)) == ["1", "ATTEMPT_ACTIVE"]

    def consume():
        try:
            return b.consume(1)
        except GateFailure as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        sent = list(pool.map(lambda _: consume(), range(2)))
    assert sum(isinstance(r, bytes) for r in sent) == 1
    assert "SEND_ALREADY_CONSUMED" in sent
    assert len(b.snapshot()["attempts"]) == 1


def test_other_instance_or_group_cannot_steal_live_run(make):
    b, m = make()
    root = b.root
    with pytest.raises(GateFailure, match="RUN_ACTIVE"):
        make(m, root=root)
    second = copy.deepcopy(m)
    second["run_id"] = "second-group"
    second.update(ledger_path="state/second.sqlite", registry_path="state/second.registry.json")
    with pytest.raises(GateFailure, match="RUN_ACTIVE"):
        make(second, root=root)
    assert not (root / "state/second.sqlite").exists()


@pytest.mark.parametrize(
    "change,code",
    [
        ({"model": "other"}, "INVALID_OUTPUT"),
        ({"status": "incomplete"}, "INVALID_OUTPUT"),
        ({"input_tokens": None}, "UNKNOWN_USAGE"),
        ({"output_tokens": True}, "UNKNOWN_USAGE"),
        ({"output_tokens": 999999}, "USAGE_EXCEEDED"),
        ({"response_sha256": "bad"}, "INVALID_OBSERVATION"),
    ],
)
def test_bad_receipts_halt_keep_attempt_and_cannot_continue(make, change, code):
    b, _ = make()
    with pytest.raises(GateFailure, match=code):
        step(b, response=change)
    snap = b.snapshot()
    assert snap["run"]["halted"] == code and len(snap["attempts"]) == 1
    assert snap["attempts"][0]["state"] == "failed"
    assert snap["attempts"][0]["cost"] > 0
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        b.prepare()


def test_schema_validation_is_real_and_refs_cannot_trigger_io(make, tmp_path):
    m = manifest(tmp_path)
    m["stages"]["inventory"]["schema"] = {"type": "object", "required": ["absent"]}
    b, _ = make(m, root=tmp_path)
    with pytest.raises(GateFailure, match="INVALID_OUTPUT_SCHEMA"):
        step(b)
    m2 = manifest(tmp_path / "other")
    m2["stages"]["inventory"]["schema"] = {"$ref": "http://metadata/private"}
    with pytest.raises(GateFailure, match="SCHEMA_REFERENCE_FORBIDDEN"):
        make(m2, root=tmp_path / "other")


def test_sources_changed_halt_durably_even_if_restored(make):
    b, _ = make()
    proof = b.root / "proof.txt"
    old = proof.read_text()
    proof.write_text("changed")
    with pytest.raises(GateFailure, match="FREEZE_CHANGED"):
        b.prepare()
    proof.write_text(old)
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        b.prepare()


def test_receipt_mutation_or_missing_parent_is_detected(make):
    b, _ = make()
    step(b)
    step(b)
    req = b.prepare()
    assert len(req["parents"]) == 2
    with pytest.raises(GateFailure, match="DERIVATION_MISMATCH"):
        b.reserve(req["slot"], req["wire"], req["parents"][:1])
    assert b.snapshot()["run"]["halted"] == "DERIVATION_MISMATCH"
    other, _ = make()
    step(other)
    with sqlite3.connect(other.ledger) as db:
        db.execute("update children set value_hash=? where number=1", ("b" * 64,))
    with pytest.raises(GateFailure, match="PARENT_HASH_MISMATCH"):
        other.prepare()
    assert other.snapshot()["run"]["halted"] == "PARENT_HASH_MISMATCH"


def test_registry_or_ledger_cannot_be_replaced_or_repathed(make, tmp_path):
    b, m = make()
    root = b.root
    b.close()
    (root / m["ledger_path"]).unlink()
    with pytest.raises(GateFailure, match="LEDGER_MISSING"):
        make(m, root=root)
    clone = tmp_path / "clone"
    shutil.copytree(root, clone)
    with pytest.raises(GateFailure, match="ROOT_CHANGED"):
        make(m, root=clone)


@pytest.mark.parametrize(
    "field,value", [("ledger_path", "../escape.sqlite"), ("registry_path", "/tmp/other.json")]
)
def test_path_escape_rejected(make, tmp_path, field, value):
    m = manifest(tmp_path)
    m[field] = value
    with pytest.raises(GateFailure, match="UNSAFE_PATH"):
        make(m, root=tmp_path)


def test_symlink_paths_and_world_readable_ledger_are_rejected(make, tmp_path):
    m = manifest(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "state").symlink_to(outside, target_is_directory=True)
    with pytest.raises(GateFailure, match="UNSAFE_PATH"):
        make(m, root=tmp_path)
    b, m = make()
    root = b.root
    b.close()
    (root / m["ledger_path"]).chmod(0o644)
    with pytest.raises(GateFailure, match="LEDGER_UNSAFE"):
        make(m, root=root)


def test_worst_case_budget_must_cover_all_reachable_slots(make, tmp_path):
    m = manifest(tmp_path, k=16, corrections=2)
    assert m["bounds"]["requests"] == 59
    m["bounds"]["cost_micro"] -= 1
    with pytest.raises(GateFailure, match="INSUFFICIENT_WORST_CASE_BUDGET"):
        make(m, root=tmp_path)


def test_clock_rollback_and_expiry_halt_without_reset(make, monkeypatch):
    b, m = make()
    last = b.snapshot()["run"]["last_clock"]
    monkeypatch.setattr(d.time, "time", lambda: last - 1)
    with pytest.raises(GateFailure, match="CLOCK_ROLLBACK"):
        b.prepare()


def test_reopened_complete_receipts_resume_only_next_unreserved_slot(make):
    b, m = make()
    step(b)
    root = b.root
    before = b.snapshot()
    b.close()
    resumed, _ = make(m, root=root)
    assert resumed.prepare()["slot"] == "case0.r0.coverage.0"
    assert resumed.snapshot()["run"]["deadline"] == before["run"]["deadline"]
    assert len(resumed.snapshot()["attempts"]) == 1


def test_two_cases_require_explicit_assessment_not_model_pass(make):
    b, _ = make(cases=2)
    round_steps(b)
    with pytest.raises(GateFailure, match="CASE_REVIEW_REQUIRED"):
        b.prepare()
    b.decide("continue", assessment_sha256=p.digest("synthetic case review"))
    assert b.prepare()["slot"] == "case1.r0.inventory.0"
    round_steps(b)
    b.decide("continue", assessment_sha256=p.digest("synthetic second case review"))
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        b.prepare()


def test_corrections_restart_with_new_snapshot_and_full_dag(make):
    b, _ = make(corrections=2)
    step(b)
    step(b)
    step(b, edit=lambda v: v.update(verdict="revise", findings=[issue()]))
    step(b)
    step(b)
    b.decide("correct", assessment_sha256=p.digest("synthetic complete revision gate"))
    req, _ = step(b)
    assert req["slot"] == "case0.r0.correction.0" and len(req["parents"]) == 5
    next_req = b.prepare()
    assert next_req["slot"] == "case0.r1.inventory.0" and len(next_req["parents"]) == 1
    data = json.loads(json.loads(next_req["wire"])["input"][1]["content"])
    assert data["candidate"]["content"]["markdown"].startswith("Updated")
    round_steps(b)
    b.decide("continue", assessment_sha256=p.digest("synthetic case final review"))
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        b.prepare()
    assert len(b.snapshot()["attempts"]) == 11


def test_legacy_v1_rejects_new_contract_without_changes(make):
    b, m = make()
    with pytest.raises(GateFailure, match="INVALID_FREEZE"):
        FrozenBudget(m, b.root / "legacy.sqlite", root=b.root, approval=approval(m))


def test_stage_deadline_expires_before_overall_deadline(make, monkeypatch):
    b, _ = make()
    req = b.prepare()
    n = b.reserve(req["slot"], req["wire"], req["parents"])
    last = b.snapshot()["run"]["last_clock"]
    monkeypatch.setattr(d.time, "time", lambda: last + 31)
    with pytest.raises(GateFailure, match="ATTEMPT_TIMEOUT"):
        b.consume(n)
    assert b.snapshot()["run"]["halted"] == "ATTEMPT_TIMEOUT"
    assert len(b.snapshot()["attempts"]) == 1


def test_late_completed_result_does_not_pass(make, monkeypatch):
    b, _ = make()
    req = b.prepare()
    n = b.reserve(req["slot"], req["wire"], req["parents"])
    b.consume(n)
    last = b.snapshot()["run"]["last_clock"]
    value = sample_value(b, req)
    monkeypatch.setattr(d.time, "time", lambda: last + 31)
    with pytest.raises(GateFailure, match="ATTEMPT_TIMEOUT"):
        b.finish(
            n,
            value=bound_value(req, value),
            model=b.manifest["target"]["model"],
            status="completed",
            input_tokens=10,
            output_tokens=2,
            response_sha256=p.digest(value),
        )
    assert b.snapshot()["attempts"][0]["state"] == "failed"


@pytest.mark.parametrize("field,value", [("input_tokens", 10**100), ("output_tokens", 10**100)])
def test_unrepresentable_usage_halts_without_sqlite_integer_overflow(make, field, value):
    b, _ = make()
    with pytest.raises(GateFailure, match="USAGE_EXCEEDED"):
        step(b, response={field: value})
    assert b.snapshot()["run"]["halted"] == "USAGE_EXCEEDED"
    assert b.snapshot()["attempts"][0][field] is None


def test_result_size_and_early_inventory_claim_limit(make, tmp_path):
    m = manifest(tmp_path)
    m["stages"]["inventory"]["max_result_bytes"] = 10
    b, _ = make(m, root=tmp_path)
    with pytest.raises(GateFailure, match="RESULT_TOO_LARGE"):
        step(b)
    other, m = make()

    def add_claim(value):
        new = copy.deepcopy(value["claims"][0])
        new["text"] = "Distinct interpretation, same exact source"
        value["claims"].append(new)

    with pytest.raises(GateFailure, match="CLAIM_LIMIT"):
        step(other, edit=add_claim)
    assert len(other.snapshot()["attempts"]) == 1


def test_coverage_uncertainty_stops_before_any_claim(make):
    b, _ = make()
    step(b)
    with pytest.raises(GateFailure, match="COVERAGE_UNRESOLVED"):
        step(b, edit=lambda v: v.update(uncertainties=["Synthetic uncertain coverage"]))
    assert len(b.snapshot()["attempts"]) == 2


def test_correct_declines_without_correction_permission(make):
    b, _ = make()
    step(b)
    step(b)
    step(b, edit=lambda v: v.update(verdict="revise", findings=[issue()]))
    step(b)
    step(b)
    with pytest.raises(GateFailure, match="CORRECTION_NOT_APPROVED"):
        b.decide("correct", assessment_sha256=p.digest("synthetic request"))
    assert len(b.snapshot()["attempts"]) == 5


def test_all_59_slots_keep_single_budget_and_two_corrections(make, tmp_path):
    m = manifest(tmp_path, k=16, corrections=2)
    m["cases"][0]["content"] = {"markdown": ". ".join(f"Clause{i}" for i in range(16)) + "."}
    b, m = make(m, root=tmp_path)
    for r in range(3):
        step(b)
        step(b)
        step(b, edit=lambda v: v.update(verdict="revise", findings=[issue()]))
        for _ in range(15):
            step(b)
        step(b)
        if r < 2:
            b.decide("correct", assessment_sha256=p.digest(["synthetic revision gate", r]))
            step(b, edit=lambda v: v.update(content=m["cases"][0]["content"]))
    assert len(b.snapshot()["attempts"]) == 59
    with pytest.raises(GateFailure, match="CORRECTION_NOT_APPROVED"):
        b.decide("correct", assessment_sha256=p.digest("must not create a third correction"))
    b.decide("continue", assessment_sha256=p.digest("synthetic diagnostic case gate"))
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        b.prepare()
    assert len(b.snapshot()["attempts"]) == 59
    assert sum(a["cost"] for a in b.snapshot()["attempts"]) <= m["bounds"]["cost_micro"]


def test_zero_network_even_through_schema_validation(make, monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        pytest.fail("Network attempted in zero-call mechanism test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    b, _ = make()
    round_steps(b)
    assert len(b.snapshot()["attempts"]) == 5


def test_identical_cases_cannot_replay_previous_slot_response(make):
    b, _ = make(cases=2)
    req = b.prepare()
    old = bound_value(req, sample_value(b, req))
    round_steps(b)
    b.decide("continue", assessment_sha256=p.digest("synthetic first case gate"))
    new = b.prepare()
    n = b.reserve(new["slot"], new["wire"], new["parents"])
    b.consume(n)
    with pytest.raises(GateFailure, match="RESPONSE_BINDING_MISMATCH"):
        b.finish(
            n,
            value=old,
            model=b.manifest["target"]["model"],
            status="completed",
            input_tokens=10,
            output_tokens=2,
            response_sha256=p.digest(old),
        )
    assert b.snapshot()["run"]["halted"] == "RESPONSE_BINDING_MISMATCH"


def test_escaped_data_is_counted_from_actual_wire_and_cannot_exceed_frozen_bound(make, tmp_path):
    m = manifest(tmp_path)
    m["cases"][0]["content"] = {"markdown": "\x00" * 4000}
    b, _ = make(m, root=tmp_path)
    req = b.prepare()
    assert len(req["wire"]) > m["stages"]["inventory"]["max_wire_bytes"]
    with pytest.raises(GateFailure, match="INPUT_BOUND_EXCEEDED"):
        b.reserve(req["slot"], req["wire"], req["parents"])
    assert b.snapshot()["attempts"] == []
    assert b.snapshot()["run"]["halted"] == "INPUT_BOUND_EXCEEDED"


def test_registry_content_change_prevents_any_new_reservation(make):
    b, _ = make()
    b.registry.write_text("{}")
    with pytest.raises(GateFailure, match="REGISTRY_MISMATCH"):
        b.prepare()


@pytest.mark.parametrize("count", [True, -1, 3])
def test_reasoning_subcount_must_be_numeric_and_inside_total(make, count):
    b, _ = make()
    with pytest.raises(GateFailure, match="INVALID_OBSERVATION"):
        step(b, response={"reasoning_tokens": count})
    assert b.snapshot()["run"]["halted"] == "INVALID_OBSERVATION"


def test_unknown_reasoning_remains_null_and_known_is_not_added_to_total(make):
    b, _ = make()
    step(b, response={"reasoning_tokens": 1})
    step(b)
    rows = b.snapshot()["attempts"]
    assert rows[0]["output_tokens"] == 2 and rows[0]["reasoning_tokens"] == 1
    assert rows[1]["reasoning_tokens"] is None


def test_bool_parent_id_is_not_equal_to_valid_integer_id(make):
    b, _ = make()
    step(b)
    req = b.prepare()
    req["parents"][0]["number"] = True
    with pytest.raises(GateFailure, match="DERIVATION_MISMATCH"):
        b.reserve(req["slot"], req["wire"], req["parents"])
    assert len(b.snapshot()["attempts"]) == 1


def test_bool_attempt_number_cannot_consume_or_double_send(make):
    b, _ = make()
    req = b.prepare()
    b.reserve(req["slot"], req["wire"], req["parents"])
    with pytest.raises(GateFailure, match="INVALID_ATTEMPT"):
        b.consume(True)
    assert b.snapshot()["attempts"][0]["state"] == "reserved"


@pytest.mark.parametrize("intent", [False, True])
def test_transport_abort_keeps_reservation_with_unknown_usage(make, intent):
    b, _ = make()
    req = b.prepare()
    n = b.reserve(req["slot"], req["wire"], req["parents"])
    if intent:
        b.consume(n)
    before = b.snapshot()["attempts"][0]["cost"]
    with pytest.raises(GateFailure, match="RATE_LIMITED"):
        b.abort(n, error_code="RATE_LIMITED")
    report = b.snapshot()
    assert report["run"]["halted"] == "RATE_LIMITED"
    assert report["attempts"][0]["cost"] == before
    assert report["attempts"][0]["input_tokens"] is None
    assert report["attempts"][0]["state"] == "failed"


def test_arbitrary_vendor_error_is_never_persisted(make):
    b, _ = make()
    req = b.prepare()
    n = b.reserve(req["slot"], req["wire"], req["parents"])
    with pytest.raises(GateFailure, match="INVALID_ABORT"):
        b.abort(n, error_code="PRIVATE_VENDOR_ERROR_TEXT")
    assert "PRIVATE_VENDOR_ERROR_TEXT" not in json.dumps(b.snapshot())
