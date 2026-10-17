"""New single compatibility call: denies before private state/credentials without approval."""

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

BASE = "docs/acceptance/phase-1-qwen-compatibility-r01"
PRIVATE = "local-materials/phase-1-qwen-compatibility-r01"


def load(root=ROOT):
    p = old.read(root / BASE / "proposal.json")
    a = old.read(root / BASE / "run-approval.json")
    old.require(
        a.get("proposal_sha256") == old.stable(p)
        and a.get("reviewer") == "Lee"
        and type(a.get("requests")) is int
        and a.get("requests") == 1
        and type(a.get("cost_micro_cny")) is int
        and a.get("cost_micro_cny") == p["cost_micro_cny"]
        and a.get("user_confirmation")
        and a.get("source_message_id"),
        "NOT_AUTHORIZED",
    )
    old.require(
        time.time() < datetime.fromisoformat(p["expiry_local"]).timestamp()
        and p["execution_root"] == str(root.resolve()),
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
    today = time.strftime("%Y-%m-%d")
    terms = old.read(root / BASE / ("terms-" + today + ".json"))
    old.require(
        terms.get("checked_on") == today
        and terms.get("proposal_sha256") == old.stable(p)
        and terms.get("prices_and_limits_unchanged") is True,
        "TERMS_RECHECK_REQUIRED",
    )
    return p, a


def budget(p, a, root):
    m = p["budget_manifest"]
    return FrozenBudget(
        m,
        root / PRIVATE / "budget.sqlite",
        root=root,
        approval=Approval(
            old.stable(m), "diagnostic", 1, p["cost_micro_cny"], old.stable(a), True
        ),
    )


async def step(root=ROOT, attempt=perform):
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
        gate = budget(p, a, root)
        snap = gate.snapshot()
        old.require(
            not snap["attempts"] and not snap["halted"], "RUN_STOPPED_OR_EXHAUSTED"
        )
        data = old.read(root / old.DESIGN / "cases.json")
        case = data["reachable-safety:candidate"]
        wire = bytes.fromhex(old.read(root / BASE / "request.json")["wire_hex"])
        tid = next(iter(gate.manifest["targets"]))
        number = gate.reserve("compatibility", "probe", tid, wire, resource="unit")
        record = None
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
                    outcome["sent"] == 1
                    and outcome["normal_finish"]
                    and outcome["schema_valid"]
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
                record = {
                    "status": "COMPATIBLE_PENDING_SEMANTIC_REVIEW",
                    "outcome": outcome,
                    "human_confirmed": False,
                    "t040_passed": False,
                }
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
                    "input_tokens": None,
                    "output_tokens": None,
                }
            )
            gate.finish(
                number,
                error_code=observation["normalized_error"],
                input_tokens=observation.get("input_tokens"),
                output_tokens=observation.get("output_tokens"),
            )
            gate.halt("ADMISSION_FAILED")
            record = {
                "status": "COMPATIBILITY_FAILED_STOPPED",
                "observation": observation,
                "t040_passed": False,
            }
        receipt = {
            "proposal_sha256": old.stable(p),
            "request_sha256": sha(wire),
            **record,
        }
        old.private_write(private / "receipt.json", receipt)
        return {
            "status": receipt["status"],
            "receipt_sha256": old.stable(receipt),
            "t040_passed": False,
        }
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-one", required=True, action="store_true")
    parser.parse_args()
    try:
        print(json.dumps(asyncio.run(step())))
    except (GateFailure, OSError, ValueError):
        print(json.dumps({"status": "STOPPED_OR_NOT_AUTHORIZED", "t040_passed": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
