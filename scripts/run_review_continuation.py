"""Explicit five-case continuation, separate from stopped historical ledgers."""

# ruff: noqa: E402
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
import time

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
import run_final_review_candidate as parent
import run_safety_retry as retry

BASE = "docs/acceptance/phase-1-review-continuation-r01"
PRIVATE = "local-materials/phase-1-review-continuation-r01"
SLOTS = tuple(parent.SLOTS[7:])
USER_MESSAGE = "超时解决好了？那继续下面5条"


def old_stopped(root):
    retry.old_stopped(root)
    retry.verify(root)
    receipt = read(root / retry.PRIVATE / "receipt.json")
    require(
        receipt == read(root / retry.BASE / "results/screen-safety.json")
        and sha(canonical(receipt))
        == "3f1480a837f7446ed390c7874e4d11820bb338b007c2f687e7304443bcd1fb95"
        and receipt["stopped"] is True
        and receipt["structural_criterion"] is True,
        "RETRY_EVIDENCE_CHANGED",
    )


def freeze(root):
    old_stopped(root)
    old, old_hash = retry.verify(root)
    files = dict(old["files"])
    names = [
        retry.BASE + "/manifest.json",
        retry.BASE + "/results/screen-safety.json",
        retry.BASE + "/results/claim-review.json",
        retry.BASE + "/results/run-summary.json",
        "scripts/run_review_continuation.py",
        "scripts/tests/test_review_continuation.py",
    ]
    names += [
        p.relative_to(root).as_posix()
        for p in (root / BASE).iterdir()
        if p.is_file() and p.name not in {"manifest.json", "run-approval.json"}
    ]
    for name in names:
        p = root / name
        require(
            not p.is_symlink() and p.resolve().is_relative_to(root.resolve()),
            "UNSAFE_SOURCE",
        )
        files[name] = sha(p.read_bytes())
    requests = read(root / BASE / "requests.json")
    original = read(root / parent.BASE / "requests.json")
    require(list(requests) == list(SLOTS), "SLOT_ORDER_CHANGED")
    require(all(requests[s] == original[s] for s in SLOTS), "REQUEST_CHANGED")
    plan = read(root / BASE / "plan.json")
    require(plan["slots"] == list(SLOTS) and plan["requests_max"] == 5, "PLAN_CHANGED")
    return dict(
        kind="EXPLICIT_FIVE_CASE_CONTINUATION_SEPARATE_LEDGER",
        execution_root=str(root.resolve()),
        files=dict(sorted(files.items())),
        env_metadata=old["env_metadata"],
        parent_retry_manifest_sha256=old_hash,
        slots=list(SLOTS),
        requests_max=5,
        request_sha256={s: requests[s]["wire_sha256"] for s in SLOTS},
        expires_at_epoch=datetime.fromisoformat(plan["expires_at"]).timestamp(),
        old_run_stays_stopped=True,
    )


def verify(root):
    m = read(root / BASE / "manifest.json")
    require(
        m["execution_root"] == str(root.resolve())
        and m["requests_max"] == 5
        and m["slots"] == list(SLOTS),
        "MANIFEST_CHANGED",
    )
    for name, digest in m["files"].items():
        p = root / name
        require(
            not p.is_symlink()
            and p.resolve().is_relative_to(root.resolve())
            and sha(p.read_bytes()) == digest,
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
        and a["requests"] == 5
        and a.get("reviewer") == "Lee"
        and a.get("source_user_message") == USER_MESSAGE
        and a.get("decision") == "continue_exact_remaining_five"
        and a.get("old_run_resume") is False
        and a.get("per_result_actual_human_gate") is True,
        "NOT_AUTHORIZED",
    )
    require(time.time() < m["expires_at_epoch"], "APPROVAL_EXPIRED")
    return m, h


def previous(root, p, h, requests, expected):
    for n, slot in enumerate(SLOTS):
        rp = p / f"{slot}-reservation.json"
        if not rp.exists():
            require(
                not any((p / f"{s}-reservation.json").exists() for s in SLOTS[n + 1 :]),
                "SLOT_ORDER_CHANGED",
            )
            return n
        reservation = read(rp)
        require(
            reservation["manifest_sha256"] == h
            and reservation["slot"] == slot
            and reservation["request_sha256"] == requests[slot]["wire_sha256"],
            "RESERVATION_CHANGED",
        )
        receipt_path = p / f"{slot}-receipt.json"
        if not receipt_path.exists():
            parent.halted(p, "SEND_STATE_UNCERTAIN")
            raise ValueError("SEND_STATE_UNCERTAIN")
        receipt = read(receipt_path)
        require(
            receipt["manifest_sha256"] == h
            and receipt["slot"] == slot
            and receipt["reservation_sha256"] == sha(canonical(reservation))
            and receipt["expected"] == expected[slot],
            "RECEIPT_CHANGED",
        )
        require(receipt["structural_criterion"] is True, "FAILED_RECEIPT")
        parent.structural_criterion(
            receipt["outcome"], expected[slot], requests[slot]["wire_sha256"]
        )
        sp = root / BASE / "assessments" / f"{slot}.json"
        if not sp.exists():
            raise ValueError("HUMAN_CHECK_REQUIRED")
        signed = read(sp)
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
            parent.halted(p, "SEMANTIC_OR_CITATION_FAILURE")
            raise ValueError("CANDIDATE_FAILED")
    return len(SLOTS)


