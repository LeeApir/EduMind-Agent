"""One paired regression of original relay faults; exact new approval is mandatory."""

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.p15_candidate_compatibility import Runner, evidence, parse  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Limits, Refused  # noqa: E402
from run_p15_candidate_compatibility import bounded_resolver  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-relay-regression-r01"
OUTPUT = Path("/tmp/edumind-p15-relay-regression-r01")
BATCH = "p15-relay-regression-r01"
PURPOSE = "one_pair_original_relay_fault_regression_fail_then_discard"
LIMITS = Limits(2, 4096, 16, 10000, 90)
CANDIDATE = dict(
    base_url="https://www.cbbb.fun/v1",
    model="gpt-6-luna",
    response_model_ids=["gpt-6-luna"],
    configured_base_url="https://www.cbbb.fun",
    credential_source="project_dotenv_EDUMIND_PROVIDER_API_KEY",
    reasoning_effort="none",
    service_tier="default",
)


def load_package(base=BASE, root=ROOT):
    raw = (base / "manifest.json").read_bytes()
    manifest = parse(raw)
    if (
        manifest.get("batch_id") != BATCH
        or manifest.get("purpose") != PURPOSE
        or manifest.get("limits") != asdict(LIMITS)
        or manifest.get("candidate") != CANDIDATE
        or len(manifest.get("cases", [])) != 1
    ):
        raise Refused("RELAY_PACKAGE_SCOPE_CHANGED")
    for name, sha in manifest["sha256"].items():
        path = root / name
        if (
            not path.resolve().is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise Refused("FROZEN_PACKAGE_CHANGED")
    case = manifest["cases"][0]
    path = base / case["body"]
    if (
        not path.resolve().is_relative_to(base.resolve())
        or case["id"] != "S1"
        or case["body_sha256"]
        != "cc45e19ba242760b756bca579ee80e45c6dd93e35c351ed6128a8bef7e459422"
        or hashlib.sha256(path.read_bytes()).hexdigest() != case["body_sha256"]
        or case["output_max"] != 16
        or case["expected"] != {"result": "OK"}
    ):
        raise Refused("ORIGINAL_SYNTHETIC_CASE_CHANGED")
    return manifest, hashlib.sha256(raw).hexdigest()


def gate(base=BASE, root=ROOT):
    manifest, package = load_package(base, root)
    grants = []
    for kind in ("contract", "execution"):
        path = base / (kind + "-approval.json")
        if not path.is_file():
            raise Refused("EXACT_NEW_RELAY_APPROVAL_REQUIRED")
        grant = parse(path.read_bytes())
        if (
            grant.get("kind") != kind
            or grant.get("scope") != "PHASE-1.5-T038"
            or grant.get("purpose") != PURPOSE
            or grant.get("batch_id") != BATCH
            or grant.get("package_sha256") != package
            or grant.get("limits") != asdict(LIMITS)
            or grant.get("fee_cap_waiver") is not False
            or not all(
                isinstance(grant.get(k), str) and grant[k].strip()
                for k in ("human_message", "reviewer", "received_at", "evidence_ref")
            )
        ):
            raise Refused("EXACT_NEW_RELAY_APPROVAL_REQUIRED")
        grants.append(grant)
    if grants[0].get("decisions") != ["A", "B", "C"]:
        raise Refused("ADR0031_ACCURATE_APPROVAL_REQUIRED")
    if any(
        grants[1].get(k) is not True
        for k in (
            "unknown_vendor_currency_and_rates_accepted",
            "unverified_upstream_bounds_risk_accepted",
            "local_usd_allowance_is_not_invoice_cap_accepted",
            "fail_then_discard_no_retry",
            "root_to_v1_mapping_accepted",
            "no_course_admission",
        )
    ):
        raise Refused("UNKNOWN_RELAY_RISK_APPROVAL_REQUIRED")
    return manifest, package, grants


def credential_after_approval(root=ROOT):
    # Read only the selected project .env after gate; never evaluate shell syntax.
    wanted = {
        "EDUMIND_PROVIDER_BASE_URL",
        "EDUMIND_PROVIDER_MODEL",
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
        "EDUMIND_PROVIDER_API_KEY",
    }
    values = {}
    for line in (root / ".env").read_text().splitlines():
        name, sep, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if not sep or name not in wanted:
            continue
        if name in values:
            raise Refused("AMBIGUOUS_DOTENV_CONFIG")
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise Refused("INVALID_DOTENV_QUOTING")
            value = value[1:-1]
        values[name] = value
    if (
        values.get("EDUMIND_PROVIDER_BASE_URL") != CANDIDATE["configured_base_url"]
        or values.get("EDUMIND_PROVIDER_MODEL") != CANDIDATE["model"]
        or values.get("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT")
        != "responses_json_schema"
    ):
        raise Refused("FROZEN_DOTENV_IDENTITY_CHANGED")
    key = values.get("EDUMIND_PROVIDER_API_KEY", "")
    if len(key) < 16 or not key.isascii() or any(c.isspace() for c in key):
        raise Refused("CURRENT_RELAY_CREDENTIAL_REQUIRED")
    return key


async def run(
    base, output, manifest, package, grants, key, target_factory, transport_factory
):
    runner = Runner(
        base, output, manifest, package, grants[1], LIMITS, key, contract=grants[0]
    )
    summary = await runner.execute(target_factory, transport_factory)
    clean = summary["status"] == "minimal_compatibility_observed_pass"
    assessment = dict(
        outcome="original_fault_not_observed_one_case_only"
        if clean
        else "candidate_rejected_stop_using",
        safe_failure_code=summary["safe_failure_code"],
        http_dispatch_markers=summary["http_dispatch_markers"],
        model_dispatch_markers=summary["model_dispatch_markers"],
        package_sha256=package,
        actual_vendor_currency=None,
        actual_vendor_rates=None,
        actual_invoice=None,
        local_fee_units_are_unvalidated_planning_allowance=True,
        upstream_token_and_invoice_hard_bounds_verified=False,
        complete_compatibility_matrix_passed=False,
        course_diagnostic_preparation_unlocked=False,
        course_generation_authorized=False,
        T038_completed=False,
        further_calls_authorized=False,
        automatically_retry=False,
    )
    evidence(output / "assessment.json", assessment)
    return assessment


def execute(base=BASE, root=ROOT, output=OUTPUT):
    manifest, package, grants = gate(base, root)
    if output.exists():
        raise Refused("ALREADY_STARTED_NO_RESTART")
    key = credential_after_approval(root)
    from app.core.provider_target import ProviderTargetGuard, TargetPolicy

    return asyncio.run(
        run(
            base,
            output,
            manifest,
            package,
            grants,
            key,
            lambda: ProviderTargetGuard(
                CANDIDATE["base_url"], TargetPolicy(), resolver=bounded_resolver
            ).approve_base(),
            lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.check:
        _, sha = load_package()
        print("RELAY_PACKAGE_VERIFIED_NO_CALLS " + sha)
    else:
        result = execute()
        print(json.dumps({"outcome": result["outcome"]}))
        if result["outcome"] != "original_fault_not_observed_one_case_only":
            raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "REFUSED_OR_STOPPED; no retry; inspect protected evidence"
        ) from None
