"""Fixed 20-slot acceptance: no warmups, replacements or client POST retries."""

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

GOAL = "我想理解单链表的前置知识，先看 C 代码。"


async def run(args):
    ledger = json.loads(args.ledger.read_text())
    if ledger["provider_calls"] or ledger["limit"] != 240:
        raise ValueError("REQUIRES_FRESH_240_ATTEMPT_LEDGER")
    with args.output.open("x") as handle:
        handle.write("{}\n")
    report = {
        "schema": "first-screen-wire-v2",
        "samples_planned": 20,
        "concurrency": 1,
        "warmups": 0,
        "total_timeout_seconds": 180,
        "manual_review_pending": True,
        "samples": [],
        "configured_model": ledger["configured_model"],
        "structured_transport": ledger["structured_transport"],
        "text_transport": "Responses streaming",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "httpx": httpx.__version__,
            "provider_cold_state": "unknown",
            "client_wire": "loopback HTTP/1.1 via actual Vite",
        },
        "instruction_source_sha256": {
            name: hashlib.sha256(
                (Path(__file__).resolve().parents[2] / name).read_bytes()
            ).hexdigest()
            for name in (
                "backend/app/services/first_learning.py",
                "backend/app/agents/profile_agent.py",
                "backend/app/agents/learning_resource_prompt.py",
                "backend/app/agents/review_agent.py",
            )
        },
        "goal": GOAL,
    }
    stop = None
    for number in range(1, 21):
        if stop:
            item = {
                "number": number,
                "status": "unattempted",
                "errors": [stop],
                "candidates": [],
                "milestones_ns": {},
                "started_ns": None,
            }
        else:
            print(f"START_SAMPLE {number}/20", flush=True)
            started = time.monotonic_ns()
            before = len(json.loads(args.ledger.read_text())["provider_calls"])
            try:
                # Auth preparatory request is separate from the learning POST clock.
                async with httpx.AsyncClient(
                    base_url="http://127.0.0.1:4182",
                    trust_env=False,
                    headers={"Origin": "http://127.0.0.1:4182"},
                    timeout=30,
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
                        "journey_started_ns": started,
                        "anonymous_session_ms": (stream.started_ns - started) / 1e6,
                        "anonymous_http_ms": (auth_end - auth_start) / 1e6,
                        "anonymous_setup_ms": (stream.started_ns - started) / 1e6,
                    }
                    recovery_before = len(json.loads(args.ledger.read_text())["provider_calls"])
                    if stream.operation_id:
                        try:
                            recovered = await client.get(
                                f"/api/learning-operations/{stream.operation_id}",
                                headers={"Cookie": f"edumind_session={cookie}"},
                            )
                            item["recovery_http_status"] = recovered.status_code
                            if recovered.status_code == 200:
                                item["recovery_state"] = recovered.json().get("status")
                        except httpx.HTTPError:
                            item["recovery_error"] = "READ_FAILED"
                    item["recovery_extra_attempts"] = (
                        len(json.loads(args.ledger.read_text())["provider_calls"]) - recovery_before
                    )
            except (httpx.HTTPError, KeyError):
                item = {
                    "number": number,
                    "status": "failed",
                    "errors": ["AUTH_FAILED"],
                    "candidates": [],
                    "milestones_ns": {},
                    "started_ns": started,
                }
            item["attempts_before"] = before
        report["samples"].append(item)
        ledger = json.loads(args.ledger.read_text())
        calls = ledger["provider_calls"]
        if len(calls) >= 240:
            stop = "BUDGET_EXHAUSTED"
        if ledger.get("halted"):
            stop = ledger["halted"]
        if any(c.get("error_code") in {"AUTHENTICATION_FAILED", "RATE_LIMITED"} for c in calls):
            stop = "AUTH_OR_QUOTA_FAILURE"
        report["actual_provider_attempts"] = len(calls)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"END_SAMPLE {number}: {item['status']}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("This future benchmark requires separate authorization and --confirm-billable")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
