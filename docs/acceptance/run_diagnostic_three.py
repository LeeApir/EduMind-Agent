"""Exactly three diagnostic slots, no retries/warmups/replacements or P95 claim."""

import argparse
import asyncio
import hashlib
import json
import platform
import time
from pathlib import Path
from uuid import uuid4

import httpx
from first_screen_v2 import raw_learning_post
from run_first_screen_v2 import GOAL


async def run(args):
    ledger = json.loads(args.ledger.read_text())
    if ledger["limit"] != 36 or ledger["provider_calls"]:
        raise ValueError("FRESH_36_ATTEMPT_LEDGER_REQUIRED")
    args.output.open("x").close()
    report = {
        "schema": "three-diagnostic-wire-v2",
        "samples_planned": 3,
        "concurrency": 1,
        "warmups": 0,
        "deadline_seconds": 180,
        "configured_model": ledger["configured_model"],
        "structured_transport": ledger["structured_transport"],
        "goal": GOAL,
        "samples": [],
        "formal_acceptance": False,
    }
    report["environment"] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "httpx": httpx.__version__,
        "client_wire": "loopback HTTP/1.1 via actual Vite",
        "provider_cold_state": "unknown",
        "text_transport": "Responses streaming",
    }
    report["instruction_source_sha256"] = {
        name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
        for name in (
            "backend/app/services/first_learning.py",
            "backend/app/agents/profile_agent.py",
            "backend/app/agents/learning_resource_prompt.py",
            "backend/app/agents/review_agent.py",
        )
    }
    stop = None
    for number in range(1, 4):
        print(f"START_SAMPLE {number}/3", flush=True)
        if stop:
            item = {"number": number, "status": "unattempted", "errors": [stop]}
        else:
            journey = time.monotonic_ns()
            before = len(json.loads(args.ledger.read_text())["provider_calls"])
            try:
                async with httpx.AsyncClient(
                    base_url="http://127.0.0.1:4182",
                    trust_env=False,
                    timeout=30,
                    headers={"Origin": "http://127.0.0.1:4182"},
                ) as client:
                    auth_start = time.monotonic_ns()
                    auth = await client.post("/api/auth/guest")
                    auth.raise_for_status()
                    auth_end = time.monotonic_ns()
                    cookie = auth.cookies["edumind_session"]
                    stream = await raw_learning_post(
                        port=4182,
                        cookie=cookie,
                        csrf=auth.json()["csrf_token"],
                        key=str(uuid4()),
                        goal=GOAL,
                        timeout=180,
                    )
                    item = {
                        "number": number,
                        **stream.evidence(public_benchmark=True),
                        "journey_started_ns": journey,
                        "anonymous_http_ms": (auth_end - auth_start) / 1e6,
                        "anonymous_setup_ms": (stream.started_ns - journey) / 1e6,
                    }
                    recovery_before = len(json.loads(args.ledger.read_text())["provider_calls"])
                    if stream.operation_id:
                        try:
                            response = await client.get(
                                f"/api/learning-operations/{stream.operation_id}",
                                headers={"Cookie": f"edumind_session={cookie}"},
                            )
                            item["recovery_http_status"] = response.status_code
                            if response.status_code == 200:
                                item["recovery_state"] = response.json().get("status")
                        except httpx.HTTPError:
                            # A read failure must never discard the completed generation evidence.
                            item["recovery_error"] = "READ_FAILED"
                    recovery_after = len(json.loads(args.ledger.read_text())["provider_calls"])
                    item["recovery_extra_attempts"] = recovery_after - recovery_before
            except (httpx.HTTPError, KeyError):
                item = {"number": number, "status": "failed", "errors": ["AUTH_OR_READ_FAILED"]}
            item["attempts_before"] = before
        report["samples"].append(item)
        ledger = json.loads(args.ledger.read_text())
        if ledger.get("halted") or len(ledger["provider_calls"]) >= 36:
            stop = ledger.get("halted", "BUDGET_EXHAUSTED")
        report["actual_attempts"] = len(ledger["provider_calls"])
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            f"END_SAMPLE {number}: {item['status']}; attempts={report['actual_attempts']}",
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("Requires billing authorization")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
