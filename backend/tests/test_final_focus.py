"""Final round: synthetic transport, frozen source lineage and independently checked controls."""

import asyncio
import ctypes
import itertools
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from test_fixed_focus import rig as r10_rig  # noqa: F401

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import prepare_t040_final_focus as prepare  # noqa: E402
import run_t040_final_focus as runner  # noqa: E402
from acceptance_support import claim_review_prototype as p  # noqa: E402
from acceptance_support.final_focus_contract import (  # noqa: E402
    SYSTEM,
    VERSION,
    FinalFocusGate,
    fixture,
)
from acceptance_support.phase1_budget import GateFailure  # noqa: E402


@pytest.fixture
def rig(r10_rig):  # noqa: F811 - pytest injects the imported fixture by name.
    root, prior, _, _, _, old_authorize, old_gate, old_step, old_evidence = r10_rig
    import run_t040_focus as old_runner

    old_authorize()
    old_step()
    old_runner.assess(root, old_evidence())
    old_step()
    b = old_gate()
    try:
        with b._db() as db:
            with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
                b._halt(db, "ADMISSION_FAILED")
    finally:
        b.close()
    files = [
        "scripts/prepare_t040_final_focus.py",
        "scripts/run_t040_final_focus.py",
        "scripts/acceptance_support/final_focus_contract.py",
        "backend/tests/test_final_focus.py",
        prepare.BASE_REL + "/samples.json",
        prepare.BASE_REL + "/scope.json",
        prepare.BASE_REL + "/token-cost-proof.json",
        prepare.PRIOR_REL + "/delegated-stop-focus-02.json",
    ]
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    previous = {
        "root_sha256": p.digest(prior),
        "state": "HALTED_ADMISSION_FAILED",
        "synthetic_test_only": True,
    }
    prior_path = root / prepare.PRIOR_REL / "results/r10-focus-02.json"
    prior_path.parent.mkdir(exist_ok=True)
    prior_path.write_bytes(p.encoded(previous))
    data = prepare.build(root)
    base = root / prepare.BASE_REL
    for name, value in data.items():
        (base / name).write_bytes(p.encoded(value))
    m, plan, requests = runner.load(root)
    state = {"sends": [], "edit": None}
    approval = {
        "version": "fixed-final-focus-run-approval-v1",
        "root_sha256": p.digest(m),
        "requests": 4,
        "cost_micro_cny": plan["cost_cap_micro_cny"],
        "scope_sha256": plan["scope_sha256"],
        "expires_at": plan["expires_at"],
        "exit_limits": plan["exit_limits"],
        "confirmed_by": "Lee",
        "user_confirmation": "Synthetic only; no real authorization",
        "source_message_id": "synthetic-final-round",
        "terms_verified_on": time.strftime("%Y-%m-%d"),
    }

    def authorize():
        (base / "run-approval.json").write_bytes(p.encoded(approval))
        return runner.approval(root, m, plan)

    async def handle(req):
        state["sends"].append(req)
        wire = json.loads(req.content)
        user = json.loads(wire["input"][1]["content"])
        n = len(state["sends"])
        area = ["fact", "code_safety", None, None][n - 1]
        value = {
            "version": "span-focus-review-v1",
            "request_id": user["request_id"],
            "verdict": "revise" if area else "pass",
            "uncertain": False,
            "findings": [{"area": area, "severity": "major", "message": "Synthetic finding"}]
            if area
            else [],
            "other_findings": [],
        }
        if state["edit"]:
            state["edit"](value)
        body = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        return httpx.Response(200, stream=httpx.ByteStream(p.encoded(body)))

    def step():
        return asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(handle),
                resolver=lambda host, port: ("8.8.8.8",),
            )
        )

    def assess(passed=True):
        report = runner.report(root)
        row = report["attempts"][-1]
        return runner.assess(
            root,
            {
                "root_sha256": report["root_sha256"],
                "number": row["number"],
                "value_hash": row["value_hash"],
                "passed": passed,
                "confirmed_by": "Lee",
                "user_confirmation": "Synthetic fact check",
                "source_message_id": "synthetic",
                "observation": "Synthetic only",
            },
        )

    return root, m, plan, requests, state, approval, authorize, step, assess


