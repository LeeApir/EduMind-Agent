"""Build or verify the fixed DeepSeek execution package without a Provider."""

import argparse
import json

from scripts import head_course_deepseek_wire as direct
from scripts import head_course_goal as entry
from scripts import prepare_head_course_fixed as fixed

canonical, sha = entry.canonical, fixed.reuse.sha


def outputs():
    files = fixed.outputs()
    config = json.loads(files["candidate-config.json"])
    config.update(
        batch=direct.BATCH,
        endpoint=direct.ENDPOINT,
        response_contract=direct.VERSION,
        development_database=direct.DATABASE,
        window_seconds=direct.WINDOW_SECONDS,
        minimum_send_window_seconds=direct.IO_TIMEOUT,
        authorization_status="pending_exact_approval",
    )
    approval = json.loads(files["approval.template.json"])
    for key in ("starts_epoch", "expires_epoch", "accept_ADR0055_and_batch_C2"):
        del approval[key]
    approval.update(
        batch=direct.BATCH,
        accept_ADR0058_and_batch_C2=False,
        execution_window={
            "starts_at": "<ACTUAL_OPERATION_CREATED_AT>",
            "expires_at": "<ACTUAL_OPERATION_DEADLINE_AT>",
        },
    )
    files.update(
        {
            "candidate-config.json": canonical(config) + b"\n",
            "approval.template.json": canonical(approval) + b"\n",
        }
    )
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = entry.DIRECT_PACKAGE
    generated = outputs()
    for name, data in generated.items():
        path = here / name
        if args.check:
            if path.read_bytes() != data:
                raise SystemExit(f"Generated file differs: {path}")
        else:
            path.write_bytes(data)
    paths = set(fixed.base.paths()) | {
        "docs/ADR/0058-head-fixed-deepseek-direct.md",
        "docs/acceptance/phase-1.5-head-fixed-t111/review-policy.md",
        "docs/acceptance/phase-1.5-fixed-provider-t113/observations.json",
        "scripts/prepare_head_course_fixed.py",
        "scripts/prepare_head_course_deepseek.py",
        "scripts/head_course_deepseek_wire.py",
        "scripts/run_catalog_db_tests.py",
        "backend/tests/test_head_course_deepseek_wire.py",
        "backend/tests/test_head_course_fixed.py",
        "backend/tests/test_head_course_reuse.py",
    }
    paths.update(
        str((here / name).relative_to(entry.ROOT))
        for name in (*generated, "README.md", "CHECKS.md")
    )
    manifest = (
        canonical(
            dict(
                version=direct.VERSION,
                batch=direct.BATCH,
                status="prepared_not_authorized",
                files={
                    path: sha((entry.ROOT / path).read_bytes())
                    for path in sorted(paths)
                },
            )
        )
        + b"\n"
    )
    path = here / "manifest.json"
    if args.check:
        if path.read_bytes() != manifest:
            raise SystemExit("Frozen manifest differs")
    else:
        path.write_bytes(manifest)
    print(
        json.dumps(
            dict(files=len(paths), manifest_sha256=sha(manifest), provider_calls=0)
        )
    )


if __name__ == "__main__":
    main()
