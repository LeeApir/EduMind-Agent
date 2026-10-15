"""r09: explicit single-step dispatch and content-bound human fact gates. No automatic loop."""
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

from acceptance_support.claim_review_prototype import digest, encoded  # noqa: E402
from acceptance_support.derived_diagnostic_budget import DerivedBudget, exact, require  # noqa: E402
from acceptance_support.derived_responses_sender import (
    CredentialLease,
    FrozenResponsesSender,
)  # noqa: E402
from acceptance_support.phase1_budget import Approval, GateFailure  # noqa: E402
from app.services.provider_protocol import strict_json  # noqa: E402
from prepare_t040_derived_run import BASE_REL, PRIVATE_REL, environment_version  # noqa: E402


def read(root, name):
    path = root / BASE_REL / name
    require(not path.is_symlink(), "UNSAFE_PATH")
    return strict_json(path.read_bytes())


def frozen(root):
    m = read(root, "run-r09.json")
    require(m["execution_root"] == str(root.resolve()), "ROOT_CHANGED")
    check = object.__new__(DerivedBudget)
    check.serialized, check.root = encoded(m), root.resolve()
    check._validate()
    check._sources()
    require(m["corrections"] == 0 and m["bounds"]["requests"] == 38, "FREEZE_CHANGED")
    require(
        [c["id"] for c in m["cases"]] == ["queue-error", "correct-control"],
        "FREEZE_CHANGED",
    )
    return m


def run_approval(root, m):
    path = root / BASE_REL / "run-approval.json"
    require(path.is_file() and not path.is_symlink(), "NOT_AUTHORIZED")
    raw = path.read_bytes()
    a = strict_json(raw)
    exact(
        a,
        "version root_sha256 requests cost_micro_cny expires_at target_sha256 "
        "consent_sha256 proof_sha256 confirmed_by user_confirmation source_message_id terms_verified_on",
    )
    target = read(root, "target.json")
    require(
        a["version"] == "derived-calibration-run-approval-v1"
        and a["root_sha256"] == digest(m)
        and type(a["requests"]) is int
        and a["requests"] == m["bounds"]["requests"]
        and type(a["cost_micro_cny"]) is int
        and a["cost_micro_cny"] == m["bounds"]["cost_micro"]
        and type(a["expires_at"]) is int
        and a["expires_at"] == m["bounds"]["expires_at"]
        and a["target_sha256"] == m["target"]["target_sha256"]
        and a["consent_sha256"] == target["consent_sha256"]
        and a["proof_sha256"] == m["stages"]["inventory"]["proof_sha256"]
        and a["confirmed_by"] == "Lee"
        and type(a["user_confirmation"]) is str
        and bool(a["user_confirmation"].strip())
        and type(a["source_message_id"]) is str
        and bool(a["source_message_id"].strip())
        and a["terms_verified_on"] == time.strftime("%Y-%m-%d", time.localtime())
        and time.time() < a["expires_at"],
        "NOT_AUTHORIZED",
    )
    # This record is written by the trusted operator from actual human approval;
    # no CLI flag, model output or arbitrary approved=true field can create it.
    return Approval(
        digest(m),
        "diagnostic",
        a["requests"],
        a["cost_micro_cny"],
        hashlib.sha256(raw).hexdigest(),
        True,
    )


def leases(root, m, approval):
    target, consent = read(root, "target.json"), read(root, "consent.json")
    require(
        digest(target) == m["target"]["target_sha256"]
        and digest(consent) == target["consent_sha256"],
        "TARGET_CHANGED",
    )
    binding = consent["credential_binding"]
    require(
        binding["path"] == ".env"
        and target["credential_ref"] == "server-env:" + digest(binding),
        "TARGET_CHANGED",
    )

    def current():
        require(run_approval(root, m) == approval, "NOT_AUTHORIZED")
        path = root / ".env"
        require(environment_version(path) == binding["metadata"], "SAFETY_FAILURE")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r") as stream:
            st = os.fstat(stream.fileno())
            actual = {k: getattr(st, k) for k in binding["metadata"]}
            require(actual == binding["metadata"], "SAFETY_FAILURE")
            wanted = {
                "EDUMIND_PROVIDER_BASE_URL",
                "EDUMIND_PROVIDER_MODEL",
                "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
                "EDUMIND_PROVIDER_API_KEY",
            }
            values = {}
            for line in stream:
                key, sep, value = line.partition("=")
                if sep and key.strip() in wanted:
                    require(key.strip() not in values, "SAFETY_FAILURE")
                    values[key.strip()] = value.strip().strip('"').strip("'")
            st = os.fstat(stream.fileno())
            require(
                {k: getattr(st, k) for k in binding["metadata"]} == binding["metadata"],
                "SAFETY_FAILURE",
            )
        require(
            environment_version(path) == binding["metadata"] and set(values) == wanted,
            "SAFETY_FAILURE",
        )
        require(
            values["EDUMIND_PROVIDER_BASE_URL"] == target["base_url"]
            and values["EDUMIND_PROVIDER_MODEL"] == target["model"]
            and values["EDUMIND_PROVIDER_STRUCTURED_TRANSPORT"] == target["transport"],
            "TARGET_CHANGED",
        )
        return CredentialLease(
            values["EDUMIND_PROVIDER_API_KEY"],
            target["credential_ref"],
            target["credential_version"],
            target["consent_sha256"],
            digest(m),
            min(m["bounds"]["expires_at"], time.time() + 120),
        )

    return current