def test_contract_and_new_samples_do_not_send_labels():
    samples = json.loads((REPO / prepare.BASE_REL / "samples.json").read_bytes())
    assert [i["expected"] for i in samples["items"]] == ["fact", "code_safety", "pass", "pass"]
    for i in samples["items"]:
        item, req = fixture(i)
        assert item["claim"]["text"] in i["markdown"]
        assert req["system"] == SYSTEM and VERSION in SYSTEM
        assert not {"expected", "criterion", "title", "probe_id"} & set(req["payload"])
        assert "Do not force" in SYSTEM and "Other discoveries may be omitted" in SYSTEM
        assert "existing check has been deleted" in SYSTEM and "explicit preconditions" in SYSTEM


def test_not_authorized_does_not_enroll_final_round(rig):
    root, _, plan, _, state, _, _, step, _ = rig
    assert plan["last_round"] and plan["round"] == 2 and plan["provider_requests_authorized"] == 0
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        step()
    assert not state["sends"]
    assert not (root / "local-materials/span-selection-redesign-v1/round-2.json").exists()


@pytest.mark.parametrize("kind", ["wire", "env", "source"])
def test_final_source_or_credential_change_stops_before_http(rig, kind):
    root, _, _, _, state, _, authorize, step, _ = rig
    authorize()
    if kind == "wire":
        path = root / prepare.BASE_REL / "requests.json"
    elif kind == "env":
        path = root / ".env"
    else:
        path = root / "scripts/acceptance_support/final_focus_contract.py"
    path.write_text("synthetic changed source")
    with pytest.raises(GateFailure):
        step()
    assert not state["sends"]


def test_last_round_crash_cannot_replay_and_prior_run_is_unchanged(rig):
    root, m, plan, requests, state, _, authorize, step, _ = rig
    a = authorize()
    prior = root / "local-materials/phase-1-t040-focus-r10/budget.sqlite"
    original = prior.read_bytes()
    gate = FinalFocusGate(root, m, plan, requests, a)
    gate.consume(gate.reserve_next())
    gate.close()
    with pytest.raises(GateFailure, match="SAFETY_FAILURE"):
        step()
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        step()
    assert not state["sends"] and prior.read_bytes() == original


def test_third_round_or_unhalted_first_round_is_not_allowed(rig):
    root, m, plan, requests, state, _, authorize, _, _ = rig
    a = authorize()
    with pytest.raises(GateFailure, match="INVALID_ROUND"):
        FinalFocusGate(root, m, {**plan, "round": 3}, requests, a)
    # Synthetic-only prior ledger: model the unresolved prerequisite.
    import sqlite3

    prior = root / "local-materials/phase-1-t040-focus-r10/budget.sqlite"
    with sqlite3.connect(prior) as db:
        db.execute("UPDATE run SET halted=NULL")
    with pytest.raises(GateFailure, match="PREREQUISITE_MISSING"):
        FinalFocusGate(root, m, plan, requests, a)
    assert not state["sends"]


@pytest.mark.parametrize(
    "key,value",
    [("requests", 8), ("cost_micro_cny", 1), ("scope_sha256", "0" * 64), ("root_sha256", "0" * 64)],
)
def test_final_exact_approval_mismatch_rejected(rig, key, value):
    _, _, _, _, state, a, authorize, step, _ = rig
    a[key] = value
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        authorize()
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        step()
    assert not state["sends"]


def test_four_final_calls_pause_then_complete_without_formal_acceptance(rig):
    root, _, _, _, state, _, authorize, step, assess = rig
    authorize()
    for n in range(1, 5):
        assert step()["number"] == n
        with pytest.raises(GateFailure, match="HUMAN_REVIEW_REQUIRED"):
            step()
        assess()
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        step()
    assert len(state["sends"]) == 4
    assert runner.report(root)["t040_complete"] is False


