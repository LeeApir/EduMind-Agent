"""Prepare/check exact one-request packet; never contacts Provider or opens a vault."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services import head_course_fact_revision as f  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402

HERE = ROOT / "docs/acceptance/phase-1.5-head-fact-revision-r01"


def main():
    check = "--check" in sys.argv
    outputs = {
        "request.json": canonical(f.body()),
        "output.schema.json": canonical(f.SCHEMA),
        "input.json": canonical(f.inputs()),
        "approval.template.json": canonical(
            dict(
                explicit_user_authorization=False,
                accept_fact_revision_and_batch_C2=False,
                manifest_sha256="TO_BE_APPROVED",
                parent_digest=f.PARENT,
                max_http_requests=1,
                starts_epoch=None,
                expires_epoch=None,
            )
        ),
    }
    for name, b in outputs.items():
        if check:
            assert (HERE / name).read_bytes() == b, name
        else:
            (HERE / name).write_bytes(b)
    paths = set(
        json.loads(
            (
                ROOT / "docs/acceptance/phase-1.5-head-goal-t108-r03/manifest.json"
            ).read_text()
        )["files"]
    )
    paths.update(
        json.loads(
            (
                ROOT
                / "docs/acceptance/phase-1.5-head-goal-r03-recovery/delivery-manifest.json"
            ).read_text()
        )["files"]
    )
    paths.update(
        str(p.relative_to(ROOT))
        for p in HERE.iterdir()
        if p.is_file() and p.name != "manifest.json"
    )
    paths.update(
        [
            "backend/app/services/head_course_fact_revision.py",
            "backend/tests/test_head_course_fact_revision.py",
            "scripts/head_course_fact_revision.py",
            "scripts/prepare_head_course_fact_revision.py",
            "docs/ADR/0052-four-field-fact-revision.md",
        ]
    )
    # Governance and future approval records remain mutable; execution inputs/sources are frozen.
    paths.difference_update(["task.json", "process.txt", "docs/PRD.md"])
    paths = {p for p in paths if (ROOT / p).is_file()}
    manifest = canonical(
        dict(
            protocol_version=f.VERSION,
            parent_digest=f.PARENT,
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
    assert len(outputs["request.json"]) <= 131072
    print(
        json.dumps(
            dict(
                status="prepared_not_authorized",
                provider_calls=0,
                request_bytes=len(outputs["request.json"]),
                manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                files=len(paths),
            )
        )
    )


if __name__ == "__main__":
    main()
