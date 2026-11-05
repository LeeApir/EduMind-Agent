"""Derive T110 teaching evidence from saved T109 materials; never revise the original."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services import head_course_materials as m  # noqa: E402
from app.services import head_course_reuse as r  # noqa: E402
from app.services import head_course_teaching_evidence as evidence  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from scripts.head_course_goal import raw_io  # noqa: E402

OLD = ROOT / "docs/acceptance/phase-1.5-head-reuse-live-r01"
HERE = ROOT / "docs/acceptance/phase-1.5-head-evidence-t110"


def outputs():
    original_bytes = (OLD / "candidate.json").read_bytes()
    c = raw_io.wire.strict_json(original_bytes)
    rec = raw_io.wire.strict_json((OLD / "generate.record.json").read_bytes())
    replay = r.record(
        c["payload"],
        rec["request"],
        (OLD / "generate.raw.json").read_bytes(),
        raw_io,
        evidence_kind="actual_provider_response",
    )
    assert replay == rec and c == replay["candidate"]
    payload = evidence.with_evidence(c["payload"])
    bundle = payload["teaching_evidence"]
    # Isolated citation check: no new candidate, no text replacement, no publication.
    probe = json.loads(canonical(c["raw_output"]))
    probe["paragraphs"][5]["fact_ids"] = [evidence.DISCARDED]
    try:
        m.validate_content(c["payload"], probe)
    except Exception as exc:
        assert getattr(exc, "code", None) == "HEAD_FACT_REFERENCE"
    else:
        raise AssertionError("Old material version must reject new supplement IDs")
    m.validate_content(payload, probe)
    values = {
        "teaching-evidence.json": bundle,
        "generation-input.preview.json": dict(
            status="offline_evidence_input_preview_not_a_new_candidate", payload=payload
        ),
        "teaching-request.preview.json": m.body(payload),
        "claim-evidence-map.json": dict(
            original_candidate_digest=c["candidate_digest"],
            original_candidate_file_sha256=hashlib.sha256(original_bytes).hexdigest(),
            original_request_sha256=hashlib.sha256(
                (OLD / "generate.request.json").read_bytes()
            ).hexdigest(),
            original_materials_digest=c["payload"]["materials"]["materials_digest"],
            original_replay_equal=True,
            original_candidate_modified=False,
            evidence_version=evidence.VERSION,
            evidence_digest=bundle["evidence_digest"],
            S01=dict(
                path=["failure_scope"],
                original_text=c["raw_output"]["failure_scope"],
                disputed_quote="只通过 allocation_success 条件掩码演示“不分配”的分支",
                evidence_fact_ids=[evidence.DISPLAYED],
                allocations=["f01", "f07"],
                null_checks=["f02", "f08"],
                continue_frames=["f03", "f09"],
                shown_no_allocation_frames=[],
                verdict="original_scope_claim_not_supported_by_13_frames",
            ),
            C01=dict(
                path=["paragraphs", 5],
                original_text=c["raw_output"]["paragraphs"][5]["text"],
                original_fact_ids=c["raw_output"]["paragraphs"][5]["fact_ids"],
                usable_fact_ids=[evidence.DISCARDED],
                facts_origin="separately_computed_not_main_animation",
                expected_caller_reachable=[-8],
                expected_unreachable=["t0", "t1"],
                original_ids_unchanged=True,
            ),
            citation_probe=dict(
                offline_only=True,
                teaching_text_changed=False,
                new_candidate_created=False,
                old_material_rejects_new_id=True,
                evidence_material_accepts_new_id=True,
                model_calls=0,
            ),
        ),
    }
    return {name: canonical(value) + b"\n" for name, value in values.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    HERE.mkdir(exist_ok=True)
    for name, raw in outputs().items():
        if args.check:
            assert (HERE / name).read_bytes() == raw, name
        else:
            (HERE / name).write_bytes(raw)
    print(
        "PASS: original response/candidate replay; versioned facts and citation check; Provider0"
    )


if __name__ == "__main__":
    main()
