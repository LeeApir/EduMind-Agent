"""Exact three-role protocol admission. All course generation remains outside this entry."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_role_schema_contract as contract  # noqa: E402
from scripts.isolated_diagnostics import p15_role_schema_probe as probe  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_wire import ROUTES, strict_json  # noqa: E402
from scripts.isolated_diagnostics.p15_schema_probe_p02 import Refused, sha  # noqa: E402
from scripts.run_p15_schema_probe_p02 import runtime_versions  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-schema-compatibility/role-probe-r01"
OUTPUT = Path("/private/tmp/edumind-p15-role-schema-probe-r01")
PARENT = ROOT / "docs/acceptance/phase-1.5-schema-compatibility/probe-p02/manifest.json"
PARENT_SHA = "c40aa91a6bbbb6f0c21c7c61d8f66459800826c674ce5080327bf89759718cf4"


def policy() -> dict[str, Any]:
    return dict(scope="PHASE-1.5-T078", version=contract.VERSION, limits=contract.LIMITS,
                requests=[dict(name=n, stage=contract.STAGES[n], role=contract.ROLES[n],
                    url=ROUTES[contract.ROLES[n]]["url"], model=ROUTES[contract.ROLES[n]]["model"],
                    reasoning=ROUTES[contract.ROLES[n]]["reasoning"],
                    input_reservation=contract.CAPS[n][0], max_output_tokens=contract.CAPS[n][1])
                    for n in contract.ORDER], production=False, course_calls=False)


def schemas() -> dict[str, Any]:
    inventory = contract.schema_manifest()
    return {n: {**inventory[n], "original_schema": s,
                "wire_schema": contract.explicit_literal_types(s)[0]}
            for n, s in contract.original_schemas().items()}


def required_files() -> set[str]:
    raw = PARENT.read_bytes()
    if sha(raw) != PARENT_SHA:
        raise Refused("PARENT_PROBE_FREEZE_DRIFT")
    return {r["path"] for r in strict_json(raw)["files"]} | {
        str(PARENT.relative_to(ROOT)), "scripts/isolated_diagnostics/p15_schema_audit.py",
        "scripts/isolated_diagnostics/p15_role_schema_contract.py",
        "scripts/isolated_diagnostics/p15_role_schema_probe.py",
        "scripts/run_p15_role_schema_probe.py", "scripts/tests/test_p15_role_schema_contract.py",
        "scripts/tests/test_p15_role_schema_probe.py",
        "docs/ADR/0045-role-schema-protocol-admission.md",
        *{str((BASE / n).relative_to(ROOT)) for n in (
            "README.md", "policy.json", "pricing.json", "schemas.json", "S1.json", "S2.json", "S3.json")},
    }


def load_package() -> tuple[str, dict[str, bytes]]:
    raw = (BASE / "manifest.json").read_bytes()
    m = strict_json(raw)
    if (m.get("version") != contract.VERSION or m.get("scope") != "PHASE-1.5-T078"
            or m.get("runtime") != runtime_versions()):
        raise Refused("ROLE_PACKAGE_SCOPE_OR_RUNTIME")
    required = required_files()
    if len(m["files"]) != len(required) or {r["path"] for r in m["files"]} != required:
        raise Refused("ROLE_SOURCE_CLOSURE_CHANGED")
    for row in m["files"]:
        rel = Path(row["path"])
        path = ROOT / rel
        if (rel.is_absolute() or ".." in rel.parts or any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file() or path.stat().st_size > 4000000
                or sha(path.read_bytes()) != row["sha256"]):
            raise Refused("ROLE_FROZEN_PACKAGE_DRIFT")
    if (strict_json((BASE / "policy.json").read_bytes()) != policy()
            or strict_json((BASE / "schemas.json").read_bytes()) != schemas()):
        raise Refused("ROLE_POLICY_OR_SCHEMA_BINDING")
    bodies = {n: (BASE / f"{n}.json").read_bytes() for n in contract.ORDER}
    if bodies != contract.bodies():
        raise Refused("ROLE_REQUEST_BYTES_CHANGED")
    return sha(raw), bodies


def credential() -> dict[str, str]:
    from dotenv import dotenv_values
    values = dotenv_values(ROOT / ".env", interpolate=False)
    def value(name: str) -> str | None:
        return os.environ[name] if name in os.environ else values.get(name)
    generation = value("EDUMIND_DEEPSEEK_COMPAT_API_KEY")
    review = value("EDUMIND_AIAPI_REVIEW_API_KEY")
    if not review and value("EDUMIND_PROVIDER_BASE_URL") in (
        "https://aiapi.world/v1", "https://aiapi.world/v1/",
    ):
        review = value("EDUMIND_PROVIDER_API_KEY")
    result = {}
    for role, key in (("generation", generation), ("review", review)):
        if not isinstance(key, str) or len(key) < 16 or not key.isascii() or any(c.isspace() for c in key):
            raise Refused("ROLE_EXACT_CREDENTIALS_REQUIRED")
        result[role] = key
    return result


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
            print(json.dumps(dict(package_sha256=package, model_requests=0,
                request_bytes={n: len(r) for n, r in bodies.items()},
                type_additions={n: len(row["added_type_pointers"])
                                for n, row in contract.schema_manifest().items()},
                course_requests_authorized=False)))
            return 0
        grant = strict_json((BASE / "execution-approval.json").read_bytes())
        probe.check_grant(grant, package, now=time.time(), current=not args.check_results)
        if args.check_results:
            result = probe.verify_results(OUTPUT, package, grant)
        else:
            if OUTPUT.exists() or OUTPUT.is_symlink():
                raise Refused("ROLE_EXISTING_OUTPUT_NO_RESTART")
            keys = credential()
            result = asyncio.run(probe.Runner(OUTPUT, package, grant, keys).run())
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["outcome"] == "roles_protocol_admitted" else 2
    except (ValueError, OSError, KeyError, TypeError):
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, Refused) else "ROLE_LOCAL_PACKAGE_OR_PROTOCOL_FAILURE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
