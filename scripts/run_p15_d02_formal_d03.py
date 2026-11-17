"""ADR0034 isolated course experiment. --check never reads keys or uses network."""
# ruff: noqa: E402

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
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
from isolated_diagnostics.p15_d02_formal_d03 import (
    ExplorationLimits,
    ExplorationLedger,
    ExplorationJournal,
    ExplorationAdapter,
    run_experimental_slot,
)
from isolated_diagnostics.p15_d02_review_d02 import (
    SplitExecution,
    assess,
    verify_consistency,
)
from isolated_diagnostics import p15_split_provider as source_reader
from isolated_diagnostics.p15_d02_formal_d03 import review_pending
from run_p15_candidate_compatibility import bounded_resolver
from isolated_diagnostics.p15_d02_observation_d02 import audit_records
from isolated_diagnostics.p15_review_turn_metadata import VERSION as OBSERVATION_POLICY

BASE = ROOT / "docs/acceptance/phase-1.5-d02-formal-d03"
OUTPUT = Path("/tmp/edumind-p15-d02-formal-d03")
BATCH = "p15-split-experiment-d02-d03"
DATABASE = "edumind_catalog_p15_t020_d02_d03"


def gate(*, execute=False):
    manifest_raw = (BASE / "manifest.json").read_bytes()
    manifest = parse(manifest_raw)
    required = {
        "scripts/run_p15_d02_formal_d03.py",
        "scripts/isolated_diagnostics/p15_d02_formal_d03.py",
        "backend/app/agents/free_course_planning.py",
        "scripts/isolated_diagnostics/p15_d02_wire_d02.py",
        "scripts/isolated_diagnostics/p15_review_turn_metadata.py",
        "docs/ADR/0040-final-d02-turn-metadata-proposal.md",
        "scripts/isolated_diagnostics/p15_d02_scheduler_d02.py",
        "scripts/isolated_diagnostics/p15_d02_slot_d02.py",
        "scripts/isolated_diagnostics/p15_d02_review_d02.py",
        "backend/app/services/free_scene_consistency.py",
        "backend/app/services/free_scene_semantics.py",
        "scripts/isolated_diagnostics/p15_course_sol_bridge.py",
        "scripts/isolated_diagnostics/p15_review_observability.py",
        "scripts/isolated_diagnostics/p15_d02_observation_d02.py",
        "docs/ADR/0038-approval-20261027.json",
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
    plan = parse((BASE / "plan.json").read_bytes())
    slots = parse((BASE / "slots.json").read_bytes())
    original = parse(
        (
            ROOT / "docs/acceptance/phase-1.5-split-exploration-r02/slots.json"
        ).read_bytes()
    )
    if (
        slots != [v for v in original if v["slot_id"] == "D02-known"]
        or len(slots) != 1
        or plan["prior_requests"] != 30
    ):
        raise Refused("EXACT_D02_TWO_SCENES_AND_HISTORY_REQUIRED")
    if (
        plan.get("planning_prompt_version") != "free-course-plan-v2"
        or plan.get("planning_contract_version")
        != "planning-objectives-and-constraints-v1"
        or plan.get("scene_prompt_version") != "free-scene-generation-v5"
        or plan.get("scene_rule_version") != "free-scene-hard-gate-v4"
        or plan.get("consistency_policy") != "free-scene-consistency-v2"
        or plan.get("review_observability_policy") != OBSERVATION_POLICY
        or plan.get("prior_reported_input") != 138390
        or plan.get("prior_reported_output") != 31075
    ):
        raise Refused("EXACT_REPAIRED_CONFIGURATION_REQUIRED")
    grant = parse((BASE / "execution-approval.json").read_bytes())
    if execute:
        import time

        if (
            grant.get("approved") is not True
            or grant.get("adr0040_A_B_scope_extension_approved") is not True
            or grant.get("planning_v2_patch_scope_approved") is not True
            or grant.get("test_before_reassessment_approved") is not True
            or grant.get("final_one_shot_stop_rule_approved") is not True
            or grant.get("package_sha256") != package
            or grant.get("batch_id") != BATCH
            or grant.get("limits") != asdict(ExplorationLimits())
            or grant.get("scope") != "PHASE-1.5-T038"
            or grant.get("observability_policy_version") != OBSERVATION_POLICY
            or grant.get("full_review_contract_approved") is not True
            or grant.get("reviewer") != "Codex assistant"
            or grant.get("review_type") != "delegated_assistant"
            or grant.get("independent_human_truth") is not False
            or grant.get("new_time_window_approved") is not True
            or grant.get("synthetic_course_transfer_approved") is not True
            or grant.get("fee_cap_waiver") is not True
            or grant.get("token_bound_proof_waiver") is not True
            or not grant.get("human_message")
            or not grant.get("evidence_ref")
        ):
            raise Refused("EXACT_D02_AND_NEW_WINDOW_APPROVAL_REQUIRED")
        start, end = grant.get("window_start_epoch"), grant.get("window_deadline_epoch")
        if (
            type(start) not in (int, float)
            or type(end) not in (int, float)
            or not 0 < end - start <= 1800
            or not start <= time.time() < end
        ):
            raise Refused("NEW_EXPLICIT_WINDOW_REQUIRED_OR_EXPIRED")
    return package, grant, plan, slots


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


async def step(review_path=None, adjudication_path=None):
    package, grant, plan, slots = gate(execute=True)
    url = database()
    # Do not even read keys for pure human report import or pending checkpoints.
    j = None
    if OUTPUT.exists():
        j = ExplorationJournal(
            ExplorationLedger(OUTPUT / "ledger.sqlite"), BATCH, package, OUTPUT
        )
        engine = None
    else:
        if review_path or adjudication_path:
            raise Refused("NO_EXISTING_BATCH_FOR_LOCAL_REVIEW")
        selected, source = keys()
        j = ExplorationJournal.create(OUTPUT, BATCH, package, grant)
        j.record(
            "credential_binding",
            {"generation": "EDUMIND_DEEPSEEK_COMPAT_API_KEY", "review": source},
        )
        j.record("planned_slots", {"slots": slots})
    execution = SplitExecution(j, slots)
    try:
        if review_path or adjudication_path:
            try:
                if adjudication_path:
                    report = parse(Path(adjudication_path).read_bytes())
                    if (
                        report.get("reviewer") != "Codex assistant"
                        or report.get("review_type") != "delegated_assistant"
                        or report.get("independent_human_truth") is not False
                        or report.get("decision") != "false_alarm"
                    ):
                        raise Refused("EXACT_DELEGATED_FALSE_ALARM_ONLY")
                    identity = source_reader.Identity(**report["identity"])
                    j.adjudicate_false_alarm(identity, report["source_sha256"], report)
                    return {
                        "state": "adjudication_recorded_no_calls",
                        "provider_calls_this_step": 0,
                    }
                if review_path:
                    execution.review(parse(Path(review_path).read_bytes()))
                    return {
                        "state": "assistant_report_recorded_no_automatic_continuation",
                        "provider_calls_this_step": 0,
                    }
            except (Refused, ValueError, KeyError, TypeError, AttributeError, OSError):
                # A rejected local report is not a failed Provider send or a retry.
                return {
                    "state": "local_review_rejected_no_calls",
                    "provider_calls_this_step": 0,
                }
        outputs, reviews = (
            execution.events("slot_output"),
            execution.events("human_review"),
        )
        execution.verify_outputs(outputs)
        durable = j.ledger.db.execute(
            "SELECT state,reason FROM batches WHERE id=?", (BATCH,)
        ).fetchone()
        if durable[0] == "stopped":
            return {
                "state": "stopped",
                "safe_failure_code": durable[1],
                "usage": j.ledger.usage(BATCH),
                "provider_calls_this_step": 0,
            }
        pending = None
        if len(outputs) != len(reviews):
            pending = outputs[-1]
            value = parse((OUTPUT / (pending["slot_id"] + ".json")).read_bytes())
            raw_identity = value.get("scene_review_identity")
            if raw_identity:
                identity = source_reader.Identity(**raw_identity)
                finished = {
                    v["source_sha256"]
                    for v in j.events("scene_review_finished")
                    if v["identity"] == identity.packed()
                }
                missing = any(
                    t["payload"]["source_sha256"] not in finished
                    for t in j.sources(identity)
                )
            else:
                missing = False
            try:
                j.guard()
            except Refused as exc:
                if str(exc) != "SCENE_ADVISORY_REQUIRES_HUMAN":
                    raise
                return {
                    "state": "scene_adjudication_or_failed_report_required",
                    "slot": pending,
                    "provider_calls_this_step": 0,
                    "output_path": str(OUTPUT / (pending["slot_id"] + ".json")),
                }
            if not missing:
                return {
                    "state": "assistant_review_required",
                    "slot": pending,
                    "provider_calls_this_step": 0,
                    "output_path": str(OUTPUT / (pending["slot_id"] + ".json")),
                }
        j.guard()
        gate(execute=True)
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
            if pending:

                async def current(target):
                    return target in await source_reader.load_targets(
                        sessions, identity
                    )

                state = await review_pending(adapter, identity, verify_current=current)
                j.record(
                    "scene_reviews_resumed",
                    {
                        "identity": identity.packed(),
                        "state": state,
                        "original_slot_output_unchanged": True,
                    },
                )
                return {"state": state, "slot": pending, "usage": j.ledger.usage(BATCH)}
            record = await execution.advance(
                lambda slot: run_experimental_slot(slot, sessions, adapter)
            )
            summary = {
                "state": (
                    "stopped"
                    if j.ledger.db.execute(
                        "SELECT state FROM batches WHERE id=?", (BATCH,)
                    ).fetchone()[0]
                    == "stopped"
                    else "assistant_review_required"
                    if record
                    else "completed_pending_result_validation"
                ),
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
    mode.add_argument("--adjudicate", type=Path)
    mode.add_argument("--assessment", action="store_true")
    args = parser.parse_args()
    try:
        if args.assessment:
            package, _, _, slots = gate()
            if not OUTPUT.exists():
                raise Refused("NO_BATCH_EVIDENCE")
            db = sqlite3.connect(
                (OUTPUT / "ledger.sqlite").as_uri() + "?mode=ro", uri=True
            )
            try:
                db.execute("BEGIN")

                def events(kind):
                    return [
                        parse(r[0])
                        for r in db.execute(
                            "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                            (BATCH, kind),
                        )
                    ]

                grant = parse((BASE / "execution-approval.json").read_bytes())
                actual = db.execute(
                    "SELECT package,approval FROM batches WHERE id=?", (BATCH,)
                ).fetchone()
                from acceptance_support.p15_diagnostic_ledger import digest

                if actual != (package, digest(grant)) or events("planned_slots") != [
                    {"slots": slots}
                ]:
                    raise Refused("EXACT_BATCH_AUTHORITY_CHANGED")
                values = []
                for record in events("slot_output"):
                    raw = (OUTPUT / (record["slot_id"] + ".json")).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                        raise Refused("OUTPUT_CHANGED")
                    values.append({"slot_id": record["slot_id"], **parse(raw)})
                for call in events("live_dispatch_reserved"):
                    raw = (OUTPUT / (call["ticket"] + "-request.json")).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != call["request_sha256"]:
                        raise Refused("REQUEST_EVIDENCE_CHANGED")
                for attempt, body in db.execute(
                    "SELECT attempt,body FROM receipts WHERE batch=? AND kind='settled_observation'",
                    (BATCH,),
                ):
                    raw = (OUTPUT / (attempt + "-response.json")).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != parse(body)["proof_sha256"]:
                        raise Refused("RESPONSE_EVIDENCE_CHANGED")
                if values:
                    verify_consistency(values, events("consistency_observation"))
                elif events("consistency_observation"):
                    raise Refused("ORPHAN_CONSISTENCY_OBSERVATIONS")
                audit_records(
                    output=OUTPUT,
                    calls=events("live_dispatch_reserved"),
                    settlements=[
                        (attempt, parse(body))
                        for attempt, body in db.execute(
                            "SELECT attempt,body FROM receipts WHERE batch=? "
                            "AND kind='settled_observation'",
                            (BATCH,),
                        )
                    ],
                    observations=events("review_protocol_observation"),
                    slots=slots,
                )
                print(
                    json.dumps(
                        assess(
                            slots,
                            values,
                            events("assistant_review"),
                            events("primary_schema"),
                        ),
                        ensure_ascii=False,
                    )
                )
            finally:
                db.close()
        elif not args.step and not args.review and not args.adjudicate:
            package, grant, _, _ = gate()
            print(
                json.dumps(
                    {
                        "package_verified": package,
                        "real_calls_this_check": 0,
                        "bounded_output_verified": False,
                        "fee_cap": None,
                        "execution_approved": grant.get("approved") is True,
                        "new_window_required": True,
                        "scope": "D02-known only: exactly two scenes",
                    }
                )
            )
        else:
            result = asyncio.run(step(args.review, args.adjudicate))
            print(json.dumps(result, ensure_ascii=False))
            if result.get("state") == "stopped":
                raise SystemExit(2)
    except Refused as exc:
        print(str(exc))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
