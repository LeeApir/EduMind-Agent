"""Independent r02 proposal/execution composition after the r01 review miss."""
# ruff: noqa: E402

import argparse
import asyncio
import json
from pathlib import Path

import prepare_t040_diagnostics as preparation
import run_t040_diagnostics as execution
from acceptance_support.phase1_budget import GateFailure, sha
from app.agents.review_agent import REVIEW_INSTRUCTION_VERSION

ROOT = preparation.ROOT
BASE = ROOT / "docs/acceptance/phase-1-t040-deepseek-v2"
RAW = ROOT / "local-materials/phase-1-t040-deepseek-v2"


async def proposed():
    bodies, plan = await preparation.prepare()
    plan.update(
        version="t040-deepseek-diagnostic-proposal-v2",
        round="r02",
        review_instruction_version=REVIEW_INSTRUCTION_VERSION,
        previous_failed_result="docs/acceptance/phase-1-t040-deepseek-v1/results/diagnostic-r01.json",
        historical_candidates_used_for_diagnostic_tuning=True,
        formal_samples_used_for_tuning=False,
        old_budget_transferred=False,
    )
    return bodies, plan


def write_proposal():
    if (BASE / "proposal.json").exists():
        raise GateFailure("FREEZE_CHANGED")
    bodies, plan = asyncio.run(proposed())
    BASE.mkdir(parents=True, exist_ok=True)
    requests_path = BASE / "requests.json"
    requests_path.write_text(json.dumps(bodies, ensure_ascii=False, indent=2) + "\n")
    old = json.loads((preparation.BASE / "proposal.json").read_text())
    paths = [
        ROOT / path
        for path in old["files"]
        if path != str((preparation.BASE / "requests.json").relative_to(ROOT))
    ]
    paths += [
        requests_path,
        Path(__file__).resolve(),
        ROOT / "scripts/run_t040_diagnostics.py",
        ROOT / "scripts/run_deepseek_connection.py",
        ROOT / "scripts/run_phase1_provider_connection.py",
        ROOT / "scripts/acceptance_support/connection_diagnostics.py",
        ROOT / "backend/tests/test_t040_diagnostic_runner.py",
        ROOT / "backend/tests/test_review_failure_paths.py",
        ROOT / plan["previous_failed_result"],
    ]
    plan["files"] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}
    (BASE / "proposal.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "requests": plan["requested_total_calls"],
                "cost_micro_cny": plan["requested_total_cost_micro_cny"],
                "authorized": False,
                "real_calls": 0,
            }
        )
    )


def check_proposal():
    bodies, expected = asyncio.run(proposed())
    plan = json.loads((BASE / "proposal.json").read_text())
    files = plan.pop("files")
    if plan != expected or json.loads((BASE / "requests.json").read_text()) != bodies:
        raise GateFailure("FREEZE_CHANGED")
    for relative, digest in files.items():
        path = ROOT / relative
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(ROOT)
            or sha(path.read_bytes()) != digest
        ):
            raise GateFailure("FREEZE_CHANGED")
    print(
        "PASS: r02 source, production prompt, historical candidates and budgets; real calls=0"
    )


def configure_execution():
    """Keep a distinct frozen run, approval record and durable ledger namespace."""
    execution.BASE = BASE
    execution.RAW = RAW
    execution.ROUND = "r02"
    execution.check_proposal = check_proposal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-proposal", action="store_true")
    group.add_argument("--check-proposal", action="store_true")
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run-one", choices=preparation.GROUPS)
    args = parser.parse_args()
    try:
        if args.write_proposal:
            write_proposal()
        elif args.check_proposal:
            check_proposal()
        else:
            configure_execution()
            execution.freeze() if args.freeze else asyncio.run(
                execution.run_one(args.run_one)
            )
    except Exception as exc:
        print(
            "Stopped: "
            + (exc.code if isinstance(exc, GateFailure) else type(exc).__name__)
        )
        raise SystemExit(1) from None
