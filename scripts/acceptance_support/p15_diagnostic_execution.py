"""Serial diagnostic slots and human checkpoints; never creates execution authority."""

import asyncio
import hashlib
import json
from dataclasses import asdict
from uuid import NAMESPACE_URL, UUID, uuid5

from acceptance_support.p15_diagnostic_ledger import Limits, Refused, digest

PROBE_PROMPT = (
    "审核以下数据结构教学片段的事实、步骤、代码安全、复杂度、答案和跨场景一致性。"
    "只报告能定位到原文的实质问题；不要因片段简短虚构缺失要求。"
    "按 resource-review-v3 输出 verdict 和 issues；严重错误标记 severe。"
)


def verify_approval(manifest, package, approval):
    """Registry is manually recorded from a human message, not manufactured by this tool."""
    limits = Limits(**manifest["limits"])
    if not approval or (
        approval.get("scope") != "PHASE-1.5-T038"
        or approval.get("package_sha256") != package
        or approval.get("batch_id") != manifest["batch_id"]
        or approval.get("limits") != asdict(limits)
        or approval.get("fee_cap_waiver") is not True
        or not approval.get("human_message")
        or not approval.get("reviewer")
        or not approval.get("received_at")
        or not approval.get("evidence_ref")
    ):
        raise Refused("EXACT_T038_HUMAN_APPROVAL_REQUIRED")
    return limits


class Execution:
    def __init__(self, ledger, manifest, package, slots, output):
        self.ledger, self.manifest, self.package = ledger, manifest, package
        self.batch, self.slots, self.output = manifest["batch_id"], slots, output

    def start(self, approval):
        limits = verify_approval(self.manifest, self.package, approval)
        self.ledger.start(
            self.batch, self.package, limits, approval, pinned_approval_sha256=digest(approval)
        )
        self.ledger.record(self.batch, "planned_slots", {"slots": self.slots})

    def events(self, kind):
        return [
            json.loads(row[0])
            for row in self.ledger.db.execute(
                "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                (self.batch, kind),
            )
        ]

    def review(self, review):
        """Human truth comes before the next model slot. Empty/generated pass is refused."""
        with self.ledger.transaction():
            self.ledger.guard(self.batch, self.package)
        outputs, reviews = self.events("slot_output"), self.events("human_review")
        if len(outputs) != len(reviews) + 1:
            raise Refused("NO_PENDING_REVIEW")
        pending = outputs[-1]
        self.verify_outputs(outputs)
        if (
            review.get("slot_id") != pending["slot_id"]
            or review.get("output_sha256") != pending["sha256"]
            or not review.get("reviewer")
            or not review.get("reviewed_at")
            or not review.get("evidence_ref")
            or review.get("exhaustive_coverage_attested") is not True
            or not review.get("items")
            or any(
                not item.get("location")
                or not item.get("reason")
                or item.get("verdict") not in ["pass", "fail", "unresolved"]
                for item in review["items"]
            )
        ):
            raise Refused("EXACT_EXHAUSTIVE_HUMAN_REVIEW_REQUIRED")
        slot = self.slots[len(reviews)]
        required = {
            "course": {"requirements", "learnability", "facts", "answers", "profile"},
            "negative": {"unsupported_or_conflict_boundary"},
            "probe": {"true_positive_or_false_block"},
        }[slot["kind"]]
        if slot.get("pair_id"):
            previous = [
                outputs[i]
                for i, previous_slot in enumerate(self.slots[: len(reviews)])
                if previous_slot.get("pair_id") == slot["pair_id"]
            ]
            if previous:
                required.add("pair")
                if review.get("pair_output_sha256") != [previous[-1]["sha256"], pending["sha256"]]:
                    raise Refused("EXACT_PAIR_OUTPUTS_REQUIRED")
        if not required <= {item.get("area") for item in review["items"]}:
            raise Refused("REVIEW_COVERAGE_MISSING")
        if (
            type(review.get("natural_severe_errors")) is not int
            or review["natural_severe_errors"] < 0
        ):
            raise Refused("SEVERE_ERROR_COUNT_REQUIRED")
        if slot["kind"] == "probe":
            if (
                type(review.get("severe_detected")) is not bool
                or type(review.get("flagged_correct_control")) is not bool
                or type(review.get("findings_total")) is not int
                or type(review.get("findings_true")) is not int
                or not 0 <= review["findings_true"] <= review["findings_total"]
                or (review["severe_detected"] and not review.get("matched_issue_quote"))
                or (review["severe_detected"] and review["findings_true"] == 0)
            ):
                raise Refused("HUMAN_PROBE_MATCH_COUNTS_REQUIRED")
            review = {**review, "accepted_label": slot["proposed_label"]}
        self.ledger.record(self.batch, "human_review", review)
        if review["natural_severe_errors"]:
            self.ledger.halt(self.batch, "natural_severe_error")
        elif any(item["verdict"] != "pass" for item in review["items"]):
            # Conservative stop. Never silently drop a failed/unresolved planned slot.
            self.ledger.halt(self.batch, "threshold_unreachable")
        elif slot["kind"] == "probe":
            probes = [r for r in self.events("human_review") if "accepted_label" in r]
            misses = sum(
                r["accepted_label"] == "severe" and not r["severe_detected"] for r in probes
            )
            false_blocks = sum(
                r["accepted_label"] == "correct" and r["flagged_correct_control"] for r in probes
            )
            total = sum(r["findings_total"] for r in probes)
            true = sum(r["findings_true"] for r in probes)
            if (
                misses > 1
                or false_blocks
                or (len(probes) == 20 and (not total or true / total < 0.9))
            ):
                self.ledger.halt(self.batch, "threshold_unreachable")

    def verify_outputs(self, outputs):
        for record in outputs:
            path = self.output / (record["slot_id"] + ".json")
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
            ):
                self.ledger.halt(self.batch, "independence_contaminated")
                raise Refused("OUTPUT_CHANGED")

    async def advance(self, runner):
        with self.ledger.transaction():
            self.ledger.guard(self.batch, self.package)
            starts, outputs, reviews = (
                self.events(k) for k in ["slot_started", "slot_output", "human_review"]
            )
            # The surrounding transaction must preserve any integrity stop.
            for record in outputs:
                path = self.output / (record["slot_id"] + ".json")
                if (
                    not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
                ):
                    self.ledger.stop(self.batch, "OUTPUT_CHANGED")
                    raise Refused("OUTPUT_CHANGED")
            if len(starts) != len(outputs):
                self.ledger.stop(self.batch, "INTERRUPTED_SLOT_NO_AUTOMATIC_RESEND")
                raise Refused("INTERRUPTED_SLOT_NO_AUTOMATIC_RESEND")
            if len(outputs) != len(reviews):
                raise Refused("HUMAN_REVIEW_PENDING")
            if len(outputs) == len(self.slots):
                self.ledger.record(self.batch, "batch_completed", {"slots": len(outputs)})
                self.ledger.stop(self.batch, "COMPLETED")
                return None
            slot = self.slots[len(outputs)]
            self.ledger.record(self.batch, "slot_started", {"slot_id": slot["slot_id"]})
        try:
            result = await runner(slot)
            raw = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode()
            path = self.output / (slot["slot_id"] + ".json")
            with path.open("xb") as stream:
                stream.write(raw)
            record = {"slot_id": slot["slot_id"], "sha256": hashlib.sha256(raw).hexdigest()}
            self.ledger.record(self.batch, "slot_output", record)
            if result.get("engineering_pass") is not True:
                self.ledger.halt(self.batch, "threshold_unreachable")
            return record
        except BaseException:
            self.ledger.halt(self.batch, "provider_contract_failure")
            raise


