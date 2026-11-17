"""Actual PG/ASGI replay mainline, source integrity and typed-answer regressions."""

import asyncio
import os
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.main import app
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.free_course_answers import TYPED_RULE, compare_answer, comparison_rule
from app.services.free_course_snapshots import SnapshotError
from app.services.head_course_replay import (
    import_course,
    mapping,
    require_development_database,
    validate_replay,
)


def work(action):
    async def run():
        require_development_database(os.environ["EDUMIND_TEST_DATABASE_URL"])
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                return await action(db)
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.mark.parametrize(
    "kind,key,answer,ok",
    [
        ("json_integer_array", "[2,1,9]", "[2, 1, 9]", True),
        ("json_integer_array", "[5]", "[\n5\n]", True),
        ("json_integer_array", "[5]", "[5.0]", False),
        ("json_integer_array", "[1]", "[true]", False),
        ("json_integer_array", "[5]", "[[5]]", False),
        ("json_integer_array", "[5]", "[5]，完整遍历", False),
        ("json_integer_array", "[5]", "5", False),
        ("json_integer_array", "[2,1,9]", "[1,2,9]", False),
        ("integer", "1", " 1 ", True),
        ("integer", "1", "1.0", False),
        ("integer", "1", "true", False),
        ("integer", "1", "NaN", False),
        ("short_text", "Ｔ１", "t1", True),
    ],
)
def test_typed_comparison(kind, key, answer, ok):
    result, explanation = compare_answer(
        dict(input_type=kind, answer_key=key, solution="原解析"), answer
    )
    assert result is ok and explanation.endswith("原解析")


def test_database_and_source_allowlists():
    for url in [
        "postgresql+asyncpg://a:b@localhost:15437/edumind_catalog_p15_t107_dev",
        "postgresql+asyncpg://a:b@127.0.0.1:15437/production",
    ]:
        with pytest.raises(SnapshotError):
            require_development_database(url)
    with pytest.raises(SnapshotError):
        mapping("C02-generate")


