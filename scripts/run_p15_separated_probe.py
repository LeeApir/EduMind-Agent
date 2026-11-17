"""Exact ADR0048 package. No execution before its own approval, fee acceptance and window."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_separated_probe_contract as contract  # noqa: E402
from scripts.isolated_diagnostics import p15_separated_probe as probe  # noqa: E402
from scripts.isolated_diagnostics.p15_schema_probe_p02 import Refused, sha  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_wire import strict_json  # noqa: E402
from scripts.run_p15_union_schema_probe import credential, runtime_versions  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-separated-validation-r01"
OUTPUT = Path("/private/tmp/edumind-p15-separated-validation-r01")
PARENT = contract.DESIGN / "manifest.json"
PARENT_SHA = "abe3f498b662c526f6a85c569fbfbbb63f448af2b30689168cb050e03984ebea"


def required_files() -> set[str]:
    raw = PARENT.read_bytes()
    if sha(raw) != PARENT_SHA:
        raise Refused("ADR0048_PROPOSAL_DRIFT")
    parent = strict_json(raw)
    return {r["path"] for r in [*parent["files"], *parent["source_pins"]]} | {
        str(PARENT.relative_to(ROOT)),
        "docs/ADR/0048-approval-20261029.json",
        "scripts/isolated_diagnostics/p15_separated_probe_contract.py",
        "scripts/isolated_diagnostics/p15_separated_probe.py",
        "scripts/run_p15_separated_probe.py",
        "scripts/tests/test_p15_separated_probe.py",
        *{
            str((BASE / n).relative_to(ROOT))
            for n in (
                "README.md",
                "policy.json",
                "pricing.json",
                "requests.json",
                "mock-evidence.json",
                "check_preparation.py",
                *(n + ".json" for n in contract.ORDER),
            )
        },
    }


def policy() -> dict[str, Any]:
    return dict(
        version=contract.VERSION,
        scope="PHASE-1.5-T088",
        preparation_task="PHASE-1.5-T087",
        order=list(contract.ORDER),
        limits=contract.LIMITS,
        requests=contract.policy_requests(),
        wire_validation="same frozen phase/schema-echo/wire/local checks, no JSON repair",
        postconditions=dict(
            echo="strict local validity plus exact expected_output",
            repair="strict local validity plus exactly one changed paragraph; pending independent semantic review",
        ),
        terminal_after_R0="network_complete_pending_semantic_review",
        repair_success_always_false=True,
        semantic_decision_interface=False,
        exit_codes=dict(
            offline_check=0,
            network_complete_pending_semantic_review=3,
            stopped_or_refused=2,
        ),
        monetary_boundary=dict(
            mode="requires_new_explicit_unverified_fee_exception",
            actual_charge_hard_cap=None,
            actual_account_rates_verified=False,
            old_fee_exceptions_inherited=False,
        ),
        no_retry=True,
        no_redirect=True,
        no_fallback=True,
        no_restart=True,
        course_calls=False,
        full_role_admission=False,
    )


def load_package() -> tuple[str, dict[str, bytes]]:
    raw = (BASE / "manifest.json").read_bytes()
    m = strict_json(raw)
    if (
        m.get("version") != contract.VERSION
        or m.get("scope") != "PHASE-1.5-T088"
        or m.get("runtime") != runtime_versions()
    ):
        raise Refused("SEPARATED_PACKAGE_SCOPE_RUNTIME")
    required = required_files()
    if len(m["files"]) != len(required) or {r["path"] for r in m["files"]} != required:
        raise Refused("SEPARATED_SOURCE_CLOSURE")
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
            raise Refused("SEPARATED_PACKAGE_CHANGED")
    if strict_json((BASE / "policy.json").read_bytes()) != policy():
        raise Refused("SEPARATED_POLICY_CHANGED")
    bodies = {name: (BASE / (name + ".json")).read_bytes() for name in contract.ORDER}
    if bodies != contract.bodies():
        raise Refused("SEPARATED_APPROVED_INPUT_CHANGED")
    return sha(raw), bodies


def result_exit_code(result: dict[str, Any]) -> int:
    if (
        result.get("repair_success") is not False
        or result.get("diagnostic_success") is not False
    ):
        raise Refused("NO_AUTOMATIC_REPAIR_SUCCESS")
    if result.get("network_phase_complete") is True:
        if (
            result.get("repair_status") != "pending_independent_semantic_review"
            or result.get("independent_semantic_review_pending") is not True
        ):
            raise Refused("COMPLETION_REQUIRES_PENDING_SEMANTIC_STATE")
        return 3
    return 2


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
                        check_is_not_execution_authority=True,
                        R0_success_not_automatic=True,
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
            if OUTPUT.exists() or any(
                p.is_symlink() for p in (OUTPUT, *OUTPUT.parents)
            ):
                raise Refused("EXISTING_OR_SYMLINK_OUTPUT_NO_RESTART")
            key = credential()
            result = asyncio.run(
                probe.Runner(OUTPUT, package, grant, dict(generation=key)).run()
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return result_exit_code(result)
    except (ValueError, OSError, KeyError, TypeError):
        error = sys.exc_info()[1]
        print(
            str(error)
            if isinstance(error, Refused)
            else "SEPARATED_PACKAGE_OR_PROTOCOL_FAILURE"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
