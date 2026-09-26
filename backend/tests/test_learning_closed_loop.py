"""Real PostgreSQL/REST closed loop; only model output is mocked, never persisted state."""

import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.learning_sessions import provider_gateway
from app.core.auth import COOKIE_NAME
from app.main import app
from app.services.profile_behavior_updates import profile_behavior_gateway_factory
from app.services.provider_gateway import ProviderGateway, StructuredResult
from tests.test_learning_sessions import FakeAdapter, event_data
from tests.test_profile_behavior_updates import StubGateway

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def test_learning_quiz_mastery_replan_correction_wrong_fallback_and_process_recovery(monkeypatch):
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    adapter = FakeAdapter()
    behavior = StubGateway(StructuredResult({"updates": {}}, "mock-behavior"))
    app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(adapter)
    app.dependency_overrides[profile_behavior_gateway_factory] = lambda: lambda: behavior
    try:
        with TestClient(app, base_url="https://testserver") as client:
            guest = client.post("/api/auth/guest")
            csrf = guest.json()["csrf_token"]

            def headers(key):
                return {"Origin": "https://testserver", "X-CSRF-Token": csrf,
                        "Idempotency-Key": key}

            result = client.post("/api/learning-sessions", json={
                "goal": "讲解单链表", "preferred_language": "c",
            }, headers=headers("closed-loop-learning-001"))
            assert result.status_code == 200
            ready = next(event_data(event) for event in result.text.split("\n\n")
                         if event.startswith("event: scene_ready"))
            unit_id = ready["learning_unit_id"]
            unit = client.get(f"/api/learning-units/{unit_id}").json()
            assert unit["knowledge_node_id"] == "c-pointer"
            target = {"target_node_id": "single-linked-list"}
            initial_path = client.get("/api/path/current", params=target).json()
            assert initial_path["current_node_id"] == "c-pointer"
            resources = [client.get(f"/api/resource/{rid}").json()
                         for rid in ready["resource_ids"]]
            exercise = next(item for item in resources if item["type"] == "exercise")
            assert all("answer" not in item and "explanation" not in item
                       for item in exercise["content"]["items"])
            quiz = {"resource_id": exercise["id"], "resource_version": exercise["version"],
                    "answers": [{"question_id": "q1", "answer": "后继指针"},
                                {"question_id": "q2", "answer": "起点"}]}
            for attempt in range(2):
                receipt = client.post("/api/quiz-submissions", json=quiz,
                                      headers=headers(f"closed-loop-correct-{attempt:03}"))
                assert receipt.status_code == 200 and receipt.json()["score"] == 1
            mastered = receipt.json()
            assert mastered["mastery_changes"][0]["status"] == "mastered"
            replay = client.post("/api/quiz-submissions", json=quiz,
                                 headers=headers("closed-loop-correct-001"))
            assert replay.json() == mastered
            states = client.get("/api/mastery").json()
            assert states["items"][0]["revision"] == 2

            def replan(key):
                previous = client.get("/api/path/current", params=target).json()
                response = client.post("/api/path/replan",
                                       json={**target, "reason": "mastery_changed"},
                                       headers={**headers(key),
                                                "If-Match-Path-Version": str(previous["version"])})
                assert response.status_code == 200
                return response.json()

            progressed = replan("closed-loop-progress-001")
            assert progressed["current_node_id"] != "c-pointer"
            profile = client.get("/api/profile/me").json()
            corrected = client.patch("/api/profile/me", json={
                "engineering_preference": {"code_first": True},
            }, headers={**headers("closed-loop-correction-001"),
                        "If-Match-Profile-Version": str(profile["version"])})
            assert corrected.status_code == 200
            assert corrected.json()["evidence"]["engineering_preference"][-1]["source"] \
                == "manual_correction"
            assert client.get("/api/path/current", params=target).json()["is_stale"] is True
            corrected_path = replan("closed-loop-profile-replan")
            assert any(item["recommended_resource"] == "code"
                       for item in corrected_path["node_details"])
            quiz["answers"] = [{"question_id": "q1", "answer": "wrong"},
                               {"question_id": "q2", "answer": "wrong"}]
            for attempt in range(2):
                failed = client.post("/api/quiz-submissions", json=quiz,
                                     headers=headers(f"closed-loop-wrong-{attempt:03}"))
                assert failed.status_code == 200 and failed.json()["score"] == 0
            fallback = replan("closed-loop-fallback-001")
            assert fallback["current_node_id"] == "c-pointer"
            assert fallback["node_details"][0]["recommended_resource"] == "review"
            assert "wrong_streak=2" in str(fallback["reasons"])
            with TestClient(app, base_url="https://testserver") as stranger:
                other = stranger.post("/api/auth/guest").json()
                assert stranger.get(f"/api/learning-units/{unit_id}").status_code == 404
                foreign = stranger.post("/api/quiz-submissions", json=quiz, headers={
                    "Origin": "https://testserver", "X-CSRF-Token": other["csrf_token"],
                    "Idempotency-Key": "closed-loop-foreign-001",
                })
                assert foreign.status_code == 404
                assert stranger.get("/api/mastery").json()["items"] == []
            state = {"session_token": client.cookies[COOKIE_NAME], "unit_id": unit_id,
                     "resource_id": exercise["id"], "target": target["target_node_id"],
                     "evidence_id": failed.json()["evidence_id"], "path": fallback,
                     "mastery": client.get("/api/mastery").json()}
            process = subprocess.run([sys.executable, "-m", "tests.learning_recovery_probe"],
                                     input=json.dumps(state), text=True, capture_output=True,
                                     timeout=30, check=False)
            assert process.returncode == 0, process.stderr
            assert json.loads(process.stdout)["fresh_process_recovery"] is True
    finally:
        app.dependency_overrides.pop(provider_gateway, None)
        app.dependency_overrides.pop(profile_behavior_gateway_factory, None)
