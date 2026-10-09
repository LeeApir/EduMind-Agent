"""Real PG two-attempt recovery, original-session fallback gates and queue migration."""

import asyncio
import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_animation_dsl_review import GENERATION, GRAPH, AnimationDSLReviewAgent, FakeGateway
from test_dsl_animation_jobs import setup
from test_video_dsl_generation import candidate

from app.agents.animation_dsl_review import digest
from app.core.database import create_database_engine
from app.models.animation import AnimationDispatchOutbox, AnimationJob, AnimationJobEvent
from app.models.auth import GuestSessionRecord
from app.models.learning import LearningUnit, utc_now
from app.services.animation_dsl_candidates import (
    admit_current_policy,
    build_dsl_reference,
    revoke_candidate,
)
from app.services.animation_dsl_failure import authorized_template_fallback, settle_dsl_failure
from app.services.animation_dsl_handoff import handoff_video_plan
from app.services.animation_intent import VideoIntent
from app.services.animation_preparation import reserve_preparation
from app.services.animation_worker import _locked_current_job, claim_animation_job
from app.services.durable_job_dispatch import DispatchMessage, route_queued_template_jobs
from app.services.video_dsl_generation import VideoPlan

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="dedicated PostgreSQL required")


@pytest.mark.parametrize("gate", ["allowed", "expired", "optout", "withdrawn"])
def test_pg_two_claims_then_one_distinct_template_and_original_session_gates(monkeypatch, gate):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids, session_hash = await setup(sessions)
            intent = VideoIntent(
                "linked-list-insertion",
                "insert",
                json.dumps({"values": [1, 2], "index": 1, "value": 7}),
                "detailed_trace",
            )
            async with sessions() as db, db.begin():
                unit = await db.get(LearningUnit, ids[1])
                unit.knowledge_point_id = intent.knowledge_point_id
                await admit_current_policy(db)
            async with sessions() as db:
                reserved = await reserve_preparation(
                    db,
                    GRAPH,
                    owner=ids[0],
                    session_hash=session_hash,
                    unit_id=ids[1],
                    scene_id=ids[2],
                    scene_version=1,
                    intent=intent,
                    idempotency_key=str(uuid4()),
                    allow_template_fallback=gate != "optout",
                )
                ref = await build_dsl_reference(
                    db, GRAPH, owner=ids[0], unit_id=ids[1], scene_id=ids[2], version=1
                )
            outcome = await AnimationDSLReviewAgent(FakeGateway()).review(
                candidate(intent.knowledge_point_id).decode(),
                reference=ref,
                generation_source=GENERATION,
                animation_intent=intent.payload(),
            )
            assert outcome.approved
            async with sessions() as db:
                job = await handoff_video_plan(
                    db,
                    GRAPH,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=reserved.operation.id,
                    execution_token=reserved.operation.execution_token,
                    plan=VideoPlan(
                        "generated_dsl",
                        digest({"intent": intent.payload(), "reference": ref.sha256}),
                        outcome=outcome,
                    ),
                )
            assert job is not None
            original = (job.candidate_id, job.source_sha256, job.cache_key, job.render_kind)
            assert await route_queued_template_jobs(sessions, (job.id,), backend="celery") == 1
            assert await route_queued_template_jobs(sessions, (job.id,), backend="pg_poll") == 1
            assert await route_queued_template_jobs(sessions, (job.id,), backend="celery") == 1
            for attempt in (1, 2):
                async with sessions() as db:
                    current = await db.get(AnimationJob, job.id)
                    epoch = current.dispatch_epoch
                lease = await claim_animation_job(sessions, message=DispatchMessage(job.id, epoch))
                assert lease is not None and lease.attempt == attempt
                if attempt == 2 and gate in {"expired", "withdrawn"}:
                    async with sessions() as db, db.begin():
                        if gate == "expired":
                            session = await db.get(GuestSessionRecord, session_hash)
                            session.expires_at = utc_now() - timedelta(seconds=1)
                            # A later live session of the same owner cannot authorize fallback.
                            db.add(
                                GuestSessionRecord(
                                    token_hash=uuid4().hex * 2,
                                    user_id=ids[0],
                                    created_at=utc_now(),
                                    expires_at=utc_now() + timedelta(hours=1),
                                )
                            )
                        else:
                            await revoke_candidate(
                                db,
                                GRAPH,
                                owner=ids[0],
                                candidate_id=job.candidate_id,
                                reason="SAFETY_WITHDRAWN",
                            )
                async with sessions() as db:
                    current = await _locked_current_job(db, lease)
                    assert current is not None
                    await settle_dsl_failure(db, current, code="DSL_RENDER_FAILED")
                    await db.commit()
                async with sessions() as db:
                    current = await db.get(AnimationJob, job.id)
                    assert (
                        current.candidate_id,
                        current.source_sha256,
                        current.cache_key,
                        current.render_kind,
                    ) == original
                    assert current.attempt == attempt and current.status == (
                        "queued" if attempt == 1 else "failed"
                    )
            async with sessions() as db:
                current = await db.get(AnimationJob, job.id, with_for_update=True)
                repeated = await authorized_template_fallback(db, current)
                await db.commit()
                children = (
                    await db.scalars(select(AnimationJob).where(AnimationJob.fallback_of == job.id))
                ).all()
                assert len(children) == (1 if gate == "allowed" else 0)
                events = (
                    await db.scalars(
                        select(AnimationJobEvent).where(AnimationJobEvent.job_id == job.id)
                    )
                ).all()
                last = max(events, key=lambda row: row.event_id)
                if gate == "allowed":
                    child = children[0]
                    assert (
                        repeated.id == child.id
                        and child.render_kind == "template"
                        and child.candidate_id is None
                    )
                    assert child.parameters == {"values": [1, 2], "index": 1, "value": 7}
                    assert last.payload["fallback_job_id"] == str(child.id)
                    assert (
                        child.generation_id == reserved.operation.id
                        and child.fallback_reason_code == "DSL_RENDER_FAILED"
                    )

                    async def replay_fallback():
                        async with sessions() as other:
                            parent = await other.get(AnimationJob, job.id, with_for_update=True)
                            repeated_child = await authorized_template_fallback(other, parent)
                            await other.commit()
                            return repeated_child.id

                    assert await asyncio.gather(replay_fallback(), replay_fallback()) == [
                        child.id,
                        child.id,
                    ]
                    assert await authorized_template_fallback(db, child) is None  # No cycle.
                    # Retire the fixture child after assertions, keeping the test queue clean.
                    if child.dispatch_backend == "celery":
                        assert await db.scalar(
                            select(AnimationDispatchOutbox.id).where(
                                AnimationDispatchOutbox.job_id == child.id
                            )
                        )
                    child.status = "failed"
                    child.error_code = "RENDER_FAILED"
                    await db.commit()
                else:
                    assert repeated is None and "fallback_job_id" not in last.payload
        finally:
            await engine.dispose()

    asyncio.run(exercise())