@pytest.mark.parametrize("slot", ["C01", "C02"])
def test_actual_owner_private_import_read_answer_refresh_and_idempotency(monkeypatch, slot):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **k: pytest.fail("Provider forbidden"),
    )
    with (
        TestClient(app, base_url="https://testserver") as client,
        TestClient(app, base_url="https://testserver") as other,
    ):
        auth = client.post("/api/auth/guest").json()
        other.post("/api/auth/guest")
        owner = UUID(auth["user"]["id"])

        async def imported(db):
            value = await import_course(db, owner, slot)
            await db.commit()
            return value

        result = work(imported)
        cid = result["course_id"]
        root = f"/api/free-courses/{cid}"
        assert client.get(root).json()["head"]["complete"] is True
        sid = result["scene_id"]
        route = root + f"/versions/{result['version']}/scenes/{sid}"
        response = client.get(route)
        assert response.status_code == 200, response.text
        view = response.json()
        assert (
            '"answer_key"' not in response.text
            and '"solution"' not in response.text
            and "original_candidate_utf8" not in response.text
        )
        assert view["replay_source"]["slot"] == slot
        expected, private = mapping(slot)
        assert view["blocks"][:-1] == expected["blocks"][:-1]
        exercise = view["blocks"][-1]
        assert exercise["items"] == expected["blocks"][-1]["items"]
        headers = {"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())}
        body = dict(
            course_version=result["version"],
            scene_id=sid,
            scene_version_id=view["scene_version_id"],
            exercise_id=exercise["exercise_id"],
            exercise_version_id=exercise["exercise_version_id"],
            answers=[],
        )
        for q in private["exercise"]["items"]:
            body["answers"].append(
                dict(
                    question_id=q["question_id"],
                    answer=q["answer_key"].replace(",", ", ")
                    if q["input_type"] == "json_integer_array"
                    else q["answer_key"],
                )
            )
        partial = {**body, "answers": body["answers"][:1]}
        posted = client.post(root + "/attempts", json=partial, headers=headers)
        assert posted.status_code == 201, posted.text
        partial_result = client.get(root + "/attempts/" + posted.json()["attempt_id"]).json()
        assert (
            partial_result["comparison_score"] is None and partial_result["question_results"] == []
        )
        headers["Idempotency-Key"] = str(uuid4())
        posted = client.post(root + "/attempts", json=body, headers=headers)
        assert posted.status_code == 201, posted.text
        aid = posted.json()["attempt_id"]
        attempt = client.get(root + "/attempts/" + aid).json()
        assert (
            attempt["comparison_score"] == 1
            and attempt["mastery_effect"] == "course_only"
            and attempt["reliability"] == "provisional"
        )
        assert all(
            q["explanation"] == private["exercise"]["items"][i]["solution"]
            for i, q in enumerate(attempt["question_results"])
        )
        assert (
            other.get(route).status_code == 404
            and other.get(root + "/attempts/" + aid).status_code == 404
        )
        assert (
            client.post(
                root + "/attempts",
                json={**body, "course_version": 1},
                headers={**headers, "Idempotency-Key": str(uuid4())},
            ).status_code
            == 409
        )
        assert (
            client.post(
                root + "/attempts", json=body, headers={"Idempotency-Key": str(uuid4())}
            ).status_code
            == 403
        )

        async def audit(db):
            row = await db.scalar(
                select(FreeSceneGenerationResult).where(
                    FreeSceneGenerationResult.course_id == UUID(cid)
                )
            )
            assert (
                row.origin_type == "existing_real_candidate_replay"
                and row.sent_attempts == 0
                and row.usage_json is None
            )
            assert (
                row.input_snapshot["replay"]["original_candidate_utf8"]
                == private["original_candidate_utf8"]
            )
            actual = deepcopy(row.input_snapshot["inputs"])
            for key, value in [("sent_attempts", 1), ("origin_type", "model_generation")]:
                old = getattr(row, key)
                setattr(row, key, value)
                with pytest.raises(SnapshotError):
                    validate_replay(row, actual)
                setattr(row, key, old)
            assert comparison_rule(row.response_json["blocks"][-1]) == TYPED_RULE
            count = await db.scalar(
                select(func.count())
                .select_from(FreeSceneGenerationResult)
                .where(FreeSceneGenerationResult.user_id == owner)
            )
            replay = await import_course(db, owner, slot)
            assert replay["imported"] is False and replay["course_id"] == cid
            assert count == await db.scalar(
                select(func.count())
                .select_from(FreeSceneGenerationResult)
                .where(FreeSceneGenerationResult.user_id == owner)
            )
            await db.commit()

        work(audit)
        with TestClient(app, base_url="https://testserver", cookies=client.cookies) as restored:
            assert restored.get(route).json() == view
            assert restored.get(root + "/attempts/" + aid).json() == attempt


def test_normal_model_generation_still_uses_existing_hard_gate():
    from test_free_scene_availability import make_validation, setup

    from app.models.auth import User

    async def action(db):
        owner = uuid4()
        db.add(User(id=owner, is_guest=True))
        await db.commit()
        _, cid, fence, pid, sids = await setup(db, owner, 1)
        result = await make_validation(db, owner, cid, fence, pid, sids[0], 1)
        from app.models.free_scene_validation import FreeSceneValidation

        assert (await db.get(FreeSceneValidation, result)).state == "accepted"
        row = await db.scalar(
            select(FreeSceneGenerationResult).where(FreeSceneGenerationResult.course_id == cid)
        )
        assert row.origin_type == "model_generation" and row.sent_attempts == 1

    work(action)


def test_database_rejects_forged_origin_attempt_and_usage_pairs():
    async def action(db):
        row = await db.scalar(
            select(FreeSceneGenerationResult).where(
                FreeSceneGenerationResult.origin_type == "existing_real_candidate_replay"
            )
        )
        assert row is not None
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        for origin, attempts, usage in [
            ("model_generation", 0, None),
            ("existing_real_candidate_replay", 1, None),
            ("existing_real_candidate_replay", 0, {"input_tokens": 1}),
            ("unknown", 0, None),
        ]:
            with pytest.raises(DBAPIError, match="ck_fc_scene_gen_sent"):
                async with db.begin_nested():
                    await db.execute(
                        insert(FreeSceneGenerationResult).values(
                            **{
                                **values,
                                "id": uuid4(),
                                "call_key": str(uuid4()),
                                "origin_type": origin,
                                "sent_attempts": attempts,
                                "usage_json": usage,
                            }
                        )
                    )

    work(action)
