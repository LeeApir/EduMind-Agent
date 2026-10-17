"""Repaired remaining 3+8 Qwen cases; immutable old ledgers and per-result human gates."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_qwen_review as old
from acceptance_support.qwen_review_attempt import perform, AttemptFailure
from acceptance_support.qwen_review_budget import (
    Approval,
    FrozenBudget,
    GateFailure,
    sha,
)
from acceptance_support.qwen_compatibility_transport import QwenCompatibilityTransport
from app.services.learning_policy import active_policy_digest
from app.services.qwen_schema import QWEN_SCHEMA_PROFILE

BASE = "docs/acceptance/phase-1-qwen-continuation-r01"
PRIVATE = "local-materials/phase-1-qwen-continuation-r01"


def load(root=ROOT, stop_only=False):
    p = old.read(root / BASE / "proposal.json")
    a = old.read(root / BASE / "run-approval.json")
    old.require(
        a.get("proposal_sha256") == old.stable(p)
        and a.get("reviewer") == "Lee"
        and type(a.get("requests")) is int
        and a["requests"] == 11
        and type(a.get("cost_micro_cny")) is int
        and a["cost_micro_cny"] == p["cost_micro_cny"]
        and a.get("source_message_id")
        and a.get("user_confirmation"),
        "NOT_AUTHORIZED",
    )
    old.require(
        p["execution_root"] == str(root.resolve())
        and (
            stop_only
            or time.time() < datetime.fromisoformat(p["expiry_local"]).timestamp()
        ),
        "NOT_AUTHORIZED",
    )
    for name, digest in p["sources"].items():
        path = root / name
        old.require(
            not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and sha(path.read_bytes()) == digest,
            "FREEZE_CHANGED",
        )
    old.require(p["policy_digest"] == active_policy_digest(), "FREEZE_CHANGED")
    imported = old.read(root / p["imported_human_path"])
    receipt = old.read(root / p["imported_receipt_path"])
    human_valid(imported, old.stable(receipt), receipt["proposal_sha256"])
    old.require(
        old.stable(receipt) == p["imported_receipt_sha256"]
        and imported["interpretation"] == p["human_interpretation"],
        "HUMAN_CHECK_REQUIRED",
    )
    if not stop_only:
        today = time.strftime("%Y-%m-%d")
        terms = old.read(root / BASE / ("terms-" + today + ".json"))
        old.require(
            terms.get("proposal_sha256") == old.stable(p)
            and terms.get("checked_on") == today
            and terms.get("prices_and_limits_unchanged") is True,
            "TERMS_RECHECK_REQUIRED",
        )
    return p, a


def human_valid(value, receipt_sha, proposal_sha):
    old.require(
        value.get("proposal_sha256") == proposal_sha
        and value.get("receipt_sha256") == receipt_sha
        and value.get("reviewer") == "Lee"
        and value.get("source_message_id")
        and value.get("decision") == "continue"
        and value.get("issues") == []
        and all(
            value.get(k) is True
            for k in [
                "completeness_checked",
                "all_assertions_checked",
                "all_citations_checked",
            ]
        ),
        "HUMAN_CHECK_REQUIRED",
    )


def gate_for(p, a, root):
    m = p["budget_manifest"]
    return FrozenBudget(
        m,
        root / PRIVATE / "budget.sqlite",
        root=root,
        approval=Approval(
            old.stable(m), "diagnostic", 11, p["cost_micro_cny"], old.stable(a), True
        ),
    )


def human_checks(p, snapshot, gate, root):
    receipts = {"reachable-safety:candidate": p["imported_receipt_sha256"]}
    for row in snapshot["attempts"]:
        old.require(row[6] == "complete", "RUN_STOPPED")
        receipt = old.read(root / PRIVATE / (row[1] + ".json"))
        receipts[row[1]] = old.stable(receipt)
        confirmation = old.read(root / PRIVATE / (row[1] + "-human.json"))
        old.require(
            confirmation.get("proposal_sha256") == old.stable(p)
            and confirmation.get("receipt_sha256") == old.stable(receipt)
            and confirmation.get("reviewer") == "Lee"
            and confirmation.get("source_message_id"),
            "HUMAN_CHECK_REQUIRED",
        )
        if confirmation.get("decision") == "eliminate" or confirmation.get("issues"):
            gate.halt("ADMISSION_FAILED")
            raise GateFailure("RUN_STOPPED")
        human_valid(confirmation, old.stable(receipt), old.stable(p))
    if len(snapshot["attempts"]) >= 3:
        decision = old.read(root / PRIVATE / "screen-pass.json")
        expected = {
            name: receipts[name]
            for name in [
                "reachable-safety:candidate",
                *[s["id"] for s in p["slots"][:3]],
            ]
        }
        old.require(
            decision.get("proposal_sha256") == old.stable(p)
            and decision.get("receipt_digests") == expected
            and decision.get("reviewer") == "Lee"
            and decision.get("decision") == "admit_generalization"
            and decision.get("source_message_id"),
            "SCREEN_SIGNOFF_REQUIRED",
        )


async def step(root=ROOT, attempt=perform, check_complete=False):
    p, a = load(root)
    private = root / PRIVATE
    old.require(
        not private.is_symlink()
        and private.parent.resolve().is_relative_to(root.resolve()),
        "SAFETY_FAILURE",
    )
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    old.require(private.stat().st_mode & 0o077 == 0, "SAFETY_FAILURE")
    fd = os.open(
        private / "execution.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate = gate_for(p, a, root)
        enrollment = private / "enrollment.json"
        if enrollment.exists():
            old.require(
                old.read(enrollment) == {"proposal_sha256": old.stable(p)}
                and gate.ledger.is_file(),
                "LEDGER_MISSING",
            )
        else:
            old.require(not gate.ledger.exists(), "LEDGER_MISMATCH")
            old.private_write(enrollment, {"proposal_sha256": old.stable(p)})
        snapshot = gate.snapshot()
        old.require(snapshot["halted"] is None, "RUN_HALTED")
        human_checks(p, snapshot, gate, root)
        if check_complete:
            old.require(len(snapshot["attempts"]) == 11, "DIAGNOSTIC_INCOMPLETE")
            return {
                "status": "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION",
                "requests_sent": 0,
                "t040_passed": False,
            }
        old.require(snapshot["unattempted_slots"], "BUDGET_EXHAUSTED")
        slot = snapshot["unattempted_slots"][0]
        case = old.read(root / old.DESIGN / "cases.json")[slot]
        wire = bytes.fromhex(old.read(root / BASE / "requests.json")[slot]["wire_hex"])
        tid = next(iter(gate.manifest["targets"]))
        number = gate.reserve(slot, "probe", tid, wire, resource="unit")
        outcome = None
        receipt = None
        try:
            async with asyncio.timeout(60):
                endpoint, key = old.credentials(root, p)

                async def authorize(request):
                    load(root)
                    old.require(
                        request.route.model_id == "qwen3.8-max-0902"
                        and request.capabilities.schema_profile == QWEN_SCHEMA_PROFILE
                        and request.purpose == "connection_test"
                        and request.route.data_categories == frozenset({"probe"}),
                        "TARGET_CHANGED",
                    )
                    gate._authorize()

                outcome = await attempt(
                    case,
                    wire,
                    endpoint=endpoint,
                    key=key,
                    database_url=old.database_url(),
                    authorize=authorize,
                    schema_profile=QWEN_SCHEMA_PROFILE,
                    audit_factory=QwenCompatibilityTransport,
                )
                old.require(
                    outcome["normal_finish"]
                    and outcome["schema_valid"]
                    and outcome["sent"] == 1
                    and all(outcome["cleanup"].values()),
                    "INVALID_OUTPUT",
                )
                old.require(
                    type(outcome["input_tokens"]) is int
                    and 0 <= outcome["input_tokens"] <= 1048576 + len(wire)
                    and type(outcome["output_tokens"]) is int
                    and 0 <= outcome["output_tokens"] <= 8202,
                    "USAGE_UNKNOWN",
                )
                old.require(
                    outcome["review_record"]["request_digest"] == sha(wire)
                    and outcome["review_record"]["binding"]
                    == case["material"]["binding"],
                    "TARGET_CHANGED",
                )
                evaluation = old.assess(case, outcome["review_record"]["result"])
                receipt = {
                    "proposal_sha256": old.stable(p),
                    "slot": slot,
                    "phase": next(s["phase"] for s in p["slots"] if s["id"] == slot),
                    "request_sha256": sha(wire),
                    "outcome": outcome,
                    "local_assessment": evaluation,
                    "human_confirmed": False,
                    "t040_passed": False,
                }
                old.require(
                    evaluation["criterion_signal"], "CANDIDATE_CRITERION_FAILED"
                )
                old.private_write(private / (slot + ".json"), receipt)
                gate.finish(
                    number,
                    input_tokens=outcome["input_tokens"],
                    output_tokens=outcome["output_tokens"],
                )
        except BaseException as exc:
            observation = (
                exc.observation
                if isinstance(exc, AttemptFailure)
                else {
                    "normalized_error": "TIMEOUT"
                    if isinstance(exc, TimeoutError)
                    else "INVALID_OUTPUT",
                    "gate_code": getattr(exc, "code", None),
                    "input_tokens": outcome.get("input_tokens") if outcome else None,
                    "output_tokens": outcome.get("output_tokens") if outcome else None,
                }
            )
            gate.finish(
                number,
                error_code=observation["normalized_error"],
                input_tokens=observation.get("input_tokens"),
                output_tokens=observation.get("output_tokens"),
            )
            gate.halt("ADMISSION_FAILED")
            old.private_write(
                private / (slot + "-failure.json"),
                {
                    "proposal_sha256": old.stable(p),
                    "slot": slot,
                    "observation": observation,
                    "complete_review_receipt": receipt,
                    "complete_outcome": outcome,
                    "candidate_eliminated": True,
                    "t040_passed": False,
                },
            )
            return {
                "status": "CANDIDATE_ELIMINATED",
                "requests_sent": observation.get("sent"),
                "t040_passed": False,
            }
        return {
            "status": "HUMAN_CHECK_REQUIRED",
            "slot": slot,
            "receipt_sha256": old.stable(receipt),
            "requests_sent": 1,
            "t040_passed": False,
        }
    finally:
        os.close(fd)


def eliminate(root, slot, issues):
    p, a = load(root, stop_only=True)
    old.require(
        isinstance(issues, list)
        and issues
        and all(isinstance(i, str) and i.strip() for i in issues),
        "INVALID_OBSERVATION",
    )
    fd = os.open(root / PRIVATE / "execution.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = old.read(root / PRIVATE / (slot + ".json"))
        gate_for(p, a, root).halt("ADMISSION_FAILED")
        old.private_write(
            root / PRIVATE / (slot + "-semantic-stop.json"),
            {
                "proposal_sha256": old.stable(p),
                "receipt_sha256": old.stable(receipt),
                "reviewer_type": "assistant",
                "issues": issues,
                "decision": "eliminate_candidate",
                "t040_passed": False,
            },
        )
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--run-one", action="store_true")
    choice.add_argument("--check-complete", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(step(check_complete=args.check_complete))
    except (GateFailure, OSError, ValueError):
        print(json.dumps({"status": "STOPPED_OR_NOT_AUTHORIZED", "t040_passed": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
