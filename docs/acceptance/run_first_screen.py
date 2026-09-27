"""One frozen real HTTP run; no replacement samples or client generation retries."""

import argparse
import asyncio
import hashlib
import json
import math
import platform
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.agents.learning_resource_prompt import RESOURCE_INSTRUCTION_VERSION
from app.agents.learning_resource_schema import RESOURCE_PROMPT_VERSION
from app.agents.profile_agent import PROFILE_INSTRUCTION_VERSION, PROFILE_PROMPT_VERSION
from app.agents.review_agent import REVIEW_INSTRUCTION_VERSION
from app.agents.review_schema import REVIEW_PROMPT_VERSION

GOAL = "我想理解单链表的前置知识，先看 C 代码。"
METRICS = ("headers", "status", "token", "paragraph", "published")


def paragraph_candidate(text, ended=False):
    """First complete prose paragraph outside fences, with a sentence terminator.

    This is a syntactic candidate only; pedagogical meaning requires manual review.
    """
    fence = None
    lines = []
    for line in text.replace("\r\n", "\n").splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else (marker if fence is None else fence)
            continue
        if fence is not None:
            continue
        if not stripped:
            candidate = "\n".join(lines).strip()
            if eligible(candidate):
                return candidate
            lines = []
        elif not re.match(r"^#{1,6}\s", stripped):
            lines.append(line)
    candidate = "\n".join(lines).strip()
    return candidate if ended and fence is None and eligible(candidate) else None


def eligible(text):
    return bool(re.search(r"[\w\u4e00-\u9fff]", text) and re.search(r"[。！？.!?]", text))


def summarize(samples, metric):
    values = sorted(
        s["validated_ms"].get(metric) for s in samples if s["validated_ms"].get(metric) is not None
    )
    missing = len(samples) - len(values)
    # Missing milestones are +infinity for the full planned distribution.
    rank = math.ceil(0.95 * len(samples))
    return {
        "observed": len(values),
        "missing": missing,
        "planned_p95_ms": values[rank - 1] if rank <= len(values) else None,
        "planned_p95_missing": rank > len(values),
        "conditional_observed_p95_ms": values[math.ceil(0.95 * len(values)) - 1]
        if values
        else None,
    }


