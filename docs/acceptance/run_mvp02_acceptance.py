"""Opt-in real Provider REST/SSE closed loop and local path latency evidence.

Run from backend: uv run --env-file ../.env python ../docs/acceptance/run_mvp02_acceptance.py
  --confirm-billable --output ../docs/acceptance/mvp-0.2-stage-report.json
Only public questions are printed; enter independently solved answers as JSON.
No answer key, credential or opaque session token is exported.
"""

import argparse
import json
import math
import platform
import sys
import time
from datetime import datetime
from os import getenv
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi.testclient import TestClient

from app.api.learning_sessions import provider_gateway
from app.core.provider_factory import build_server_provider_gateway, configured_provider_adapter
from app.main import app
from app.services.profile_behavior_updates import profile_behavior_gateway_factory
from app.services.provider_gateway import ProviderError


class BoundedAdapter:
    def __init__(self, adapter, ledger):
        self.adapter = adapter
        self.ledger = ledger

    def reserve(self, kind):
        if len(self.ledger) >= 30:
            raise RuntimeError("ACCEPTANCE_PROVIDER_BUDGET_EXHAUSTED")
        self.ledger.append({"kind": kind})

    async def generate_text(self, request):
        self.reserve("text")
        result = await self.adapter.generate_text(request)
        self.ledger[-1]["model"] = result.model_id
        return result

    async def generate_structured(self, request):
        self.reserve("structured")
        entry = self.ledger[-1]
        try:
            result = await self.adapter.generate_structured(request)
        except ProviderError as error:
            entry["error_code"] = error.code.value
            for name in ("output_failure_reason", "json_syntax_reason"):
                value = getattr(error, name, None)
                if value is not None:
                    entry[name] = value.value
            if error.schema_keyword is not None:
                entry["schema_keyword"] = error.schema_keyword
            if error.usage is not None:
                entry["usage"] = {
                    "input_tokens": error.usage.input_tokens,
                    "output_tokens": error.usage.output_tokens,
                }
            raise
        self.ledger[-1]["model"] = result.model_id
        if result.usage is not None:
            entry["usage"] = {
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
            }
        return result

    async def stream_text(self, request):
        self.reserve("stream")
        async for delta in self.adapter.stream_text(request):
            yield delta


