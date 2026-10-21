"""One separately approved corrected-schema request; old r02 is never resumed."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_admission_gate import (
    read,
    require,
    env_metadata,
    private_write,
)
from acceptance_support.luna_schema_projection import ProjectedReviewAdapter
from acceptance_support.luna_review_routing import ExplicitRouter, CONFIG
from acceptance_support.qwen_review_budget import canonical, sha
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow
from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from prepare_luna_admission import candidates
from prepare_luna_schema_validation import PARENT, BASE, SLOT
from run_luna_admission import (
    credential,
    ExactTransport,
    safe_failure,
    LunaAttemptFailure,
)

PRIVATE = "local-materials/phase-1-luna-schema-validation-r01"


def verify(root):
    m = read(root / BASE / "manifest.json")
    require(m["execution_root"] == str(root.resolve()), "EXECUTION_ROOT_CHANGED")
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
        and a.get("decision") == "approve_one_corrected_schema_validation"
        and a.get("reviewer") == "Lee"
        and a.get("source_user_message")
        and a.get("cost_policy") == "uncapped_by_explicit_user_instruction",
        "NOT_AUTHORIZED",
    )
    require(time.time() < m["expires_at_epoch"], "APPROVAL_EXPIRED")
    # Truth labels may be retained only because the candidate, input, goal, policy and
    # criterion are byte-for-byte identical. This does NOT reuse old request authority.
    parent = read(root / PARENT / "manifest.json")
    ph = sha(canonical(parent))
    labels = read(root / PARENT / "labels-human.json")
    require(
        labels["manifest_sha256"] == ph
        and labels["decision"] == "accept_all_materials_and_labels"
        and labels["reviewer"] == "Lee"
        and labels["source_user_message"],
        "PARENT_LABEL_MISMATCH",
    )
    require(
        sha(canonical(read(root / PARENT / "cases.json")[SLOT])) == m["case_sha256"],
        "CASE_CHANGED",
    )
    return m, h


def assert_parent_stopped(root):
    p = root / "local-materials/phase-1-luna-v49-admission-r02/requests.sqlite"
    require(p.is_file() and not p.is_symlink(), "PARENT_LEDGER_REQUIRED")
    with sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True) as c:
        run = c.execute("SELECT hash,halted FROM run").fetchall()
        rows = c.execute("SELECT slot,state FROM calls").fetchall()
    require(
        run
        == [
            (
                "2cb7190424d4b6d47e9d77be4b02f2548bf913b39fc046c793c73d51be73d130",
                "CAPABILITY_UNAVAILABLE",
            )
        ]
        and rows == [(SLOT, "reserved")],
        "PARENT_STATE_CHANGED",
    )


async def perform(root, manifest, case, wire, checked_authorize):
    key = credential(root, manifest)
    guard = ProviderTargetGuard(CONFIG.review_base, TargetPolicy())
    target = await asyncio.to_thread(guard.approve_base)
    audit = ExactTransport(wire, target, checked_authorize)
    adapter = ProjectedReviewAdapter(
        ProviderSettings(CONFIG.review_base, key, CONFIG.review_model),
        SimpleNamespace(approve_base=lambda: target),
        transport=audit,
        reasoning_effort=CONFIG.review_reasoning,
    )

    class NoGeneration:
        async def generate_structured(self, request):
            raise ValueError("GENERATION_FORBIDDEN")

    router = ExplicitRouter(NoGeneration(), adapter)
    m = case["material"]
    started = time.monotonic()
    try:
        record = await review_once(
            router,
            CallWindow(),
            binding=m["binding"],
            target_digest=m["unit_digest"],
            payload={"unit": m, "reference_context": m["reference_context"]},
            candidates=candidates(case),
            scope="unit",
            input_snapshot=case["input_snapshot"],
        )
        require(
            audit.sent == 1
            and audit.raw_complete
            and record["request_digest"] == sha(wire),
            "AUDIT_MISMATCH",
        )
        require(key not in canonical(record).decode(), "SECRET_REFLECTION")
        return {
            "record": record,
            "sent": audit.sent,
            "http_status": audit.status,
            "raw_response_sha256": audit.raw_hash.hexdigest(),
            "raw_bytes": audit.raw_bytes,
            "raw_complete": audit.raw_complete,
            "model": CONFIG.review_model,
            "input_tokens": router.last_usage.input_tokens,
            "output_tokens": router.last_usage.output_tokens,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    except BaseException as exc:
        usage = getattr(exc, "usage", None) or router.last_usage
        raise LunaAttemptFailure(
            safe_failure(exc),
            {
                "http_status": audit.status,
                "sent": audit.sent,
                "raw_bytes": audit.raw_bytes,
                "raw_complete": audit.raw_complete,
                "raw_response_sha256": audit.raw_hash.hexdigest(),
                "provider_error": audit.error_metadata,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "output_failure_reason": getattr(
                    getattr(exc, "output_failure_reason", None), "value", None
                ),
                "schema_keyword": getattr(exc, "schema_keyword", None),
            },
        ) from None
    finally:
        async with asyncio.timeout(5):
            await audit.aclose()


async def step(root=ROOT, attempt=perform):
    m, h = authorize(root)  # No private state/key/DNS/HTTP before new exact approval.
    assert_parent_stopped(root)
    p = root / PRIVATE
    require(
        not p.is_symlink() and p.parent.resolve().is_relative_to(root.resolve()),
        "UNSAFE_PRIVATE_PATH",
    )
    p.mkdir(parents=True, mode=0o700, exist_ok=True)
    require(p.stat().st_mode & 0o077 == 0, "UNSAFE_PRIVATE_MODE")
    # O_EXCL is the durable single-call reservation and process concurrency gate.
    # Crashes, local preflight errors and uncertain sends all consume it, never replay.
    reservation = {
        "manifest_sha256": h,
        "slot": SLOT,
        "request_sha256": m["request_sha256"],
        "created_epoch": int(time.time()),
    }
    private_write(p / "reservation.json", reservation)
    case = read(root / PARENT / "cases.json")[SLOT]
    wire = bytes.fromhex(read(root / BASE / "request.json")["wire_hex"])
    require(sha(wire) == m["request_sha256"], "REQUEST_CHANGED")
    sent_authority = False

    def checked_authorize():
        nonlocal sent_authority
        require(not sent_authority, "SINGLE_CALL_ONLY")
        authorize(root)
        assert_parent_stopped(root)
        require(read(p / "reservation.json") == reservation, "RESERVATION_CHANGED")
        sent_authority = True

    try:
        async with asyncio.timeout(60):
            outcome = await attempt(root, m, case, wire, checked_authorize)
        receipt = {
            "manifest_sha256": h,
            "outcome": outcome,
            "semantic_accepted": False,
            "stopped": True,
            "stop_reason": "SINGLE_CALL_FINISHED_PENDING_HUMAN_REVIEW",
        }
        if outcome["record"]["local_routing"]["verdict"] != "pass":
            receipt["stop_reason"] = "CORRECT_CONTROL_NOT_PASS"
    except BaseException as exc:
        receipt = {
            "manifest_sha256": h,
            "error": safe_failure(exc),
            "details": exc.details if isinstance(exc, LunaAttemptFailure) else None,
            "semantic_accepted": False,
            "stopped": True,
            "stop_reason": "SINGLE_CALL_FAILED",
        }
    private_write(p / "receipt.json", receipt)
    return {
        "state": "STOPPED",
        "reason": receipt["stop_reason"],
        "receipt_sha256": sha(canonical(receipt)),
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--run-one", action="store_true")
    a = p.parse_args()
    if a.run_one:
        print(json.dumps(asyncio.run(step())))
    else:
        _, h = verify(ROOT)
        print(
            json.dumps(
                {
                    "manifest_sha256": h,
                    "requests_max": 1,
                    "real_calls": 0,
                    "new_request_approval": "pending",
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"state": "BLOCKED", "exception_type": type(exc).__name__}))
        raise SystemExit(2)
