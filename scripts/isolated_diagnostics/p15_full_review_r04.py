"""Source-bound delegated evidence and unchanged development quality thresholds."""

import json
import math
import re
from datetime import datetime
from collections import defaultdict

from acceptance_support.p15_diagnostic_ledger import Refused, digest
from app.services.quiz_scoring import _canonical_answer
from isolated_diagnostics.p15_delegated_exploration import SplitExecution as Delegated


def quote(source, pointer, text):
    if (
        not isinstance(pointer, str)
        or re.search(r"~(?![01])", pointer)
        or not pointer.startswith("/scene/")
    ):
        raise Refused("INVALID_REVIEW_POINTER")
    value = source
    try:
        for part in pointer.split("/")[1:]:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if (
                    not part.isascii()
                    or not part.isdecimal()
                    or len(part) > 1
                    and part.startswith("0")
                ):
                    raise Refused("INVALID_REVIEW_INDEX")
                value = value[int(part)]
            else:
                value = value[part]
    except (KeyError, IndexError, TypeError):
        raise Refused("REVIEW_QUOTE_NOT_BOUND") from None
    if (
        not isinstance(value, str)
        or not isinstance(text, str)
        or not text
        or text not in value
    ):
        raise Refused("REVIEW_QUOTE_NOT_BOUND")


def course_inventory(journal, identity, report):
    targets = journal.sources(identity)
    by_sha = {t["payload"]["source_sha256"]: t for t in targets}
    if not targets:
        raise Refused("COURSE_SOURCES_REQUIRED")
    facts = report.get("atomic_facts")
    answers = report.get("answer_checks")
    if not isinstance(facts, list) or not facts or not isinstance(answers, list):
        raise Refused("ATOMIC_FACT_AND_ANSWER_INVENTORY_REQUIRED")
    block_prefixes = {}
    blocks = set()
    questions = {}
    for sha, t in by_sha.items():
        scene = t["payload"]["source"]["scene"]
        for index, block in enumerate(scene["content"]["blocks"]):
            blocks.add((sha, block["anchor_id"]))
            block_prefixes[(sha, block["anchor_id"])] = (
                f"/scene/content/blocks/{index}/"
            )
            if block["kind"] == "exercise":
                for q in block["items"]:
                    questions[(sha, block["anchor_id"], q["question_id"])] = q
    coverage = set()
    seen_facts = set()
    for row in facts:
        key = (row.get("source_sha256"), row.get("anchor_id"))
        if (
            key not in blocks
            or row.get("verdict") not in ["pass", "fail", "unresolved"]
            or not row.get("reason")
        ):
            raise Refused("FACT_INVENTORY_INVALID")
        source = by_sha[key[0]]["payload"]["source"]
        quote(source, row.get("source_pointer"), row.get("evidence_quote"))
        fact_key = (
            key,
            row["source_pointer"],
            row["evidence_quote"],
            row.get("statement"),
        )
        if not row.get("statement") or fact_key in seen_facts:
            raise Refused("DUPLICATE_OR_EMPTY_FACT")
        seen_facts.add(fact_key)
        if row["source_pointer"].startswith(block_prefixes[key]):
            coverage.add(key)
    if coverage != blocks:
        raise Refused("UNREVIEWED_SCENE_BLOCK")
    seen_questions = set()
    for row in answers:
        key = (row.get("source_sha256"), row.get("anchor_id"), row.get("question_id"))
        if (
            key not in questions
            or key in seen_questions
            or row.get("verdict") not in ["pass", "fail", "unresolved"]
            or not row.get("reason")
        ):
            raise Refused("ANSWER_INVENTORY_INVALID")
        seen_questions.add(key)
        question = questions[key]
        if row.get("answer_key") != question["answer_key"]:
            raise Refused("ANSWER_KEY_CHANGED")
        if row["verdict"] == "pass":
            accepted = row.get("accepted_inputs")
            rejected = row.get("rejected_inputs")
            if (
                row.get("safe_for_exact_scoring") is not True
                or not isinstance(accepted, list)
                or not accepted
                or not isinstance(rejected, list)
                or not rejected
                or any(
                    not isinstance(s, str)
                    or _canonical_answer(s) != _canonical_answer(question["answer_key"])
                    for s in accepted
                )
                or any(
                    not isinstance(s, str)
                    or _canonical_answer(s) == _canonical_answer(question["answer_key"])
                    for s in rejected
                )
            ):
                raise Refused("EXACT_SCORING_CHECK_REQUIRED")
    if seen_questions != questions.keys():
        raise Refused("UNREVIEWED_QUESTION")
    if any(r["verdict"] != "pass" for r in facts) and not any(
        i["area"] == "facts" and i["verdict"] != "pass" for i in report["items"]
    ):
        raise Refused("FACT_FAILURE_HIDDEN")
    if any(r["verdict"] != "pass" for r in answers) and not any(
        i["area"] == "answers" and i["verdict"] != "pass" for i in report["items"]
    ):
        raise Refused("ANSWER_FAILURE_HIDDEN")