async def step(root=ROOT, *, transport=None, resolver=None):
    m = frozen(root)
    approval = run_approval(
        root, m
    )  # No state, key, DNS or network before exact approval.
    b = DerivedBudget(m, root=root, approval=approval)
    try:
        req = (
            b.prepare()
        )  # Includes case-review gate; no next case until human assessment.
        number = b.reserve(req["slot"], req["wire"], req["parents"])
        sender = FrozenResponsesSender(
            b,
            read(root, "target.json"),
            credentials=leases(root, m, approval),
            transport=transport,
            resolver=resolver,
        )
        return await sender.send(number)
    finally:
        b.close()


def reports(root=ROOT):
    m = frozen(root)
    path = root / m["ledger_path"]
    require(
        path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0,
        "LEDGER_MISSING",
    )
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        run = db.execute("SELECT * FROM run").fetchone()
        require(run["root"] == digest(m), "LEDGER_MISMATCH")
        result = []
        labels = read(root, "labels.json")
        for case in m["cases"]:
            rows = db.execute(
                "SELECT * FROM children WHERE case_id=? ORDER BY number", (case["id"],)
            ).fetchall()
            items, findings = [], []
            complete = False
            for row in rows:
                item = {
                    k: row[k]
                    for k in (
                        "number",
                        "slot",
                        "state",
                        "value_hash",
                        "response_hash",
                        "input_tokens",
                        "output_tokens",
                        "reasoning_tokens",
                        "cost",
                    )
                }
                if row["state"] == "verified":
                    value = strict_json(row["value"])
                    require(digest(value) == row["value_hash"], "PARENT_HASH_MISMATCH")
                    require(
                        value["request_binding"]["root_sha256"] == digest(m),
                        "PARENT_BINDING_MISMATCH",
                    )
                    check = object.__new__(DerivedBudget)
                    check.freeze = digest(m)
                    inner = check._value(row)
                    require(
                        hashlib.sha256(row["wire"]).hexdigest() == row["wire_hash"],
                        "WIRE_HASH_MISMATCH",
                    )
                    wire = strict_json(row["wire"])
                    payload = strict_json(wire["input"][1]["content"])
                    require(
                        payload["request_binding"] == value["request_binding"],
                        "PARENT_BINDING_MISMATCH",
                    )
                    item["result"] = inner
                    for i, finding in enumerate(inner.get("findings", [])):
                        findings.append(
                            {"ref": f"{row['number']}:finding:{i}", **finding}
                        )
                    for i, extra in enumerate(inner.get("incidental_findings", [])):
                        findings.append(
                            {
                                "ref": f"{row['number']}:incidental:{i}",
                                **extra["finding"],
                            }
                        )
                    complete |= row["stage"] == "overall"
                items.append(item)
            label = next(x for x in labels if x["case_id"] == case["id"])
            result.append(
                {
                    "version": "derived-case-report-v1",
                    "root_sha256": digest(m),
                    "case_id": case["id"],
                    "label_sha256": case["label_sha256"],
                    "criteria": label["criteria"],
                    "complete": complete,
                    "run_halted": run["halted"],
                    "findings": findings,
                    "attempts": items,
                }
            )
        return result
    finally:
        db.close()


