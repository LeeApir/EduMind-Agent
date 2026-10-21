"""Offline lane probes and read-only summaries; deliberately no live run/init command."""

# ruff: noqa: E402
import argparse
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.separated_diagnostics import (
    fixed_review,
    generation_draft,
    review_summary,
    generator_assessment,
)
from acceptance_support.luna_high_candidate import offline_router
from acceptance_support.om_diagnostic import valid_review
from app.agents.shared_learning_plan import PlanInputs
from prepare_five_hour_materials import draft_for, contents
from prepare_defect_regression import BASE as REVIEW_BASE

BASE = ROOT / "docs/acceptance/phase-1-separated-diagnostics-r01"


def read(p):
    return json.loads(p.read_text())


def fixed_materials():
    labels = read(REVIEW_BASE / "labels.json")["labels"]
    return {
        n: (
            read(REVIEW_BASE / f"cases/{n}.json"),
            read(REVIEW_BASE / f"requests/{n}.json"),
            label,
        )
        for n, label in labels.items()
    }


async def capture_review(name):
    case, request, _ = fixed_materials()[name]
    router, generation, reviews, targets = offline_router(valid_review("unit"))
    output = await fixed_review(router, case)
    if generation or len(reviews) != 1 or reviews[0].hex() != request["wire_hex"]:
        raise ValueError("FIXED_REVIEW_ROUTE_CHANGED")
    return dict(
        lane="review",
        mock_requests=1,
        generation_calls=0,
        target=targets[0],
        provider_calls=0,
        semantic_result="not evaluated; Mock response discarded",
        material_sha256=output["material_sha256"],
    )


async def capture_generation(name):
    case = read(BASE / f"inputs/{name}.json")
    s = case["input_snapshot"]
    inputs = PlanInputs(
        s["metadata"],
        s["references"],
        frozenset(s["node_ids"]),
        s["learner_evidence"],
        case["reference_context"],
        teaching_context=s.get("teaching_context"),
    )
    values = [
        draft_for(inputs, "complete"),
        *[
            dict(resource_type=r, prompt_version="learning-resources-v1", content=c)
            for r, c in contents("complete").items()
        ],
    ]
    wires = []
    review_wires = []
    targets = []

    class Sequence:
        async def generate_structured(self, request, *, retry_safe=False):
            router, g, r, t = offline_router(values.pop(0))
            value = await router.generate_structured(request, retry_safe=retry_safe)
            wires.extend(g)
            review_wires.extend(r)
            targets.extend(t)
            return value

    with patch(
        "app.agents.planned_scene_generation.uuid4",
        side_effect=[
            uuid5(NAMESPACE_URL, "offline-gen:" + name + ":" + r)
            for r in ["explanation", "code", "exercise"]
        ],
    ):
        draft = await generation_draft(Sequence(), case, "offline-probe-r01")
    if values or review_wires or len(wires) != 4:
        raise ValueError("GENERATION_LANE_CHANGED")
    return dict(
        lane="generation",
        case_id=name,
        mock_requests=4,
        review_calls=0,
        provider_calls=0,
        limits=[json.loads(w)["max_output_tokens"] for w in wires],
        models=[json.loads(w)["model"] for w in wires],
        targets=targets,
        published=draft["published"],
        review_status=draft["review_status"],
        semantic_result="not evaluated; scripted adapter outputs are transport stubs, not goal-correct courses",
        wire_hex=[w.hex() for w in wires],
    )


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=[
            "review-capture",
            "generation-capture",
            "review-summary",
            "generation-assess",
        ],
    )
    p.add_argument("--case")
    p.add_argument("--records", type=Path)
    p.add_argument("--draft", type=Path)
    p.add_argument("--checks", type=Path)
    a = p.parse_args()
    if a.command == "review-capture":
        value = await capture_review(a.case)
    elif a.command == "generation-capture":
        value = await capture_generation(a.case)
    elif a.command == "review-summary":
        value = review_summary(read(a.records), fixed_materials())
    else:
        value = generator_assessment(read(a.draft), read(a.checks))
    # Captures may be large; stdout contains only test prompts/bodies, never keys/real reasoning.
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
