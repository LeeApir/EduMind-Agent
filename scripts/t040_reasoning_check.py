"""Two historical cases to evaluate an explicit high-reasoning review strategy."""
# ruff: noqa: E402

import argparse
import asyncio
import json
from pathlib import Path

import prepare_t040_diagnostics as preparation
import run_t040_diagnostics as execution
from acceptance_support.phase1_budget import GateFailure, canonical, sha

ROOT = preparation.ROOT
BASE = ROOT / "docs/acceptance/phase-1-t040-reasoning-check"
RAW = ROOT / "local-materials/phase-1-t040-reasoning-check"


async def proposed():
    history = json.loads(preparation.HISTORY.read_text())["cases"]
    selected = [
        next(c for c in history if c["id"] == key)
        for key in ("linked-list-concept:explanation:1", "correct-list-concept")
    ]
    bodies, rows = {}, []
    for index, case in enumerate(selected, 1):
        body = await preparation.capture_case(case)
        body["reasoning"] = {"effort": "high"}
        body["max_output_tokens"] = 8192
        slot = f"reasoning_check:{index:02}"
        bodies[slot] = body
        rows.append(
            {
                "slot": slot,
                "historical_case_id": case["id"],
                "payload_sha256": case["payload_sha256"],
                "request_sha256": sha(canonical(body)),
                "request_bytes": len(canonical(body)),
                "input_token_upper_bound": len(canonical(body)) + 1024,
                "output_token_upper_bound": 8192,
                "reservation_micro_cny": (len(canonical(body)) + 1024) * 2 + 8192 * 8,
            }
        )
    reservation = sum(r["reservation_micro_cny"] for r in rows)
    plan = {
        "version": "t040-reasoning-strategy-proposal-v1",
        "round": "r03",
        "state": "PENDING_BUDGET_APPROVAL",
        "real_requests_sent": 0,
        "provider_requests_authorized": 0,
        "provider_cost_micro_authorized": 0,
        "model_id": "deepseek-flash",
        "model_revision": "DeepSeek-V4.1-Flash",
        "base_url": "https://api.deepseek.com",
        "transport": "responses_json_schema",
        "adapter": "DeepSeekResponsesAdapter",
        "reasoning_effort": "high",
        "review_instruction_version": "resource-review-instructions-v3",
        "temperature": 0,
        "temperature_effect": "Ignored by provider in thinking mode.",
        "max_output_tokens_including_reasoning": 8192,
        "groups": [
            {
                "id": "reasoning_check",
                "state": "PENDING_BUDGET_APPROVAL",
                "requests": 2,
                "cost_cap_micro_cny": ((reservation + 9999) // 10000) * 10000,
                "computed_reservation_micro_cny": reservation,
                "timeout_seconds_per_request": 120,
                "max_active_requests": 1,
                "retries": 0,
                "fallbacks": 0,
                "corrections": 0,
                "slots": rows,
            }
        ],
        "requested_total_calls": 2,
        "requested_total_cost_micro_cny": ((reservation + 9999) // 10000) * 10000,
        "input_peak_uncached_cny_per_million": 2,
        "output_peak_cny_per_million": 8,
        "input_bound": "Entire UTF-8 wire bytes plus 1024 template tokens.",
        "pricing_sources": ["https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"],
        "capability_sources": [
            "https://api-docs.deepseek.com/api/create-response/",
            "https://api-docs.deepseek.com/guides/responses_api/",
        ],
        "scope": "Strategy check only; does not replace any of four required diagnostic groups.",
        "comparison_limits": "Compared with r02, effort, total output cap and deadline change; no causal attribution from two cases.",
        "stop_conditions": [
            "Known defect passed or concretely missed; wrong safety category.",
            "Correct control rejected; protocol/schema/completion/model/usage/budget failure.",
        ],
        "production_mode": "catalog_only",
        "production_default_effort": "none",
        "formal_quality_authorized": False,
        "dsl_quality_authorized": False,
        "t041_authorized": False,
        "automatic_next_round": False,
        "human_factual_signoff_inferred": False,
        "old_budget_transferred": False,
    }
    return bodies, plan


def write_proposal():
    if (BASE / "proposal.json").exists():
        raise GateFailure("FREEZE_CHANGED")
    bodies, plan = asyncio.run(proposed())
    BASE.mkdir(parents=True, exist_ok=True)
    requests = BASE / "requests.json"
    requests.write_text(json.dumps(bodies, ensure_ascii=False, indent=2) + "\n")
    paths = list((ROOT / "backend/app").rglob("*.py")) + [
        Path(__file__).resolve(),
        requests,
        preparation.HISTORY,
        ROOT / "backend/pyproject.toml",
        ROOT / "backend/uv.lock",
        ROOT / "scripts/prepare_t040_diagnostics.py",
        ROOT / "scripts/run_t040_diagnostics.py",
        ROOT / "scripts/run_deepseek_connection.py",
        ROOT / "scripts/run_phase1_provider_connection.py",
        ROOT / "scripts/acceptance_support/phase1_budget.py",
        ROOT / "scripts/acceptance_support/connection_diagnostics.py",
        ROOT / "backend/tests/test_deepseek_reasoning.py",
        ROOT / "backend/tests/test_t040_diagnostic_runner.py",
        ROOT / "docs/ADR/0011-dynamic-approval-20261008.json",
        ROOT / "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
        ROOT / "docs/acceptance/phase-1-t040-deepseek-v2/results/diagnostic-r02.json",
    ]
    plan["files"] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}
    (BASE / "proposal.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "calls": 2,
                "cost_cap_micro_cny": plan["requested_total_cost_micro_cny"],
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
    print("PASS: high-reasoning two-case strategy proposal/source hashes; real calls=0")


def configure_execution():
    execution.BASE, execution.RAW, execution.ROUND = BASE, RAW, "r03"
    execution.GROUPS = ("reasoning_check",)
    execution.check_proposal = check_proposal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for name in ("write-proposal", "check-proposal", "freeze", "run-one"):
        group.add_argument("--" + name, action="store_true")
    args = parser.parse_args()
    try:
        if args.write_proposal:
            write_proposal()
        elif args.check_proposal:
            check_proposal()
        else:
            configure_execution()
            execution.freeze() if args.freeze else asyncio.run(
                execution.run_one("reasoning_check")
            )
    except Exception as exc:
        print(
            "Stopped: "
            + (exc.code if isinstance(exc, GateFailure) else type(exc).__name__)
        )
        raise SystemExit(1) from None
