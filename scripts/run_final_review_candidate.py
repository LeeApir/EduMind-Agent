"""Only final high candidate: twelve bounded stage-gated calls, failure stops this R&D batch."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_admission_gate import (
    read,
    require,
    env_metadata,
    private_write,
)
from acceptance_support.qwen_review_budget import canonical, sha
from run_final_review_attempt import perform
import run_luna_process_calibration as retired
from run_luna_admission import safe_failure, LunaAttemptFailure
from app.agents.hybrid_resource_review import UNIT_CHECKS

BASE = "docs/acceptance/phase-1-review-final-execution-r01"
MATERIALS = "docs/acceptance/phase-1-review-last-candidate-r01"
PRIVATE = "local-materials/phase-1-review-final-execution-r01"
from prepare_last_review_candidate import SLOTS


def verify(root):
    m = read(root / BASE / "manifest.json")
    require(m["execution_root"] == str(root.resolve()), "EXECUTION_ROOT_CHANGED")
    require(m["requests_max"] == 12 and m["slots"] == list(SLOTS), "PLAN_CHANGED")
    require(
        m["candidate_count_max"] == 1 and m["candidate_id"] == "luna-high-v49-final-01",
        "CANDIDATE_CHANGED",
    )
    for name, expected in m["files"].items():
        path = root / name
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and sha(path.read_bytes()) == expected,
            "FREEZE_CHANGED",
        )
    require(env_metadata(root / ".env") == m["env_metadata"], "ENV_CHANGED")
    return m, sha(canonical(m))


def authorize(root):
    m, h = verify(root)
    a = read(root / BASE / "run-approval.json")
    require(
        a.get("manifest_sha256") == h
        and type(a.get("requests")) is int
        and a["requests"] == 12
        and a.get("decision") == "approve_final_candidate_twelve_requests"
        and a.get("reviewer") == "Lee"
        and a.get("source_user_message")
        and a.get("cost_policy") == "uncapped_by_explicit_user_instruction",
        "NOT_AUTHORIZED",
    )
    truth = read(root / BASE / "truth-confirmation.json")
    require(
        truth["material_files"]
        == {
            name: m["files"][MATERIALS + "/" + name]
            for name in ("cases.json", "labels.json", "requests.json", "plan.json")
        }
        and truth["results_presigned"] is False,
        "LABEL_REVIEW_REQUIRED",
    )
    require(time.time() < m["expires_at_epoch"], "APPROVAL_EXPIRED")
    return m, h


def historical_stop(root):
    retired.verify(root)
    retired.historical_stop(root)
    old_private = root / retired.PRIVATE
    require(
        read(old_private / "halt.json")
        == read(root / retired.BASE / "results/halt.json"),
        "OLD_STOP_CHANGED",
    )
    require(
        read(root / MATERIALS / "retirement.json")["state"] == "RETIRED",
        "RETIRED_CANDIDATE_REQUIRED",
    )
    for slot in ("cal-01", "cal-02"):
        require(
            read(old_private / (slot + "-receipt.json"))
            == read(root / retired.BASE / "results" / (slot + ".json")),
            "OLD_STOP_CHANGED",
        )
    require(
        not (old_private / "cal-03-reservation.json").exists()
        and not (old_private / "cal-04-reservation.json").exists(),
        "OLD_STOP_CHANGED",
    )


def halted(private, reason):
    path = private / "halt.json"
    if not path.exists():
        try:
            private_write(
                path,
                {
                    "reason": reason,
                    "research_batch": "STOPPED_SCOPE_DISCUSSION_REQUIRED",
                    "next_candidates_allowed": 0,
                },
            )
        except FileExistsError:
            pass
    return {"state": "STOPPED", "reason": read(path)["reason"]}


def structural_criterion(outcome, expected, request_digest):
    record = outcome["record"]
    value = record["result"]
    require(
        outcome["sent"] == 1
        and outcome["http_status"] == 200
        and outcome["raw_complete"] is True
        and outcome["model"] == "gpt-6-luna"
        and outcome.get("requested_reasoning") == "high"
        and record["request_digest"] == request_digest
        and type(outcome["input_tokens"]) is int
        and outcome["input_tokens"] >= 0
        and type(outcome["output_tokens"]) is int
        and 0 <= outcome["output_tokens"] <= 8192,
        "TECHNICAL_INTEGRITY_FAILED",
    )
    require(
        value["verdict"] == record["local_routing"]["verdict"] == expected
        and value["schema_version"] == "resource-review-v4"
        and value["scope"] == "unit"
        and set(value["coverage"]["checked"]) == UNIT_CHECKS
        and len(value["coverage"]["checked"]) == len(UNIT_CHECKS)
        and not value["coverage"]["unchecked"]
        and (bool(value["findings"]) if expected == "reject" else not value["findings"])
        and (
            value["unresolved"] == []
            if expected == "pass"
            else bool(value["unresolved"])
            if expected == "needs_human"
            else True
        ),
        "FROZEN_CRITERION_FAILED",
    )
    # This intentionally cannot decide all assertions/references or whether the
    # pedagogical gap is accurately explained. Human review remains mandatory.


def previous_checks(root, private, h, requests):
    expected = read(root / BASE / "plan.json")["expected"]
    for n, slot in enumerate(SLOTS):
        reservation_path = private / f"{slot}-reservation.json"
        if not reservation_path.exists():
            require(
                not any(
                    (private / f"{s}-reservation.json").exists() for s in SLOTS[n + 1 :]
                ),
                "SLOT_ORDER_CHANGED",
            )
            return n
        reservation = read(reservation_path)
        require(
            reservation["manifest_sha256"] == h
            and reservation["slot"] == slot
            and reservation["request_sha256"] == requests[slot]["wire_sha256"],
            "RESERVATION_CHANGED",
        )
        receipt_path = private / f"{slot}-receipt.json"
        if not receipt_path.exists():
            halted(private, "SEND_STATE_UNCERTAIN")
            raise ValueError("SEND_STATE_UNCERTAIN")
        receipt = read(receipt_path)
        require(
            receipt["manifest_sha256"] == h and receipt["slot"] == slot,
            "RECEIPT_CHANGED",
        )
        require(receipt["expected"] == expected[slot], "RECEIPT_CHANGED")
        require(
            receipt["reservation_sha256"] == sha(canonical(reservation)),
            "RECEIPT_CHANGED",
        )
        require(receipt["structural_criterion"] is True, "FAILED_RECEIPT")
        structural_criterion(
            receipt["outcome"], receipt["expected"], requests[slot]["wire_sha256"]
        )
        signed_path = root / BASE / "assessments" / f"{slot}.json"
        if not signed_path.exists():
            raise ValueError("HUMAN_CHECK_REQUIRED")
        signed = read(signed_path)
        require(
            signed.get("manifest_sha256") == h
            and signed.get("slot") == slot
            and signed.get("receipt_sha256") == sha(canonical(receipt))
            and signed.get("reviewer") == "Lee"
            and signed.get("source_user_message"),
            "HUMAN_CHECK_REQUIRED",
        )
        if not (
            all(
                signed.get(k) is True
                for k in ("integrity", "all_claims", "all_citations", "criterion")
            )
            and signed.get("issues") == []
        ):
            halted(private, "SEMANTIC_OR_CITATION_FAILURE")
            raise ValueError("CANDIDATE_FAILED")
    return len(SLOTS)


async def step(root=ROOT, attempt=perform):
    m, h = authorize(root)  # before private state, key access, DNS or HTTP
    historical_stop(root)
    private = root / PRIVATE
    require(
        not private.is_symlink()
        and private.parent.resolve().is_relative_to(root.resolve()),
        "UNSAFE_PRIVATE_PATH",
    )
    private.mkdir(parents=True, mode=0o700, exist_ok=True)
    require(private.stat().st_mode & 0o077 == 0, "UNSAFE_PRIVATE_MODE")
    if (private / "halt.json").exists():
        return {"state": "STOPPED", "reason": read(private / "halt.json")["reason"]}
    if (private / f"{SLOTS[0]}-reservation.json").exists():
        first = read(private / f"{SLOTS[0]}-reservation.json")
        if time.time() - first["created_epoch"] >= 86400:
            return halted(private, "WALL_TIME_EXPIRED")
    requests = read(root / BASE / "requests.json")
    n = previous_checks(root, private, h, requests)
    if n == len(SLOTS):
        private_write(
            private / "halt.json",
            {
                "reason": "DIAGNOSTIC_COMPLETE_NO_FURTHER_CALLS",
                "research_batch": "DIAGNOSTIC_COMPLETE_PENDING_ADMISSION",
                "next_candidates_allowed": 0,
            },
        )
        return {
            "state": "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION",
            "requests_reserved": 12,
            "formal_T040_pass": False,
        }
    slot = SLOTS[n]
    wire = bytes.fromhex(requests[slot]["wire_hex"])
    require(sha(wire) == m["request_sha256"][slot], "REQUEST_CHANGED")
    case = read(root / MATERIALS / "cases.json")[slot]
    expected = read(root / BASE / "plan.json")["expected"][slot]
    reservation = {
        "manifest_sha256": h,
        "slot": slot,
        "request_sha256": sha(wire),
        "created_epoch": time.time(),
    }
    # O_EXCL is the concurrency lock: any crash/unknown send consumes this slot.
    private_write(private / f"{slot}-reservation.json", reservation)
    sent_authority = False

    def checked_authorize():
        nonlocal sent_authority
        require(not sent_authority, "SINGLE_CALL_ONLY")
        authorize(root)
        historical_stop(root)
        require(not (private / "halt.json").exists(), "RUN_STOPPED")
        first = read(private / f"{SLOTS[0]}-reservation.json")
        require(time.time() - first["created_epoch"] < 86400, "WALL_TIME_EXPIRED")
        require(
            read(private / f"{slot}-reservation.json") == reservation,
            "RESERVATION_CHANGED",
        )
        sent_authority = True

    receipt = dict(
        manifest_sha256=h,
        slot=slot,
        expected=expected,
        reservation_sha256=sha(canonical(reservation)),
        structural_criterion=False,
        human_accepted=False,
    )
    try:
        first = read(private / f"{SLOTS[0]}-reservation.json")
        # Reserve up to five seconds for the transport's bounded cleanup when
        # cancellation arrives near the wall/absolute deadline.
        remaining = (
            min(
                86400 - (time.time() - first["created_epoch"]),
                m["expires_at_epoch"] - time.time(),
            )
            - 5
        )
        require(remaining > 0, "WALL_TIME_EXPIRED")
        async with asyncio.timeout(min(60, remaining)):
            outcome = await attempt(root, m, case, wire, checked_authorize)
        receipt["outcome"] = outcome
        require(sent_authority, "NO_SEND_AUTHORITY")
        structural_criterion(outcome, expected, sha(wire))
        receipt["structural_criterion"] = True
    except BaseException as exc:
        receipt["error"] = safe_failure(exc)
        if type(exc) is ValueError and str(exc) in {
            "TECHNICAL_INTEGRITY_FAILED",
            "FROZEN_CRITERION_FAILED",
            "NO_SEND_AUTHORITY",
        }:
            receipt["error"] = str(exc)
        receipt["failure_type"] = type(exc).__name__
        receipt["details"] = (
            exc.details if isinstance(exc, LunaAttemptFailure) else None
        )
        receipt["stop_reason"] = "TECHNICAL_OR_CRITERION_FAILURE"
    private_write(private / f"{slot}-receipt.json", receipt)
    if not receipt["structural_criterion"]:
        return {
            **halted(private, receipt["stop_reason"]),
            "slot": slot,
            "receipt_sha256": sha(canonical(receipt)),
        }
    return {
        "state": "WAITING_HUMAN_REVIEW",
        "slot": slot,
        "receipt_sha256": sha(canonical(receipt)),
        "requests_reserved": n + 1,
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--run-one", action="store_true")
    args = p.parse_args()
    if args.run_one:
        print(json.dumps(asyncio.run(step())))
    else:
        m, h = verify(ROOT)
        print(
            json.dumps(
                dict(
                    manifest_sha256=h,
                    requests_max=12,
                    mode="READ_ONLY_FREEZE_VERIFICATION_NOT_LIVE_CALL_COUNT",
                    actual_calls="consult private receipts; no request made by this command",
                    approval_file_present=(ROOT / BASE / "run-approval.json").exists(),
                    expires_at_epoch=m["expires_at_epoch"],
                )
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"state": "BLOCKED", "exception_type": type(exc).__name__}))
        raise SystemExit(2)
