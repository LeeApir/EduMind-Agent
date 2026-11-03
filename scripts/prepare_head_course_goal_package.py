"""Freeze exact T108 instructions/materials/dependencies; examples are explicitly not real plans."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.agents.free_course_planning import SCHEMA as PLAN_SCHEMA, build_request  # noqa: E402
from app.services import head_course_materials as m  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from scripts.head_course_goal import planning_body  # noqa: E402

HERE = ROOT / "docs/acceptance/phase-1.5-head-goal-t108"


def outputs():
    ids = dict(
        course_id="<ACTUAL_COURSE_UUID>",
        operation_id="<ACTUAL_OPERATION_UUID>",
        request_id="<ACTUAL_REQUEST_UUID>",
    )
    inputs = dict(
        **ids,
        original_goal=m.GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={
            "request_1": dict(request_id=ids["request_id"], version=1, text=m.GOAL)
        },
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.SUPPORT,
    )
    result = {
        "planning-system.txt": build_request(inputs).prompt.messages[0].content.encode()
        + b"\n",
        "planning-schema.json": canonical(PLAN_SCHEMA) + b"\n",
        "planning-input.template.json": canonical(inputs) + b"\n",
        "planning-request.template.json": canonical(planning_body(inputs)) + b"\n",
        "teaching-system.txt": m.INSTRUCTION.encode() + b"\n",
        "repair-system.txt": m.REPAIR_INSTRUCTION.encode() + b"\n",
        "teaching-schema.json": canonical(m.SCHEMA) + b"\n",
        "candidate-config.json": canonical(
            dict(
                version=m.VERSION,
                status="proposed_not_authorized",
                goal=m.GOAL,
                example_specs=m.SPECS,
                origin=m.ORIGIN,
                endpoint="https://api.deepseek.com/responses",
                model="deepseek-flash",
                reasoning="none",
                temperature=0.2,
                max_output_tokens=8000,
                stream=False,
                store=False,
                http_limit=3,
                window_seconds=600,
                request_bytes=131072,
                response_bytes=2097152,
                local_input_reservation_per_request=139264,
                total_local_input_reservation=417792,
                total_requested_output=24000,
                request_io_timeout=90,
                repairs="at most one independently approved minor wording repair; no planning/protocol/fact/answer/safety repairs; stop on unknown",
                real_calls_authorized=0,
            )
        )
        + b"\n",
        "runtime.json": canonical(
            dict(
                python=platform.python_version(),
                interpreter_path=sys.executable,
                interpreter_sha256=hashlib.sha256(
                    Path(sys.executable).read_bytes()
                ).hexdigest(),
                packages={
                    n: importlib.metadata.version(n)
                    for n in (
                        "httpx",
                        "cryptography",
                        "jsonschema",
                        "sqlalchemy",
                        "fastapi",
                        "playwright",
                    )
                },
            )
        )
        + b"\n",
    }
    for key in m.SPECS:
        # Only a selection fixture, never passed off as actual planner output.
        result[key + ".materials.json"] = (
            canonical(
                dict(
                    status="offline_selected_materials_not_a_model_plan",
                    materials=m.materials(
                        dict(
                            shared_example=key,
                            scenes=[dict(forms=m.SUPPORT["required_forms"])],
                        )
                    ),
                )
            )
            + b"\n"
        )
    return result


def paths():
    # Reuse the imported old raw-collector's dependency inventory, not its stale authorization.
    old = json.loads(
        (
            ROOT / "docs/acceptance/phase-1.5-limited-c-preparation-t104/manifest.json"
        ).read_text()
    )
    result = set(old["files"])
    result.update(
        str(p.relative_to(ROOT))
        for base in (ROOT / "backend/app", ROOT / "web/src")
        for p in base.rglob("*")
        if p.is_file()
        and p.suffix in (".py", ".json", ".ts", ".vue", ".css")
        and "__pycache__" not in p.parts
    )
    result.update(
        [
            "backend/alembic/versions/0050_head_goal_generation.py",
            "backend/app/contracts/free_course.openapi.json",
            "backend/pyproject.toml",
            "backend/uv.lock",
            "backend/tests/test_head_course_goal.py",
            "web/tests/course-visualization.spec.ts",
            "web/package.json",
            "web/pnpm-lock.yaml",
            "web/vite.config.ts",
            "scripts/head_course_goal.py",
            "scripts/head_course_goal_fixture.py",
            "scripts/run_head_course_goal_dev.py",
            "scripts/check_head_course_goal_browser.py",
            "scripts/prepare_head_course_goal_package.py",
            "docs/ADR/0052-limited-head-goal-mainline.md",
            "docs/acceptance/phase-1.5-limited-c-preparation-t104/manifest.json",
            "docs/acceptance/phase-1.5-head-replay-t107/manifest.json",
            "docs/acceptance/phase-1.5-head-replay-t107/INDEPENDENT-EVALUATION.md",
        ]
    )
    result.update(
        str(p.relative_to(ROOT))
        for p in HERE.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    )
    return sorted(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    for name, raw in outputs().items():
        if a.check:
            assert (HERE / name).read_bytes() == raw, name
        else:
            (HERE / name).write_bytes(raw)
    frozen = dict(
        version=m.VERSION,
        status="proposed_not_authorized",
        files={
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in paths()
        },
    )
    raw = canonical(frozen) + b"\n"
    if a.check:
        assert (HERE / "manifest.json").read_bytes() == raw, "manifest.json"
    else:
        (HERE / "manifest.json").write_bytes(raw)
    print(
        json.dumps(
            dict(
                status="prepared_not_authorized",
                package_sha256=hashlib.sha256(raw).hexdigest(),
                files=len(frozen["files"]),
                provider_calls=0,
            )
        )
    )


if __name__ == "__main__":
    main()
