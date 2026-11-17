"""Freeze the limited head-new-B request builders; never call a Provider or invent a plan."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.agents import head_course_planning_wire as wire  # noqa: E402
from app.services import head_course_materials as m  # noqa: E402
from app.services import head_course_reuse as reuse  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from app.services.head_course_planning_basis import selected_basis  # noqa: E402
from scripts import prepare_head_course_goal_package as old  # noqa: E402
from scripts.head_course_goal import planning_body  # noqa: E402

HERE = ROOT / "docs/acceptance/phase-1.5-head-reuse-t109"


def outputs():
    ids = {
        k: "<ACTUAL_" + k.upper() + "_UUID>"
        for k in ("course_id", "operation_id", "request_id")
    }
    inputs = dict(
        **ids,
        original_goal=m.REUSE_GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={
            "request_1": dict(
                request_id=ids["request_id"], version=1, text=m.REUSE_GOAL
            )
        },
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.support_for_goal(m.REUSE_GOAL),
    )
    materials = m.materials_for_example("head-new-B")
    # Future model plan is intentionally absent. This is a request template, never a plan fixture.
    payload = dict(
        original_goal=m.REUSE_GOAL,
        source_binding=ids,
        prerequisite_evidence=dict(
            source="request_1",
            excerpt="我已了解 C 指针、struct、NULL 和函数返回值",
            self_reported=m.KNOWN,
            demonstrated_mastery=None,
        ),
        plan="<EXACT_APPROVED_REAL_MODEL_PLAN_FROM_THIS_BATCH>",
        materials=materials,
        planning_basis=selected_basis(materials),
        unknown_learner_fields="all others",
    )
    config = dict(
        version=reuse.VERSION,
        batch=reuse.BATCH,
        status="prepared_not_authorized",
        endpoint="https://api.deepseek.com/responses",
        model="deepseek-flash",
        protocol="Responses/text.format/json_schema/strict",
        planning_wire=wire.VERSION,
        planning_prompt=wire.PROMPT_VERSION,
        local_planning=wire.local.SCHEMA_VERSION,
        teaching_schema=m.VERSION,
        repair_protocol=reuse.REVISION_VERSION,
        max_http_requests=3,
        stages=["plan", "generate", "conditional_paragraph_repair"],
        output_limits=[8000, 8000, 4000],
        total_output_reservation=20000,
        local_input_reservation_per_request=139264,
        total_input_reservation=417792,
        window_seconds=600,
        request_bytes_limit=131072,
        response_bytes_limit=2097152,
        io_timeout_seconds=90,
        temperature=0.2,
        reasoning="none",
        stream=False,
        store=False,
        tools=[],
        retries=0,
        fallback=False,
        money_hard_cap=None,
        real_calls_authorized=0,
        old_allowance_inherited=0,
        assistant_teaching_edits_allowed=0,
        stop="planning/protocol/material/safety/unknown failures; full review failure after one scoped revision",
    )
    result = dict(
        **{
            "goal.txt": m.REUSE_GOAL.encode() + b"\n",
            "teaching-system.txt": m.INSTRUCTION.encode() + b"\n",
            "revision-system.txt": reuse.REVISION_INSTRUCTION.rstrip().encode() + b"\n",
        },
    )
    values = {
        "planning-input.template.json": inputs,
        "planning-request.template.json": planning_body(inputs),
        "planning-wire.schema.json": wire.SCHEMA,
        "planning-local.schema.json": wire.local.SCHEMA,
        "teaching.schema.json": m.SCHEMA,
        "teaching-request.template.json": m.body(payload),
        "head-new-B.materials.json": materials,
        "planning-basis.json": payload["planning_basis"],
        "candidate-config.json": config,
        "approval.template.json": dict(
            package_sha256="<MANIFEST_SHA256>",
            version=reuse.VERSION,
            explicit_user_authorization=False,
            accept_ADR0053_and_batch_C2=False,
            max_http_requests=3,
            planning_wire_version=wire.VERSION,
            planning_prompt_version=wire.PROMPT_VERSION,
            starts_epoch="<REGISTER_WHEN_TERMINAL_READY>",
            expires_epoch="<START_PLUS_600>",
        ),
        "revision-protocol.json": dict(
            version=reuse.REVISION_VERSION,
            builder="app.services.head_course_reuse.revision_body(exact_parent, exact_review)",
            schema="Closed object, only paragraph_<review index>:{text,fact_ids} and/or learning_summary:string",
            runtime_only=[
                "parent_candidate",
                "review",
                "revision_contract.targets",
                "revision_contract.responsibilities",
                "revision_contract.schema",
            ],
            semantic_check="All target duties, all claims/citations, no adjacent copy/omitted explanations; full lesson re-review",
            immutable=[
                "code",
                "facts",
                "trace",
                "answers",
                "step_notes",
                "questions",
                "prerequisites",
                "failure_scope",
                "lifecycle",
                "payload",
            ],
        ),
    }
    result.update({name: canonical(value) + b"\n" for name, value in values.items()})
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
    # Reuse the existing actual-entry dependency inventory; no new compilation/framework.
    paths = set(old.paths()) | {
        "backend/app/services/head_course_reuse.py",
        "backend/tests/test_head_course_reuse.py",
        "scripts/prepare_head_course_reuse.py",
        "docs/ADR/0053-limited-head-reuse.md",
        "docs/acceptance/phase-1.5-head-fact-live-r01/delivery-manifest.json",
    }
    paths.update(
        str(p.relative_to(ROOT))
        for p in HERE.iterdir()
        if p.is_file() and p.name not in ("manifest.json", "PREPARATION-REVIEW.md")
    )
    body = (
        canonical(
            dict(
                version=reuse.VERSION,
                status="prepared_not_authorized",
                files={
                    p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                    for p in sorted(paths)
                },
            )
        )
        + b"\n"
    )
    if args.check:
        assert (HERE / "manifest.json").read_bytes() == body, "manifest.json"
    else:
        (HERE / "manifest.json").write_bytes(body)
    print(
        json.dumps(
            dict(
                status="prepared_not_authorized",
                provider_calls=0,
                manifest_sha256=hashlib.sha256(body).hexdigest(),
                files=len(paths),
            )
        )
    )


if __name__ == "__main__":
    main()
