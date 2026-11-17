"""Freeze the exact B local revision. No Provider, vault, window or model candidate creation."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services import head_course_evidence_revision as f  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402
from scripts.prepare_head_course_goal_package import paths as original_paths  # noqa: E402

HERE = f.PACKAGE


def main():
    check = "--check" in sys.argv
    data = f.inputs()
    values = {
        "input.json": data,
        "request.json": f.body(),
        "output.schema.json": f.schema(data),
        "allowed-diff.json": dict(
            parent_digest=data["parent_candidate"]["candidate_digest"],
            evidence_digest=data["teaching_evidence"]["evidence_digest"],
            allowed_leaf_paths=[
                ["failure_scope"],
                ["paragraphs", 5, "text"],
                ["paragraphs", 5, "fact_ids"],
            ],
            allowed_payload_addition=["teaching_evidence"],
            unchanged=[
                "all other raw_output fields",
                "materials",
                "planning_basis",
                "plan",
                "goal",
                "source_binding",
            ],
            prefer_original_paragraph_text=True,
            assistant_teaching_edits=0,
        ),
        "approval.template.json": dict(
            explicit_user_authorization=False,
            accept_ADR0054_scope_and_batch_C2=False,
            protocol_version=f.VERSION,
            manifest_sha256="TO_BE_APPROVED",
            parent_digest=data["parent_candidate"]["candidate_digest"],
            evidence_digest=data["teaching_evidence"]["evidence_digest"],
            max_http_requests=1,
            starts_epoch=None,
            expires_epoch=None,
        ),
        "execution-config.json": dict(
            protocol_version=f.VERSION,
            batch=data["revision_scope"]["batch"],
            endpoint="https://api.deepseek.com/responses",
            model="deepseek-flash",
            reasoning="none",
            temperature=0.2,
            stream=False,
            store=False,
            max_output_tokens=4000,
            max_http_requests=1,
            planning_calls=0,
            full_generation_calls=0,
            local_input_reservation=139264,
            request_bytes=131072,
            response_bytes=2097152,
            io_timeout_seconds=90,
            window_seconds=600,
            retry=0,
            fallback=False,
            duplicate_recovery=False,
            real_calls_authorized=0,
            old_allowance_inherited=0,
            money_hard_cap=None,
            stop_after_one_request=True,
            send_entry="scripts/head_course_fact_revision.py --profile evidence --send",
            import_entry="scripts/head_course_fact_revision.py --profile evidence --publish --owner <actual>",
        ),
    }
    for name, value in values.items():
        raw = canonical(value)
        if check:
            assert (HERE / name).read_bytes() == raw, name
        else:
            (HERE / name).write_bytes(raw)
    paths = set(original_paths()) | {
        "backend/app/services/head_course_evidence_revision.py",
        "backend/app/services/head_course_evidence_publication.py",
        "backend/app/services/head_course_teaching_evidence.py",
        "scripts/head_course_fact_revision.py",
        "scripts/prepare_head_b_local_revision.py",
        "backend/tests/test_head_b_local_revision.py",
        "docs/ADR/0054-head-b-local-revision.md",
    }
    for base in (f.ORIGINAL, ROOT / "docs/acceptance/phase-1.5-head-evidence-t110"):
        paths.update(str(p.relative_to(ROOT)) for p in base.iterdir() if p.is_file())
    paths.update(
        str(p.relative_to(ROOT))
        for p in HERE.iterdir()
        if p.is_file() and p.name not in ("manifest.json", "PREPARATION-REVIEW.md")
    )
    paths.difference_update({"task.json", "process.txt", "docs/PRD.md"})
    manifest = canonical(
        dict(
            protocol_version=f.VERSION,
            parent_digest=data["parent_candidate"]["candidate_digest"],
            evidence_digest=data["teaching_evidence"]["evidence_digest"],
            max_http_requests=1,
            files={
                p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                for p in sorted(paths)
            },
        )
    )
    if check:
        assert (HERE / "manifest.json").read_bytes() == manifest
    else:
        (HERE / "manifest.json").write_bytes(manifest)
    request_size = len((HERE / "request.json").read_bytes())
    assert request_size <= 131072
    print(
        json.dumps(
            dict(
                status="prepared_not_authorized",
                provider_calls=0,
                request_bytes=request_size,
                manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                files=len(paths),
            )
        )
    )


if __name__ == "__main__":
    main()
