"""Full four-group historical diagnosis proposal after the bounded high-strategy check."""

import argparse
import asyncio
import json
from pathlib import Path

import t040_diagnostics_v2 as prior
import run_t040_diagnostics as execution
from acceptance_support.phase1_budget import GateFailure, canonical, sha

ROOT = prior.ROOT
BASE = ROOT / "docs/acceptance/phase-1-t040-deepseek-high-v1"
RAW = ROOT / "local-materials/phase-1-t040-deepseek-high-v1"
STRATEGY_RESULT = (
    "docs/acceptance/phase-1-t040-reasoning-check/results/strategy-r03.json"
)


async def proposed():
    bodies, plan = await prior.proposed()
    plan.update(
        version="t040-high-diagnostics-proposal-v1",
        round="r04",
        reasoning_effort="high",
        max_output_tokens_including_reasoning=8192,
        strategy_check_result=STRATEGY_RESULT,
        temperature_effect="Ignored by provider in thinking mode.",
    )
    for body in bodies.values():
        body["reasoning"] = {"effort": "high"}
        body["max_output_tokens"] = 8192
    for group in plan["groups"]:
        for slot in group["slots"]:
            body = bodies[slot["slot"]]
            slot.update(
                request_sha256=sha(canonical(body)),
                request_bytes=len(canonical(body)),
                input_token_upper_bound=len(canonical(body)) + 1024,
                output_token_upper_bound=8192,
                reservation_micro_cny=(len(canonical(body)) + 1024) * 2 + 8192 * 8,
            )
        reservation = sum(s["reservation_micro_cny"] for s in group["slots"])
        group.update(
            timeout_seconds_per_request=120,
            computed_reservation_micro_cny=reservation,
            cost_cap_micro_cny=((reservation + 9999) // 10000) * 10000,
        )
    plan["requested_total_cost_micro_cny"] = sum(
        g["cost_cap_micro_cny"] for g in plan["groups"]
    )
    return bodies, plan


def write_proposal():
    if (BASE / "proposal.json").exists():
        raise GateFailure("FREEZE_CHANGED")
    bodies, plan = asyncio.run(proposed())
    BASE.mkdir(parents=True, exist_ok=True)
    requests = BASE / "requests.json"
    requests.write_text(json.dumps(bodies, ensure_ascii=False, indent=2) + "\n")
    strategy = json.loads((ROOT / STRATEGY_RESULT).read_text())
    if strategy["real_requests"] != 2 or strategy["reasoning_tokens"] <= 0:
        raise GateFailure("PREREQUISITE_MISSING")
    old = json.loads((prior.BASE / "proposal.json").read_text())
    paths = [
        ROOT / p
        for p in old["files"]
        if p != str((prior.BASE / "requests.json").relative_to(ROOT))
    ]
    paths += [
        requests,
        Path(__file__).resolve(),
        ROOT / "scripts/t040_diagnostics_v2.py",
        ROOT / "backend/tests/test_t040_high_plan.py",
        ROOT / STRATEGY_RESULT,
    ]
    plan["files"] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}
    (BASE / "proposal.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "real_calls": 0,
                "requests": 13,
                "cost_micro_cny": plan["requested_total_cost_micro_cny"],
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
    print("PASS: high full-diagnostic proposal/source hashes; real calls=0")


def configure_execution():
    execution.BASE, execution.RAW, execution.ROUND = BASE, RAW, "r04"
    execution.GROUPS = prior.preparation.GROUPS
    execution.check_proposal = check_proposal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    for name in ("write-proposal", "check-proposal", "freeze"):
        action.add_argument("--" + name, action="store_true")
    action.add_argument("--run-one", choices=prior.preparation.GROUPS)
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
