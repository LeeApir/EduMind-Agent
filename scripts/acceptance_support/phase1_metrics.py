"""Offline metrics over fixed samples; annotations are evidence, not inferred LLM quality."""

from __future__ import annotations

from .phase1_budget import HASH, GateFailure


def score_review(cases: list[dict], observations: list[dict], *, freeze: str) -> dict:
    """Missing/unavailable rows remain in denominators; one immutable configuration per run.

    Concrete detection is human-coded against the exact response hash and expected defect.
    An LLM saying reject, or a locally invalid response, is not concrete detection.
    """
    ids = {c["id"] for c in cases}
    if len(ids) != len(cases):
        raise GateFailure("INVALID_FREEZE")
    rows = {}
    for row in observations:
        if row["id"] not in ids or row["id"] in rows or row["freeze"] != freeze:
            raise GateFailure("OBSERVATION_MISMATCH")
        rows[row["id"]] = row
    counts = {k: [0, 0] for k in ("detection", "classification", "correct_pass", "long_complete")}
    for case in cases:
        row = rows.get(case["id"], {})
        complete = (
            row.get("complete") is True
            and row.get("schema_valid") is True
            and row.get("input_sha256") == case["input_sha256"]
        )
        response = row.get("response_sha256")
        annotation = row.get("annotation_sha256")
        labeled = (
            complete
            and row.get("human_annotation_bound") is True
            and isinstance(response, str)
            and HASH.fullmatch(response) is not None
            and row.get("annotated_response_sha256") == response
            and isinstance(annotation, str)
            and HASH.fullmatch(annotation) is not None
        )
        if case["kind"] == "severe_error":
            detected = labeled and row.get("concrete_defect") == case["target_defect"]
            counts["detection"][1] += 1
            counts["classification"][1] += 1
            counts["detection"][0] += int(detected)
            counts["classification"][0] += int(
                detected and row.get("area") == case["expected_area"]
            )
        elif case["kind"] == "correct_control":
            counts["correct_pass"][1] += 1
            counts["correct_pass"][0] += int(labeled and row.get("verdict") == "pass")
        elif case["kind"] == "long_review":
            counts["long_complete"][1] += 1
            counts["long_complete"][0] += int(complete)
        else:
            raise GateFailure("INVALID_FREEZE")
    metrics = {k: {"numerator": v[0], "denominator": v[1]} for k, v in counts.items()}
    # Proposed thresholds, effective only after ADR-0011 approval. Exact integer arithmetic.
    requirements = {
        "detection": (20, 90),
        "classification": (20, 90),
        "correct_pass": (20, 95),
        "long_complete": (10, 95),
    }
    eligible = len(rows) == len(cases) and all(
        v[1] >= requirements[k][0] and v[0] * 100 >= v[1] * requirements[k][1]
        for k, v in counts.items()
    )
    return {
        "freeze": freeze,
        "metrics": metrics,
        "proposed_admission_met": eligible,
        "missing": [c["id"] for c in cases if c["id"] not in rows],
    }


def score_generation(slots: list[dict], observations: list[dict], *, freeze: str) -> dict:
    ids = {slot["id"] for slot in slots}
    if len(ids) != len(slots) or not slots:
        raise GateFailure("INVALID_FREEZE")
    rows = {}
    for row in observations:
        if row["id"] not in ids or row["id"] in rows or row["freeze"] != freeze:
            raise GateFailure("OBSERVATION_MISMATCH")
        rows[row["id"]] = row
    first = published = 0
    invalid_publication = []
    for slot in slots:
        row = rows.get(slot["id"], {})
        bound = row.get("input_sha256") == slot["input_sha256"]
        first += int(bound and row.get("first_schema_valid") is True)
        if row.get("published") is True:
            eligible = (
                bound
                and row.get("final_schema_valid") is True
                and row.get("all_three_reviewed") is True
            )
            published += int(eligible)
            if not eligible:
                invalid_publication.append(slot["id"])
    n = len(slots)
    return {
        "freeze": freeze,
        "first_schema": {"numerator": first, "denominator": n},
        "published": {"numerator": published, "denominator": n},
        "invalid_publication": invalid_publication,
        "admission_met": len(rows) == n
        and n >= 100
        and first * 100 >= n * 98
        and published * 100 >= n * 95
        and not invalid_publication,
        "missing": [slot["id"] for slot in slots if slot["id"] not in rows],
    }


def enforce_admission(result: dict, budget) -> None:
    """Trusted phase composition calls this before advancing to another stage/attempt."""
    if result.get("freeze") != budget.freeze:
        budget.halt("ADMISSION_FAILED")
        raise GateFailure("OBSERVATION_MISMATCH")
    if result.get("proposed_admission_met", result.get("admission_met")) is not True:
        budget.halt("ADMISSION_FAILED")
        raise GateFailure("ADMISSION_FAILED")
