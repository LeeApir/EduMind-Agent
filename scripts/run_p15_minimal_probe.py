"""Seven approved synthetic compatibility requests; pending fees fail before credentials."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_minimal_probe_contract as contract  # noqa: E402
from scripts.isolated_diagnostics import p15_minimal_probe as probe  # noqa: E402
from scripts.isolated_diagnostics.p15_schema_probe_p02 import Refused, sha  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_wire import strict_json, ROUTES  # noqa: E402
from scripts.run_p15_role_schema_probe import credential  # noqa: E402
from scripts.run_p15_schema_probe_p02 import runtime_versions  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-minimal-live-r01"
OUTPUT = Path("/private/tmp/edumind-p15-minimal-live-r01")
PARENT = ROOT / "docs/acceptance/phase-1.5-minimal-output-adapter-r01/manifest.json"
PARENT_SHA = "b959c3cc3cd5e52f367c4659821313544413036e4f65495d40019640bc638416"


def required_files() -> set[str]:
    raw = PARENT.read_bytes()
    if sha(raw) != PARENT_SHA:
        raise Refused("ADAPTER_FREEZE_DRIFT")
    parent = strict_json(raw)
    return {r["path"] for r in [*parent["files"], *parent["source_pins"]]} | {
        str(PARENT.relative_to(ROOT)),
        "scripts/isolated_diagnostics/p15_minimal_probe_contract.py",
        "scripts/isolated_diagnostics/p15_minimal_probe.py",
        "scripts/run_p15_minimal_probe.py",
        "scripts/tests/test_p15_minimal_probe.py",
        *{
            str((BASE / n).relative_to(ROOT))
            for n in (
                "README.md",
                "policy.json",
                "pricing.json",
                *(f"S{i}.json" for i in range(1, 8)),
            )
        },
    }


def policy() -> dict[str, Any]:
    return dict(
        version=contract.VERSION,
        scope="PHASE-1.5-T085",
        limits=contract.LIMITS,
        requests=[
            dict(
                name=n,
                stage=contract.STAGES[n],
                role=contract.ROLES[n],
                url=ROUTES[contract.ROLES[n]]["url"],
                model=ROUTES[contract.ROLES[n]]["model"],
                reasoning=ROUTES[contract.ROLES[n]]["reasoning"],
                input_reservation=contract.CAPS[n][0],
                max_output_tokens=contract.CAPS[n][1],
            )
            for n in contract.ORDER
        ],
        response_policy=dict(
            schema_echo_required=True,
            no_future_enforcement_claim=True,
            message_phase=["absent", "final_answer"],
            review_instruction_suffix="\n\nYou are a helpful coding assistant.",
            review_reasoning_summary_max_chars=4096,
            paired_uuid_metadata_only=True,
        ),
        course_calls=False,
        no_retry=True,
        no_redirect=True,
        no_fallback=True,
        no_restart=True,
    )


def load_package() -> tuple[str, dict[str, bytes]]:
    raw = (BASE / "manifest.json").read_bytes()
    m = strict_json(raw)
    if (
        m.get("scope") != "PHASE-1.5-T085"
        or m.get("version") != contract.VERSION
        or m.get("runtime") != runtime_versions()
    ):
        raise Refused("MINIMAL_PACKAGE_SCOPE_RUNTIME")
    required = required_files()
    if len(m["files"]) != len(required) or {r["path"] for r in m["files"]} != required:
        raise Refused("MINIMAL_SOURCE_CLOSURE")
    for row in m["files"]:
        rel = Path(row["path"])
        path = ROOT / rel
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or any(p.is_symlink() for p in (path, *path.parents))
            or not path.is_file()
            or path.stat().st_size > 4000000
            or sha(path.read_bytes()) != row["sha256"]
        ):
            raise Refused("MINIMAL_PACKAGE_CHANGED")
    if strict_json((BASE / "policy.json").read_bytes()) != policy():
        raise Refused("MINIMAL_POLICY_CHANGED")
    bodies = {n: (BASE / (n + ".json")).read_bytes() for n in contract.ORDER}
    if bodies != contract.bodies():
        raise Refused("MINIMAL_BODY_CHANGED")
    return sha(raw), bodies


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
            print(
                json.dumps(
                    dict(
                        package_sha256=package,
                        request_bytes={n: len(b) for n, b in bodies.items()},
                        model_requests=0,
                        approved_request_scope=7,
                    )
                )
            )
            return 0
        grant = strict_json((BASE / "execution-approval.json").read_bytes())
        probe.check_grant(
            grant, package, now=time.time(), current=not args.check_results
        )
        if args.check_results:
            result = probe.verify_results(OUTPUT, package, grant)
        else:
            if OUTPUT.exists() or OUTPUT.is_symlink():
                raise Refused("EXISTING_OUTPUT_NO_RESTART")
            if any(path.is_symlink() for path in (OUTPUT, *OUTPUT.parents)):
                raise Refused("MINIMAL_OUTPUT_SYMLINK")
            keys = credential()
            result = asyncio.run(probe.Runner(OUTPUT, package, grant, keys).run())
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["protocol_admission_complete"] else 2
    except (ValueError, OSError, KeyError, TypeError):
        error = sys.exc_info()[1]
        print(
            str(error)
            if isinstance(error, Refused)
            else "MINIMAL_PACKAGE_OR_PROTOCOL_FAILURE"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
