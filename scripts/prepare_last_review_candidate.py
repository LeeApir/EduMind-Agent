"""Prepare the only remaining candidate with unchanged materials/Prompt/Schema, zero calls."""

# ruff: noqa: E402
import argparse
import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_high_candidate import CONFIG, offline_router
from acceptance_support.om_diagnostic import valid_review
from acceptance_support.qwen_review_budget import sha, canonical
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow
from prepare_luna_admission import candidates
import prepare_luna_admission as generation_capture

BASE = "docs/acceptance/phase-1-review-last-candidate-r01"
CAL = "docs/acceptance/phase-1-luna-process-calibration-r01"
LOW = "docs/acceptance/phase-1-luna-process-execution-r01"
OLD = "docs/acceptance/phase-1-luna-v49-admission-r02"
SLOTS = (
    "compat-schema",
    "cal-01",
    "cal-02",
    "cal-03",
    "cal-04",
    "screen-fact",
    "screen-safety",
    "screen-mixed",
    "holdout-stack-complete",
    "holdout-stack-fact",
    "holdout-stack-safety",
    "holdout-prerequisite",
)


def read(path):
    return json.loads(path.read_bytes())


async def build(root=ROOT):
    cal = read(root / CAL / "cases.json")
    old = read(root / OLD / "cases.json")
    originals = {
        **read(root / LOW / "requests.json"),
        **read(root / OLD / "requests.json"),
    }
    old_labels = {
        v["id"]: v for v in read(root / OLD / "proposed-labels.json")["labels"]
    }
    cal_labels = {
        v["id"]: v for v in read(root / CAL / "proposed-labels.json")["labels"]
    }
    cases, requests, labels = {}, {}, {}
    for slot in SLOTS:
        source = "cal-01" if slot == "compat-schema" else slot
        case = deepcopy((cal if source.startswith("cal-") else old)[source])
        cases[slot] = case
        source_label = deepcopy(
            (cal_labels if source.startswith("cal-") else old_labels)[source]
        )
        expected = source_label.get(
            "proposed_verdict", source_label.get("expected_local_verdict")
        )
        labels[slot] = dict(
            source_package=CAL if source.startswith("cal-") else OLD,
            source_id=source,
            source_label=source_label,
            expected=expected,
            source_material_sha256=sha(canonical(case)),
            actual_result=None,
        )
        router, gen, wires, targets = offline_router(valid_review("unit"))
        material = case["material"]
        record = await review_once(
            router,
            CallWindow(),
            binding=material["binding"],
            target_digest=material["unit_digest"],
            payload={
                "unit": material,
                "reference_context": material["reference_context"],
            },
            candidates=candidates(case),
            scope="unit",
            input_snapshot=case["input_snapshot"],
        )
        assert not gen and len(wires) == 1
        actual = wires[0]
        after = json.loads(actual)
        before = json.loads(bytes.fromhex(originals[source]["wire_hex"]))
        # Legacy r02 wires predate the already successful Schema projection.
        # Normalize ONLY that known transport projection before comparison.
        from acceptance_support.luna_schema_projection import projection

        before["text"]["format"]["schema"], _ = (
            projection(before["text"]["format"]["schema"])
            if source not in cal
            else (before["text"]["format"]["schema"], {})
        )
        before["reasoning"] = {"effort": "high"}
        assert before == after and record["request_digest"] == sha(actual)
        requests[slot] = dict(
            wire_hex=actual.hex(),
            wire_sha256=sha(actual),
            wire_bytes=len(actual),
            target=targets[0],
            anchor_catalog=record["anchor_catalog"],
            only_effective_request_change="reasoning.effort:low->high; r02 requests first use already successful unchanged schema projection",
            scripted_reply_not_quality=True,
        )
    # Prove the four generation roles retain DeepSeek/none with this exact router.
    with patch.object(generation_capture, "offline_router", offline_router):
        generation = await generation_capture.capture_generation(cal["cal-01"])
    plan = dict(
        candidate_id="luna-high-v49-final-01",
        candidate_count_max=1,
        configuration=asdict(CONFIG),
        slots=list(SLOTS),
        requests_max=12,
        stage_counts={
            "full_schema_compatibility": 1,
            "four_calibration_cases": 4,
            "fact_safety_mixed": 3,
            "preexisting_unused_materials": 4,
        },
        compatibility="full actual review request, complete original business Schema validation; no tiny schema probe. Repeat cal01 in calibration costs another request and is not independent replication evidence",
        expected={s: labels[s]["expected"] for s in SLOTS},
        immutable_inputs="all source cases/labels/Prompt/policy/Schema projection; no exit explanation relocated",
        output_tokens_per_call_max=8192,
        output_tokens_total_max=98304,
        per_call_timeout_seconds=60,
        model_wait_total_seconds_max=720,
        transport_cleanup_seconds_max=5,
        wall_seconds_including_human_wait=86400,
        monetary_cap=None,
        monetary_policy="uncapped_by_explicit_user_instruction",
        input_tokens="unknown until provider reports; fixed exact finite wires, not byte-to-token estimates",
        retries=0,
        corrections=0,
        fallback=False,
        new_candidates_after_failure=0,
        requests_authorized=0,
        generation_calls_authorized=0,
        stop_on="any technical, criterion, unsupported assertion/evidence claim, invented requirement, false positive or severe miss; no waiver/relabel/continuation of unused slots",
        research_exit="candidate fails once or deadline/budget exhausted: stop this batch automatic-review R&D; preserve failures and unsent; discuss delivery scope. No another model,effort,Prompt,material or budget expansion within batch",
        after_all_pass="only T040 admission review;freeze formal independent full set separately;98/95/90 thresholds and human-not-in-auto-numerator remain",
        truth_sources="unchanged cal four confirmation and r02 actual human confirmation; no model results presigned",
        holdout_limit="four old r02 holdout cases did not participate in recent cal repair; visible to preparer,not statistically blind,not formal independent set",
        real_high_provider_support="unverified third-party channel; actual outbound high can be audited,provider internal effective effort unknown without trustworthy metadata",
        execution="zero-call proposal/capture only; new durable 12-slot executable authority must be implemented and frozen before real request approval",
    )
    return {
        "cases.json": cases,
        "labels.json": labels,
        "requests.json": requests,
        "generation-capture.json": generation,
        "plan.json": plan,
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    for name, value in asyncio.run(build()).items():
        path = ROOT / BASE / name
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_text() != raw:
                raise ValueError("REFUSE_REWRITE")
            path.write_text(raw)
        else:
            assert path.read_text() == raw, name
    print(
        json.dumps(
            dict(
                candidate_count=1,
                requests_proposed=12,
                real_calls=0,
                live_authorization=0,
            )
        )
    )


if __name__ == "__main__":
    main()
