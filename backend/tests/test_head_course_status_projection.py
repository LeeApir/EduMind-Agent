"""Only the finite head protocol projection and ordinary budget remain in scope."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.free_course_snapshots import SnapshotRepository
from scripts import head_course_goal as entry


@pytest.mark.parametrize(
    "version,finite",
    [
        ("head-goal-course-v1", True),
        ("head-reuse-course-v1", True),
        ("free-course-plan-v2", False),
        ("head-reuse-course-v999", False),
    ],
)
def test_actual_api_projection_and_ordinary_budget(monkeypatch, version, finite):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])

        async def seed(db):
            repo = SnapshotRepository(db, owner)
            value = await repo.create_course(
                "T110状态投影夹具", key=str(uuid4()), config={"prompt_version": version}
            )
            op = await repo._operation(UUID(value["course_id"]), UUID(value["operation_id"]))
            op.state, op.reason_code = "failed", "TEACHING_REVIEW_FAILED"
            return value

        created = asyncio.run(entry.database(seed))
        route = f"/api/free-courses/{created['course_id']}/operations/{created['operation_id']}"
        response = client.get(route)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["state"] == "failed"
        if finite:
            assert value["execution_mode"] == "finite_head_foreground"
            assert value["budget"] is None
        else:
            assert "execution_mode" not in value
            assert value["budget"]["attempts_used"] == 0
            assert value["budget"]["attempts_remaining"] == 13
        assert client.get(route).json() == value
