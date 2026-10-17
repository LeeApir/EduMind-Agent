"""One frozen Qwen diagnostic slot, never generation or a default Provider switch."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.om_diagnostic import stable
from acceptance_support.qwen_review_budget import (
    Approval,
    FrozenBudget,
    GateFailure,
    canonical,
    sha,
)
from acceptance_support.qwen_review_attempt import AttemptFailure, perform, require
from app.agents.hybrid_resource_review import route_review
from app.services.learning_policy import active_policy_digest
from app.services.provider_protocol import strict_json

BASE = "docs/acceptance/phase-1-qwen-review-execution-r01"
DESIGN = "docs/acceptance/phase-1-review-model-candidate-r01"
PRIVATE = "local-materials/phase-1-qwen-review-execution-r01"
DATABASE = "edumind_catalog_qwen_review_20261017"


def read(path):
    require(path.is_file() and not path.is_symlink(), "NOT_AUTHORIZED")
    return strict_json(path.read_bytes())


def private_write(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


def load(root=ROOT, *, stop_only=False):
    p = read(root / BASE / "proposal.json")
    a = read(root / BASE / "run-approval.json")
    require(
        a.get("version") == "qwen-review-real-approval-v1"
        and a.get("proposal_sha256") == stable(p)
        and a.get("requests") == 12
        and type(a.get("requests")) is int
        and a.get("cost_micro_cny") == p["cost_micro_cny"]
        and type(a.get("cost_micro_cny")) is int
        and a.get("reviewer") == "Lee"
        and a.get("user_confirmation")
        and a.get("source_message_id")
        and (
            stop_only
            or time.time() < datetime.fromisoformat(p["expiry_local"]).timestamp()
        ),
        "NOT_AUTHORIZED",
    )
    require(p["execution_root"] == str(root.resolve()), "TARGET_CHANGED")
    for name, h in p["sources"].items():
        path = root / name
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and sha(path.read_bytes()) == h,
            "FREEZE_CHANGED",
        )
    data = read(root / DESIGN / "cases.json")
    labels = read(root / DESIGN / "proposed-labels.json")
    require(
        stable(data) == p["cases_sha256"]
        and stable(labels) == p["labels_sha256"]
        and active_policy_digest() == p["policy_digest"],
        "FREEZE_CHANGED",
    )
    human = read(root / BASE / "labels-human.json")
    require(
        human.get("proposal_sha256") == stable(p)
        and human.get("labels_sha256") == stable(labels)
        and human.get("case_digests")
        == {s: stable(c["material"]) for s, c in data.items()}
        and human.get("reviewer") == "Lee"
        and human.get("decision") == "accept_calibration_labels"
        and human.get("source_message_id"),
        "LABEL_REVIEW_REQUIRED",
    )
    if not stop_only:
        today = time.strftime("%Y-%m-%d")
        terms = read(root / BASE / ("terms-" + today + ".json"))
        require(
            terms.get("proposal_sha256") == stable(p)
            and terms.get("checked_on") == today
            and terms.get("official_terms_sha256") == p["official_terms_sha256"]
            and terms.get("unchanged_model_prices_and_limits") is True
            and terms.get("verified_by") == "assistant"
            and terms.get("source_urls") == p["official_sources"],
            "TERMS_RECHECK_REQUIRED",
        )
    require(
        len(data) == 12
        and tuple(data) == tuple(s["id"] for s in p["slots"])
        and [s["phase"] for s in p["slots"]] == ["screen"] * 4 + ["generalization"] * 8,
        "FREEZE_CHANGED",
    )
    for s in p["slots"]:
        wire = bytes.fromhex(data[s["id"]]["candidate_wire_hex"])
        body = strict_json(wire)
        require(
            sha(wire) == s["wire_sha256"]
            and len(wire) == s["wire_bytes"]
            and len(wire) <= 65536
            and body["model"] == "qwen3.8-max-0902"
            and body["enable_thinking"] is False
            and body["max_completion_tokens"] == 8192
            and body["response_format"]["type"] == "json_schema"
            and body["response_format"]["json_schema"]["strict"] is True
            and s["cost_micro_cny"] == 12 * (1048576 + len(wire)) + 36 * 8202,
            "OUTPUT_BUDGET_MISMATCH",
        )
    require(
        p["cost_micro_cny"] == sum(s["cost_micro_cny"] for s in p["slots"]) == 161071260
        and p["cost_micro_cny"] <= 164000000,
        "OUTPUT_BUDGET_MISMATCH",
    )
    return p, a, data


def manifest(p, root):
    target = {
        "provider_type": "openai-compatible",
        "model_id": "qwen3.8-max-0902",
        "adapter_sha256": p["sources"]["backend/app/services/openai_compatible.py"],
        "capability_sha256": p["official_terms_sha256"],
        "model_revision": "qwen3.8-max-0902",
        "currency": "CNY",
        "input_price_micro_per_million": 12000000,
        "output_price_micro_per_million": 36000000,
        "input_overhead_tokens": 1048576,
        "max_wire_bytes": max(s["wire_bytes"] for s in p["slots"]),
        "max_total_output_tokens": 8202,
        "total_output_limit_verified": True,
        "token_byte_bound_verified": True,
        "output_limit_path": ["max_completion_tokens"],
    }
    tid = stable(target)
    files = {
        **p["sources"],
        BASE + "/proposal.json": sha((root / BASE / "proposal.json").read_bytes()),
    }
    if (root / BASE / "labels-human.json").is_file():
        files[BASE + "/labels-human.json"] = sha(
            (root / BASE / "labels-human.json").read_bytes()
        )
    return {
        "version": "phase1-run-v1",
        "run_id": "qwen-review-execution-r01",
        "state": "FROZEN_RUN_READY",
        "phase": "diagnostic",
        "files": files,
        "targets": {tid: target},
        "slots": [
            {
                "id": s["id"],
                "input_sha256": s["wire_sha256"],
                "attempts": 1,
                "stages": ["probe"],
                "targets": [tid],
                "resources": ["unit"],
            }
            for s in p["slots"]
        ],
        "bounds": {
            "requests": 12,
            "cost_micro": p["cost_micro_cny"],
            "max_active_attempts": 1,
            "timeout_seconds": 60,
            "corrections_per_resource": 2,
        },
        "required_evidence": ["adr", "connection"],
        "evidence": {
            "adr": files["docs/ADR/0015-approval-20261015.json"],
            "connection": files[
                "docs/acceptance/phase-1-provider-connection-v1/results/final.json"
            ],
        },
    }


def credentials(root, p):
    fd = os.open(root / ".env", os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        meta = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(meta.st_mode)
            and meta.st_mode & 0o077 == 0
            and all(
                getattr(meta, k) == v for k, v in p["credential_file_metadata"].items()
            ),
            "TARGET_CHANGED",
        )
        groups = []
        group = {}
        mode = None
        wanted = {
            "EDUMIND_PROVIDER_BASE_URL",
            "EDUMIND_PROVIDER_MODEL",
            "EDUMIND_PROVIDER_API_KEY",
        }
        for line in stream:
            line = line.strip()
            comment = line.startswith("#")
            text = line[1:].strip() if comment else line
            name, sep, value = text.partition("=")
            name = name.strip()
            if sep and name in wanted:
                if mode != comment or name in group:
                    group = {}
                    mode = comment
                group[name] = value.strip().strip('"').strip("'")
                if set(group) == wanted:
                    groups.append((mode, group))
                    group = {}
                    mode = None
        current = os.fstat(stream.fileno())
        require(
            all(
                getattr(current, k) == getattr(meta, k)
                for k in p["credential_file_metadata"]
            ),
            "SAFETY_FAILURE",
        )
    active = [
        g
        for mode, g in groups
        if not mode
        and g["EDUMIND_PROVIDER_MODEL"] == "deepseek-flash"
        and g["EDUMIND_PROVIDER_BASE_URL"] == "https://api.deepseek.com"
    ]
    qwen = [
        g
        for mode, g in groups
        if mode
        and g["EDUMIND_PROVIDER_MODEL"] == "qwen3.8-max-0902"
        and sha(g["EDUMIND_PROVIDER_BASE_URL"].encode()) == p["endpoint_sha256"]
    ]
    require(len(active) == len(qwen) == 1, "TARGET_CHANGED")
    key = qwen[0]["EDUMIND_PROVIDER_API_KEY"]
    require(
        key
        and key != active[0]["EDUMIND_PROVIDER_API_KEY"]
        and all(32 < ord(c) < 127 for c in key),
        "SAFETY_FAILURE",
    )
    return qwen[0]["EDUMIND_PROVIDER_BASE_URL"], key


def database_url():
    from sqlalchemy.engine import make_url

    raw = os.environ.get("EDUMIND_TEST_DATABASE_URL", "")
    try:
        u = make_url(raw)
    except Exception:
        raise GateFailure("PRIVATE_DATABASE_REQUIRED") from None
    require(
        u.drivername == "postgresql+asyncpg"
        and u.host == "127.0.0.1"
        and u.port == 15437
        and u.database == DATABASE,
        "PRIVATE_DATABASE_REQUIRED",
    )
    return raw


def human_checks(root, p, snapshot, gate):
    private = root / PRIVATE
    receipts = {}
    for row in snapshot["attempts"]:
        require(row[6] == "complete", "SEND_STATE_UNCERTAIN")
        slot = row[1]
        receipt = read(private / (slot + ".json"))
        receipts[slot] = stable(receipt)
        decision = read(private / (slot + "-human.json"))
        require(
            decision.get("proposal_sha256") == stable(p)
            and decision.get("receipt_sha256") == stable(receipt)
            and decision.get("reviewer") == "Lee"
            and decision.get("source_message_id"),
            "HUMAN_CHECK_REQUIRED",
        )
        if decision.get("decision") == "eliminate" or decision.get("issues"):
            gate.halt("ADMISSION_FAILED")
            raise GateFailure("RUN_HALTED")
        require(
            decision.get("decision") == "continue"
            and all(
                decision.get(k) is True
                for k in [
                    "completeness_checked",
                    "all_assertions_checked",
                    "all_citations_checked",
                ]
            )
            and decision.get("issues") == [],
            "HUMAN_CHECK_REQUIRED",
        )
    if len(snapshot["attempts"]) >= 4:
        phase = read(private / "screen-pass.json")
        expected = {s["id"]: receipts[s["id"]] for s in p["slots"][:4]}
        require(
            phase.get("proposal_sha256") == stable(p)
            and phase.get("receipt_digests") == expected
            and phase.get("decision") == "admit_generalization"
            and phase.get("reviewer") == "Lee"
            and phase.get("source_message_id"),
            "SCREEN_SIGNOFF_REQUIRED",
        )
    return receipts


def assess(case, value):
    route = route_review(value, scope="unit", catalog=case["anchors"])
    kind = case["comparison_kind"]
    if kind == "positive":
        ok = route["verdict"] == "pass"
    else:
        ok = route["verdict"] == "reject" and any(
            f["category"] == ("fact" if kind == "fact" else "code_safety")
            and f["severity"] in {"major", "severe"}
            for f in value["findings"]
        )
    if kind == "mixed":
        ok = ok and bool(value["unresolved"])
    return {
        "route": route,
        "criterion_signal": ok,
        "semantic_confirmed": False,
        "all_assertions_and_citations_human_check_required": True,
    }


def _gate(p, a, root):
    private = root / PRIVATE
    m = manifest(p, root)
    return FrozenBudget(
        m,
        private / "budget.sqlite",
        root=root,
        approval=Approval(
            stable(m), "diagnostic", 12, p["cost_micro_cny"], stable(a), True
        ),
    )


async def step(root=ROOT, *, attempt=perform, check_complete=False):
    p, a, data = load(root)
    private = root / PRIVATE
    require(
        not private.is_symlink()
        and private.parent.resolve().is_relative_to(root.resolve()),
        "SAFETY_FAILURE",
    )
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(
        not private.is_symlink()
        and private.resolve().is_relative_to(root.resolve())
        and private.stat().st_mode & 0o077 == 0,
        "SAFETY_FAILURE",
    )
    fd = os.open(
        private / "execution.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate = _gate(p, a, root)
        enrollment = private / "enrollment.json"
        if enrollment.exists():
            require(
                read(enrollment) == {"proposal_sha256": stable(p)}
                and gate.ledger.is_file(),
                "LEDGER_MISSING",
            )
        else:
            require(not gate.ledger.exists(), "LEDGER_MISMATCH")
            private_write(enrollment, {"proposal_sha256": stable(p)})
        snap = gate.snapshot()
        require(snap["halted"] is None, "RUN_HALTED")
        human_checks(root, p, snap, gate)
        if check_complete:
            require(len(snap["attempts"]) == 12, "DIAGNOSTIC_INCOMPLETE")
            return {
                "status": "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION",
                "t040_passed": False,
                "requests_sent": 0,
            }
        require(snap["unattempted_slots"], "BUDGET_EXHAUSTED")
        slot = snap["unattempted_slots"][0]
        case = data[slot]
        wire = bytes.fromhex(case["candidate_wire_hex"])
        tid = next(iter(gate.manifest["targets"]))
        number = gate.reserve(slot, "probe", tid, wire, resource="unit")
        receipt = None
        outcome = None
        try:
            async with asyncio.timeout(60):
                endpoint, key = credentials(root, p)
                url = database_url()

                async def authorize(request):
                    require(
                        request.route.model_id == "qwen3.8-max-0902"
                        and request.purpose == "connection_test"
                        and request.route.data_categories == frozenset({"probe"}),
                        "TARGET_CHANGED",
                    )
                    fresh_p, fresh_a, _ = load(root)
                    require(
                        stable(fresh_p) == stable(p) and stable(fresh_a) == stable(a),
                        "NOT_AUTHORIZED",
                    )
                    gate._authorize()

                outcome = await attempt(
                    case,
                    wire,
                    endpoint=endpoint,
                    key=key,
                    database_url=url,
                    authorize=authorize,
                )
                usage = (outcome["input_tokens"], outcome["output_tokens"])
                require(all(type(v) is int and v >= 0 for v in usage), "USAGE_UNKNOWN")
                require(
                    usage[0] <= 1048576 + len(wire) and usage[1] <= 8202,
                    "USAGE_BOUND_EXCEEDED",
                )
                record = outcome["review_record"]
                require(
                    record["request_digest"] == sha(wire)
                    and record["binding"] == case["material"]["binding"]
                    and record["prompt_version"] == "evidence-resource-review-v4.5",
                    "TARGET_CHANGED",
                )
                evaluation = assess(case, record["result"])
                receipt = {
                    "proposal_sha256": stable(p),
                    "slot": slot,
                    "phase": next(s["phase"] for s in p["slots"] if s["id"] == slot),
                    "request_sha256": sha(wire),
                    "review_record": record,
                    "model_id": outcome["model_id"],
                    "input_tokens": usage[0],
                    "output_tokens": usage[1],
                    "completeness": {
                        "normal_finish": outcome["normal_finish"],
                        "response_model_matches": outcome["model_id"]
                        in {"qwen3.8-max-0902", "qwen3.8-max-2026-09-02"},
                        "schema_valid": outcome["schema_valid"],
                        "exact_wire_and_bound_policy": True,
                        "usage_known_and_within_8202": True,
                        "single_send": outcome["sent"] == 1,
                        "credential_cleanup": all(outcome["cleanup"].values()),
                    },
                    "local_assessment": evaluation,
                    "raw_response_sha256": outcome["raw_response_sha256"],
                    "human_confirmed": False,
                    "t040_passed": False,
                }
                require(all(receipt["completeness"].values()), "INVALID_OUTPUT")
                require(evaluation["criterion_signal"], "CANDIDATE_CRITERION_FAILED")
                private_write(private / (slot + ".json"), receipt)
                gate.finish(number, input_tokens=usage[0], output_tokens=usage[1])
        except BaseException as exc:
            observation = (
                exc.observation
                if isinstance(exc, AttemptFailure)
                else {
                    "version": "qwen-runner-failure-v1",
                    "normalized_error": "TIMEOUT"
                    if isinstance(exc, (TimeoutError, asyncio.CancelledError))
                    else "INVALID_OUTPUT",
                    "gate_code": exc.code if isinstance(exc, GateFailure) else None,
                    "input_tokens": outcome.get("input_tokens") if outcome else None,
                    "output_tokens": outcome.get("output_tokens") if outcome else None,
                    "cleanup": outcome.get("cleanup") if outcome else None,
                }
            )
            try:
                gate.finish(
                    number,
                    error_code=observation["normalized_error"],
                    input_tokens=observation.get("input_tokens"),
                    output_tokens=observation.get("output_tokens"),
                )
            finally:
                gate.halt("ADMISSION_FAILED")
            if receipt is not None:
                private_write(private / (slot + "-failed.json"), receipt)
            private_write(
                private / (slot + "-failure.json"),
                {
                    "proposal_sha256": stable(p),
                    "slot": slot,
                    "observation": observation,
                    "complete_review_record": outcome.get("review_record")
                    if outcome
                    else None,
                    "candidate_eliminated": True,
                    "t040_passed": False,
                },
            )
            raise GateFailure("CANDIDATE_ELIMINATED") from None
        return {
            "status": "HUMAN_CHECK_REQUIRED",
            "slot": slot,
            "receipt_sha256": stable(receipt),
            "requests_sent": 1,
            "t040_passed": False,
        }
    finally:
        os.close(fd)


def eliminate(root, slot, issues):
    """Persist assistant/human semantic failure separately, never rewrite original receipt."""
    p, a, _ = load(root, stop_only=True)
    private = root / PRIVATE
    fd = os.open(private / "execution.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate = _gate(p, a, root)
        receipt = read(private / (slot + ".json"))
        require(
            isinstance(issues, list)
            and issues
            and all(isinstance(i, str) and i.strip() for i in issues),
            "INVALID_OBSERVATION",
        )
        gate.halt("ADMISSION_FAILED")
        private_write(
            private / (slot + "-semantic-stop.json"),
            {
                "proposal_sha256": stable(p),
                "receipt_sha256": stable(receipt),
                "decision": "eliminate_candidate",
                "issues": issues,
                "reviewer_type": "assistant",
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
        print(json.dumps(asyncio.run(step(check_complete=args.check_complete))))
    except (GateFailure, OSError, ValueError):
        print(json.dumps({"status": "STOPPED_OR_NOT_AUTHORIZED", "t040_passed": False}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
