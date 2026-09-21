"""Billable, opt-in MVP 0.1 acceptance against the running real Provider stack."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

COOKIE_NAME = "edumind_session"


@dataclass(frozen=True, slots=True)
class StreamResult:
    first_content_ms: int
    learning_unit_id: str | None
    status: str | None


def authenticated_client(base_url: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(180.0, connect=15.0),
        headers={"Origin": base_url},
        trust_env=False,
    )
    response = client.post("/api/auth/guest")
    response.raise_for_status()
    token = response.cookies.get(COOKIE_NAME)
    csrf_token = response.json().get("csrf_token")
    if not token or not isinstance(csrf_token, str):
        client.close()
        raise RuntimeError("AUTH_SESSION_INVALID")
    # The production cookie is Secure. The acceptance target is trusted local HTTP,
    # so copy the opaque value into a process-local cookie jar for this CLI only.
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, token)
    return client, csrf_token


def run_stream(
    *, base_url: str, goal: str, consume_to_completion: bool
) -> StreamResult:
    client, csrf_token = authenticated_client(base_url)
    started = time.perf_counter()
    first_content_ms: int | None = None
    learning_unit_id: str | None = None
    final_status: str | None = None
    current_event = ""
    try:
        with client.stream(
            "POST",
            "/api/learning-sessions",
            json={"goal": goal, "preferred_language": "c"},
            headers={
                "Accept": "text/event-stream",
                "X-CSRF-Token": csrf_token,
                "Idempotency-Key": str(uuid4()),
            },
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line.split(":", 1)[1].strip())
                if current_event == "token" and payload.get("temporary") is True:
                    delta = payload.get("delta")
                    if isinstance(delta, str) and delta.strip() and first_content_ms is None:
                        first_content_ms = round((time.perf_counter() - started) * 1000)
                        if not consume_to_completion:
                            break
                elif current_event == "scene_ready":
                    candidate = payload.get("learning_unit_id")
                    if isinstance(candidate, str):
                        learning_unit_id = candidate
                elif current_event == "error":
                    code = payload.get("code")
                    raise RuntimeError(code if isinstance(code, str) else "PROVIDER_ERROR")
                elif current_event == "done":
                    candidate = payload.get("status")
                    if isinstance(candidate, str):
                        final_status = candidate
    finally:
        client.close()
    if first_content_ms is None:
        raise RuntimeError("NO_FIRST_CONTENT")
    return StreamResult(first_content_ms, learning_unit_id, final_status)


def verify_published_unit(base_url: str, goal: str) -> dict[str, Any]:
    client, csrf_token = authenticated_client(base_url)
    started = time.perf_counter()
    first_content_ms: int | None = None
    learning_unit_id: str | None = None
    final_status: str | None = None
    current_event = ""
    try:
        with client.stream(
            "POST",
            "/api/learning-sessions",
            json={"goal": goal, "preferred_language": "c"},
            headers={
                "Accept": "text/event-stream",
                "X-CSRF-Token": csrf_token,
                "Idempotency-Key": str(uuid4()),
            },
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.split(":", 1)[1].strip())
                    if current_event == "token" and payload.get("temporary") is True:
                        delta = payload.get("delta")
                        if isinstance(delta, str) and delta.strip() and first_content_ms is None:
                            first_content_ms = round((time.perf_counter() - started) * 1000)
                    elif current_event == "scene_ready":
                        candidate = payload.get("learning_unit_id")
                        if isinstance(candidate, str):
                            learning_unit_id = candidate
                    elif current_event == "error":
                        code = payload.get("code")
                        raise RuntimeError(code if isinstance(code, str) else "PROVIDER_ERROR")
                    elif current_event == "done":
                        candidate = payload.get("status")
                        if isinstance(candidate, str):
                            final_status = candidate
        if first_content_ms is None or learning_unit_id is None or final_status != "published":
            raise RuntimeError("FULL_FLOW_NOT_PUBLISHED")
        unit_response = client.get(f"/api/learning-units/{learning_unit_id}")
        unit_response.raise_for_status()
        unit = unit_response.json()
        resources = [
            resource
            for scene in unit.get("scenes", [])
            for resource in scene.get("resources", [])
        ]
        resource_types = sorted(
            resource.get("type") for resource in resources if isinstance(resource, dict)
        )
        if unit.get("status") != "ready" or resource_types != [
            "code",
            "exercise",
            "explanation",
        ]:
            raise RuntimeError("PUBLISHED_RESOURCES_INVALID")
        return {
            "published": True,
            "first_content_ms": first_content_ms,
            "total_ms": round((time.perf_counter() - started) * 1000),
            "resource_types": resource_types,
            "resource_count": len(resources),
        }
    finally:
        client.close()


def percentile_nearest_rank(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--confirm-billable", action="store_true")
    args = parser.parse_args()
    if not args.confirm_billable:
        raise SystemExit("Refusing real Provider calls without --confirm-billable")
    if not 1 <= args.samples <= 100:
        raise SystemExit("--samples must be between 1 and 100")

    goal = "学习链表头部插入，先解释 next 指针，再给出 C 代码和三道练习。"
    try:
        full_flow = verify_published_unit(args.base_url, goal)
    except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        full_flow = {
            "published": False,
            "error_class": type(error).__name__,
            "error_code": str(error)
            if isinstance(error, RuntimeError)
            else "ACCEPTANCE_REQUEST_FAILED",
        }
    timings: list[int] = []
    failures: list[str] = []
    for index in range(args.samples):
        try:
            result = run_stream(
                base_url=args.base_url,
                goal=f"链表头部插入首段性能样本 {index + 1}",
                consume_to_completion=False,
            )
            timings.append(result.first_content_ms)
        except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            failures.append(type(error).__name__)

    report: dict[str, Any] = {
        "full_flow": full_flow,
        "benchmark": {
            "requested_samples": args.samples,
            "successful_samples": len(timings),
            "failed_samples": len(failures),
            "failure_rate": round(len(failures) / args.samples, 4),
            "first_content_ms": timings,
            "p50_ms": round(statistics.median(timings)) if timings else None,
            "p95_ms": percentile_nearest_rank(timings, 0.95) if timings else None,
            "max_ms": max(timings) if timings else None,
            "error_classes": sorted(set(failures)),
        },
    }
    print(json.dumps(report, ensure_ascii=False))
    if (
        not full_flow["published"]
        or failures
        or not timings
        or report["benchmark"]["p95_ms"] > 10_000
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