class SplitExecution(Delegated):
    def review(self, report):
        if (
            report.get("reviewer") != "Codex assistant"
            or report.get("review_type") != "delegated_assistant"
            or report.get("independent_human_truth") is not False
        ):
            raise Refused("DELEGATED_ASSISTANT_PROVENANCE_REQUIRED")
        outputs = self.events("slot_output")
        reviews = self.events("human_review")
        if len(outputs) != len(reviews) + 1:
            raise Refused("NO_PENDING_REVIEW")
        pending = outputs[-1]
        self.verify_outputs(outputs)
        slot = self.slots[len(reviews)]
        required = {
            "course": {"requirements", "learnability", "facts", "answers", "profile"},
            "negative": {"unsupported_or_conflict_boundary"},
            "probe": {"true_positive_or_false_block"},
        }[slot["kind"]]
        if (
            report.get("slot_id") != pending["slot_id"]
            or report.get("output_sha256") != pending["sha256"]
            or not report.get("reviewed_at")
            or not report.get("evidence_ref")
            or report.get("exhaustive_coverage_attested") is not True
            or not report.get("items")
            or not required <= {i.get("area") for i in report["items"]}
            or any(
                i.get("verdict") not in ["pass", "fail", "unresolved"]
                or not i.get("reason")
                or not i.get("location")
                for i in report["items"]
            )
            or type(report.get("natural_severe_errors")) is not int
            or report["natural_severe_errors"] < 0
        ):
            raise Refused("EXACT_EXHAUSTIVE_ASSISTANT_REVIEW_REQUIRED")
        value = json.loads((self.output / (pending["slot_id"] + ".json")).read_bytes())
        from isolated_diagnostics.p15_split_provider import Identity

        identity = (
            Identity(**value["scene_review_identity"])
            if slot["kind"] == "course"
            else None
        )
        failed = (
            any(i["verdict"] != "pass" for i in report["items"])
            or report["natural_severe_errors"] > 0
        )
        if identity:
            course_inventory(self.journal, identity, report)
            opinions = [
                v
                for v in self.journal.events("scene_review_finished")
                if v["identity"] == identity.packed()
            ]
            expected = {
                v["source_sha256"]: v
                for v in opinions
                if v["opinion"]["verdict"] != "pass"
            }
            adjudications = report.get("model_adjudications", [])
            if (
                len(adjudications) != len(expected)
                or {r.get("source_sha256") for r in adjudications} != expected.keys()
            ):
                raise Refused("ALL_MODEL_ADJUDICATIONS_REQUIRED")
            for decision in adjudications:
                original = expected[decision["source_sha256"]]
                if (
                    decision.get("opinion_sha256") != digest(original["opinion"])
                    or not decision.get("reason")
                    or decision.get("decision")
                    not in [
                        "false_alarm",
                        "confirmed_nonsevere",
                        "confirmed_severe",
                        "unresolved",
                    ]
                ):
                    raise Refused("EXACT_MODEL_ADJUDICATION_REQUIRED")
                if decision["decision"] == "false_alarm" and not any(
                    r["identity"] == identity.packed()
                    and r["source_sha256"] == decision["source_sha256"]
                    and r.get("review_type") == "delegated_assistant"
                    and r.get("independent_human_truth") is False
                    for r in self.journal.events("scene_false_alarm_adjudicated")
                ):
                    raise Refused("EXPLICIT_FALSE_ALARM_ADJUDICATION_REQUIRED")
                if decision["decision"] != "false_alarm" and not failed:
                    raise Refused("CONFIRMED_OR_UNRESOLVED_ISSUE_CANNOT_PASS")
                if (
                    decision["decision"] == "confirmed_severe"
                    and not report["natural_severe_errors"]
                ):
                    raise Refused("SEVERE_ERROR_HIDDEN")
                if (
                    decision["decision"] == "false_alarm"
                    and original["opinion"]["verdict"] == "uncertain"
                ):
                    raise Refused("UNCERTAINTY_CANNOT_BE_LABELLED_FALSE_ALARM")
            if report.get(
                "scene_review_checkpoint_sha256"
            ) != self.journal.review_checkpoint(identity):
                raise Refused("EXACT_SCENE_REVIEW_CHECKPOINT_REQUIRED")
        # Only a failing report may record an incomplete model-review set, then halt.
        self.journal._failure_import = failed
        try:
            super().review(report)
        finally:
            self.journal._failure_import = False


