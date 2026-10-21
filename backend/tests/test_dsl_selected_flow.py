"""Selected-model API task and temporary operation leases; all sends use MockTransport."""

import json
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_dsl_animation_jobs import GRAPH, intent
from test_model_preferences import internal
from test_provider_connection_test_api import ORIGINAL_SEND, create, output
from test_provider_connections_api import guest, setup_api  # noqa: F401
from test_video_dsl_generation import PASS, REVISE, candidate

from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.models.learning import LearningScene, LearningUnit
from app.models.provider_model_snapshots import ProviderModelSnapshot
from app.services.animation_dsl_candidates import build_dsl_reference
from app.services.animation_dsl_flow import SelectedDSLFlow
from app.services.animation_preparation import reserve_preparation
from app.services.temporary_credentials import TemporaryCredentialService
from app.services.video_dsl_generation import VideoDSLPlanner

pytestmark = pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="dedicated PG required"
)


@pytest.mark.parametrize("mode", ["persistent", "temporary"])
@pytest.mark.parametrize("same_model", [True, False])
def test_pg_selected_flow_independent_review_corrections_and_single_temporary_lease(
    setup_api,  # noqa: F811 -- shared real-PG fixture
    monkeypatch,
    mode,
    same_model,  # noqa: F811 -- imported real PG fixture
):
    client, users, _ = setup_api
    token, headers = guest(client, users)
    cid = create(client, headers, mode=mode)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    sent, profiles = [], []

    class Budget:
        async def authorize(self, request, profile):
            profiles.append(profile.value)

    async def configure(store, identity):
        async with store.factory() as db, db.begin():
            db.add(
                ProviderModelSnapshot(
                    connection_id=UUID(cid),
                    config_version=1,
                    refreshed_at=datetime.now(timezone.utc),
                    models=[
                        {
                            "id": model,
                            "capabilities": {
                                "version": "explicit-flow-test-v1",
                                "streaming": True,
                                "structured_output": True,
                                "source": "declared",
                            },
                        }
                        for model in ("generation-model", "review-model")
                    ],
                )
            )

    internal(users, token, configure)
    for profile in ("quality", "review"):
        result = client.put(
            "/api/model-preferences/" + profile,
            headers=headers,
            json={
                "expected_version": 0,
                "route": {
                    "connection_id": cid,
                    "config_version": 1,
                    "model_id": "generation-model"
                    if same_model or profile == "quality"
                    else "review-model",
                    "data_categories": ["learning_goal", "content_for_review"],
                },
                "fallbacks": [],
                "consent_accepted": True,
            },
        )
        assert result.status_code == 200, result.text

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        # Explicit sequence proves review is a separate call even when its model is the same.
        position = len(sent)
        value = (
            candidate("array").decode()
            if position in (1, 3)
            else json.dumps(REVISE if position == 2 else PASS)
        )
        response = output(value)
        response["model"] = body["model"]
        return httpx.Response(200, json=response)

    monkeypatch.setattr(httpx.AsyncClient, "send", ORIGINAL_SEND)

    async def exercise(store, identity):
        store.factory = async_sessionmaker(store.factory.kw["bind"], expire_on_commit=False)
        registry = TemporaryCredentialRegistry()
        operation_id = uuid4()
        quality_handle = review_handle = None
        unrelated = None
        if mode == "temporary":
            service = TemporaryCredentialService(store, registry)
            quality_handle, _ = await service.register(
                identity,
                UUID(cid),
                1,
                operation_id,
                "generation",
                "generation-model",
                {"api_key": "TEST_ONLY_FLOW_KEY"},
            )
            unrelated, _ = await service.register(
                identity,
                UUID(cid),
                1,
                operation_id,
                "model_refresh",
                "generation-model",
                {"api_key": "TEST_ONLY_UNRELATED_PURPOSE"},
            )
            if not same_model:
                review_handle, _ = await service.register(
                    identity,
                    UUID(cid),
                    1,
                    operation_id,
                    "generation",
                    "review-model",
                    {"api_key": "TEST_ONLY_FLOW_REVIEW_KEY"},
                )
        async with store.factory() as db, db.begin():
            unit = LearningUnit(
                user_id=identity.user_id, knowledge_point_id="array", status="ready"
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id,
                scene_key="animation",
                scene_order=1,
                scene_type="video",
                version=1,
                generation_status="complete",
                review_status="passed",
            )
            db.add(scene)
            await db.flush()
            unit_id, scene_id = unit.id, scene.id
            reference = await build_dsl_reference(
                db, GRAPH, owner=identity.user_id, unit_id=unit_id, scene_id=scene_id, version=1
            )
        async with store.factory() as db:
            reserved = await reserve_preparation(
                db,
                GRAPH,
                owner=identity.user_id,
                session_hash=identity.session_hash,
                unit_id=unit_id,
                scene_id=scene_id,
                scene_version=1,
                intent=intent(),
                idempotency_key=str(uuid4()),
                operation_id=operation_id,
            )
        flow = SelectedDSLFlow(
            store,
            GRAPH,
            reserved.operation,
            identity,
            Budget(),
            quality_handle=quality_handle,
            review_handle=review_handle,
            registry=registry,
            transport=httpx.MockTransport(handler),
        )
        try:
            frozen = await flow.freeze_sources()
            result = await VideoDSLPlanner(flow.generator()).plan(
                intent(), reference=reference, dynamic_allowed=True
            )
            assert result.source == "generated_dsl" and result.candidates == 2
            assert (result.outcome.generation_source.source, result.outcome.review_source) == frozen
            async with store.factory() as db:
                from app.models.animation_generation import AnimationPreparation

                row = await db.get(AnimationPreparation, operation_id)
                assert row.generation_attempts == 2 and row.review_attempts == 2
                assert row.stage == "reviewing"
        finally:
            await flow.close()
            if unrelated is not None:
                assert set(registry._entries) == {unrelated}
                registry.retire_operation(
                    identity.user_id, identity.session_hash, operation_id, purpose="model_refresh"
                )
            assert not registry._entries
            await registry.close()
        assert profiles == ["quality", "review", "quality", "review"]
        assert len(sent) == 4 and not any("TEST_ONLY_FLOW" in json.dumps(body) for body in sent)

    internal(users, token, exercise)