async def step(root=ROOT, attempt=perform):
    m, h = authorize(root)
    old_stopped(root)
    p = root / PRIVATE
    require(
        not p.is_symlink() and p.parent.resolve().is_relative_to(root.resolve()),
        "UNSAFE_PRIVATE_PATH",
    )
    p.mkdir(parents=True, mode=0o700, exist_ok=True)
    require(p.stat().st_mode & 0o077 == 0, "UNSAFE_PRIVATE_MODE")
    if (p / "halt.json").exists():
        return dict(state="STOPPED", reason=read(p / "halt.json")["reason"])
    requests = read(root / BASE / "requests.json")
    expected = read(root / BASE / "plan.json")["expected"]
    n = previous(root, p, h, requests, expected)
    if n == len(SLOTS):
        return parent.halted(p, "FIVE_CASES_COMPLETE_PENDING_T040_ADMISSION")
    slot = SLOTS[n]
    wire = bytes.fromhex(requests[slot]["wire_hex"])
    require(sha(wire) == m["request_sha256"][slot], "REQUEST_CHANGED")
    case = read(root / parent.MATERIALS / "cases.json")[slot]
    reservation = dict(
        manifest_sha256=h,
        slot=slot,
        request_sha256=sha(wire),
        created_epoch=time.time(),
    )
    private_write(p / f"{slot}-reservation.json", reservation)
    sent = False

    def checked():
        nonlocal sent
        require(not sent, "SINGLE_CALL_ONLY")
        authorize(root)
        old_stopped(root)
        require(not (p / "halt.json").exists(), "RUN_STOPPED")
        require(
            read(p / f"{slot}-reservation.json") == reservation, "RESERVATION_CHANGED"
        )
        sent = True

    receipt = dict(
        manifest_sha256=h,
        slot=slot,
        expected=expected[slot],
        reservation_sha256=sha(canonical(reservation)),
        structural_criterion=False,
        actual_human_accepted=False,
        old_run_resumed=False,
    )
    try:
        async with asyncio.timeout(
            min(60, max(0, m["expires_at_epoch"] - time.time() - 5))
        ):
            outcome = await attempt(root, m, case, wire, checked)
        receipt["outcome"] = outcome
        require(sent, "NO_SEND_AUTHORITY")
        parent.structural_criterion(outcome, expected[slot], sha(wire))
        receipt["structural_criterion"] = True
    except BaseException as exc:
        receipt["error"] = parent.safe_failure(exc)
        receipt["failure_type"] = type(exc).__name__
        receipt["details"] = (
            exc.details if isinstance(exc, parent.LunaAttemptFailure) else None
        )
    private_write(p / f"{slot}-receipt.json", receipt)
    if not receipt["structural_criterion"]:
        return {
            **parent.halted(p, "TECHNICAL_OR_CRITERION_FAILURE"),
            "slot": slot,
            "receipt_sha256": sha(canonical(receipt)),
        }
    return dict(
        state="WAITING_HUMAN_REVIEW",
        slot=slot,
        receipt_sha256=sha(canonical(receipt)),
        requests_reserved=n + 1,
    )


def main():
    parser = argparse.ArgumentParser(__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run-one", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        m = freeze(ROOT)
        path = ROOT / BASE / "manifest.json"
        raw = json.dumps(m, ensure_ascii=False, indent=2) + "\n"
        require(not path.exists() or path.read_text() == raw, "REFUSE_RESEAL")
        path.write_text(raw)
        print(
            json.dumps(
                dict(
                    manifest_sha256=sha(canonical(m)),
                    files=len(m["files"]),
                    requests_max=5,
                )
            )
        )
    elif args.run_one:
        print(json.dumps(asyncio.run(step())))
    else:
        _, h = verify(ROOT)
        print(
            json.dumps(
                dict(manifest_sha256=h, mode="read-only,no request", requests_max=5)
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(state="BLOCKED", exception_type=type(exc).__name__)))
        raise SystemExit(2)
