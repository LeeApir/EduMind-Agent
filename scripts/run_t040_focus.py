"""Fixed-focus r10: explicit one-step sender, manual fact gate and zero-call check/report."""
# ruff: noqa: E402

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from acceptance_support import claim_review_prototype as p
from acceptance_support.derived_diagnostic_budget import require
from acceptance_support.fixed_focus_gate import FixedFocusGate
from acceptance_support.derived_responses_sender import (
    CredentialLease,
    FrozenResponsesSender,
)
from acceptance_support.phase1_budget import Approval, FrozenBudget, GateFailure
from app.services.provider_protocol import strict_json
from prepare_t040_focus import BASE_REL
from prepare_t040_derived_run import environment_version


def load(root):
    base = root / BASE_REL
    require(not base.is_symlink(), "UNSAFE_PATH")
    data = {
        name: strict_json((base / name).read_bytes())
        for name in ("run.json", "plan.json", "requests.json")
    }
    m, plan = data["run.json"], data["plan.json"]
    require(
        plan["execution_root"] == str(root.resolve()) and plan["round"] == 1,
        "ROOT_CHANGED",
    )
    gate = FrozenBudget(m, root / "unused.sqlite", root=root)
    for name, expected in m["files"].items():
        path = root / name
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "FREEZE_CHANGED",
        )
    require(
        list(data["requests.json"]) == [s["id"] for s in m["slots"]], "FREEZE_CHANGED"
    )
    require(
        m["bounds"]["cost_micro"] == plan["cost_cap_micro_cny"]
        and gate.manifest["bounds"]["requests"] == 4,
        "FREEZE_CHANGED",
    )
    return m, plan, data["requests.json"]


def approval(root, m, plan):
    path = root / BASE_REL / "run-approval.json"
    require(path.is_file() and not path.is_symlink(), "NOT_AUTHORIZED")
    raw = path.read_bytes()
    a = strict_json(raw)
    p.obj(
        a,
        "version root_sha256 requests cost_micro_cny scope_sha256 expires_at exit_limits "
        "confirmed_by user_confirmation source_message_id terms_verified_on",
    )
    require(
        a["version"] == "fixed-focus-run-approval-v1"
        and a["root_sha256"] == p.digest(m)
        and type(a["requests"]) is int
        and a["requests"] == 4
        and type(a["cost_micro_cny"]) is int
        and a["cost_micro_cny"] == plan["cost_cap_micro_cny"]
        and a["scope_sha256"] == plan["scope_sha256"]
        and type(a["expires_at"]) is int
        and a["expires_at"] == plan["expires_at"]
        and p.encoded(a["exit_limits"]) == p.encoded(plan["exit_limits"])
        and a["confirmed_by"] == "Lee"
        and all(
            type(a[k]) is str and bool(a[k].strip())
            for k in ("user_confirmation", "source_message_id")
        )
        and a["terms_verified_on"] == time.strftime("%Y-%m-%d", time.localtime())
        and time.time() < plan["expires_at"],
        "NOT_AUTHORIZED",
    )
    return Approval(
        p.digest(m),
        "diagnostic",
        4,
        plan["cost_cap_micro_cny"],
        hashlib.sha256(raw).hexdigest(),
        True,
    )


def credentials(root, m, plan, authorized):
    def current():
        require(approval(root, m, plan) == authorized, "NOT_AUTHORIZED")
        path = root / ".env"
        expected = plan["credential_binding"]["metadata"]
        require(environment_version(path) == expected, "SAFETY_FAILURE")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r") as stream:
            require(
                {k: getattr(os.fstat(stream.fileno()), k) for k in expected}
                == expected,
                "SAFETY_FAILURE",
            )
            values = {}
            wanted = {
                "EDUMIND_PROVIDER_BASE_URL",
                "EDUMIND_PROVIDER_MODEL",
                "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
                "EDUMIND_PROVIDER_API_KEY",
            }
            for line in stream:
                k, sep, v = line.partition("=")
                if sep and k.strip() in wanted:
                    require(k.strip() not in values, "SAFETY_FAILURE")
                    values[k.strip()] = v.strip().strip('"').strip("'")
            require(
                {k: getattr(os.fstat(stream.fileno()), k) for k in expected}
                == expected,
                "SAFETY_FAILURE",
            )
        require(
            environment_version(path) == expected and set(values) == wanted,
            "SAFETY_FAILURE",
        )
        require(
            values["EDUMIND_PROVIDER_BASE_URL"] == "https://api.deepseek.com"
            and values["EDUMIND_PROVIDER_MODEL"] == "deepseek-flash"
            and values["EDUMIND_PROVIDER_STRUCTURED_TRANSPORT"]
            == "responses_json_schema",
            "TARGET_CHANGED",
        )
        target = plan["target"]
        return CredentialLease(
            values["EDUMIND_PROVIDER_API_KEY"],
            target["credential_ref"],
            1,
            target["consent_sha256"],
            p.digest(m),
            min(plan["expires_at"], time.time() + 60),
        )

    return current