@pytest.mark.parametrize("case", ["miss", "wrong_area", "unsupported_extra"])
def test_first_error_or_review_fact_failure_stops_without_retry(rig, case):
    root, _, _, _, state, _, authorize, step, assess = rig
    authorize()
    if case == "miss":
        state["edit"] = lambda v: v.update(verdict="pass", findings=[])
    elif case == "wrong_area":
        state["edit"] = lambda v: v["findings"][0].update(area="code_safety")
    if case == "unsupported_extra":
        step()
        # Human semantic check is intentionally separate from schema/category checks.
        with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
            assess(False)
    else:
        with pytest.raises(GateFailure):
            step()
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        step()
    assert len(state["sends"]) == 1 and runner.report(root)["run"]["halted"]


def test_real_safety_defect_must_not_be_classified_only_fact(rig):
    root, _, _, _, state, _, authorize, step, assess = rig
    authorize()
    step()
    assess()
    state["edit"] = lambda v: v["findings"][0].update(area="fact")
    with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
        step()
    assert len(state["sends"]) == 2 and runner.report(root)["run"]["halted"] == "ADMISSION_FAILED"


def test_correct_control_rejects_any_extra_finding(rig):
    root, _, _, _, state, _, authorize, step, assess = rig
    authorize()
    for _ in range(2):
        step()
        assess()
    state["edit"] = lambda v: v.update(
        other_findings=[
            {
                "span_ids": ["s0001"],
                "finding": {
                    "area": "code_safety",
                    "severity": "minor",
                    "message": "Synthetic false positive",
                },
            }
        ]
    )
    with pytest.raises(GateFailure, match="CONTROL_REJECTED"):
        step()
    assert len(state["sends"]) == 3 and runner.report(root)["run"]["halted"] == "CONTROL_REJECTED"


def test_final_round_cannot_erase_or_replace_previous_root(rig):
    root, m, plan, requests, state, _, authorize, _, _ = rig
    a = authorize()
    with pytest.raises(GateFailure, match="PREREQUISITE_MISSING"):
        FinalFocusGate(root, m, {**plan, "prior_root_sha256": "0" * 64}, requests, a)
    assert not state["sends"]


def test_control_c_programs_against_independent_operation_oracles(tmp_path):
    compiler = shutil.which("cc")
    assert compiler, "C compiler required to verify authored correct controls"
    samples = json.loads((REPO / prepare.BASE_REL / "samples.json").read_bytes())["items"]
    libs = []
    for i in (2, 3):
        code = samples[i]["markdown"].split("```c\n", 1)[1].split("```", 1)[0]
        source, lib = tmp_path / f"control{i}.c", tmp_path / f"control{i}.dylib"
        source.write_text(code)
        subprocess.run(
            [
                compiler,
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(source),
                "-o",
                str(lib),
            ],
            check=True,
            capture_output=True,
        )
        libs.append(ctypes.CDLL(str(lib)))

    class Stack(ctypes.Structure):
        _fields_ = [("data", ctypes.c_int * 4), ("size", ctypes.c_int)]

    stack_lib, search_lib = libs
    stack_lib.init.argtypes = [ctypes.POINTER(Stack)]
    stack_lib.push.argtypes = [ctypes.POINTER(Stack), ctypes.c_int]
    stack_lib.pop.argtypes = [ctypes.POINTER(Stack), ctypes.POINTER(ctypes.c_int)]
    stack_lib.push.restype = stack_lib.pop.restype = ctypes.c_bool
    for operations in itertools.product((10, 20, None), repeat=6):
        stack, oracle = Stack(), []
        stack_lib.init(ctypes.byref(stack))
        for op in operations:
            if op is None:
                out = ctypes.c_int(-99)
                ok = stack_lib.pop(ctypes.byref(stack), ctypes.byref(out))
                assert ok == bool(oracle)
                if ok:
                    assert out.value == oracle.pop()
                else:
                    assert out.value == -99
            else:
                ok = stack_lib.push(ctypes.byref(stack), op)
                assert ok == (len(oracle) < 4)
                if ok:
                    oracle.append(op)
            assert stack.size == len(oracle)
    search_lib.binary_search.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int]
    search_lib.binary_search.restype = ctypes.c_int
    for n in range(6):
        for values in itertools.combinations_with_replacement(range(-1, 2), n):
            array = (ctypes.c_int * n)(*values) if n else None
            for target in range(-2, 3):
                found = search_lib.binary_search(array, n, target)
                assert (found == -1) == (target not in values)
                if found != -1:
                    assert 0 <= found < n and values[found] == target
