"""Read-only checks of frozen inputs and GPT record structure, never a semantic oracle."""

# ruff: noqa: E402
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from jsonschema import Draft202012Validator
from acceptance_support.qwen_review_budget import canonical, sha
from app.services.unit_material import restore_material
from prepare_five_hour_materials import BASE


def verify_freeze(base=BASE, root=ROOT):
    m = json.loads((base / "manifest.json").read_text())
    if (
        m.get("kind") != "FROZEN_INPUTS_AND_GPT_RECORD_FORMAT_NOT_EXECUTION_AUTHORITY"
        or m.get("real_requests_authorized") != 0
    ):
        raise ValueError("NOT_A_ZERO_CALL_MATERIAL_FREEZE")
    for name, expected in m["files"].items():
        path = root / name
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
            or ".env" in path.parts
            or name.startswith("local-materials/")
            or sha(path.read_bytes()) != expected
        ):
            raise ValueError("FREEZE_CHANGED_OR_UNSAFE")
    return sha(canonical(m))


def validate_evaluation(value, *, base=BASE):
    schema = json.loads((base / "evaluation.schema.json").read_text())
    Draft202012Validator(schema).validate(value)
    actual, grades = value["actual"], value["grades"]
    labels = json.loads((base / "labels.json").read_text())["labels"]
    entries = json.loads((base / "case-index.json").read_text())["entries"]
    entry = next(e for e in entries if e["id"] == value["case_id"])
    if value["case_sha256"] != entry["case_sha256"] or value["label_sha256"] != sha(
        canonical(labels[value["case_id"]])
    ):
        raise ValueError("EVALUATION_BINDING_CHANGED")
    if not value["case_id"].startswith("A") and actual["actual_call_count"] > 1:
        raise ValueError("INDEPENDENT_REVIEW_IS_ONE_CALL")
    if not value["case_id"].startswith("A") and actual["course_state"] is not None:
        raise ValueError("INDEPENDENT_REVIEW_HAS_NO_COURSE_PUBLICATION_STATE")
    if grades["core_expected"] == "pass":
        if value["case_id"].startswith("A"):
            if (
                actual["course_state"] != "completed"
                or actual["local_verdict"] != "pass"
            ):
                raise ValueError("GENERATION_CORE_REQUIRES_AUTOMATIC_COMPLETION")
        else:
            allowed = labels[value["case_id"]]["expected_verdicts"]
            if (
                actual["model_verdict"] not in allowed
                or actual["local_verdict"] not in allowed
            ):
                raise ValueError("CORE_ROUTING_NOT_IN_FROZEN_LABEL")
    if actual["status"] == "not_run":
        if (
            actual["actual_call_count"]
            or actual["model_verdict"] is not None
            or actual["request_receipt_paths"]
            or actual["response_artifact_paths"]
            or any(
                grades[k] != "unassessed"
                for k in (
                    "technical_integrity",
                    "core_expected",
                    "all_claims",
                    "all_citations",
                    "full_quality",
                )
            )
            or grades["final_status"] != "not_run"
        ):
            raise ValueError("UNRUN_CANNOT_BE_SCORED")
    if grades["full_quality"] == "pass":
        if not (
            all(
                grades[k] == "pass"
                for k in (
                    "technical_integrity",
                    "core_expected",
                    "all_claims",
                    "all_citations",
                )
            )
            and value["reviewed_all_candidates_and_audit_history"]
            and not value["unresolved"]
            and value["evidence"]
            and actual["status"] == "observed"
            and actual["actual_call_count"] > 0
            and actual["request_receipt_paths"]
            and actual["response_artifact_paths"]
            and value["run_id"]
            and value["evaluator"]["evaluated_at"]
        ):
            raise ValueError("FULL_PASS_WITHOUT_COMPLETE_EVIDENCE")
        if any(
            c["result"] != "supported"
            for c in value["claim_checks"] + value["citation_checks"]
        ):
            raise ValueError("UNSUPPORTED_CLAIM_CANNOT_PASS")
    if grades["final_status"] == "pass" and (
        grades["full_quality"] != "pass" or grades["impact"] != "green"
    ):
        raise ValueError("CASE_PASS_REQUIRES_FULL_QUALITY")
    if (
        value["corrections"]["unsupported_feedback_entered"] is True
        and grades["impact"] != "red"
    ):
        raise ValueError("PROPAGATION_REQUIRES_RED_STOP")
    if grades["impact"] == "red" and grades["final_status"] != "fail":
        raise ValueError("RED_CANNOT_PASS_OR_BE_UNRESOLVED")
    evidence_ids = {e["id"] for e in value["evidence"]}
    if len(evidence_ids) != len(value["evidence"]):
        raise ValueError("DUPLICATE_EVIDENCE_ID")
    for check in value["claim_checks"] + value["citation_checks"]:
        if not set(check["evidence_ids"]) <= evidence_ids or (
            check["result"] == "supported" and not check["evidence_ids"]
        ):
            raise ValueError("CLAIM_EVIDENCE_MISSING")
    for citation in value["citation_checks"]:
        if citation["end_utf8"] <= citation["start_utf8"]:
            raise ValueError("CITATION_RANGE_INVALID")
    # This checks record consistency only. It does not establish that recorded
    # quotations, evidence interpretation or semantic labels are themselves true.


