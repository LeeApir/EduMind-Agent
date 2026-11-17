"""ADR0034 isolated course experiment. --check never reads keys or uses network."""
# ruff: noqa: E402

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import dotenv_values
import httpx
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.database import create_database_engine
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from acceptance_support.p15_diagnostic_ledger import Refused
from acceptance_support.p15_candidate_compatibility import parse, evidence
from isolated_diagnostics.p15_exploration import (
    ExplorationLimits,
    ExplorationLedger,
    ExplorationJournal,
    ExplorationAdapter,
    run_experimental_slot,
)
from isolated_diagnostics.p15_split_provider import SplitExecution
from run_p15_candidate_compatibility import bounded_resolver

BASE = ROOT / "docs/acceptance/phase-1.5-split-exploration-r01"
OUTPUT = Path("/tmp/edumind-p15-split-exploration-r01")
BATCH = "p15-split-experiment-r01"
DATABASE = "edumind_catalog_p15_t020_exploration_20261027"


def gate():
    manifest_raw = (BASE / "manifest.json").read_bytes()
    manifest = parse(manifest_raw)
    required = {
        "scripts/run_p15_split_exploration.py",
        "scripts/isolated_diagnostics/p15_exploration.py",
        "scripts/isolated_diagnostics/p15_experimental_scheduler.py",
        "scripts/isolated_diagnostics/p15_experimental_slot.py",
        "docs/ADR/0034-user-directed-unbounded-exploration.md",
        str((BASE / "plan.json").relative_to(ROOT)),
        str((BASE / "slots.json").relative_to(ROOT)),
    }
    if (
        manifest.get("batch_id") != BATCH
        or not required <= manifest.get("sha256", {}).keys()
        or manifest.get("limits") != asdict(ExplorationLimits())
    ):
        raise Refused("EXPERIMENT_MANIFEST_INVALID")
    for name, sha in manifest["sha256"].items():
        path = (ROOT / name).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise Refused("FROZEN_EXPERIMENT_CHANGED")
    package = hashlib.sha256(manifest_raw).hexdigest()
    grant = parse((BASE / "user-direction.json").read_bytes())
    if (
        grant.get("package_sha256") != package
        or grant.get("batch_id") != BATCH
        or grant.get("limits") != asdict(ExplorationLimits())
        or grant.get("human_message") != "不考虑上界与费用，先完成项目"
        or grant.get("fee_cap_waiver") is not True
        or grant.get("token_bound_proof_waiver") is not True
        or grant.get("new_package_independently_human_reviewed") is not False
        or grant.get("scope") != "PHASE-1.5-T038"
        or not grant.get("evidence_ref")
    ):
        raise Refused("EXPLICIT_CURRENT_DIRECTION_REQUIRED")
    return (
        package,
        grant,
        parse((BASE / "plan.json").read_bytes()),
        parse((BASE / "slots.json").read_bytes()),
    )


def keys():
    env = dotenv_values(ROOT / ".env", interpolate=False)

    def value(name):
        return os.getenv(name) or env.get(name)

    generation = value("EDUMIND_DEEPSEEK_COMPAT_API_KEY")
    review = value("EDUMIND_AIAPI_REVIEW_API_KEY")
    source = "EDUMIND_AIAPI_REVIEW_API_KEY"
    if not review and value("EDUMIND_PROVIDER_BASE_URL") == "https://aiapi.world/v1":
        review = value("EDUMIND_PROVIDER_API_KEY")
        source = "EDUMIND_PROVIDER_API_KEY (exact AIAPI base URL binding)"
    selected = {"generation": generation, "review": review}
    if (
        any(
            not isinstance(v, str)
            or len(v) < 16
            or not v.isascii()
            or any(c.isspace() for c in v)
            for v in selected.values()
        )
        or generation == review
    ):
        raise Refused("DISTINCT_DEEPSEEK_AND_AIAPI_CREDENTIALS_REQUIRED")
    return selected, source