async def run_slot(slot, sessions, adapter, ledger, batch, package):
    """Actual product scheduler and actual counted adapter; tests inject only HTTP transport."""
    from sqlalchemy import select

    from app.agents import free_course_planning as planner
    from app.agents import free_scene_generation as generator
    from app.agents.review_schema import review_output_schema, validate_review
    from app.models.auth import Base, User
    from app.models.free_course import FreeCoursePlan
    from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
    from app.models.free_course_writes import FreeCourseOperation
    from app.models.learning import StudentProfile
    from app.services.free_course_scheduler import Scheduler
    from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest

    if slot["kind"] == "probe":
        reply = await adapter.send(
            StructuredRequest(
                TextRequest(
                    (ChatMessage("system", PROBE_PROMPT), ChatMessage("user", slot["content"])),
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
            "engineering_pass": reply.evidence == "complete_response" and opinion is not None,
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
    created = await scheduler.enqueue(owner, slot.get("original_goal", slot.get("goal")), key="r01")
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
                        FreeCourseAttempt.course_id == cid, FreeCourseAttempt.purpose == "primary"
                    )
                )
                for attempt, settlement in primary:
                    if str(attempt.id) in checked:
                        continue
                    packed = attempt.request_json["request"]
                    validator = (
                        planner if packed["stage"] == "free_course_plan_generation" else generator
                    )
                    try:
                        validator.validate_response(
                            settlement.outcome_json.get("value"), attempt.input_snapshot
                        )
                        valid = True
                    except (TypeError, ValueError):
                        valid = False
                    ledger.record(
                        batch, "primary_schema", {"attempt": str(attempt.id), "valid": valid}
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
            plan = await db.scalar(select(FreeCoursePlan).where(FreeCoursePlan.course_id == cid))
            op = await db.get(FreeCourseOperation, oid)
            if plan is not None and frozen_n is None:
                frozen_n = len(plan.plan_json["scenes"])
                ledger.record(
                    batch, "scene_denominator", {"slot_id": slot["slot_id"], "n": frozen_n}
                )
                if slot["kind"] == "negative":
                    raise Refused("NEGATIVE_CONTROL_PLANNED_UNSUPPORTED_CONTENT")
                low, high = slot["scene_count_range"]
                if not low <= frozen_n <= high:
                    raise Refused("SCENE_COUNT_OUTSIDE_FROZEN_EXPECTATION")
            if op.state not in ["queued", "running"]:
                tables = {}
                for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
                    if "course_id" in table.c and "user_id" in table.c:
                        rows = await db.execute(
                            select(table).where(table.c.course_id == cid, table.c.user_id == owner)
                        )
                        tables[table.name] = [dict(row) for row in rows.mappings()]
                return {
                    "engineering_pass": op.state
                    == ("awaiting_clarification" if slot["kind"] == "negative" else "succeeded"),
                    "operation_state": op.state,
                    "reason": op.reason_code,
                    "planned_scene_denominator": frozen_n
                    or slot.get("scene_count_range", [0, 0])[1],
                    "tables": tables,
                }
        await asyncio.sleep(0.05)
    raise Refused("SLOT_STEP_LIMIT")