async def sample(base, number):
    record = {
        "number": number,
        "validated_ms": {},
        "client_ms": {},
        "status": "failed",
        "error_codes": [],
        "manual_review_required": True,
    }
    async with httpx.AsyncClient(
        base_url=base,
        headers={"Origin": base},
        timeout=httpx.Timeout(180, connect=15),
        trust_env=False,
    ) as client:
        started = None
        validated = None
        text = ""
        paragraph = None

        def milestone(name, now):
            if name not in record["client_ms"]:
                record["client_ms"][name] = round((now - started) / 1e6, 3)
                record["validated_ms"][name] = round((now - validated) / 1e6, 3)

        try:
            async with asyncio.timeout(180):
                auth = await client.post("/api/auth/guest")
                auth.raise_for_status()
                cookie = auth.cookies.get("edumind_session")
                csrf = auth.json()["csrf_token"]
                if not cookie or not isinstance(csrf, str):
                    raise ValueError("AUTH_INVALID")
                # Secure production cookie copied only into this trusted loopback CLI jar.
                client.cookies.clear()
                client.cookies.set("edumind_session", cookie)
            started = time.monotonic_ns()
            async with asyncio.timeout(180):
                async with client.stream(
                    "POST",
                    "/api/learning-sessions",
                    json={"goal": GOAL, "preferred_language": "c"},
                    headers={
                        "X-CSRF-Token": csrf,
                        "Idempotency-Key": str(uuid4()),
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    arrived = time.monotonic_ns()
                    record["http_status"] = response.status_code
                    response.raise_for_status()
                    validated = int(response.headers["X-Acceptance-Validated-At-Ns"])
                    if not started <= validated <= arrived:
                        raise ValueError("CLOCK_INVALID")
                    milestone("headers", arrived)
                    event = ""
                    data = []
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data.append(line[5:].strip())
                        elif not line and data:
                            payload = json.loads("\n".join(data))
                            data = []
                            now = time.monotonic_ns()
                            if event == "agent_start":
                                milestone("status", now)
                            elif event == "token" and payload.get("temporary") is True:
                                delta = payload.get("delta", "")
                                if delta.strip():
                                    milestone("token", now)
                                text += delta
                                if paragraph is None:
                                    paragraph = paragraph_candidate(text)
                                    if paragraph:
                                        milestone("paragraph", now)
                            elif event == "stage_changed" and payload.get("stage") == "reviewing":
                                if paragraph is None:
                                    paragraph = paragraph_candidate(text, ended=True)
                                    if paragraph:
                                        milestone("paragraph", now)
                            elif event == "scene_ready":
                                milestone("published", now)
                            elif event == "error":
                                record["error_codes"].append(payload.get("code", "SSE_ERROR"))
                            elif event == "review_reject":
                                record["error_codes"].append("REVIEW_REJECT")
                            elif event == "done":
                                record["status"] = payload.get("status", "failed")
            if record["status"] != "published":
                record["error_codes"].append("NOT_PUBLISHED")
        except TimeoutError:
            record["status"] = "failed"
            record["error_codes"].append("TOTAL_TIMEOUT")
        except httpx.HTTPStatusError as error:
            record["status"] = "failed"
            record["error_codes"].append(f"HTTP_{error.response.status_code}")
        except httpx.HTTPError:
            record["status"] = "failed"
            record["error_codes"].append("HTTP_TRANSPORT_ERROR")
        except (KeyError, ValueError, TypeError):
            record["status"] = "failed"
            record["error_codes"].append("PROTOCOL_OR_CLOCK_ERROR")
        record["client_total_ms"] = (
            round((time.monotonic_ns() - started) / 1e6, 3) if started else None
        )
        if paragraph:
            record["paragraph_sha256"] = hashlib.sha256(paragraph.encode()).hexdigest()
            record["paragraph_characters"] = len(paragraph)
            print(
                f"PUBLIC_PARAGRAPH {number}: {json.dumps(paragraph, ensure_ascii=False)}",
                flush=True,
            )
        return record


async def run(args):
    # Refuse overwrite, including a prior failed run. No automatic reruns.
    with args.output.open("x") as handle:
        handle.write("{}\n")
    report = {
        "plan": "mvp-0.2-t032-first-screen-plan.md",
        "samples_planned": 20,
        "concurrency": 1,
        "billable_warmups": 0,
        "request_total_timeout_seconds": 180,
        "provider_attempt_limit": 240,
        "goal": GOAL,
        "instructions": {
            "profile_prompt": PROFILE_PROMPT_VERSION,
            "profile": PROFILE_INSTRUCTION_VERSION,
            "resources_prompt": RESOURCE_PROMPT_VERSION,
            "resources": RESOURCE_INSTRUCTION_VERSION,
            "review_prompt": REVIEW_PROMPT_VERSION,
            "review": REVIEW_INSTRUCTION_VERSION,
            "first_screen_version": "no separate version constant; source hash below",
            "first_learning_source_sha256": hashlib.sha256(
                (
                    Path(__file__).resolve().parents[2] / "backend/app/services/first_learning.py"
                ).read_bytes()
            ).hexdigest(),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "httpx": httpx.__version__,
            "client": "HTTPX via actual Vite proxy",
            "provider_network": (
                "host outbound network, trust_env=False client; "
                "Provider uses current configuration"
            ),
            "provider_cold_state": "unknown; first sample retained",
        },
        "samples": [],
        "manual_semantic_review_pending": True,
    }
    stop = None
    for number in range(1, 21):
        if stop:
            record = {
                "number": number,
                "validated_ms": {},
                "client_ms": {},
                "status": "unattempted",
                "error_codes": [stop],
            }
        else:
            print(f"START_SAMPLE {number}/20", flush=True)
            record = await sample(args.base_url, number)
        report["samples"].append(record)
        ledger = json.loads(args.ledger.read_text())
        codes = {call.get("error_code") for call in ledger["provider_calls"]}
        if len(ledger["provider_calls"]) >= 240:
            stop = "PROVIDER_BUDGET_EXHAUSTED"
        elif codes & {"AUTHENTICATION_FAILED", "RATE_LIMITED"}:
            stop = "PROVIDER_AUTH_OR_QUOTA_FAILURE"
        report["actual_provider_attempts"] = len(ledger["provider_calls"])
        report["configured_model"] = ledger["configured_model"]
        report["structured_transport"] = ledger["structured_transport"]
        report["text_transport"] = "Responses streaming"
        report["metrics"] = {m: summarize(report["samples"], m) for m in METRICS}
        report["published_failures"] = sum(s["status"] != "published" for s in report["samples"])
        report["published_failure_rate"] = report["published_failures"] / len(report["samples"])
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"END_SAMPLE {number}: {json.dumps(record, ensure_ascii=False)}", flush=True)
    print("FROZEN_RUN_FINISHED", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:4182")
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("Requires --confirm-billable")
    if args.base_url != "http://127.0.0.1:4182":
        parser.error("Frozen plan requires the local Vite proxy")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