async def step(root=ROOT, *, transport=None, resolver=None):
    m, plan, requests = load(root)
    a = approval(root, m, plan)
    gate = FixedFocusGate(root, m, plan, requests, a)
    try:
        n = gate.reserve_next()
        sender = FrozenResponsesSender(
            gate,
            plan["target"],
            credentials=credentials(root, m, plan, a),
            transport=transport,
            resolver=resolver,
        )
        result = await sender.send(n)
        gate.coarse_gate(n)
        return {**result, "state": "HUMAN_REVIEW_REQUIRED", "t040_complete": False}
    finally:
        gate.close()


def report(root=ROOT):
    m, plan, _ = load(root)
    path = root / "local-materials/phase-1-t040-focus-r10/budget.sqlite"
    require(
        path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0,
        "LEDGER_MISSING",
    )
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        run = dict(db.execute("SELECT * FROM run").fetchone())
        require(run["freeze"] == p.digest(m), "LEDGER_MISMATCH")
        rows = []
        for r in db.execute(
            "SELECT a.*,r.value,r.value_hash,r.response_hash,r.reasoning_tokens,r.assessment_hash "
            "FROM attempts a LEFT JOIN receipts r ON a.number=r.number ORDER BY a.number"
        ):
            row = dict(r)
            if row["value"] is not None:
                value = strict_json(row.pop("value"))
                require(p.digest(value) == row["value_hash"], "PARENT_HASH_MISMATCH")
                req = strict_json(requests_wire(m, root, row["slot"]))
                require(
                    value["request_id"]
                    == strict_json(req["input"][1]["content"])["request_id"],
                    "PARENT_BINDING_MISMATCH",
                )
                row["value"] = value
            rows.append(row)
        return {
            "root_sha256": p.digest(m),
            "run": run,
            "attempts": rows,
            "t040_complete": False,
        }
    finally:
        db.close()


def requests_wire(m, root, slot):
    requests = strict_json((root / BASE_REL / "requests.json").read_bytes())
    wire = p.encoded(requests[slot])
    require(
        hashlib.sha256(wire).hexdigest()
        == next(s["input_sha256"] for s in m["slots"] if s["id"] == slot),
        "FREEZE_CHANGED",
    )
    return wire


def assess(root, evidence):
    m, plan, requests = load(root)
    a = approval(root, m, plan)
    gate = FixedFocusGate(root, m, plan, requests, a)
    try:
        private = root / "local-materials/phase-1-t040-focus-r10"
        path = (
            private / f"assessment-{evidence['number']}-{p.digest(evidence)[:16]}.json"
        )
        require(
            type(evidence["number"]) is int and 1 <= evidence["number"] <= 4,
            "INVALID_ASSESSMENT",
        )
        raw = p.encoded(evidence)
        if path.exists():
            require(
                not path.is_symlink() and path.read_bytes() == raw, "INVALID_ASSESSMENT"
            )
        else:
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        gate.assess(evidence)
        return {"fact_gate_passed": evidence["passed"], "t040_complete": False}
    finally:
        gate.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "step", "report", "assess"))
    parser.add_argument("--assessment", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "check":
            m, plan, _ = load(ROOT)
            print(
                json.dumps(
                    {
                        "state": "NO_MODEL_CALL",
                        "root_sha256": p.digest(m),
                        "requests": 4,
                        "cost_micro_cny": plan["cost_cap_micro_cny"],
                    }
                )
            )
        elif args.command == "step":
            print(json.dumps(asyncio.run(step())))
        elif args.command == "report":
            print(json.dumps(report(), ensure_ascii=False))
        else:
            require(args.assessment is not None, "INVALID_ASSESSMENT")
            print(json.dumps(assess(ROOT, strict_json(args.assessment.read_bytes()))))
    except (GateFailure, p.Invalid, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "error": exc.code
                    if isinstance(exc, GateFailure)
                    else "LOCAL_VALIDATION_FAILED",
                    "t040_complete": False,
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
