"""Freeze the T118 citation-only request and entry using the sealed r02 source."""

import argparse
import json

from app.services import head_course_citation_revision as revision
from app.services.free_course_snapshots import canonical
from scripts.prepare_head_course_goal_package import paths as source_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = revision.PACKAGE
    data = revision.inputs()
    request = canonical(revision.body())
    if len(request) > 131072:
        raise ValueError("Request exceeds frozen byte limit")
    evidence_digest = data["teaching_evidence"]["evidence_digest"]
    files = {
        "request.json": request,
        "output.schema.json": canonical(revision.schema()),
        "scope.json": canonical(
            dict(
                batch=revision.BATCH,
                protocol_version=revision.VERSION,
                source_manifest_sha256=revision.SOURCE_MANIFEST,
                source_stop_sha256=revision.SOURCE_STOP,
                parent_digest=revision.PARENT,
                original_review_sha256=revision.REVIEW,
                plan_review_sha256=revision.PLAN_REVIEW,
                planning_basis_binding=data["parent_candidate"]["payload"][
                    "planning_basis"
                ]["binding"],
                evidence_digest=evidence_digest,
                allowed_leaf_path=["raw_output", *revision.PATH],
                prior_fact_ids=revision.BEFORE,
                required_fact_ids=revision.AFTER,
                requested_counts=dict(plan=0, generate=0, revision=1),
                timeout_seconds=90,
                window_seconds=600,
                input_reservation=139264,
                output_limit=4000,
                request_limit_bytes=131072,
                response_limit_bytes=2097152,
            )
        ),
        "approval.template.json": canonical(
            {
                "explicit_user_authorization": False,
                revision.APPROVAL_KEY: False,
                "manifest_sha256": None,
                "batch": revision.BATCH,
                "owner": None,
                "protocol_version": revision.VERSION,
                "parent_digest": revision.PARENT,
                "original_review_sha256": revision.REVIEW,
                "evidence_digest": evidence_digest,
                "max_http_requests": 1,
                "starts_epoch": None,
                "expires_epoch": None,
            }
        ),
    }

    def write_or_check(name, raw):
        path = here / name
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"Frozen file differs: {path}")
        else:
            path.write_bytes(raw)

    for name, raw in files.items():
        write_or_check(name, raw)
    root = revision.entry.ROOT
    paths = set(source_paths()) | {
        "scripts/head_course_fact_revision.py",
        "scripts/head_course_deepseek_wire.py",
        "scripts/prepare_head_course_citation_revision.py",
        "backend/tests/test_head_course_citation_revision.py",
        "docs/ADR/0058-t118-citation-revision-supplement.md",
        "docs/acceptance/phase-1.5-head-empty-t118-r02/manifest.json",
        "docs/ADR/0058-t118-r02-approval-20261110.json",
    }
    paths.update(str((here / name).relative_to(root)) for name in (*files, "README.md"))
    paths.difference_update({"task.json", "process.txt", "docs/PRD.md"})
    manifest = canonical(
        dict(
            batch=revision.BATCH,
            protocol_version=revision.VERSION,
            status="prepared_not_authorized",
            request_sha256=revision.sha(request),
            files={
                name: revision.sha((root / name).read_bytes()) for name in sorted(paths)
            },
        )
    )
    write_or_check("manifest.json", manifest)
    print(
        json.dumps(
            dict(
                files=len(paths),
                manifest_sha256=revision.sha(manifest),
                request_sha256=revision.sha(request),
                request_bytes=len(request),
                provider_calls=0,
            )
        )
    )


if __name__ == "__main__":
    main()
