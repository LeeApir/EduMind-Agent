"""Frozen official-candidate synthetic probe. --check never reads credentials or calls DNS."""

import argparse
import asyncio
import hashlib
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.p15_candidate_compatibility import Runner, parse  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Limits, Refused  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-candidate-compatibility-r01"
OUTPUT = Path("/tmp/edumind-p15-candidate-compat-r01")
BATCH = "p15-candidate-compat-r01"
PURPOSE = "official_candidate_two_synthetic_cases_no_course_admission"
LIMITS = Limits(4, 8192, 144, 20000, 90)
CANDIDATE = dict(
    base_url="https://api.openai.com/v1",
    model="gpt-6-luna",
    response_model_ids=["gpt-6-luna"],
    reasoning_effort="none",
    service_tier="default",
    credential_env="EDUMIND_COMPAT_API_KEY",
)


def load_package(base=BASE, root=ROOT):
    raw = (base / "manifest.json").read_bytes()
    manifest = parse(raw)
    if (
        manifest.get("batch_id") != BATCH
        or manifest.get("purpose") != PURPOSE
        or manifest.get("limits") != asdict(LIMITS)
        or manifest.get("candidate") != CANDIDATE
    ):
        raise Refused("PACKAGE_SCOPE_CHANGED")
    pins = manifest["sha256"]
    if not isinstance(pins, dict) or not pins:
        raise Refused("PACKAGE_PINS_REQUIRED")
    for name, sha in pins.items():
        path = root / name
        if (
            not path.resolve().is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise Refused("FROZEN_PACKAGE_CHANGED")
    if [c["id"] for c in manifest["cases"]] != ["S1", "S2"]:
        raise Refused("CASE_ORDER_CHANGED")
    for case, cap in zip(manifest["cases"], (16, 128)):
        path = base / case["body"]
        if not path.resolve().is_relative_to(base.resolve()):
            raise Refused("CASE_PATH_CHANGED")
        body_raw = path.read_bytes()
        body = parse(body_raw)
        if (
            case["output_max"] != cap
            or case["body_sha256"] != hashlib.sha256(body_raw).hexdigest()
            or body["model"] != CANDIDATE["model"]
            or body["max_output_tokens"] != cap
            or body.get("reasoning") != {"effort": "none"}
            or body.get("service_tier") != "default"
            or body.get("stream") is not False
            or body.get("store") is not False
            or set(body)
            - {
                "model",
                "input",
                "instructions",
                "reasoning",
                "service_tier",
                "max_output_tokens",
                "stream",
                "store",
                "text",
            }
        ):
            raise Refused("CASE_CONFIG_CHANGED")
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(body["text"]["format"]["schema"])
        Draft202012Validator(body["text"]["format"]["schema"]).validate(
            case["expected"]
        )
    return manifest, hashlib.sha256(raw).hexdigest()


def gate(base=BASE, root=ROOT, *, now=None):
    manifest, package = load_package(base, root)
    rates = parse((base / "pricing.json").read_bytes())
    stamp = now or datetime.now(timezone.utc)
    if not (
        datetime.fromisoformat(rates["checked_at"]) <= stamp
        and stamp + timedelta(seconds=90) <= datetime.fromisoformat(rates["expires_at"])
    ):
        raise Refused("PRICING_EXPIRED_OR_CLOCK_CHANGED")
    grants = []
    for kind in ("contract", "execution"):
        path = base / (kind + "-approval.json")
        if not path.is_file():
            raise Refused("EXACT_APPROVALS_REQUIRED")
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
            raise Refused("EXACT_APPROVALS_REQUIRED")
        grants.append(grant)
    if grants[0].get("decisions") != ["A", "B", "C"]:
        raise Refused("ADR0030_APPROVAL_REQUIRED")
    if any(
        grants[1].get(k) is not True
        for k in (
            "count_fee_allowance_and_invoice_uncertainty_accepted",
            "no_course_admission",
            "alias_mapping_must_match_exactly",
            "one_shot_no_restart",
        )
    ):
        raise Refused("ACCURATE_FINITE_EXECUTION_APPROVAL_REQUIRED")
    return manifest, package, grants


def bounded_resolver(host, port):
    # getaddrinfo cannot be cancelled in a thread. Bound a separate DNS-only process.
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import socket,json,sys; print(json.dumps(sorted({a[4][0] for a in "
            "socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),type=socket.SOCK_STREAM)})))",
            host,
            str(port),
        ],
        env={},
        capture_output=True,
        check=True,
        timeout=5,
    )
    if len(result.stdout) > 16384:
        raise Refused("DNS_RESULT_TOO_LARGE")
    addresses = parse(result.stdout)
    if (
        not isinstance(addresses, list)
        or not addresses
        or not all(isinstance(a, str) for a in addresses)
    ):
        raise Refused("DNS_RESULT_INVALID")
    return addresses


def execute(base=BASE, root=ROOT, output=OUTPUT):
    # No key/DNS/transport/output before the exact current package and two human grants.
    manifest, package, grants = gate(base, root)
    if output.exists():
        raise Refused("ALREADY_STARTED_NO_RESTART")
    key = os.environ.get(CANDIDATE["credential_env"], "")
    if len(key) < 16 or any(ch.isspace() for ch in key) or not key.isascii():
        raise Refused("DEDICATED_OFFICIAL_CREDENTIAL_REQUIRED")
    from app.core.provider_target import ProviderTargetGuard, TargetPolicy
    import httpx

    runner = Runner(
        base, output, manifest, package, grants[1], LIMITS, key, contract=grants[0]
    )
    return asyncio.run(
        runner.execute(
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
        _, package = load_package()
        print("PACKAGE_VERIFIED_NO_CALLS " + package)
    else:
        result = execute()
        print(result["status"])
        if result["status"] != "minimal_compatibility_observed_pass":
            raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "REFUSED_OR_STOPPED; inspect protected local evidence; no restart"
        ) from None
