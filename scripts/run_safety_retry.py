"""One explicitly requested technical retry; never reopens the retired research run."""

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

BASE = "docs/acceptance/phase-1-review-safety-retry-r01"
PRIVATE = "local-materials/phase-1-review-safety-retry-r01"
SLOT = "screen-safety"


def old_stopped(root):
    parent.verify(root)
    parent.historical_stop(root)
    p = root / parent.PRIVATE
    require(
        read(p / "halt.json") == read(root / parent.BASE / "results/halt.json"),
        "PARENT_HALT_CHANGED",
    )
    require(
        read(p / "halt.json")["research_batch"] == "STOPPED_SCOPE_DISCUSSION_REQUIRED",
        "PARENT_NOT_STOPPED",
    )
    old = read(p / (SLOT + "-receipt.json"))
    require(
        sha(canonical(old))
        == "3f5836b63440d752a3a4d72e52a9fcf0a228febe01426e79b7d09380a8766667"
        and old["error"] == "TIMEOUT",
        "PARENT_FAILURE_CHANGED",
    )
    require(
        not any((p / (s + "-reservation.json")).exists() for s in parent.SLOTS[7:]),
        "PARENT_RESUMED",
    )


def freeze(root):
    old, h = parent.verify(root)
    old_stopped(root)
    files = dict(old["files"])
    names = [
        parent.BASE + "/manifest.json",
        parent.BASE + "/results/halt.json",
        parent.BASE + "/results/screen-safety.json",
        parent.BASE + "/results/terminal-decision.json",
        "scripts/run_safety_retry.py",
        "scripts/tests/test_safety_retry.py",
    ]
    names += [
        p.relative_to(root).as_posix()
        for p in (root / BASE).iterdir()
        if p.is_file() and p.name not in {"manifest.json", "run-approval.json"}
    ]
    for name in names:
        path = root / name
        require(
            not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            "UNSAFE_SOURCE",
        )
        files[name] = sha(path.read_bytes())
    request = read(root / BASE / "request.json")
    plan = read(root / BASE / "plan.json")
    require(
        request == read(root / parent.BASE / "requests.json")[SLOT], "REQUEST_CHANGED"
    )
    return dict(
        kind="EXPLICIT_ONE_TECHNICAL_RETRY_NOT_BATCH_RESUME",
        execution_root=str(root.resolve()),
        files=dict(sorted(files.items())),
        env_metadata=old["env_metadata"],
        parent_manifest_sha256=h,
        request_sha256=request["wire_sha256"],
        requests_max=1,
        expires_at_epoch=int(datetime.fromisoformat(plan["expires_at"]).timestamp()),
        old_run_stays_stopped=True,
    )


def verify(root):
    m = read(root / BASE / "manifest.json")
    require(
        m["execution_root"] == str(root.resolve()) and m["requests_max"] == 1,
        "MANIFEST_CHANGED",
    )
    for name, h in m["files"].items():
        p = root / name
        require(
            not p.is_symlink()
            and p.resolve().is_relative_to(root.resolve())
            and sha(p.read_bytes()) == h,
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
        and a["requests"] == 1
        and a.get("decision") == "explicit_one_technical_retry"
        and a.get("reviewer") == "Lee"
        and a.get("source_user_message") == "重试一次"
        and a.get("old_run_resume") is False,
        "NOT_AUTHORIZED",
    )
    require(time.time() < m["expires_at_epoch"], "APPROVAL_EXPIRED")
    return m, h


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
    reservation = dict(
        manifest_sha256=h,
        slot=SLOT,
        request_sha256=m["request_sha256"],
        created_epoch=time.time(),
    )
    private_write(p / "reservation.json", reservation)
    wire = bytes.fromhex(read(root / BASE / "request.json")["wire_hex"])
    require(sha(wire) == m["request_sha256"], "REQUEST_CHANGED")
    case = read(root / parent.MATERIALS / "cases.json")[SLOT]
    sent = False

    def checked():
        nonlocal sent
        require(not sent, "SINGLE_CALL_ONLY")
        authorize(root)
        old_stopped(root)
        require(read(p / "reservation.json") == reservation, "RESERVATION_CHANGED")
        sent = True

    receipt = dict(
        manifest_sha256=h,
        slot=SLOT,
        stopped=True,
        old_run_resumed=False,
        actual_human_accepted=False,
    )
    try:
        async with asyncio.timeout(
            min(60, max(0, m["expires_at_epoch"] - time.time() - 5))
        ):
            outcome = await attempt(root, m, case, wire, checked)
        receipt["outcome"] = outcome
        require(sent, "NO_SEND_AUTHORITY")
        parent.structural_criterion(outcome, "reject", m["request_sha256"])
        receipt["structural_criterion"] = True
        receipt["stop_reason"] = "ONE_RETRY_FINISHED_PENDING_SEMANTIC_REVIEW"
    except BaseException as exc:
        receipt["structural_criterion"] = False
        receipt["error"] = parent.safe_failure(exc)
        receipt["details"] = (
            exc.details if isinstance(exc, parent.LunaAttemptFailure) else None
        )
        receipt["stop_reason"] = "ONE_RETRY_FAILED_NO_MORE_ATTEMPTS"
    private_write(p / "receipt.json", receipt)
    return dict(
        state="STOPPED",
        reason=receipt["stop_reason"],
        receipt_sha256=sha(canonical(receipt)),
    )


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--run-one", action="store_true")
    a = p.parse_args()
    require(not (a.freeze and a.run_one), "CHOOSE_ONE_MODE")
    if a.freeze:
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
                    requests_max=1,
                )
            )
        )
    elif a.run_one:
        print(json.dumps(asyncio.run(step())))
    else:
        _, h = verify(ROOT)
        print(
            json.dumps(
                dict(manifest_sha256=h, mode="read-only,no request", requests_max=1)
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(state="BLOCKED", exception_type=type(exc).__name__)))
        raise SystemExit(2)
