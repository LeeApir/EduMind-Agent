"""Frozen synthetic role admission plus one conditional course; explicit grant required."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_combined_candidate_contract as c  # noqa: E402
from scripts.isolated_diagnostics import p15_combined_candidate_runner as runner  # noqa: E402
from scripts.isolated_diagnostics import p15_minimal_probe_contract as roles  # noqa: E402
from scripts.isolated_diagnostics import p15_minimal_contract as minimal  # noqa: E402
from scripts.isolated_diagnostics import p15_bound_pilot as bound  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_wire import ROUTES, SUFFIX, strict_json  # noqa: E402
from scripts.isolated_diagnostics.p15_schema_probe_p02 import Refused, sha  # noqa: E402
from scripts.run_p15_role_schema_probe import credential  # noqa: E402
from scripts.run_p15_schema_probe_p02 import runtime_versions  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01"
OUTPUT = Path("/private/tmp/edumind-p15-combined-candidate-r01")
PARENT = ROOT / "docs/acceptance/phase-1.5-r0-once-r01/manifest.json"
PARENT_SHA = "78f02e8b065c95537bdd361249e34715d68f070587f177a7914306bbe2b3f4c0"


def policy() -> dict[str, Any]:
    return dict(
        version=c.VERSION,
        scope=c.SCOPE,
        limits=c.LIMITS,
        roles=[
            dict(
                slot=n,
                stage=roles.STAGES[n],
                role=roles.ROLES[n],
                url=ROUTES[roles.ROLES[n]]["url"],
                model=ROUTES[roles.ROLES[n]]["model"],
                reasoning=ROUTES[roles.ROLES[n]]["reasoning"],
                input_reservation=roles.CAPS[n][0],
                max_output_tokens=roles.CAPS[n][1],
            )
            for n in roles.ORDER
        ],
        course=dict(
            arm="C",
            spec=c.SPEC,
            stages=list(c.COURSE_ORDER),
            generation_url=ROUTES["generation"]["url"],
            generation_model=ROUTES["generation"]["model"],
            generation_reasoning=ROUTES["generation"]["reasoning"],
            review_url=ROUTES["review"]["url"],
            review_model=ROUTES["review"]["model"],
            review_reasoning=ROUTES["review"]["reasoning"],
            max_output_tokens=8000,
            input_reservation=8192,
        ),
        response_policy=dict(
            schema_echo_required=True,
            phase=["absent", "final_answer"],
            instruction_echo_missing="unknown",
            review_known_suffix=SUFFIX,
            provider_enforcement_verified=False,
        ),
        no_retry=True,
        no_redirect=True,
        no_fallback=True,
        no_restart=True,
        no_course_before_seven=True,
        teaching_evaluation="user_pending",
        production=False,
    )


def required_files() -> set[str]:
    raw = PARENT.read_bytes()
    if sha(raw) != PARENT_SHA:
        raise Refused("COMBINED_PARENT_MANIFEST_DRIFT")
    parent = strict_json(raw)
    return {row["path"] for row in parent["files"]} | {
        str(PARENT.relative_to(ROOT)),
        "scripts/isolated_diagnostics/p15_clean_pilot_prompts.py",
        "scripts/isolated_diagnostics/p15_bound_pilot.py",
        "scripts/isolated_diagnostics/p15_combined_candidate_contract.py",
        "scripts/isolated_diagnostics/p15_combined_candidate_runner.py",
        "scripts/run_p15_combined_candidate.py",
        "scripts/tests/test_p15_bound_pilot.py",
        "scripts/tests/test_p15_combined_candidate_contract.py",
        "scripts/tests/test_p15_combined_candidate_runner.py",
        "scripts/isolated_diagnostics/generate_p15_bound_sample.py",
        *{
            str((BASE / name).relative_to(ROOT))
            for name in (
                "README.md",
                "policy.json",
                "pricing.json",
                "verification.txt",
                "course-plan.json",
                *(f"S{i}.json" for i in range(1, 8)),
            )
        },
    }


def load_package() -> tuple[str, dict[str, bytes]]:
    raw = (BASE / "manifest.json").read_bytes()
    m = strict_json(raw)
    if (
        m.get("scope") != c.SCOPE
        or m.get("version") != c.VERSION
        or m.get("runtime") != runtime_versions()
    ):
        raise Refused("COMBINED_PACKAGE_SCOPE_RUNTIME")
    required = required_files()
    if (
        len(m["files"]) != len(required)
        or {row["path"] for row in m["files"]} != required
    ):
        raise Refused("COMBINED_SOURCE_CLOSURE")
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
            raise Refused("COMBINED_PACKAGE_CHANGED")
    if strict_json((BASE / "policy.json").read_bytes()) != policy():
        raise Refused("COMBINED_POLICY_CHANGED")
    bodies = {n: (BASE / (n + ".json")).read_bytes() for n in roles.ORDER}
    plan = c.course_wire(
        "C_plan", bound.plan_input(c.SPEC, minimal.make_catalog(c.SPEC))
    )
    if bodies != c.role_bodies() or (BASE / "course-plan.json").read_bytes() != plan:
        raise Refused("COMBINED_REQUEST_CHANGED")
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
                        role_bytes={n: len(b) for n, b in bodies.items()},
                        model_requests=0,
                        execution_authorized=False,
                    )
                )
            )
            return 0
        grant = strict_json((BASE / "execution-approval.json").read_bytes())
        runner.check_grant(
            grant, package, now=time.time(), current=not args.check_results
        )
        if args.check_results:
            result = runner.verify_results(OUTPUT, package, grant)
        else:
            if (
                OUTPUT.exists()
                or OUTPUT.is_symlink()
                or any(p.is_symlink() for p in OUTPUT.parents)
            ):
                raise Refused("COMBINED_EXISTING_OUTPUT_NO_RESTART")
            keys = credential()
            result = asyncio.run(runner.Runner(OUTPUT, package, grant, keys).run())
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 3 if result["outcome"] == "pending_user_review" else 2
    except (ValueError, OSError, KeyError, TypeError):
        error = sys.exc_info()[1]
        print(
            str(error)
            if isinstance(error, Refused)
            else "COMBINED_PACKAGE_OR_PROTOCOL_FAILURE"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
