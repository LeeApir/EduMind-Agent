"""Real PostgreSQL preparation API contracts; mock-only selected Provider sends."""

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from test_model_preferences import internal
from test_provider_connection_test_api import ORIGINAL_SEND, create, output
from test_provider_connections_api import guest, restore, schema, setup_api  # noqa: F401
from test_video_dsl_generation import PASS, candidate

from app.api import animation_generation as api
from app.main import app
from app.models.animation import AnimationJob
from app.models.animation_generation import AnimationPreparation
from app.models.learning import LearningScene, LearningUnit
from app.models.provider_model_snapshots import ProviderModelSnapshot
from app.services.animation_dsl_candidates import admit_current_policy

pytestmark = pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="dedicated PG required"
)


def target(users, token, kp="array"):
    async def seed(store, identity):
        async with store.factory() as db, db.begin():
            await admit_current_policy(db)
            unit = LearningUnit(user_id=identity.user_id, knowledge_point_id=kp, status="ready")
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id,
                scene_key="intro",
                scene_order=1,
                scene_type="video",
                version=1,
                generation_status="complete",
                review_status="passed",
            )
            db.add(scene)
            await db.flush()
            return str(unit.id), str(scene.id)

    return internal(users, token, seed)


def payload(scene, *, goal="compare"):
    return {
        "scene_id": scene,
        "scene_version": 1,
        "goal_kind": goal,
        "parameters": {"values": [1, 2]},
    }


def headers(csrf, *, key=None, operation=None):
    return {
        **csrf,
        "Idempotency-Key": key or str(uuid4()),
        "X-Animation-Operation-ID": operation or str(uuid4()),
    }


