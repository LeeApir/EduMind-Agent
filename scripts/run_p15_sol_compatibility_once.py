"""One new synthetic sol compatibility request; never resumes a course batch."""

# ruff: noqa: E402
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from dotenv import dotenv_values
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import _wire_target
from acceptance_support.p15_candidate_compatibility import evidence, redact_check
from isolated_diagnostics import p15_sol_compatibility_proposal as proposal
from run_p15_candidate_compatibility import bounded_resolver

BASE = ROOT / "docs/acceptance/phase-1.5-sol-compatibility-once-p01"
OUTPUT = Path("/tmp/edumind-p15-sol-compatibility-once-p01")
DEADLINE = 1793078481.255075
URL = "https://aiapi.world/v1/responses"


def gate(now=None):
    raw = (BASE / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    required = {
        "scripts/run_p15_sol_compatibility_once.py",
        "scripts/isolated_diagnostics/p15_sol_compatibility_proposal.py",
        "scripts/tests/test_p15_sol_compatibility_once.py",
        str((BASE / "request.json").relative_to(ROOT)),
        str((BASE / "expected.json").relative_to(ROOT)),
    }
    if (
        manifest.get("requests") != 1
        or manifest.get("deadline_epoch") != DEADLINE
        or not required <= manifest.get("sha256", {}).keys()
    ):
        raise ValueError("ACCURATE_SINGLE_REQUEST_PACKAGE_REQUIRED")
    for name, sha in manifest["sha256"].items():
        path = (ROOT / name).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("FROZEN_PACKAGE_CHANGED")
    package = hashlib.sha256(raw).hexdigest()
    auth = json.loads((BASE / "execution-authorization.json").read_bytes())
    if (
        auth.get("package_sha256") != package
        or auth.get("human_message") != "执行"
        or auth.get("authorization_basis")
        != "latest_direct_instruction_for_presented_one_request_proposal"
        or auth.get("new_package_independently_human_reviewed") is not False
        or auth.get("requests") != 1
        or auth.get("deadline_epoch") != DEADLINE
        or not auth.get("evidence_ref")
    ):
        raise ValueError("EXPLICIT_SINGLE_REQUEST_AUTHORITY_REQUIRED")
    if (time.time() if now is None else now) + 120 > DEADLINE:
        raise ValueError("ORIGINAL_WORKFLOW_DEADLINE_INSUFFICIENT")
    body = json.loads((BASE / "request.json").read_bytes())
    if (
        body["model"] != "gpt-6.1-sol"
        or body["reasoning"] != {"effort": "low"}
        or body["max_output_tokens"] != 1536
        or body["store"] is not False
        or body["stream"] is not False
        or body["text"]["format"]["schema"] != proposal.schema()
        or body["text"]["format"]["strict"] is not True
    ):
        raise ValueError("REQUEST_CONFIGURATION_CHANGED")
    return package, body, json.loads((BASE / "expected.json").read_bytes())


def credential():
    env = dotenv_values(ROOT / ".env", interpolate=False)

    def get(name):
        return os.getenv(name) or env.get(name)

    value = get("EDUMIND_AIAPI_REVIEW_API_KEY")
    if not value and get("EDUMIND_PROVIDER_BASE_URL") == "https://aiapi.world/v1":
        value = get("EDUMIND_PROVIDER_API_KEY")
    if (
        not isinstance(value, str)
        or len(value) < 16
        or not value.isascii()
        or any(c.isspace() for c in value)
    ):
        raise ValueError("AIAPI_CREDENTIAL_REQUIRED")
    return value


def target():
    return ProviderTargetGuard(
        "https://aiapi.world/v1", TargetPolicy(), resolver=bounded_resolver
    ).approve_base()


def evaluate(body, response, expected):
    payload = json.loads(body["input"][-1]["content"])
    outcome = proposal.validate_envelope(body, response, payload)
    opinion = outcome["opinion"]
    issues = opinion["issues"]
    wrong = expected["incorrect_pointer"]
    hit = any(
        i["source_pointer"] == wrong
        and expected["incorrect_quote"] in i["evidence_quote"]
        for i in issues
    )
    false_flags = any(
        i["source_pointer"] == expected["correct_pointer"] for i in issues
    )
    return {
        **outcome,
        "synthetic_error_detected": hit,
        "correct_control_flagged": false_flags,
        "synthetic_only_pass": hit
        and not false_flags
        and opinion["verdict"] in ("revise", "reject"),
        "independent_quality_acceptance": False,
        "T038_completed": False,
    }


async def run_once(
    package,
    body,
    expected,
    key,
    *,
    output=OUTPUT,
    target_factory=target,
    transport_factory=lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False),
):
    raw = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    redact_check(raw, key)
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    evidence(
        output / "reservation.json",
        {
            "package_sha256": package,
            "requests": 1,
            "prior_workflow_requests": 6,
            "deadline_epoch": DEADLINE,
            "input_bound": None,
            "output_bound": None,
            "actual_fee_usd": None,
        },
    )
    started = time.monotonic()
    sent = False
    reported = None
    reason = None
    outcome = None
    try:
        async with asyncio.timeout(min(119, max(0, DEADLINE - time.time()))):
            approved = await asyncio.to_thread(target_factory)
            if (
                approved.url != "https://aiapi.world/v1"
                or approved.hostname != "aiapi.world"
                or approved.port != 443
            ):
                raise ValueError("APPROVED_TARGET_CHANGED")
            url, host = _wire_target(approved)
            evidence(output / "request.json", raw)
            async with httpx.AsyncClient(
                transport=transport_factory(),
                trust_env=False,
                follow_redirects=False,
                timeout=110,
            ) as client:
                request = client.build_request(
                    "POST",
                    url,
                    headers={
                        "Host": host,
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + key,
                    },
                    content=raw,
                )
                request.extensions["sni_hostname"] = approved.hostname
                evidence(
                    output / "dispatch.json",
                    {
                        "url": URL,
                        "request_sha256": hashlib.sha256(raw).hexdigest(),
                        "attempt": 1,
                        "no_retry": True,
                    },
                )
                sent = True
                response = await client.send(
                    request, stream=True, follow_redirects=False
                )
                try:
                    evidence(
                        output / "status.json", {"http_status": response.status_code}
                    )
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 2097152:
                            raise ValueError("RESPONSE_TOO_LARGE")
                finally:
                    await response.aclose()
            result = bytes(data)
            redact_check(result, key)
            evidence(output / "response.json", result)
            parsed = json.loads(result)
            usage = parsed.get("usage") if isinstance(parsed, dict) else None
            if isinstance(usage, dict):
                reported = {
                    k: usage.get(k)
                    for k in ("input_tokens", "output_tokens", "total_tokens")
                }
            if response.status_code != 200:
                raise ValueError("HTTP_NOT_200")
            outcome = evaluate(body, parsed, expected)
            if not outcome["synthetic_only_pass"]:
                raise ValueError("SYNTHETIC_EXPECTATION_FAILED")
    except BaseException as exc:
        reason = (
            str(exc)
            if isinstance(exc, ValueError)
            and str(exc)
            in {
                "APPROVED_TARGET_CHANGED",
                "RESPONSE_TOO_LARGE",
                "HTTP_NOT_200",
                "SYNTHETIC_EXPECTATION_FAILED",
                "UNRECOGNIZED_INSTRUCTION_ECHO",
                "REASONING_CONFIGURATION_CHANGED",
                "USAGE_INVALID",
                "REASONING_USAGE_INVALID",
                "UNREQUESTED_OUTPUT_TYPE",
                "NONEMPTY_OR_UNKNOWN_REASONING_ITEM",
                "OPINION_SCHEMA_INVALID",
                "QUOTE_NOT_IN_SOURCE",
                "EVIDENCE_SCOPE_INVALID",
                "CREDENTIAL_ECHO",
                "SNAPSHOT_BINDING_MISMATCH",
                "RESPONSE_CONTRACT_FAILED",
                "ONE_FINAL_JSON_REQUIRED",
            }
            else "TRANSPORT_TIMEOUT_OR_CONTRACT_FAILURE"
        )
    summary = {
        "package_sha256": package,
        "state": "one_synthetic_observation_only" if reason is None else "stopped",
        "safe_failure_code": reason,
        "dispatch_markers": int(sent),
        "actual_fee_usd": None,
        "workflow_requests_including_prior": 6 + int(sent),
        "reported_usage": reported,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "outcome": outcome,
        "course_calls": 0,
        "T038_completed": False,
        "automatic_restart": False,
    }
    evidence(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        package, body, expected = gate()
        if not args.execute:
            print(json.dumps({"verified_package": package, "real_calls_this_check": 0}))
            return 0
        if OUTPUT.exists():
            raise ValueError("SINGLE_EXECUTION_OUTPUT_ALREADY_EXISTS")
        value = asyncio.run(run_once(package, body, expected, credential()))
        print(json.dumps(value, ensure_ascii=False))
        return 0 if value["state"] == "one_synthetic_observation_only" else 2
    except (ValueError, FileExistsError):
        print("PREFLIGHT_OR_SINGLE_EXECUTION_GUARD_REFUSED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
