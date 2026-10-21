"""Four-case generation-only acceptance. Check is offline; all execution needs exact approval."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_five_hour_acceptance as parent
import acceptance_support.five_hour_runtime as kernel
from acceptance_support.five_hour_runtime import (
    read_json,
    require,
    write_once,
    private_directory,
)
from acceptance_support.luna_admission_gate import env_metadata
from acceptance_support.qwen_review_budget import canonical, sha
from check_five_hour_materials import validate_evaluation
from app.services.learning_policy import active_policy_digest

PACKAGE = ROOT / "docs/acceptance/phase-1-generation-mini-r01"
PRIVATE = ROOT / "local-materials/phase-1-generation-mini-r01"
ORDER = ["A01", "A02", "A03", "A04"]
RUN_ID = "generation-mini-r01"
DATABASE = "edumind_catalog_generation_mini_r01"


class MiniLedger(kernel.RunLedger):
    def _clock(self, db, *, sending=False):
        t0, last, halt = db.execute("select t0,last_clock,halt from run").fetchone()
        now = self.now()
        require(halt is None, "RUN_STOPPED")
        require(now >= last, "CLOCK_MOVED_BACKWARD")
        require(now < t0 + (2700 if sending else 3600), "RUN_DEADLINE")
        db.execute("update run set last_clock=?", (now,))

    def reserve(self, name, request_hash):
        require(len(self.snapshot()["calls"]) < 48, "MINI_TOTAL_REQUEST_LIMIT")
        return super().reserve(name, request_hash)


class MiniTransport(parent.AuditTransport):
    async def handle_async_request(self, request):
        body = json.loads(request.content)
        existing = []
        for row in self.context["ledger"].snapshot()["calls"]:
            path = PRIVATE / row[1] / f"{row[0]:02}-request.json"
            existing.append(json.loads(bytes.fromhex(read_json(path)["wire_hex"])))
        is_review = body.get("model") == parent.CONFIG.review_model
        require(
            body.get("model")
            in {parent.CONFIG.review_model, parent.CONFIG.generation_model},
            "MINI_MODEL_CHANGED",
        )
        matching = [b for b in existing if b["model"] == body["model"]]
        require(len(matching) < 24, "MINI_MODEL_CALL_CAP")
        if not is_review:
            limit = body.get("max_output_tokens")
            require(limit in {2048, 4096}, "MINI_GENERATION_OUTPUT_CHANGED")
            require(
                sum(b.get("max_output_tokens") == limit for b in matching)
                < (4 if limit == 2048 else 20),
                "MINI_STAGE_CALL_CAP",
            )
        return await super().handle_async_request(request)


class MiniEvidenceGateway(parent.EvidenceGateway):
    async def generate_structured(self, request, *, retry_safe=False):
        result = await super().generate_structured(request, retry_safe=retry_safe)
        output = 0
        for row in self.context["ledger"].snapshot()["calls"]:
            parsed = read_json(PRIVATE / row[1] / f"{row[0]:02}-parsed.json")
            output += parsed["usage"]["output_tokens"]
        if output > 286720:
            self.context["ledger"].stop("MINI_OUTPUT_USAGE_LIMIT")
            raise ValueError("MINI_OUTPUT_USAGE_LIMIT")
        return result


def verify():
    m = read_json(PACKAGE / "manifest.json")
    require(
        m["kind"] == "FROZEN_GENERATION_MINI_NOT_EXECUTION_AUTHORITY"
        and m["real_requests_authorized"] == 0,
        "PREPARATION_ONLY",
    )
    require(
        m["order"] == ORDER
        and m["requests_max"] == 48
        and m["normal_requests"] == 32
        and m["wall_seconds"] == 3600
        and m["send_cutoff_seconds"] == 2700,
        "BUDGET_CHANGED",
    )
    require(m["policy_digest"] == active_policy_digest(), "POLICY_CHANGED")
    require(
        m["env_metadata"] == env_metadata(ROOT / ".env"), "CONNECTION_METADATA_CHANGED"
    )
    for name, digest in m["files"].items():
        p = ROOT / name
        require(
            p.resolve().is_relative_to(ROOT)
            and not p.is_symlink()
            and sha(p.read_bytes()) == digest,
            "FREEZE_CHANGED",
        )
    for name, digest in m["historical_ledgers"].items():
        require(sha((ROOT / name).read_bytes()) == digest, "HISTORICAL_LEDGER_CHANGED")
    return m, sha(canonical(m))


def authorize():
    m, h = verify()
    path = PACKAGE / "run-approval.json"
    require(path.is_file(), "EXACT_NEW_APPROVAL_REQUIRED")
    a = read_json(path)
    require(
        a
        == dict(
            manifest_sha256=h,
            decision="approve_generation_mini_only",
            requests_max=48,
            wall_seconds=3600,
            fees="uncapped",
            reviewer="Lee",
            source_user_message=a.get("source_user_message"),
        )
        and bool(a["source_user_message"]),
        "EXACT_NEW_APPROVAL_REQUIRED",
    )
    return m, h


def configure():
    kernel.ORDER = list(ORDER)
    parent.ORDER = list(ORDER)
    parent.BASE = PACKAGE
    parent.PACKAGE = PACKAGE
    parent.PRIVATE = PRIVATE
    parent.DATABASE = DATABASE
    parent.AuditTransport = MiniTransport
    parent.EvidenceGateway = MiniEvidenceGateway


def assess(ledger, name, value):
    validate_evaluation(value, base=PACKAGE)
    require(value["run_id"] == RUN_ID and value["case_id"] == name, "WRONG_RUN_OR_CASE")
    result = read_json(PRIVATE / name / "result.json")
    state = next(row for row in ledger.snapshot()["cases"] if row[0] == name)
    require(
        state[1] == "awaiting_gpt" and state[2] == sha(canonical(result)),
        "RESULT_CHANGED",
    )
    parent.verify_artifacts(result)
    parent.check_audit_coverage(value, result, root=ROOT)
    require(
        value["actual"]["status"] == "observed"
        and value["reviewed_all_candidates_and_audit_history"],
        "COMPLETE_HISTORY_ASSESSMENT_REQUIRED",
    )
    require(
        value["actual"]["actual_call_count"] == result["actual_call_count"]
        and value["actual"]["course_state"] == result["course_state"],
        "OBSERVATION_CHANGED",
    )
    expected = {
        str((PRIVATE / name / f"{n:02}-{kind}.json").relative_to(ROOT))
        for n in result["call_ids"]
        for kind in ["request", "receipt"]
    }
    require(
        set(value["actual"]["request_receipt_paths"]) == expected,
        "ALL_REQUEST_RECEIPTS_REQUIRED",
    )
    expected = {
        str((PRIVATE / name / f"{n:02}-response.bin").relative_to(ROOT))
        for n in result["call_ids"]
    }
    require(
        set(value["actual"]["response_artifact_paths"]) == expected,
        "ALL_RESPONSES_REQUIRED",
    )
    unit = next((r for r in result["reviews"] if r["result"]["scope"] == "unit"), None)
    if unit is None:
        require(
            value["grades"]["core_expected"] != "pass",
            "UNIT_REVIEW_REQUIRED_FOR_CORE_PASS",
        )
    parsed = [
        read_json(PRIVATE / name / f"{n:02}-parsed.json")
        if (PRIVATE / name / f"{n:02}-parsed.json").exists()
        else None
        for n in result["call_ids"]
    ]
    for field in ("input_tokens", "output_tokens"):
        known = all(p and p.get("usage", {}).get(field) is not None for p in parsed)
        expected_usage = sum(p["usage"][field] for p in parsed) if known else None
        require(value["actual"][field] == expected_usage, "ACTUAL_USAGE_CHANGED")
    if unit:
        require(
            value["actual"]["model_verdict"] == unit["result"]["verdict"]
            and value["actual"]["local_verdict"] == unit["local_routing"]["verdict"],
            "ACTUAL_VERDICT_CHANGED",
        )
    for e in value["evidence"]:
        p = ROOT / e["artifact_path"]
        require(
            p.resolve().is_relative_to(ROOT)
            and not p.is_symlink()
            and sha(p.read_bytes()) == e["artifact_sha256"],
            "ASSESSMENT_EVIDENCE_CHANGED",
        )
    g = value["grades"]
    red = g["impact"] == "red"
    digest = write_once(PRIVATE / name / "evaluation.json", value)
    ledger.assess(name, digest, red=red)
    if g["technical_integrity"] != "pass":
        ledger.stop("TECHNICAL_INTEGRITY_FAILURE")
    if name in ORDER[:2] and g["full_quality"] != "pass":
        ledger.stop("TARGETED_REQUIRED_CASE_FAILED")
    scored = [
        read_json(PRIVATE / n / "evaluation.json")
        for n in ORDER
        if (PRIVATE / n / "evaluation.json").exists()
    ]
    if sum(v["grades"]["full_quality"] != "pass" for v in scored) > 1:
        ledger.stop("THREE_OF_FOUR_UNREACHABLE")
    if len(scored) == 4:
        qualified = (
            all(v["grades"]["full_quality"] == "pass" for v in scored[:2])
            and sum(v["grades"]["full_quality"] == "pass" for v in scored) >= 3
        )
        ledger.stop(
            "MINI_COMPLETED_QUALIFIED" if qualified else "MINI_COMPLETED_NOT_QUALIFIED"
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command", choices=["check", "init", "run", "assess", "report", "stop"]
    )
    p.add_argument("--case", choices=ORDER)
    p.add_argument("--evaluation", type=Path)
    args = p.parse_args()
    if args.command == "check":
        m, h = verify()
        print(
            json.dumps(
                dict(
                    manifest_sha256=h,
                    order=ORDER,
                    normal_requests=32,
                    max_requests=48,
                    live_execution_authorized=False,
                    provider_calls=0,
                )
            )
        )
        return
    m, h = authorize()
    configure()
    private_directory(PRIVATE)
    with (PRIVATE / "process.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "init":
            require(not (PRIVATE / "run.sqlite").exists(), "NO_RUN_REPLAY")
            env = parent.isolated_environment()
            asyncio.run(
                parent.verify_database(env["EDUMIND_DATABASE_URL"], require_empty=True)
            )
            parent.load_keys(m["env_metadata"])
            write_once(PRIVATE / "credential-binding.json", m["env_metadata"])
            ledger = MiniLedger(PRIVATE / "run.sqlite", h, t0=time.time())
        else:
            ledger = MiniLedger(PRIVATE / "run.sqlite", h)
        if args.command == "run":
            require(args.case is not None, "CASE_REQUIRED")
            parent.verify_prior_results(ledger)
            env = parent.isolated_environment()
            url = env["EDUMIND_DATABASE_URL"]
            asyncio.run(parent.verify_database(url))
            keys = parent.load_keys(read_json(PRIVATE / "credential-binding.json"))
            ledger.start_case(args.case)
            directory = private_directory(PRIVATE / args.case)
            os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
            try:
                print(
                    json.dumps(
                        asyncio.run(
                            parent.execute_case(args.case, ledger, directory, url, keys)
                        )
                    )
                )
            finally:
                os.environ.pop("EDUMIND_PRODUCT_MODE", None)
        elif args.command == "assess":
            require(
                args.case is not None and args.evaluation is not None,
                "ASSESSMENT_REQUIRED",
            )
            assess(ledger, args.case, read_json(args.evaluation))
        elif args.command == "stop":
            ledger.stop("EXPLICIT_MINI_STOP")
        print(json.dumps(ledger.snapshot()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Mini run failed closed; no automatic retry or old-run reopening.",
            file=sys.stderr,
        )
        sys.exit(1)
