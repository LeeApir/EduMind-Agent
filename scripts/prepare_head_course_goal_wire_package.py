"""Freeze T108 r02 boundary changes without rewriting the stopped r01 preparation/package."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.agents import head_course_planning_wire as wire  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from scripts import prepare_head_course_goal_package as previous  # noqa: E402

HERE = ROOT / "docs/acceptance/phase-1.5-head-goal-t108-r02"


def outputs():
    result = (
        previous.outputs()
    )  # Pure bytes only; never call old writer or change old package.
    result["planning-local-schema.json"] = result["planning-schema.json"]
    result["planning-schema.json"] = canonical(wire.SCHEMA) + b"\n"
    inputs = json.loads(result["planning-input.template.json"])
    result["planning-system.txt"] = (
        wire.build_request(inputs).prompt.messages[0].content.encode() + b"\n"
    )
    # previous.outputs calls the actual entry's current planning_body, not a copied example.
    config = json.loads(result["candidate-config.json"])
    config.update(
        batch="head-goal-r02_proposed_not_authorized",
        planning_wire_version=wire.VERSION,
        local_planning_schema_version=wire.local.SCHEMA_VERSION,
        approval_flag="accept_ADR0052_R02_and_batch_C2",
        prior_allowance_inherited=0,
        on_simplified_planning_rejection="stop_and_ask_user_provider_route_decision_no_patch",
    )
    result["candidate-config.json"] = canonical(config) + b"\n"
    result["request-protocols.json"] = (
        canonical(
            dict(
                plan=dict(
                    builder="scripts.head_course_goal.planning_body",
                    wire_version=wire.VERSION,
                    schema_sha256=hashlib.sha256(canonical(wire.SCHEMA)).hexdigest(),
                    local_schema=wire.local.SCHEMA_VERSION,
                    conversion="app.agents.head_course_planning_wire.mapping_record",
                ),
                generate=dict(
                    builder="app.services.head_course_materials.body(payload)",
                    schema="head-goal-course-v1",
                    format="Responses text.format json_schema",
                ),
                repair=dict(
                    builder="app.services.head_course_materials.body(payload,parent,issues)",
                    schema="head-goal-course-v1",
                    format="Responses text.format json_schema",
                ),
                dynamic_inputs="Actual app identity, actual model plan and exact parent do not exist yet; save actual requests before sends.",
            )
        )
        + b"\n"
    )
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
    old = json.loads((previous.HERE / "manifest.json").read_text())
    paths = set(old["files"])
    paths.update(
        [
            "backend/app/agents/head_course_planning_wire.py",
            "backend/app/agents/head_course_planning_wire.schema.json",
            "backend/tests/test_head_course_planning_wire.py",
            "scripts/prepare_head_course_goal_wire_package.py",
            "docs/ADR/0052-planning-wire-r02.md",
            "docs/acceptance/phase-1.5-head-goal-t108/manifest.json",
            "docs/acceptance/phase-1.5-head-goal-live-r01/delivery-manifest.json",
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
                status="proposed_not_authorized",
                previous_package_sha256=hashlib.sha256(
                    (previous.HERE / "manifest.json").read_bytes()
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