def done(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "private, no-store"
    events = [part for part in response.text.split("\n\n") if part.startswith("event: done\n")]
    assert len(events) == 1
    assert not any(
        secret in response.text
        for secret in (
            "execution_token",
            "originating_session",
            "canonical_dsl",
            "TEST_ONLY",
            "temporary_handle",
        )
    )
    snapshot = json.loads(events[0].split("data: ", 1)[1])
    schema("AnimationPreparation").validate(snapshot)
    return snapshot


def test_pg_api_default_budget_fail_closed_replay_owner_csrf_and_input(setup_api, monkeypatch):  # noqa: F811
    client, users, _ = setup_api
    token, csrf = guest(client, users)
    unit, scene = target(users, token)
    path = f"/api/learning-units/{unit}/animations/generate"
    h = headers(csrf)
    assert client.post(path, headers=h, json=payload(scene)).status_code == 409  # catalog_only
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    assert (
        client.post(
            path, headers={k: v for k, v in h.items() if k != "X-CSRF-Token"}, json=payload(scene)
        ).status_code
        == 403
    )
    for extra in (
        {"dsl": "exec(secret)"},
        {"owner": str(uuid4())},
        {"base_url": "http://localhost"},
    ):
        response = client.post(path, headers=h, json={**payload(scene), **extra})
        assert response.status_code == 422 and "exec(secret)" not in response.text
    bad = payload(scene)
    bad["parameters"] = {"values": [True, 2]}
    assert client.post(path, headers=h, json=bad).status_code == 422
    result = done(client.post(path, headers=h, json=payload(scene)))
    assert result["stage"] == "failed" and "job_id" not in result
    replay = done(
        client.post(
            path, headers={**h, "X-Animation-Operation-ID": str(uuid4())}, json=payload(scene)
        )
    )
    assert replay == result
    changed = payload(scene)
    changed["parameters"] = {"values": [2, 3]}
    assert client.post(path, headers=h, json=changed).status_code == 409
    assert client.get("/api/animation-preparations/" + result["id"]).json() == result
    guest(client, users)
    assert client.get("/api/animation-preparations/" + result["id"]).status_code == 404
    restore(client, token)

    async def inspect(store, identity):
        async with store.factory() as db:
            row = await db.get(AnimationPreparation, UUID(result["id"]))
            assert row.generation_attempts == row.review_attempts == 0
            assert (
                await db.scalar(select(AnimationJob).where(AnimationJob.generation_id == row.id))
                is None
            )

    internal(users, token, inspect)


def test_pg_api_selected_sse_handoff_and_version_cache_no_second_calls(
    setup_api,  # noqa: F811 -- shared real-PG fixture
    monkeypatch,
    tmp_path,  # noqa: F811 -- shared fixture
):  # noqa: F811
    client, users, _ = setup_api
    token, csrf = guest(client, users)
    cid = create(client, csrf)
    unit, scene = target(users, token)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_ANIMATION_CACHE_ROOT", str(tmp_path))

    async def configure(store, identity):
        async with store.factory() as db, db.begin():
            db.add(
                ProviderModelSnapshot(
                    connection_id=UUID(cid),
                    config_version=1,
                    refreshed_at=datetime.now(timezone.utc),
                    models=[
                        {
                            "id": "test-model",
                            "capabilities": {
                                "version": "explicit-api-test-v1",
                                "streaming": True,
                                "structured_output": True,
                                "source": "declared",
                            },
                        }
                    ],
                )
            )

    internal(users, token, configure)
    for profile in ("quality", "review"):
        response = client.put(
            "/api/model-preferences/" + profile,
            headers=csrf,
            json={
                "expected_version": 0,
                "route": {
                    "connection_id": cid,
                    "config_version": 1,
                    "model_id": "test-model",
                    "data_categories": ["learning_goal", "content_for_review"],
                },
                "fallbacks": [],
                "consent_accepted": True,
            },
        )
        assert response.status_code == 200, response.text
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        value = candidate("array").decode() if len(sent) % 2 else json.dumps(PASS)
        result = output(value)
        result["model"] = "test-model"
        return httpx.Response(200, json=result)

    class Budget:
        async def authorize(self, request, profile):
            pass  # Explicit test-only authorization; production default remains deny.

    app.dependency_overrides[api.dsl_call_budget] = lambda: Budget()
    app.dependency_overrides[api.dsl_transport] = lambda: httpx.MockTransport(handler)
    monkeypatch.setattr(httpx.AsyncClient, "send", ORIGINAL_SEND)
    jobs = []
    try:
        path = f"/api/learning-units/{unit}/animations/generate"
        # Freeze valid routes but retain the default denied budget: no HTTP sends.
        app.dependency_overrides.pop(api.dsl_call_budget)
        denied = done(client.post(path, headers=headers(csrf), json=payload(scene)))
        assert denied["stage"] == "failed" and not sent
        app.dependency_overrides[api.dsl_call_budget] = lambda: Budget()
        h = headers(csrf)
        first_response = client.post(path, headers=h, json=payload(scene))
        first = done(first_response)
        assert first["stage"] == "handed_off" and first["source"] == "generated_dsl"
        assert "compiled" in first_response.text
        assert len(sent) == 2
        assert done(client.post(path, headers=h, json=payload(scene))) == first
        second = done(client.post(path, headers=headers(csrf), json=payload(scene)))
        assert second["stage"] == "handed_off" and second["source"] == "reviewed_dsl_cache"
        assert len(sent) == 2 and second["job_id"] != first["job_id"]
        for receipt in (first, second):
            jobs.append(receipt["job_id"])
            job = client.get("/api/animation-jobs/" + receipt["job_id"])
            schema("AnimationJob").validate(job.json())
            assert job.status_code == 200 and job.json()["render_kind"] == "dsl"
            assert (
                job.json()["template_id"] is None and job.json()["generation_id"] == receipt["id"]
            )
            cancelled = client.post(
                "/api/animation-preparations/" + receipt["id"] + "/cancel",
                headers={**csrf, "Idempotency-Key": str(uuid4())},
            )
            assert cancelled.json() == receipt  # Handed-off Job uses its own cancel endpoint.

        async def disconnected(store, identity):
            from sqlalchemy.ext.asyncio import async_sessionmaker
            from starlette.requests import Request

            from app.core.auth import AuthenticatedSession
            from app.models.auth import GuestSessionRecord, User
            from app.services.animation_intent import VideoIntent
            from app.services.animation_job_qualification import current_animation_graph
            from app.services.animation_preparation import reserve_preparation

            store.factory = async_sessionmaker(store.factory.kw["bind"], expire_on_commit=False)
            graph = current_animation_graph()
            changed = VideoIntent("array", "compare", '{"values":[3,4]}')
            async with store.factory() as db:
                reserved = await reserve_preparation(
                    db,
                    graph,
                    owner=identity.user_id,
                    session_hash=identity.session_hash,
                    unit_id=UUID(unit),
                    scene_id=UUID(scene),
                    scene_version=1,
                    intent=changed,
                    idempotency_key=str(uuid4()),
                )
                current = AuthenticatedSession(
                    await db.get(User, identity.user_id),
                    await db.get(GuestSessionRecord, identity.session_hash),
                    "unused-internal-test",
                )
            started, interrupted = asyncio.Event(), asyncio.Event()

            async def blocked(request):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    interrupted.set()

            stream = api._preparation_events(
                reserved.operation,
                created=True,
                current=current,
                store=store,
                sessions=store.factory,
                intent=changed,
                request=Request({"type": "http", "app": app}),
                budget=Budget(),
                transport=httpx.MockTransport(blocked),
                quality_handle=None,
                review_handle=None,
            )
            await anext(stream)
            wait = asyncio.create_task(anext(stream))
            # stage_changed may precede the blocked transport; consume it without closing holder.
            while not started.is_set():
                if wait.done():
                    await wait
                    wait = asyncio.create_task(anext(stream))
                await asyncio.sleep(0.01)
            wait.cancel()
            await asyncio.gather(wait, return_exceptions=True)
            await stream.aclose()
            await asyncio.wait_for(interrupted.wait(), timeout=2)
            async with store.factory() as db:
                row = await db.get(AnimationPreparation, reserved.operation.id)
                assert row.stage == "cancelled" and row.job_id is None
                assert row.generation_attempts == 1 and row.review_attempts == 0

        internal(users, token, disconnected)
    finally:
        for job_id in jobs:
            response = client.post(
                "/api/animation-jobs/" + job_id + "/cancel",
                headers={**csrf, "Idempotency-Key": str(uuid4())},
            )
            assert response.status_code == 200, response.text
        app.dependency_overrides.pop(api.dsl_call_budget, None)
        app.dependency_overrides.pop(api.dsl_transport, None)


def test_pg_api_template_degradation_requires_explicit_request(setup_api, monkeypatch, tmp_path):  # noqa: F811
    client, users, _ = setup_api
    token, csrf = guest(client, users)
    unit, scene = target(users, token, "linked-list-insertion")
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_ANIMATION_CACHE_ROOT", str(tmp_path))
    body = payload(scene, goal="trace_insert")
    body["parameters"] = {"values": [1, 2], "index": 1, "value": 7}
    path = f"/api/learning-units/{unit}/animations/generate"
    denied = done(client.post(path, headers=headers(csrf), json=body))
    assert denied["stage"] == "failed" and "job_id" not in denied
    allowed = done(
        client.post(
            path,
            headers={**headers(csrf), "X-Animation-Allow-Template-Fallback": "true"},
            json=body,
        )
    )
    assert allowed["stage"] == "handed_off" and allowed["source"] == "template_fallback"
    job = client.get("/api/animation-jobs/" + allowed["job_id"]).json()
    assert job["render_kind"] == "template" and job["template_id"] == "linked-list-insertion"
    assert "fallback_reason_code" in job and "candidate_id" not in job
    assert (
        client.post(
            "/api/animation-jobs/" + job["id"] + "/cancel",
            headers={**csrf, "Idempotency-Key": str(uuid4())},
        ).status_code
        == 200
    )


def test_pg_original_post_disconnect_cancels_but_observer_disconnect_does_not(
    setup_api,  # noqa: F811 -- shared real-PG fixture
    monkeypatch,
):  # noqa: F811
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from starlette.requests import Request

    from app.core.auth import AuthenticatedSession
    from app.models.auth import GuestSessionRecord, User
    from app.services.animation_dsl_flow import UnavailableDSLCallBudget
    from app.services.animation_intent import VideoIntent
    from app.services.animation_job_qualification import current_animation_graph
    from app.services.animation_preparation import reserve_preparation

    client, users, _ = setup_api
    token, _ = guest(client, users)
    unit, scene = target(users, token)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise(store, identity):
        store.factory = async_sessionmaker(store.factory.kw["bind"], expire_on_commit=False)
        value = VideoIntent("array", "compare", '{"values":[1,2]}')
        async with store.factory() as db:
            reservation = await reserve_preparation(
                db,
                current_animation_graph(),
                owner=identity.user_id,
                session_hash=identity.session_hash,
                unit_id=UUID(unit),
                scene_id=UUID(scene),
                scene_version=1,
                intent=value,
                idempotency_key=str(uuid4()),
            )
            user = await db.get(User, identity.user_id)
            session = await db.get(GuestSessionRecord, identity.session_hash)
        current = AuthenticatedSession(user, session, "unused-internal-test")

        def stream(created):
            return api._preparation_events(
                reservation.operation,
                created=created,
                current=current,
                store=store,
                sessions=store.factory,
                intent=value,
                request=Request({"type": "http", "app": app}),
                budget=UnavailableDSLCallBudget(),
                transport=None,
                quality_handle=None,
                review_handle=None,
            )

        observer = stream(False)
        assert "agent_start" in await anext(observer)
        await observer.aclose()
        async with store.factory() as db:
            assert (
                await db.get(AnimationPreparation, reservation.operation.id)
            ).stage == "reserved"
        original = stream(True)
        await anext(original)
        import anyio

        with anyio.CancelScope() as scope:
            scope.cancel()
            await original.aclose()  # ASGI level cancellation must not abandon cleanup.
        await asyncio.sleep(0.1)
        async with store.factory() as db:
            row = await db.get(AnimationPreparation, reservation.operation.id)
            assert row.stage == "cancelled" and row.job_id is None
            assert row.generation_attempts == row.review_attempts == 0

    internal(users, token, exercise)