def private_record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = encoded(value)
    require(
        not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
        "UNSAFE_PATH",
    )
    if path.exists():
        require(path.read_bytes() == raw, "EVIDENCE_EXISTS")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def assess(root, evidence):
    m = frozen(root)
    a = run_approval(root, m)
    exact(
        evidence,
        "version root_sha256 case_id report_sha256 confirmed_by user_confirmation "
        "source_message_id criteria",
    )
    report = next(
        (r for r in reports(root) if r["case_id"] == evidence["case_id"]), None
    )
    require(
        report is not None and report["complete"] and report["run_halted"] is None,
        "INVALID_ASSESSMENT",
    )
    require(
        evidence["version"] == "derived-case-assessment-v1"
        and evidence["root_sha256"] == digest(m)
        and evidence["report_sha256"] == digest(report)
        and evidence["confirmed_by"] == "Lee"
        and type(evidence["user_confirmation"]) is str
        and bool(evidence["user_confirmation"].strip())
        and type(evidence["source_message_id"]) is str
        and bool(evidence["source_message_id"].strip()),
        "INVALID_ASSESSMENT",
    )
    rows = evidence["criteria"]
    require(
        type(rows) is list
        and [x.get("criterion") for x in rows if type(x) is dict] == report["criteria"],
        "INVALID_ASSESSMENT",
    )
    found = {f["ref"]: f for f in report["findings"]}
    passed = True
    for row in rows:
        exact(row, "criterion passed finding_refs observation")
        require(
            type(row["passed"]) is bool
            and type(row["finding_refs"]) is list
            and type(row["observation"]) is str
            and bool(row["observation"].strip())
            and all(type(ref) is str and ref in found for ref in row["finding_refs"]),
            "INVALID_ASSESSMENT",
        )
        if row["passed"] and evidence["case_id"] == "queue-error":
            require(
                bool(row["finding_refs"])
                and all(found[ref]["area"] == "fact" for ref in row["finding_refs"]),
                "INVALID_ASSESSMENT",
            )
        if row["passed"] and evidence["case_id"] == "correct-control":
            require(
                not found
                and all(
                    item.get("result", {}).get("verdict", "pass") == "pass"
                    for item in report["attempts"]
                ),
                "INVALID_ASSESSMENT",
            )
        passed &= row["passed"]
    b = DerivedBudget(m, root=root, approval=a)
    try:
        # Confirm the record targets the currently gated case, not a prior completed case.
        with b._db() as db:
            b._gate(db)
            require(
                not db.execute(
                    "SELECT count(*) FROM decisions WHERE case_id=?",
                    (evidence["case_id"],),
                ).fetchone()[0],
                "INVALID_ASSESSMENT",
            )
            earlier = [c["id"] for c in m["cases"]][
                : next(
                    i
                    for i, c in enumerate(m["cases"])
                    if c["id"] == evidence["case_id"]
                )
            ]
            require(
                all(
                    db.execute(
                        "SELECT action FROM decisions WHERE case_id=?", (cid,)
                    ).fetchone()
                    for cid in earlier
                ),
                "INVALID_ASSESSMENT",
            )
        private_record(
            root / PRIVATE_REL / f"assessment-{evidence['case_id']}.json", evidence
        )
        b.decide("continue" if passed else "halt", assessment_sha256=digest(evidence))
        return {
            "case_id": evidence["case_id"],
            "human_gate_passed": passed,
            "t040_complete": False,
        }
    finally:
        b.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "step", "report", "assess"))
    parser.add_argument("--assessment", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "check":
            m = frozen(ROOT)
            print(
                json.dumps(
                    {
                        "state": "AWAITING_EXACT_RUN_APPROVAL",
                        "root_sha256": digest(m),
                        "requests": m["bounds"]["requests"],
                        "cost_micro_cny": m["bounds"]["cost_micro"],
                        "key_read": False,
                        "network": False,
                    }
                )
            )
        elif args.command == "step":
            print(json.dumps(asyncio.run(step())))
        elif args.command == "report":
            for r in reports():
                path = (
                    ROOT / PRIVATE_REL / f"report-{r['case_id']}-{digest(r)[:12]}.json"
                )
                private_record(path, r)
                print(
                    json.dumps(
                        {
                            "case_id": r["case_id"],
                            "complete": r["complete"],
                            "report_sha256": digest(r),
                            "path": str(path),
                        }
                    )
                )
        else:
            require(args.assessment is not None, "INVALID_ASSESSMENT")
            print(json.dumps(assess(ROOT, strict_json(args.assessment.read_bytes()))))
    except (GateFailure, OSError, ValueError) as exc:
        # Never serialize exception text from filesystem, vendor or credential parsing.
        code = exc.code if isinstance(exc, GateFailure) else "LOCAL_VALIDATION_FAILED"
        print(json.dumps({"error": code, "t040_complete": False}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
