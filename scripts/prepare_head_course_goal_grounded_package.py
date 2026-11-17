"""Prepare T108 r03 grounded planning inputs; preserve every stopped package unchanged."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.agents import head_course_planning_wire as wire  # noqa: E402
from app.services.head_course_planning_basis import build_basis  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from scripts import prepare_head_course_goal_wire_package as previous  # noqa: E402

HERE = ROOT / "docs/acceptance/phase-1.5-head-goal-t108-r03"


def outputs():
    result = previous.outputs()  # Pure outputs only; no old package writer is called.
    basis = build_basis()
    result["planning-example-basis.json"] = canonical(basis) + b"\n"
    config = json.loads(result["candidate-config.json"])
    config.update(
        batch="head-goal-r03_proposed_not_authorized",
        planning_prompt_version=wire.PROMPT_VERSION,
        planning_basis_version=basis["version"],
        planning_basis_digest=basis["basis_digest"],
        approval_flag="accept_ADR0052_R03_and_batch_C2",
        real_calls_authorized=0,
    )
    result["candidate-config.json"] = canonical(config) + b"\n"
    protocols = json.loads(result["request-protocols.json"])
    protocols["plan"].update(
        prompt_version=wire.PROMPT_VERSION, program_basis_digest=basis["basis_digest"]
    )
    protocols["generate"]["input_binding"] = (
        "planning_basis.binding + selected evidence"
    )
    protocols["repair"]["input_binding"] = (
        "original_input.planning_basis + exact parent"
    )
    protocols["review"] = dict(
        required="planning_basis_binding exactly equals selected payload binding",
        fields=[
            "version",
            "basis_digest",
            "selected_example",
            "example_basis_digest",
            "materials_digest",
        ],
        semantic_authority="Independent review, no automatic semantic pass or planning rewrite",
    )
    result["request-protocols.json"] = canonical(protocols) + b"\n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    HERE.mkdir(exist_ok=True)
    for name, raw in outputs().items():
        if args.check:
            assert (HERE / name).read_bytes() == raw, name
        else:
            (HERE / name).write_bytes(raw)
    old_manifest = previous.HERE / "manifest.json"
    paths = set(json.loads(old_manifest.read_text())["files"])
    paths.update(
        [
            "backend/app/services/head_course_planning_basis.py",
            "backend/tests/test_head_course_planning_basis.py",
            "scripts/prepare_head_course_goal_grounded_package.py",
            "docs/ADR/0052-planning-basis-r03.md",
            "docs/acceptance/phase-1.5-head-goal-t108-r02/manifest.json",
            "docs/acceptance/phase-1.5-head-goal-t108-r02-review.md",
            "docs/acceptance/phase-1.5-head-goal-live-r02/delivery-manifest.json",
        ]
    )
    paths.update(
        str(p.relative_to(ROOT))
        for p in HERE.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    )
    raw = (
        canonical(
            dict(
                version="head-goal-course-v1",
                planning_wire_version=wire.VERSION,
                planning_prompt_version=wire.PROMPT_VERSION,
                status="proposed_not_authorized",
                previous_package_sha256=hashlib.sha256(
                    old_manifest.read_bytes()
                ).hexdigest(),
                files={
                    path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                    for path in sorted(paths)
                },
            )
        )
        + b"\n"
    )
    if args.check:
        assert (HERE / "manifest.json").read_bytes() == raw, "manifest.json"
    else:
        (HERE / "manifest.json").write_bytes(raw)
    print(
        json.dumps(
            dict(
                status="prepared_not_authorized",
                provider_calls=0,
                package_sha256=hashlib.sha256(raw).hexdigest(),
                files=len(paths),
            )
        )
    )


if __name__ == "__main__":
    main()
