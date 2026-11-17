"""Retain original review/answer standard; separately adjudicate local advisories."""

import json

from acceptance_support.p15_diagnostic_ledger import Refused, digest
from app.services.free_scene_consistency import check_consistency
from isolated_diagnostics.p15_full_review_r05 import SplitExecution as Original


def verify_consistency(values, observations):
    if len(values) != 1:
        raise Refused("ONE_D02_OUTPUT_REQUIRED")
    tables = values[0].get("tables", {})
    generations = {
        str(g["id"]): g for g in tables.get("free_course_scene_generation_results", [])
    }
    validations = tables.get("free_course_scene_validations", [])
    if len(validations) != 2 or len(observations) != 2:
        raise Refused("ALL_TWO_CONSISTENCY_REPORTS_REQUIRED")
    expected = []
    for v in validations:
        if v["rule_version"] != "free-scene-hard-gate-v4" or len(v["findings"]) != 1:
            raise Refused("CONSISTENCY_VERSION_CHANGED")
        g = generations.get(str(v["generation_result_id"]))
        if g is None:
            raise Refused("CONSISTENCY_CANDIDATE_MISSING")
        report = check_consistency(g["response_json"], g["input_snapshot"])
        if v["findings"][0]["report"] != report:
            raise Refused("CONSISTENCY_REPORT_CHANGED")
        expected.append(
            dict(
                validation_id=str(v["id"]),
                raw_digest=v["raw_digest"],
                generation_result_id=str(v["generation_result_id"]),
                report_sha256=digest(report),
                report=report,
            )
        )
    if {digest(v) for v in expected} != {digest(v) for v in observations}:
        raise Refused("CONSISTENCY_OBSERVATION_CHANGED")


class SplitExecution(Original):
    def review(self, report):
        observations = self.journal.events("consistency_observation")
        rows = report.get("consistency_checks", [])
        expected = {v["report_sha256"]: v for v in observations}
        if (
            len(observations) != 2
            or len(expected) != 2
            or len(rows) != 2
            or {r.get("report_sha256") for r in rows} != expected.keys()
        ):
            raise Refused("ALL_TWO_CONSISTENCY_REPORTS_REQUIRED")
        for row in rows:
            original = expected[row["report_sha256"]]["report"]
            if (
                digest(original) != row["report_sha256"]
                or row.get("incomplete_coverage_acknowledged") is not True
            ):
                raise Refused("CONSISTENCY_SOURCE_OR_COVERAGE_CHANGED")
            decisions = row.get("findings", [])
            if len(decisions) != len(original["findings"]):
                raise Refused("ALL_CONSISTENCY_FINDINGS_REQUIRED")
            for index, decision in enumerate(decisions):
                if (
                    decision.get("finding_sha256")
                    != digest(original["findings"][index])
                    or not decision.get("reason")
                    or decision.get("decision")
                    not in ("false_alarm", "confirmed", "unresolved")
                ):
                    raise Refused("EXACT_CONSISTENCY_DECISION_REQUIRED")
                if decision["decision"] != "false_alarm" and not any(
                    item.get("area") in ("facts", "answers")
                    and item.get("verdict") != "pass"
                    for item in report.get("items", [])
                ):
                    raise Refused("CONSISTENCY_FINDING_CANNOT_BE_HIDDEN")
        outputs = self.events("slot_output")
        self.verify_outputs(outputs)
        if len(outputs) != 1:
            raise Refused("ONE_D02_OUTPUT_REQUIRED")
        value = json.loads(
            (self.output / (outputs[0]["slot_id"] + ".json")).read_bytes()
        )
        verify_consistency([value], observations)
        return super().review(report)


def assess(slots, outputs, reports, primary):
    # This is a one-course development regression, never the full T038 denominator.
    complete = len(slots) == len(outputs) == len(reports) == 1
    passing = (
        complete
        and outputs[0].get("engineering_pass") is True
        and all(item["verdict"] == "pass" for item in reports[0]["items"])
        and reports[0]["natural_severe_errors"] == 0
        and len(outputs[0].get("scene_source_hashes", [])) == 2
        and len(primary) == 3
        and bool(reports[0].get("atomic_facts"))
        and bool(reports[0].get("answer_checks"))
        and len(reports[0].get("consistency_checks", [])) == 2
        and all(p["valid"] for p in primary)
    )
    return dict(
        local_recheck_pass=passing,
        new_substantive_quality_error_requires_reassessment=True,
        automatic_further_repairs_authorized=False,
        complete=complete,
        courses_planned=1,
        scenes_planned=2,
        courses_observed=len(outputs),
        assistant_reports=len(reports),
        first_schema_valid=sum(bool(p["valid"]) for p in primary),
        primary_observed=len(primary),
        T038_completed=False,
        independent_validation_passed=False,
        production_admitted=False,
        personalized_pair_comparison="not_assessed_single_known_profile",
    )