def check_materials(base=BASE):
    if (base / "manifest.json").exists():
        verify_freeze(base)
    index = json.loads((base / "case-index.json").read_text())
    labels = json.loads((base / "labels.json").read_text())["labels"]
    expected = (
        [f"A{i:02}" for i in range(1, 5)]
        + [f"U{i:02}" for i in range(1, 9)]
        + [f"R{i:02}" for i in range(1, 5)]
    )
    assert [e["id"] for e in index["entries"]] == expected and set(labels) == set(
        expected
    )
    assert (
        index["real_requests_authorized"] == 0
        and not index["generation_outputs_frozen"]
    )
    for entry in index["entries"]:
        c = json.loads((base / entry["case_path"]).read_text())
        assert (
            sha(canonical(c)) == entry["case_sha256"]
            and c["actual_model_result"] is None
        )
        assert labels[c["id"]]["actual_result"] is None
        request = json.loads((base / entry["request_path"]).read_text())
        wire = bytes.fromhex(request["wire_hex"])
        assert sha(wire) == request["wire_sha256"]
        body = json.loads(wire)
        if c["id"].startswith("A"):
            assert c["generated_material"] is None and body["model"] == "deepseek-flash"
            assert (
                body["reasoning"] == {"effort": "none"}
                and body["max_output_tokens"] == 2048
            )
        else:
            _, m = restore_material(c["material"])
            assert (
                body["model"] == "gpt-6-luna"
                and body["reasoning"] == {"effort": "high"}
                and body["max_output_tokens"] == 8192
            )
            data = json.loads(body["input"][1]["content"])
            assert (
                not {
                    "labels",
                    "expected_verdicts",
                    "required_findings",
                    "actual_model_result",
                }
                & data.keys()
            )
            if c["scope"] == "unit":
                # v4.9 intentionally projects background reference_context; all
                # actual students' content and authoritative bindings stay exact.
                assert set(data["unit"]) == set(m)
                assert all(
                    data["unit"][k] == value
                    for k, value in m.items()
                    if k != "reference_context"
                )
            else:
                assert (
                    data["candidate"]["role"] == c["selected_role"]
                    and "unit" not in data
                )
            Draft202012Validator.check_schema(request["business_schema"])
        assert body["temperature"] == 0
    budget = json.loads((base / "budget.json").read_text())
    assert budget["basic_expected_requests"] == 4 * 8 + 8 + 4 == 44
    assert (
        budget["base_call_slots_reserved"] + budget["shared_extra_slots_max"]
        == budget["basic_package_requests_max"]
        == 60
    )
    assert (
        budget["monetary_cap"] is None
        and budget["overall_request_budget_cap"] is None
        and budget["real_requests_authorized"] == 0
    )
    validate_evaluation(
        json.loads((base / "evaluation-template.json").read_text()), base=base
    )
    return dict(
        cases=16,
        full_review_materials=12,
        generation_input_tasks=4,
        live_authority=0,
        semantic_results="not run; GPT labels are not independent human truth",
    )


if __name__ == "__main__":
    print(json.dumps(check_materials(), ensure_ascii=False))
