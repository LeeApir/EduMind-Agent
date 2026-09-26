"""Manual Compose recovery check for resources, quiz, mastery and path state.

Run this inside the API container.  It deliberately keeps the temporary session
token in the container's /tmp directory so no credential is printed or committed.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Running this file directly places ``tests`` rather than the application root
# on sys.path.  Keep the command in the recovery guide short and explicit.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.profile_schema import empty_transient_profile
from app.core.auth import COOKIE_NAME
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.services.profile_behavior_updates import profile_behavior_gateway_factory
from app.services.profile_updates import persist_profile_version
from app.services.provider_gateway import ProviderError, ProviderErrorCode

DEFAULT_STATE_PATH = Path("/tmp/edumind-compose-recovery-state.json")


def _database_url() -> str:
    database_url = os.getenv("EDUMIND_DATABASE_URL")
    if not database_url:
        raise RuntimeError("EDUMIND_DATABASE_URL must be set inside the API container")
    return database_url


def seed(state_path: Path) -> None:
    """Create one owner-scoped, reviewed resource and retain only test state."""
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/auth/guest")
        assert response.status_code == 201, response.text
        user_id = UUID(response.json()["user"]["id"])
        session_token = client.cookies[COOKIE_NAME]

    async def write_resource() -> tuple[str, str, str]:
        engine = create_database_engine(_database_url())
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                unit = LearningUnit(
                    user_id=user_id,
                    title="Compose restart recovery check",
                    status="ready",
                )
                db.add(unit)
                await db.flush()
                scene = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="restart-recovery",
                    scene_order=1,
                    scene_type="explanation",
                    generation_status="complete",
                    review_status="passed",
                )
                db.add(scene)
                await db.flush()
                resource = GeneratedResource(
                    user_id=user_id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="explanation",
                    content={"markdown": "compose-restart-approved-resource"},
                    review_status="passed",
                    version=1,
                    published_at=datetime.now(timezone.utc),
                )
                db.add(resource)
                await persist_profile_version(
                    db, owner_id=user_id, profile=empty_transient_profile("学习C指针")
                )
                quiz_scene = LearningScene(
                    learning_unit_id=unit.id, scene_key="recovery-quiz", scene_order=2,
                    scene_type="quiz", generation_status="complete", review_status="passed",
                )
                db.add(quiz_scene)
                await db.flush()
                quiz = GeneratedResource(
                    user_id=user_id, learning_unit_id=unit.id, scene_id=quiz_scene.id,
                    knowledge_point_id="c-pointer", resource_type="exercise", version=1,
                    review_status="passed", published_at=datetime.now(timezone.utc),
                    generation_metadata={"prompt_version": "learning-resources-v1"},
                    content={"items": [
                        {"id": "q1", "question": "指针存储什么？", "answer": "地址",
                         "explanation": "指针保存地址。"},
                        {"id": "q2", "question": "NULL可以解引用吗？", "answer": "不可以",
                         "explanation": "空指针解引用未定义。"},
                    ]},
                )
                db.add(quiz)
                await db.commit()
                return str(unit.id), str(resource.id), str(quiz.id)
        finally:
            await engine.dispose()

    unit_id, resource_id, quiz_id = asyncio.run(write_resource())
    state = {
        "unit_id": unit_id, "resource_id": resource_id, "session_token": session_token,
        "quiz_id": quiz_id,
    }

    def unavailable():
        raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)

    app.dependency_overrides[profile_behavior_gateway_factory] = lambda: unavailable
    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.cookies.set(COOKIE_NAME, session_token)
            csrf = client.get("/api/auth/session").json()["csrf_token"]
            headers = {"Origin": "https://testserver", "X-CSRF-Token": csrf}
            target = {"target_node_id": "single-linked-list"}
            plan = client.post("/api/path/plan", json=target,
                               headers={**headers, "Idempotency-Key": "compose-path-plan-001"})
            assert plan.status_code == 201
            for index in range(2):
                receipt = client.post("/api/quiz-submissions", json={
                    "resource_id": quiz_id, "resource_version": 1,
                    "answers": [{"question_id": "q1", "answer": "地址"},
                                {"question_id": "q2", "answer": "不可以"}],
                }, headers={**headers, "Idempotency-Key": f"compose-quiz-correct-{index}"})
                assert receipt.status_code == 200
                assert receipt.json()["profile_update_status"] == "provider_failed"
            replan = client.post("/api/path/replan", json=target, headers={
                **headers, "Idempotency-Key": "compose-path-replan-001",
                "If-Match-Path-Version": "1",
            })
            assert replan.status_code == 200
            state["path"] = replan.json()
            state["mastery"] = client.get("/api/mastery").json()
            state["evidence_id"] = receipt.json()["evidence_id"]
    finally:
        app.dependency_overrides.pop(profile_behavior_gateway_factory, None)
    state_path.write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    state_path.chmod(0o600)
    print(json.dumps({"seeded": True, "unit_id": unit_id, "resource_id": resource_id}))


def check(state_path: Path) -> None:
    """Read the prior resource after containers have been restarted."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(COOKIE_NAME, state["session_token"])
        unit = client.get(f"/api/learning-units/{state['unit_id']}")
        resource = client.get(f"/api/resource/{state['resource_id']}")
        mastery = client.get("/api/mastery")
        path = client.get("/api/path/current", params={"target_node_id": "single-linked-list"})
        receipt = client.get("/api/quiz-submissions/latest", params={
            "resource_id": state["quiz_id"], "resource_version": 1,
        })
    assert unit.status_code == resource.status_code == 200
    assert "compose-restart-approved-resource" in unit.text
    assert resource.json()["review_status"] == "passed"
    assert mastery.status_code == path.status_code == receipt.status_code == 200
    assert mastery.json() == state["mastery"]
    assert path.json() == state["path"]
    assert receipt.json()["evidence_id"] == state["evidence_id"]
    print(json.dumps({"recovered": True, "resource_id": state["resource_id"]}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seed", "check"))
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.state_path)
    else:
        check(args.state_path)


if __name__ == "__main__":
    main()
