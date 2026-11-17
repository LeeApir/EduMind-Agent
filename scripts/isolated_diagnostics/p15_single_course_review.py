"""One exact, user-requested review of the stopped T095 synthetic course."""

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from dotenv import dotenv_values

from scripts.isolated_diagnostics import p15_combined_candidate_contract as contract
from scripts.isolated_diagnostics import p15_combined_candidate_runner as safety
from scripts.isolated_diagnostics import p15_minimal_contract as local
from scripts.isolated_diagnostics import p15_minimal_probe as net
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.isolated_diagnostics.p15_schema_probe_p02 import private_write

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01/results"
BODY = RESULT / "review-request-unsent.json"
BODY_SHA = "2846ee4c890c6a8cc082ec76d5da27d01adccf6521d336c1ecd68168ce3bc7e5"
OUTPUT = Path("/private/tmp/edumind-p15-course-review-once-r01")


def validate_input():
    raw = BODY.read_bytes()
    if len(raw) != 79305 or hashlib.sha256(raw).hexdigest() != BODY_SHA:
        raise ValueError("REQUEST_CHANGED")
    body = wire.strict_json(raw)
    if (
        body["model"] != "gpt-6.1-sol"
        or body["reasoning"] != {"effort": "low"}
        or body["max_output_tokens"] != 8000
    ):
        raise ValueError("REQUEST_CONFIGURATION")
    candidate = json.loads((RESULT / "candidate.json").read_text())
    binding = local.make_binding(candidate)
    given = wire.strict_json(body["input"][1]["content"])
    if (
        given["artifact"] != candidate
        or given["candidate_id"] != binding["candidate_id"]
        or given["target_catalog"] != binding["targets"]
    ):
        raise ValueError("CANDIDATE_BINDING")
    return raw, binding


def key_value():
    values = dotenv_values(ROOT / ".env", interpolate=False)

    def get(name):
        return os.environ.get(name, values.get(name))

    key = get("EDUMIND_AIAPI_REVIEW_API_KEY")
    if not key and get("EDUMIND_PROVIDER_BASE_URL") in (
        "https://aiapi.world/v1",
        "https://aiapi.world/v1/",
    ):
        key = get("EDUMIND_PROVIDER_API_KEY")
    if (
        not isinstance(key, str)
        or len(key) < 16
        or not key.isascii()
        or any(ch.isspace() for ch in key)
    ):
        raise ValueError("AIAPI_CREDENTIAL_UNAVAILABLE")
    return key


async def execute(raw, binding):
    if OUTPUT.exists() or any(p.is_symlink() for p in (OUTPUT, *OUTPUT.parents)):
        raise ValueError("EXISTING_OUTPUT_NO_RESTART")
    key = key_value()
    start = time.monotonic()
    OUTPUT.mkdir(mode=0o700)
    private_write(OUTPUT / "request.json", raw)
    private_write(
        OUTPUT / "approval.json",
        canonical(
            dict(
                user_message="先发送审核，查看结果是否符合要求",
                request_sha256=BODY_SHA,
                requests=1,
                window_seconds=120,
                per_http_seconds=60,
                dns_seconds=9,
                local_input_reservation=32768,
                max_output_tokens=8000,
            )
        ),
    )

    def record(name, value):
        private_write(OUTPUT / f"{name}.json", canonical(value))

    outcome = dict(state="stopped", stage="before_send")
    try:
        target = await net.bounded_target(wire.ROUTES["review"]["url"], 9.0, None)
        record(
            "target",
            dict(
                hostname=target.hostname,
                addresses=list(target.addresses),
                connect_ip=target.connect_ip,
            ),
        )
        remaining = min(60.0, 120.0 - (time.monotonic() - start))
        if remaining <= 0:
            raise ValueError("WINDOW_EXHAUSTED")
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        url = urlunsplit(("https", f"{host}:443", urlsplit(target.url).path, "", ""))
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=0),
            trust_env=False,
            follow_redirects=False,
            timeout=remaining,
        ) as client:
            req = client.build_request(
                "POST",
                url,
                content=raw,
                headers={
                    "Host": target.hostname,
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + key,
                },
            )
            req.extensions["sni_hostname"] = target.hostname
            record(
                "sent",
                dict(
                    transport="real",
                    request_sha256=BODY_SHA,
                    elapsed=time.monotonic() - start,
                ),
            )
            outcome["stage"] = "sent_unknown"
            async with asyncio.timeout(remaining):
                response = await client.send(req, stream=True, follow_redirects=False)
                try:
                    record("status", dict(http_status=response.status_code))
                    buf = bytearray()
                    async for chunk in response.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) > 65536:
                            raise ValueError("RESPONSE_SIZE")
                finally:
                    await response.aclose()
        received = bytes(buf)
        if safety.secret_visible(received, {"review": key}):
            raise ValueError("SECRET_OR_NON_UTF8")
        private_write(OUTPUT / "response.bin", received)
        if response.status_code != 200:
            raise ValueError("HTTP_STATUS")
        catalog = local.make_catalog(contract.SPEC)
        value, observation = contract.observe_course(
            "review_C", raw, received, catalog=catalog, binding=binding
        )
        if observation["reported_input_tokens"] > 32768:
            raise ValueError("INPUT_RESERVATION_EXCEEDED")
        if time.monotonic() - start >= 120:
            raise ValueError("WINDOW_EXHAUSTED")
        outcome = dict(
            state="mechanically_valid_review_pending_user",
            stage="validated",
            review=value,
            observation=observation,
            elapsed=time.monotonic() - start,
            request_sha256=BODY_SHA,
            response_sha256=hashlib.sha256(received).hexdigest(),
            semantic_verdict_by_user=False,
        )
    except Exception as exc:
        outcome["reason"] = (
            str(exc)
            if isinstance(exc, ValueError) and str(exc).isupper()
            else type(exc).__name__
        )
    record("result", outcome)
    print(json.dumps(outcome, ensure_ascii=False))
    return 0 if outcome["state"] == "mechanically_valid_review_pending_user" else 2


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    raw, binding = validate_input()
    if args.check:
        print(
            json.dumps(
                dict(
                    request_sha256=BODY_SHA,
                    bytes=len(raw),
                    candidate_id=binding["candidate_id"],
                    real_requests=0,
                )
            )
        )
        return 0
    return asyncio.run(execute(raw, binding))


if __name__ == "__main__":
    raise SystemExit(main())
