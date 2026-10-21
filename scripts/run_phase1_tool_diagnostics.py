"""Approved bounded tool diagnosis: max3 new calls, aggregate8/CNY1, no blind retries."""
# ruff: noqa: E402

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from run_phase1_provider_connection import BASE, MODEL, ROOT, canonical, dump, sha
from acceptance_support.phase1_budget import Approval, FrozenBudget
from acceptance_support.tool_probe_attempt import run_probe

AUTH = BASE / "tool-diagnostics-approval.json"
ROOT_PRIORS = [
    ("r01", 1, 10860, "TEMPORARILY_UNAVAILABLE"),
    ("diagnostic-r02", 1, 10860, None),
    ("checks-r03", 2, 24768, None),
    ("tool-r04", 1, 14724, "INVALID_OUTPUT"),
]


def names(number):
    if number not in {5, 6, 7}:
        raise ValueError("ROUND_NOT_APPROVED")
    folder = f"tool-diagnostic-r{number:02d}"
    return folder, ROOT / "local-materials/phase-1-t039" / folder


def prior_check(number):
    names(number)
    count = cost = 0
    for folder, expected_n, expected_c, expected_h in ROOT_PRIORS:
        path = ROOT / "local-materials/phase-1-t039" / folder / "budget.sqlite"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            n, c = db.execute(
                "SELECT count(*),sum(cost_micro) FROM attempts"
            ).fetchone()
            halt = db.execute("SELECT halted FROM run WHERE id=1").fetchone()[0]
        if (n, c, halt) != (expected_n, expected_c, expected_h):
            raise ValueError("PRIOR_BUDGET_CHANGED")
        count += n
        cost += c
    for i in range(5, number):
        folder, evidence = names(i)
        with sqlite3.connect(
            f"file:{evidence / 'budget.sqlite'}?mode=ro", uri=True
        ) as db:
            rows = db.execute("SELECT state,cost_micro FROM attempts").fetchall()
            halt = db.execute("SELECT halted FROM run WHERE id=1").fetchone()[0]
        if len(rows) != 1 or rows[0][0] != "failed" or not halt:
            raise ValueError("PREVIOUS_ROUND_NOT_FAILED")
        if not 0 < rows[0][1] <= 30000:
            raise ValueError("PRIOR_BUDGET_CHANGED")
        count += 1
        cost += rows[0][1]
    if count != number or count >= 8 or cost + 30000 > 1000000:
        raise ValueError("AGGREGATE_BUDGET_EXHAUSTED")
    return count, cost


def gate(number):
    folder, evidence = names(number)
    prior_check(number)
    approval = json.loads(AUTH.read_text())
    if (
        approval["user_instruction"] != "批准"
        or approval["additional_request_limit"] != 3
        or approval["aggregate_request_limit"] != 8
        or approval["aggregate_cost_micro"] != 1000000
    ):
        raise ValueError("NOT_AUTHORIZED")
    manifest = json.loads((BASE / (folder + ".json")).read_text())
    return FrozenBudget(
        manifest,
        evidence / "budget.sqlite",
        root=ROOT,
        approval=Approval(
            sha(canonical(manifest)),
            "connection",
            1,
            30000,
            sha(AUTH.read_bytes()),
            True,
        ),
    )


def freeze(number):
    folder, _ = names(number)
    target = BASE / (folder + ".json")
    if target.exists():
        raise ValueError("FREEZE_ALREADY_EXISTS")
    prior_check(number)
    config = json.loads((BASE / "tool-configuration.json").read_text())
    config["version"] = folder
    body = json.loads((BASE / "tool-followup-proposal.json").read_text())["request"]
    extra = []
    if number > 5:
        repair_path = BASE / (folder + "-repair.json")
        repair = json.loads(repair_path.read_text())
        previous = BASE / "results" / (names(number - 1)[0] + ".json")
        if (
            repair["previous_result_sha256"] != sha(previous.read_bytes())
            or repair["offline_status"] != "passed"
            or not repair["concrete_defect"]
            or not repair["fix"]
        ):
            raise ValueError("VERIFIED_REPAIR_REQUIRED")
        body = repair.get("revised_public_request", body)
        extra = [repair_path, previous]
    dump(BASE / (folder + "-body.json"), body)
    dump(BASE / (folder + "-configuration.json"), config)
    old = json.loads((BASE / "tool-r04.json").read_text())
    bound = next(iter(old["targets"].values())).copy()
    target_id = sha(canonical(config))
    bound["capability_sha256"] = target_id
    bound["adapter_sha256"] = sha(
        (ROOT / "backend/app/services/provider_connection_dispatch.py").read_bytes()
    )
    paths = (
        [ROOT / p for p in old["files"]]
        + [
            AUTH,
            Path(__file__).resolve(),
            BASE / "tool-diagnostic-budget-proposal.json",
            BASE / "target-deferral-20261014.json",
            ROOT / "scripts/acceptance_support/tool_probe_attempt.py",
            ROOT / "scripts/acceptance_support/tool_probe_observation.py",
            BASE / (folder + "-body.json"),
            BASE / (folder + "-configuration.json"),
        ]
        + extra
    )
    manifest = {
        **old,
        "run_id": "phase1-t039-" + folder,
        "files": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths},
        "targets": {target_id: bound},
        "slots": [
            {
                "id": "tool",
                "input_sha256": sha(canonical(body)),
                "attempts": 1,
                "stages": ["probe"],
                "targets": [target_id],
                "resources": ["unit"],
            }
        ],
        "bounds": {**old["bounds"], "requests": 1, "cost_micro": 30000},
    }
    dump(target, manifest)
    gate(number)._authorize()
    print("Frozen bounded diagnostic; no provider call.")


async def run(number):
    folder, evidence = names(number)
    budget = gate(number)
    budget._authorize()
    body = json.loads((BASE / (folder + "-body.json")).read_text())
    if (
        sha(canonical(body)) != budget.manifest["slots"][0]["input_sha256"]
        or body["model"] != MODEL
    ):
        raise ValueError("TARGET_CHANGED")
    config = json.loads((BASE / (folder + "-configuration.json")).read_text())
    await run_probe(
        budget=budget,
        evidence_dir=evidence,
        body=body,
        config=config,
        prior_check=lambda: prior_check(number),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=[5, 6, 7], required=True)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    try:
        freeze(args.round) if args.freeze else asyncio.run(run(args.round))
    except Exception as error:
        print("Tool diagnostic stopped: " + type(error).__name__)
        raise SystemExit(1) from None
