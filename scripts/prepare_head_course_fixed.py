"""Build the exact T111 preparation package without a Provider or an approval."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.agents import head_course_planning_wire as wire  # noqa: E402
from app.services import head_course_materials as m, head_course_reuse as reuse  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from scripts import head_course_goal as entry  # noqa: E402
from scripts import head_course_goal_fixture as fixture  # noqa: E402
from scripts import prepare_head_course_goal_package as base  # noqa: E402


def outputs():
    ids = {
        key: "<ACTUAL_" + key.upper() + "_UUID>"
        for key in (
            "course_id",
            "operation_id",
            "request_id",
        )
    }
    inputs = dict(
        **ids,
        original_goal=m.FIXED_GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={
            "request_1": dict(
                request_id=ids["request_id"], version=1, text=m.FIXED_GOAL
            )
        },
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.support_for_goal(m.FIXED_GOAL),
    )
    # Use the builder to derive owned materials. The fixture plan is replaced before export.
    payload = m.content_payload(inputs, fixture.plan(m.FIXED_EXAMPLE)["plan"])
    payload["plan"] = "<EXACT_APPROVED_REAL_MODEL_PLAN_FROM_THIS_BATCH>"
    plan, teaching = entry.planning_body(inputs), m.body(payload)
    values = {
        "planning-input.template.json": inputs,
        "planning-request.template.json": plan,
        "planning-local.schema.json": wire.local.SCHEMA,
        "teaching-request.template.json": teaching,
        "independent-reference.json": dict(
            initial=[5],
            insertions=[-2, 9],
            allocation_success=[True, True],
            receive_return=dict(caller_head="t1", reachable=[9, -2, 5], unreachable=[]),
            discard_return=dict(
                caller_head="i0", reachable=[5], unreachable=["t0", "t1"]
            ),
            displayed_lines=[None, 4, 5, 6, 7, 8, 15, 4, 5, 6, 7, 8, 16],
        ),
        "candidate-config.json": dict(
            status="prepared_not_authorized",
            version=m.FIXED_VERSION,
            batch=reuse.FIXED_BATCH,
            endpoint="https://api.deepseek.com/responses",
            model=teaching["model"],
            reasoning=teaching["reasoning"],
            temperature=teaching["temperature"],
            stream=False,
            store=False,
            protocol="Responses/text.format/json_schema/strict",
            phase_adapter=entry.raw_io.PHASE_ADAPTER_VERSION,
            planning_wire=wire.VERSION,
            planning_prompt=wire.PROMPT_VERSION,
            evidence_version=payload["teaching_evidence"]["version"],
            evidence_digest=payload["teaching_evidence"]["evidence_digest"],
            revision_protocol=reuse.FIXED_REVISION_VERSION,
            max_http_requests=3,
            stages=["plan", "generate", "conditional_repair"],
            window_seconds=600,
            output_limits=[8000, 8000, 4000],
            total_output_reservation=20000,
            input_reservation_per_request=139264,
            total_input_reservation=417792,
            request_bytes_limit=131072,
            response_bytes_limit=2097152,
            io_timeout_seconds=90,
            tools=[],
            retries=0,
            fallback=False,
            money_hard_cap=None,
            real_calls_authorized=0,
            old_allowance_inherited=0,
            assistant_teaching_edits_allowed=0,
        ),
        "approval.template.json": dict(
            package_sha256="<APPROVED_MANIFEST_SHA256>",
            version=m.FIXED_VERSION,
            batch=reuse.FIXED_BATCH,
            context_sha256="<ACTUAL_CONTEXT_FILE_SHA256>",
            explicit_user_authorization=False,
            accept_ADR0055_and_batch_C2=False,
            max_http_requests=3,
            starts_epoch="<REGISTER_AT_START>",
            expires_epoch="<START_PLUS_600>",
            planning_wire_version=wire.VERSION,
            planning_prompt_version=wire.PROMPT_VERSION,
        ),
        "revision-schema.template.json": dict(
            version=reuse.FIXED_REVISION_VERSION,
            authority="revision_contract(exact_parent, exact_independent_repair_review)",
            # A schema with all three allowed shapes, not the actual reviewed targets.
            illustrative_schema=m.closed(
                {
                    "paragraph_<reviewed_index>": m.SCHEMA["properties"]["paragraphs"][
                        "items"
                    ],
                    "learning_summary": m.TEXT,
                    "failure_scope": m.TEXT,
                }
            ),
        ),
    }
    return {
        "goal.txt": m.FIXED_GOAL.encode() + b"\n",
        "revision-system.txt": reuse.FIXED_REVISION_INSTRUCTION.rstrip().encode()
        + b"\n",
        **{name: canonical(value) + b"\n" for name, value in values.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = entry.FIXED_PACKAGE
    generated = outputs()
    for name, raw in generated.items():
        if args.check:
            assert (here / name).read_bytes() == raw, name
        else:
            (here / name).write_bytes(raw)
    paths = set(base.paths()) | {
        "scripts/prepare_head_course_fixed.py",
        "scripts/run_catalog_db_tests.py",
        "backend/tests/test_head_course_fixed.py",
        "backend/tests/test_head_course_reuse.py",
        "docs/ADR/0055-fixed-head-course-validation.md",
    }
    paths.update(
        str((here / name).relative_to(ROOT))
        for name in (
            *generated,
            "README.md",
            "review-policy.md",
        )
    )
    manifest = (
        canonical(
            dict(
                version=m.FIXED_VERSION,
                batch=reuse.FIXED_BATCH,
                status="prepared_not_authorized",
                files={
                    path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                    for path in sorted(paths)
                },
            )
        )
        + b"\n"
    )
    if args.check:
        assert (here / "manifest.json").read_bytes() == manifest
    else:
        (here / "manifest.json").write_bytes(manifest)
    print(
        json.dumps(
            dict(
                files=len(paths), manifest_sha256=reuse.sha(manifest), provider_calls=0
            )
        )
    )


if __name__ == "__main__":
    main()
