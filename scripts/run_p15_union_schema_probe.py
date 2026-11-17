"""Exact two-request union compatibility package. --check is offline; --run requires new approval."""

import argparse
import asyncio
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_union_schema_probe as probe  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_wire import strict_json  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-schema-compatibility/union-probe-p01"
OUTPUT = Path("/private/tmp/edumind-p15-union-probe-p01")
CANDIDATE = ROOT / "docs/acceptance/phase-1.5-schema-compatibility/union-proposal-r01/manifest.json"
CANDIDATE_SHA = "58ce182ab773c3e0c0a145ea6408c3a867f087c26e8a6b64f1a8e7e3a7b8db7c"


def required_files() -> set[str]:
    raw = CANDIDATE.read_bytes()
    if probe.sha(raw) != CANDIDATE_SHA:
        raise probe.Refused("OFFLINE_PROPOSAL_DRIFT")
    return {row["path"] for row in strict_json(raw)["files"]} | {
        str(CANDIDATE.relative_to(ROOT)),
        "scripts/isolated_diagnostics/p15_union_schema_probe.py",
        "scripts/run_p15_union_schema_probe.py", "scripts/tests/test_p15_union_schema_probe.py",
        *{str((BASE / name).relative_to(ROOT)) for name in (
            "README.md", "policy.json", "pricing.json", "S1.json", "S2.json")},
    }


def runtime_versions() -> dict[str, Any]:
    return dict(python=sys.version.split()[0], libraries={
        name: version(name) for name in ("httpx", "jsonschema", "mistune", "python-dotenv")})


def load_package() -> tuple[str, dict[str, bytes]]:
    raw = (BASE / "manifest.json").read_bytes()
    manifest = strict_json(raw)
    if (manifest.get("version") != "schema-union-probe-p01-v1"
            or manifest.get("scope") != "PHASE-1.5-T081"
            or manifest.get("runtime") != runtime_versions()):
        raise probe.Refused("PACKAGE_SCOPE_CHANGED")
    rows = manifest["files"]
    if len(rows) != len(required_files()) or {r["path"] for r in rows} != required_files():
        raise probe.Refused("SOURCE_CLOSURE_CHANGED")
    for row in rows:
        relative = Path(row["path"])
        path = ROOT / relative
        if (relative.is_absolute() or ".." in relative.parts
                or any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file() or path.stat().st_size > 4000000
                or probe.sha(path.read_bytes()) != row["sha256"]):
            raise probe.Refused("FROZEN_PACKAGE_DRIFT")
    policy = strict_json((BASE / "policy.json").read_bytes())
    if policy != dict(scope="PHASE-1.5-T081", url=probe.URL, model="deepseek-flash",
                      credential_env=probe.KEY_NAME, limits=probe.LIMITS,
                      order=["S1", "S2_if_S1_valid"], production=False, course_calls=False,
                      envelope_policy=probe.ENVELOPE_POLICY):
        raise probe.Refused("POLICY_IMPLEMENTATION_MISMATCH")
    bodies = {name: (BASE / f"{name}.json").read_bytes() for name in ("S1", "S2")}
    if any(bodies[n] != probe.canonical(v) or len(bodies[n]) > 1024
           for n, v in probe.request_pair().items()):
        raise probe.Refused("PAIR_OR_SINGLE_VARIABLE_DRIFT")
    return probe.sha(raw), bodies


def credential() -> str:
    from dotenv import dotenv_values
    key = os.environ.get(probe.KEY_NAME)
    if key is None:
        key = dotenv_values(ROOT / ".env", interpolate=False).get(probe.KEY_NAME)
    if not isinstance(key, str) or len(key) < 16 or not key.isascii() or any(c.isspace() for c in key):
        raise probe.Refused("DEDICATED_KEY_REQUIRED")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--run", action="store_true")
    modes.add_argument("--check-results", action="store_true")
    args = parser.parse_args()
    try:
        package, bodies = load_package()
        if args.check:
            print(json.dumps(dict(package_sha256=package, request_bytes={n: len(r) for n, r in bodies.items()},
                                  model_requests=0, check_is_not_execution_authority=True)))
            return 0
        grant: dict[str, Any] = strict_json((BASE / "execution-approval.json").read_bytes())
        probe.check_grant(grant, package, now=time.time(), require_current=not args.check_results)
        if args.check_results:
            result = probe.verify_results(OUTPUT, package, grant, bodies, require_real=True)
        else:
            if OUTPUT.exists() or OUTPUT.is_symlink():
                raise probe.Refused("EXISTING_OUTPUT_NO_RESTART")
            key = credential()  # Only after exact approval, window, package and one-shot checks.
            result = asyncio.run(probe.Runner(OUTPUT, package, grant, bodies, key).run())
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["outcome"].startswith("minimal_union_") else 2
    except (ValueError, OSError, KeyError, TypeError):
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, probe.Refused) else "LOCAL_PACKAGE_OR_PROTOCOL_FAILURE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