def assess(slots, outputs, reports, primary):
    """No truth labels are created here. All fixed slots remain in denominators."""
    by_id = {r["slot_id"]: r for r in reports}
    result_by_id = {r["slot_id"]: r for r in outputs}
    complete = (
        len(reports) == len(outputs) == len(slots) == 34
        and set(result_by_id) == set(by_id)
        and set(by_id) == {s["slot_id"] for s in slots}
    )
    courses = [s for s in slots if s["kind"] == "course"]
    pairs = set(s["pair_id"] for s in courses)

    def passed(s, area):
        return any(
            r["area"] == area and r["verdict"] == "pass"
            for r in by_id.get(s["slot_id"], {}).get("items", [])
        )

    generated = sum(
        result_by_id.get(s["slot_id"], {}).get("engineering_pass") is True
        for s in courses
    )
    requirements = sum(passed(s, "requirements") for s in courses)
    learnability = sum(passed(s, "learnability") for s in courses)
    strata = defaultdict(list)
    for s in courses:
        strata["topic:" + s["topic"]].append(s)
        strata["profile:" + ("known" if s["learner_evidence"] else "unknown")].append(s)
    strata_pass = all(
        sum(
            result_by_id.get(s["slot_id"], {}).get("engineering_pass") is True
            and passed(s, "requirements")
            and passed(s, "learnability")
            for s in rows
        )
        >= math.ceil(0.95 * len(rows))
        for rows in strata.values()
    )
    pair_success = sum(
        any(s["pair_id"] == p and passed(s, "pair") for s in courses) for p in pairs
    )
    facts = [r for v in reports for r in v.get("atomic_facts", [])]
    answers = [r for v in reports for r in v.get("answer_checks", [])]
    probes = [
        by_id[s["slot_id"]]
        for s in slots
        if s["kind"] == "probe" and s["slot_id"] in by_id
    ]
    tp = sum(
        r.get("accepted_label") == "severe" and r.get("severe_detected") is True
        for r in probes
    )
    false_blocks = sum(
        r.get("accepted_label") == "correct"
        and r.get("flagged_correct_control") is True
        for r in probes
    )
    findings = sum(r.get("findings_total", 0) for r in probes)
    true_findings = sum(r.get("findings_true", 0) for r in probes)
    unresolved = sum(
        r["verdict"] == "unresolved" for v in reports for r in v.get("items", [])
    )
    unresolved += sum(r["verdict"] == "unresolved" for r in facts + answers)
    unresolved += sum(
        a.get("decision") == "unresolved"
        for r in reports
        for a in r.get("model_adjudications", [])
    )
    gates = dict(
        complete=complete,
        engineering=all(
            result_by_id.get(s["slot_id"], {}).get("engineering_pass") is True
            for s in slots
        ),
        first_schema=bool(primary)
        and sum(r["valid"] is True for r in primary) >= math.ceil(0.98 * len(primary)),
        complete_draft=generated >= math.ceil(0.95 * 12),
        requirements=requirements >= math.ceil(0.95 * 12),
        learnability=learnability >= math.ceil(0.95 * 12),
        strata=strata_pass,
        personalization=pair_success >= math.ceil(0.9 * 6),
        facts=bool(facts)
        and sum(r["verdict"] == "pass" for r in facts) >= math.ceil(0.99 * len(facts)),
        answers=bool(answers) and all(r["verdict"] == "pass" for r in answers),
        probe_recall=tp >= 9,
        probe_precision=findings > 0 and true_findings >= math.ceil(0.9 * findings),
        correct_controls=false_blocks == 0,
        no_severe=sum(r.get("natural_severe_errors", 0) for r in reports) == 0,
        no_unresolved=unresolved == 0,
        negative_controls=all(
            passed(s, "unsupported_or_conflict_boundary")
            for s in slots
            if s["kind"] == "negative"
        ),
    )
    return dict(
        gates=gates,
        development_admitted=all(gates.values()),
        independent_quality_pass=False,
        performance_admitted=False,
        production_admission=False,
        performance=performance_observations(courses, result_by_id),
        counts=dict(
            planned=34,
            reviewed=len(reports),
            courses_generated=generated,
            facts=len(facts),
            answers=len(answers),
            severe_tp=tp,
            severe_denominator=10,
            correct_false_blocks=false_blocks,
            probe_findings=findings,
            probe_true_findings=true_findings,
            personalization_pairs=pair_success,
        ),
    )


def performance_observations(courses, outputs):
    """PG event timing only; no fabricated first-token or cache-state observations."""
    rows = []
    for slot in courses:
        value = outputs.get(slot["slot_id"], {})
        events = value.get("tables", {}).get("free_course_events", [])
        operations = value.get("tables", {}).get("free_course_operations", [])
        started = (
            datetime.fromisoformat(operations[0]["created_at"]) if operations else None
        )
        ready = sorted(
            datetime.fromisoformat(e["created_at"])
            for e in events
            if e["event_type"] == "scene_ready"
        )
        done = [
            datetime.fromisoformat(e["created_at"])
            for e in events
            if e["event_type"] == "done"
        ]
        success = value.get("engineering_pass") is True
        rows.append(
            {
                "slot_id": slot["slot_id"],
                "cache_state": "unverified",
                "first_scene_seconds": (ready[0] - started).total_seconds()
                if ready and started
                else None,
                "full_course_seconds": (done[-1] - started).total_seconds()
                if success and done and started
                else None,
                "later_scene_waits_seconds": [
                    (b - a).total_seconds() for a, b in zip(ready, ready[1:])
                ],
                "failed_or_unrun_counts_as_infinity": not success,
            }
        )
    return {
        "rows": rows,
        "timing_source": "PG operation creation and committed scene_ready/done events",
        "first_token_seconds": None,
        "cold_warm_separately_verified": False,
        "performance_gate_applied": False,
    }