def distribution(values, failures):
    ordered = sorted(values)
    total = len(values) + failures
    return {
        "samples": total,
        "successes": len(values),
        "failures": failures,
        "failure_rate": failures / total,
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None,
        "p99_ms": ordered[math.ceil(0.99 * len(ordered)) - 1] if ordered else None,
        "max_ms": max(ordered) if ordered else None,
        "latencies_ms": values,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable:
        raise SystemExit("Billable confirmation required")
    if args.output.exists():
        raise SystemExit("Refusing to overwrite previous evidence")
    ledger = []
    gateway = build_server_provider_gateway(
        lambda settings, guard: BoundedAdapter(configured_provider_adapter(settings, guard), ledger)
    )
    app.dependency_overrides[provider_gateway] = lambda: gateway
    app.dependency_overrides[profile_behavior_gateway_factory] = lambda: lambda: gateway
    report = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "transport": "TestClient actual routes, real PostgreSQL, real Provider",
            "concurrency": 1,
            "structured_transport": getenv(
                "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema"
            ),
            "provider_limit": 30,
        },
        "provider_calls": ledger,
        "passed": False,
    }
    try:
        with TestClient(
            app, base_url="https://testserver", headers={"Origin": "https://testserver"}
        ) as client:
            guest = client.post("/api/auth/guest")
            report["step"] = "guest"
            report["http_status"] = guest.status_code
            assert guest.status_code == 201
            csrf = guest.json()["csrf_token"]

            def headers():
                return {
                    "Origin": "https://testserver",
                    "X-CSRF-Token": csrf,
                    "Idempotency-Key": str(uuid4()),
                }

            started = time.perf_counter()
            response = client.post(
                "/api/learning-sessions",
                json={
                    "goal": "我想学习单链表，请从必要的前置知识开始。",
                    "preferred_language": "c",
                },
                headers=headers(),
            )
            report["step"] = "learning"
            report["http_status"] = response.status_code
            assert response.status_code == 200
            ready = None
            for frame in response.text.split("\n\n"):
                lines = frame.splitlines()
                if not lines or not lines[0].startswith("event:"):
                    continue
                name = lines[0].split(":", 1)[1].strip()
                data = json.loads(
                    next(line[5:].strip() for line in lines if line.startswith("data:"))
                )
                if name == "error":
                    raise RuntimeError(data["code"])
                if name == "scene_ready":
                    ready = data
                if name in {"done", "review_reject"}:
                    report["terminal_event"] = name
                    if name == "done":
                        report["terminal_status"] = data.get("status")
            assert ready is not None
            unit = client.get(f"/api/learning-units/{ready['learning_unit_id']}").json()
            assert unit["status"] == "ready"
            resources = [client.get(f"/api/resource/{rid}").json() for rid in ready["resource_ids"]]
            assert sorted(item["type"] for item in resources) == ["code", "exercise", "explanation"]
            assert all(item["review_status"] == "passed" for item in resources)
            exercise = next(item for item in resources if item["type"] == "exercise")
            items = exercise["content"]["items"]
            assert all("answer" not in item and "explanation" not in item for item in items)
            target = {"target_node_id": "single-linked-list"}
            before = client.get("/api/path/current", params=target).json()
            report["learning"] = {
                "node_id": unit["knowledge_node_id"],
                "published": True,
                "generation_total_ms": round((time.perf_counter() - started) * 1000),
                "resource_types": sorted(item["type"] for item in resources),
                "public_questions": items,
                "initial_current_node": before["current_node_id"],
            }
            print(json.dumps({"public_questions": items}, ensure_ascii=False), flush=True)
            print('Enter answers JSON: [{"question_id":"q1","answer":"..."}, ...]', flush=True)
            answers = json.loads(sys.stdin.readline())
            assert {item["question_id"] for item in answers} == {item["id"] for item in items}
            quiz = {
                "resource_id": exercise["id"],
                "resource_version": exercise["version"],
                "answers": answers,
            }
            receipts = []
            for _ in range(2):
                result = client.post("/api/quiz-submissions", json=quiz, headers=headers())
                assert result.status_code == 200
                receipt = result.json()
                report["step"] = "quiz"
                report["http_status"] = result.status_code
                receipts.append(
                    {
                        key: receipt[key]
                        for key in ("score", "mastery_changes", "profile_update_status")
                    }
                )
                report["quiz_receipts"] = receipts
                assert receipt["score"] == 1
                assert receipt["profile_update_status"] != "provider_failed"
            report["quiz_receipts"] = receipts
            assert receipts[-1]["mastery_changes"][0]["status"] == "mastered"
            replan = client.post(
                "/api/path/replan",
                json={**target, "reason": "mastery_changed"},
                headers={**headers(), "If-Match-Path-Version": str(before["version"])},
            )
            assert replan.status_code == 200
            path = replan.json()
            assert path["current_node_id"] != before["current_node_id"] and path["reasons"]
            report["recommendation"] = {
                key: path[key] for key in ("current_node_id", "version", "reasons", "node_details")
            }
            version = path["version"]
            for mode in ("current", "replan"):
                timings, failures = [], 0
                for index in range(105):
                    started = time.perf_counter()
                    if mode == "current":
                        measured = client.get("/api/path/current", params=target)
                    else:
                        measured = client.post(
                            "/api/path/replan",
                            json=target,
                            headers={**headers(), "If-Match-Path-Version": str(version)},
                        )
                        if measured.status_code == 200:
                            version = measured.json()["version"]
                    elapsed = round((time.perf_counter() - started) * 1000, 3)
                    if index < 5:  # explicit five warmup requests per endpoint
                        assert measured.status_code == 200
                        continue
                    if measured.status_code == 200:
                        timings.append(elapsed)
                    else:
                        failures += 1
                report[f"path_{mode}"] = distribution(timings, failures)
            assert report["path_current"]["p99_ms"] <= 200
            assert report["path_replan"]["p95_ms"] <= 200
            assert all(report[f"path_{mode}"]["failures"] == 0 for mode in ("current", "replan"))
            report["passed"] = True
    except Exception as error:
        report["failure_class"] = type(error).__name__
        # Never export arbitrary exception messages, URLs or response bodies.
    finally:
        app.dependency_overrides.pop(provider_gateway, None)
        app.dependency_overrides.pop(profile_behavior_gateway_factory, None)
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "passed": report["passed"],
                    "provider_calls": len(ledger),
                    "report": str(args.output),
                }
            ),
            flush=True,
        )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
