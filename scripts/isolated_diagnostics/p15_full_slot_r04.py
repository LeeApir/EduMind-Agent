"""Separate live experiment; immutable old batches and their bounds stay unchanged."""

import asyncio
import json
from uuid import NAMESPACE_URL, UUID, uuid5
from acceptance_support.p15_diagnostic_ledger import Refused
from acceptance_support.p15_diagnostic_execution import PROBE_PROMPT


async def run_slot(slot, sessions, adapter, ledger, batch, package):
    """Experimental scheduler fork: real product processing, waived token/cost admission. Not production bound evidence."""
    from sqlalchemy import select

    from app.agents import free_course_planning as planner
    from app.agents import free_scene_generation as generator
    from app.agents.review_schema import review_output_schema, validate_review
    from app.models.auth import Base, User
    from app.models.free_course import FreeCoursePlan
    from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
    from app.models.free_course_writes import FreeCourseOperation
    from app.models.learning import StudentProfile
    from isolated_diagnostics.p15_full_scheduler_r04 import (
        ExperimentalScheduler as Scheduler,
    )
    from app.services.provider_gateway import (
        ChatMessage,
        StructuredRequest,
        TextRequest,
    )

    if slot["kind"] == "probe":
        reply = await adapter.send(
            StructuredRequest(
                TextRequest(
                    (
                        ChatMessage("system", PROBE_PROMPT),
                        ChatMessage("user", slot["content"]),
                    ),
                    max_output_tokens=8000,
                ),
                review_output_schema(),
                "development_review_probe",
            ),
            retry_safe=False,
        )
        try:
            opinion = validate_review(reply.value)
        except ValueError:
            opinion = None
        return {
            "engineering_pass": reply.evidence == "complete_response"
            and opinion is not None,
            "opinion": opinion,
            "evidence": reply.evidence,
            "response_sha256": reply.evidence_digest,
        }
    owner = uuid5(NAMESPACE_URL, batch + "/" + slot["slot_id"])
    async with sessions() as db, db.begin():
        if await db.get(User, owner):
            raise Refused("SLOT_ALREADY_EXISTS_NO_REPLAY")
        db.add(User(id=owner, is_guest=True))
        await db.flush()
        evidence = slot.get("learner_evidence", {})
        if evidence:
            db.add(
                StudentProfile(
                    user_id=owner,
                    version=1,
                    merge_rule_version="diagnostic-self-report-v1",
                    evidence={k: {"source": "learner_statement"} for k in evidence},
                    **evidence,
                )
            )
    scheduler = Scheduler(sessions)
    created = await scheduler.enqueue(
        owner, slot.get("original_goal", slot.get("goal")), key="r01"
    )
    oid, cid = UUID(created["operation_id"]), UUID(created["course_id"])
    lease = await scheduler.claim()
    if lease is None or lease.owner != owner:
        raise Refused("ISOLATED_SCHEDULER_LEASE_REQUIRED")
    frozen_n = None
    for _ in range(100):
        with ledger.transaction():
            ledger.guard(batch, package)
        await scheduler.heartbeat(lease)
        await scheduler.run_once(lease, adapter)
        async with sessions() as db:
            if slot["kind"] == "course":
                checked = {
                    json.loads(row[0])["attempt"]
                    for row in ledger.db.execute(
                        "SELECT body FROM receipts WHERE batch=? AND kind='primary_schema'",
                        (batch,),
                    )
                }
                primary = await db.execute(
                    select(FreeCourseAttempt, FreeCourseSettlement)
                    .join(
                        FreeCourseSettlement,
                        FreeCourseSettlement.attempt_id == FreeCourseAttempt.id,
                    )
                    .where(
                        FreeCourseAttempt.course_id == cid,
                        FreeCourseAttempt.purpose == "primary",
                    )
                )
                for attempt, settlement in primary:
                    if str(attempt.id) in checked:
                        continue
                    packed = attempt.request_json["request"]
                    validator = (
                        planner
                        if packed["stage"] == "free_course_plan_generation"
                        else generator
                    )
                    try:
                        validator.validate_response(
                            settlement.outcome_json.get("value"), attempt.input_snapshot
                        )
                        valid = True
                    except (TypeError, ValueError):
                        valid = False
                    ledger.record(
                        batch,
                        "primary_schema",
                        {"attempt": str(attempt.id), "valid": valid},
                    )
                failures = sum(
                    not json.loads(row[0])["valid"]
                    for row in ledger.db.execute(
                        "SELECT body FROM receipts WHERE batch=? AND kind='primary_schema'",
                        (batch,),
                    )
                )
                # Maximum supported primary denominator is 60. Two failures cannot reach 98%.
                if failures >= 2:
                    ledger.halt(batch, "threshold_unreachable")
                    raise Refused("FIRST_SCHEMA_THRESHOLD_UNREACHABLE")
            plan = await db.scalar(
                select(FreeCoursePlan).where(FreeCoursePlan.course_id == cid)
            )
            op = await db.get(FreeCourseOperation, oid)
            if plan is not None and frozen_n is None:
                frozen_n = len(plan.plan_json["scenes"])
                ledger.record(
                    batch,
                    "scene_denominator",
                    {"slot_id": slot["slot_id"], "n": frozen_n},
                )
                if slot["kind"] == "negative":
                    raise Refused("NEGATIVE_CONTROL_PLANNED_UNSUPPORTED_CONTENT")
                low, high = slot["scene_count_range"]
                if not low <= frozen_n <= high:
                    raise Refused("SCENE_COUNT_OUTSIDE_FROZEN_EXPECTATION")
            if op.state not in ["queued", "running"]:
                tables = {}
                for table in sorted(
                    Base.metadata.tables.values(), key=lambda t: t.name
                ):
                    if "course_id" in table.c and "user_id" in table.c:
                        rows = await db.execute(
                            select(table).where(
                                table.c.course_id == cid, table.c.user_id == owner
                            )
                        )
                        tables[table.name] = [dict(row) for row in rows.mappings()]
                return {
                    "engineering_pass": op.state
                    == (
                        "awaiting_clarification"
                        if slot["kind"] == "negative"
                        else "succeeded"
                    ),
                    "operation_state": op.state,
                    "reason": op.reason_code,
                    "planned_scene_denominator": frozen_n
                    or slot.get("scene_count_range", [0, 0])[1],
                    "tables": tables,
                }
        await asyncio.sleep(0.05)
    raise Refused("SLOT_STEP_LIMIT")
