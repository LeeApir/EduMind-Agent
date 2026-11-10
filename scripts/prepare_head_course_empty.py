"""Freeze and check the exact T118 entry and request templates; no network."""

import argparse
import hashlib
import json

from app.agents import head_course_planning_wire as wire
from app.services import head_course_materials as m
from scripts import head_course_deepseek_wire as direct
from scripts import head_course_goal as entry
from scripts import prepare_head_course_goal_package as base

HERE = entry.EMPTY_PACKAGE


def inputs():
    ids = {
        key: f"<ACTUAL_{key.upper()}_UUID>"
        for key in ("course_id", "operation_id", "request_id")
    }
    return dict(
        **ids,
        original_goal=m.EMPTY_GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={
            "request_1": dict(
                request_id=ids["request_id"], version=1, text=m.EMPTY_GOAL
            )
        },
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.support_for_goal(m.EMPTY_GOAL),
    )


def outputs(*, batch=direct.EMPTY_BATCH, database=direct.EMPTY_DATABASE):
    # Only the example and forms are needed to derive materials. No model plan exists yet.
    payload = m.content_payload(
        inputs(),
        dict(
            shared_example=m.EMPTY_EXAMPLE,
            scenes=[dict(forms=m.SUPPORT["required_forms"])],
        ),
    )
    payload["plan"] = "<EXACT_APPROVED_REAL_MODEL_PLAN_FROM_THIS_BATCH>"
    plan, teaching = entry.planning_body(inputs()), m.body(payload)
    data = {
        "planning-request.template.json": plan,
        "teaching-request.template.json": teaching,
        "planning-local.schema.json": wire.local.SCHEMA,
        "candidate-config.json": dict(
            batch=batch,
            endpoint=direct.ENDPOINT,
            response_contract=direct.VERSION,
            development_database=database,
            planning_wire=wire.VERSION,
            planning_prompt=wire.PROMPT_VERSION,
            model=teaching["model"],
            store=teaching["store"],
            stream=teaching["stream"],
            temperature=teaching["temperature"],
            reasoning=teaching["reasoning"],
            materials_digest=payload["materials"]["materials_digest"],
            planning_basis_digest=payload["planning_basis"]["binding"]["basis_digest"],
            teaching_evidence_digest=payload["teaching_evidence"]["evidence_digest"],
            stages=["plan", "generate"],
            max_http_requests=2,
            retries=0,
            revisions=0,
            duplicate_recovery=False,
            fallback=False,
            window_seconds=direct.WINDOW_SECONDS,
            io_timeout_seconds=direct.IO_TIMEOUT,
            request_bytes_limit=131072,
            response_bytes_limit=2097152,
            input_reservation_per_request=139264,
            total_input_reservation=278528,
            output_limits=[8000, 8000],
            total_output_reservation=16000,
            money_hard_cap=None,
            real_calls_authorized=0,
        ),
        "approval.template.json": dict(
            package_sha256="<APPROVED_MANIFEST_SHA256>",
            version=m.FIXED_VERSION,
            batch=batch,
            context_sha256="<ACTUAL_CONTEXT_FILE_SHA256>",
            explicit_user_authorization=False,
            accept_T118_and_batch_C2=False,
            max_http_requests=2,
            execution_window=dict(
                starts_at="<ACTUAL_OPERATION_CREATED_AT>",
                expires_at="<ACTUAL_OPERATION_DEADLINE_AT>",
            ),
            planning_wire_version=wire.VERSION,
            planning_prompt_version=wire.PROMPT_VERSION,
        ),
    }
    return {"goal.txt": m.EMPTY_GOAL.encode() + b"\n"} | {
        name: entry.canonical(value) + b"\n" for name, value in data.items()
    }


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--r02", action="store_true")
    args = parser.parse_args()
    here = entry.EMPTY_R02_PACKAGE if args.r02 else HERE
    batch = direct.EMPTY_R02_BATCH if args.r02 else direct.EMPTY_BATCH
    database = direct.EMPTY_R02_DATABASE if args.r02 else direct.EMPTY_DATABASE
    generated = outputs(batch=batch, database=database)

    def write_or_check(path, raw):
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"T118 frozen file differs: {path}")
        else:
            path.write_bytes(raw)

    for name, raw in generated.items():
        write_or_check(here / name, raw)
    paths = set(base.paths()) | {
        "scripts/head_course_deepseek_wire.py",
        "scripts/prepare_head_course_empty.py",
        "scripts/run_catalog_db_tests.py",
        "backend/tests/test_head_course_empty.py",
        "docs/ADR/0058-head-fixed-deepseek-direct.md",
        "docs/ADR/0058-t118-empty-head-supplement.md",
    }
    paths.update(
        str((here / name).relative_to(entry.ROOT))
        for name in (*generated, "README.md", "independent-reference.json")
    )
    if args.r02:
        paths.add(str((HERE / "manifest.json").relative_to(entry.ROOT)))
    manifest = (
        entry.canonical(
            dict(
                version=direct.VERSION,
                batch=batch,
                status="prepared_not_authorized",
                files={
                    path: sha((entry.ROOT / path).read_bytes())
                    for path in sorted(paths)
                },
            )
        )
        + b"\n"
    )
    write_or_check(here / "manifest.json", manifest)
    print(
        json.dumps(
            dict(files=len(paths), manifest_sha256=sha(manifest), provider_calls=0)
        )
    )


if __name__ == "__main__":
    main()