def database():
    url = os.getenv("EDUMIND_TEST_DATABASE_URL", "")
    parsed = make_url(url)
    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.host != "127.0.0.1"
        or parsed.port != 15437
        or parsed.database != DATABASE
    ):
        raise Refused("EXACT_ISOLATED_DATABASE_REQUIRED")
    return url


def target(role, plan):
    endpoint = plan["providers"][role]["url"].removesuffix("/responses")
    return ProviderTargetGuard(
        endpoint, TargetPolicy(), resolver=bounded_resolver
    ).approve_base()


async def step(review_path=None):
    package, grant, plan, slots = gate()
    url = database()
    # Do not even read keys for pure human report import or pending checkpoints.
    j = None
    if OUTPUT.exists():
        j = ExplorationJournal(
            ExplorationLedger(OUTPUT / "ledger.sqlite"), BATCH, package, OUTPUT
        )
        engine = None
    else:
        selected, source = keys()
        j = ExplorationJournal.create(OUTPUT, BATCH, package, grant)
        j.record(
            "credential_binding",
            {"generation": "EDUMIND_DEEPSEEK_COMPAT_API_KEY", "review": source},
        )
        j.record("planned_slots", {"slots": slots})
    execution = SplitExecution(j, slots)
    try:
        if review_path:
            execution.review(parse(Path(review_path).read_bytes()))
            return {
                "state": "human_report_recorded_no_automatic_continuation",
                "provider_calls_this_step": 0,
            }
        outputs, reviews = (
            execution.events("slot_output"),
            execution.events("human_review"),
        )
        execution.verify_outputs(outputs)
        if len(outputs) != len(reviews):
            pending = outputs[-1]
            return {
                "state": "human_review_required",
                "slot": pending,
                "output_path": str(OUTPUT / (pending["slot_id"] + ".json")),
                "usage": j.ledger.usage(BATCH),
                "production_bounds_verified": False,
            }
        j.guard()
        selected, source = keys()
        adapter = ExplorationAdapter(
            j,
            selected,
            lambda role: target(role, plan),
            lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        )
        engine = create_database_engine(url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            record = await execution.advance(
                lambda slot: run_experimental_slot(slot, sessions, adapter)
            )
            summary = {
                "state": "human_review_required"
                if record
                else "completed_pending_result_validation",
                "slot": record,
                "usage": j.ledger.usage(BATCH),
                "T038_completed": False,
                "actual_invoice_usd": None,
                "production_bounds_verified": False,
                "output_path": str(OUTPUT),
            }
            j.record("step_summary", summary)
            evidence(OUTPUT / f"step-{len(j.events('step_summary'))}.json", summary)
            return summary
        finally:
            await engine.dispose()
    except BaseException as exc:
        code = (
            str(exc)
            if isinstance(exc, Refused)
            else "TRANSPORT_DATABASE_OR_EXECUTION_FAILURE"
        )
        j.ledger.halt(BATCH, "provider_contract_failure")
        summary = {
            "state": "stopped",
            "safe_failure_code": code,
            "usage": j.ledger.usage(BATCH),
            "T038_completed": False,
            "actual_invoice_usd": None,
            "output_path": str(OUTPUT),
        }
        j.record("step_summary", summary)
        evidence(OUTPUT / f"step-{len(j.events('step_summary'))}.json", summary)
        return summary
    finally:
        j.ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--step", action="store_true")
    mode.add_argument("--review", type=Path)
    args = parser.parse_args()
    try:
        if not args.step and not args.review:
            package, _, _, _ = gate()
            print(
                json.dumps(
                    {
                        "package_verified": package,
                        "real_calls_this_check": 0,
                        "bounded_output_verified": False,
                        "fee_cap": None,
                    }
                )
            )
        else:
            result = asyncio.run(step(args.review))
            print(json.dumps(result, ensure_ascii=False))
            if result.get("state") == "stopped":
                raise SystemExit(2)
    except Refused as exc:
        print(str(exc))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
