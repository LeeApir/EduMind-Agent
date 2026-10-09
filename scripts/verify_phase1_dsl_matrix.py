"""Offline trusted-case oracle and frozen denominators; never a media acceptance pass."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.animation_dsl_compiler import compile_animation_dsl  # noqa: E402

PLAN = ROOT / "docs/acceptance/phase-1-dsl-v1/matrix-protocol.json"


def main():
    plan = json.loads(PLAN.read_text())
    for path, digest in plan["code_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    assert len(plan["trusted_cases"]) == 20
    actions = set()
    rows = []
    for case in plan["trusted_cases"]:
        compiled = compile_animation_dsl(
            json.dumps(case["dsl"], ensure_ascii=False), knowledge_point_id="array"
        )
        frames = compiled.validated.frames
        final = frames[-1]
        expected = case["expected_final"]
        assert len(frames) == 11 and compiled.validated.duration_ms == 30800
        assert {node.id: node.value for node in final.nodes} == {
            "n0": expected["n0_value"],
            "n1": expected["n1_value"],
        }
        assert not final.edges and final.pointers[0].target is None
        assert [node.id for node in final.nodes if node.visited] == expected["visited"]
        assert final.complexity == (expected["time"], expected["space"])
        left, right = case["values"]
        comparison = "gt" if left > right else "lt" if left < right else "eq"
        assert frames[5].comparison.result == comparison
        assert len(compiled.subtitles.strip().split("\n\n")) == len(frames)
        actions.update(frame.op for frame in frames)
        rows.append(
            {
                "case_id": case["id"],
                "dsl_sha256": compiled.validated.dsl_sha256,
                "source_sha256": compiled.source_sha256,
                "trace_sha256": compiled.validated.trace_sha256,
                "subtitle_sha256": compiled.subtitles_sha256,
            }
        )
    assert actions == {
        "create_node",
        "connect",
        "disconnect",
        "move_pointer",
        "highlight",
        "compare",
        "swap",
        "visit",
        "show_complexity",
    }
    for group in ("dsl_slots", "template_slots", "cache_slots"):
        slots = plan[group]
        assert len(slots) == 100 and len({slot["id"] for slot in slots}) == 100
    assert sum(slot["cold"] for slot in plan["dsl_slots"]) == 20
    assert sum(slot["cold"] for slot in plan["template_slots"]) == 20
    assert Counter(slot["template_id"] for slot in plan["template_slots"]) == {
        "linked-list-insertion": 50,
        "linked-list-deletion": 50,
    }
    assert Counter(slot["source"] for slot in plan["cache_slots"]) == {
        "dsl": 50,
        "template": 50,
    }
    print(
        json.dumps(
            {
                "offline_plan_passed": True,
                "media_acceptance_passed": False,
                "human_review": "pending",
                "provider_requests": 0,
                "protocol_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
                "actions": sorted(actions),
                "trusted_cases": rows,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
