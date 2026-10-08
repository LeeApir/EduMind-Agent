"""Independent DSL review, strict failures and real PG immutable qualification."""

import asyncio
import copy
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_provider_connection_test_api import ORIGINAL_SEND
from test_provider_connections_api import setup_api  # noqa: F401 -- shared PG lifecycle

from app.agents.animation_dsl_review import (
    DIRECTORY,
    PROMPT_SHA256,
    REVIEW_SCHEMA_SHA256,
    AnimationDSLReviewAgent,
    DSLReference,
    GenerationSource,
    ModelSource,
    ReviewCall,
    canonical,
    digest,
)
from app.core.database import create_database_engine
from app.models.animation_dsl import DSLCandidate, DSLReviewRecord
from app.models.auth import User
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_dsl_candidates import (
    DSLCandidateUnavailable,
    admit_current_policy,
    build_dsl_reference,
    qualified_candidate,
    revoke_candidate,
    revoke_policy,
    save_dsl_review,
)
from app.services.animation_dsl_validation import DSLValidationError
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredResult,
    TaskProfile,
)

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / "docs/agents/animation-dsl-v1/valid-all-actions.json").read_text()
GRAPH = KnowledgeGraphRepository.from_file(ROOT / "data/knowledge_graph.yaml")
SOURCE = ModelSource("openai-compatible", "review-model", "adapter-v1", "capability-v1", "a" * 64)
GENERATION = GenerationSource(replace(SOURCE, model_id="generation-model"), "b" * 64, "c" * 64)
PASS = {"review_version": "animation-dsl-review-v1", "verdict": "pass", "issues": []}
URL = os.getenv("EDUMIND_TEST_DATABASE_URL")


class FakeGateway:
    def __init__(self, value=None, *, error=None, model_id="review-model"):
        self.value = copy.deepcopy(PASS if value is None else value)
        self.error = error
        self.model_id = model_id
        self.calls = []

    async def review_structured(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return ReviewCall(StructuredResult(self.value, self.model_id), SOURCE)


def reference():
    target = {"scene_version": 1}
    return DSLReference(
        canonical(
            {
                "context_version": "animation-dsl-reference-v1",
                "target": target,
                "graph_version": "synthetic-v1",
                "node": {
                    "id": "arrays",
                    "description": "Arrays support indexed access.",
                    "learning_objectives": ["Compare and swap integer values."],
                },
                "prerequisites": [],
                "known_profile": {},
            }
        ),
        digest(target),
        "e" * 64,
        "arrays",
    )


def run_review(value=None, *, ref=None, raw=RAW, gateway=None):
    fake = gateway or FakeGateway(value)
    result = asyncio.run(
        AnimationDSLReviewAgent(fake).review(
            raw, reference=ref or reference(), generation_source=GENERATION
        )
    )
    return result, fake


def issue(**updates):
    return {
        "area": "complexity",
        "severity": "major",
        "action_index": 10,
        "message": "The displayed complexity does not match this operation.",
        **updates,
    }


def test_independent_complete_review_and_source_binding():
    outcome, fake = run_review()
    assert outcome.approved and len(fake.calls) == 1
    request = fake.calls[0]
    assert request.prompt.task_profile is TaskProfile.REVIEW
    assert request.prompt.max_output_tokens == 4096
    payload = json.loads(request.prompt.messages[1].content)
    assert payload["dsl"] == json.loads(RAW)
    assert len(payload["frames"]) == 11
    assert "compiled_source" not in payload
    assert "from manim import" not in request.prompt.messages[1].content
    assert payload["reference"]["known_profile"] == {}
    assert outcome.review_source.model_id != outcome.generation_source.source.model_id
    changed, second = run_review(raw=RAW)
    assert (
        changed.approved and len(second.calls) == 1
    )  # Each invocation independently calls review.
    assert hashlib.sha256((DIRECTORY / "prompt.md").read_bytes()).hexdigest() == PROMPT_SHA256
    assert (
        hashlib.sha256((DIRECTORY / "schema.json").read_bytes()).hexdigest() == REVIEW_SCHEMA_SHA256
    )
    assert (DIRECTORY / "prompt.md").read_bytes() == (
        ROOT / "docs/agents/prompts/animation-dsl-review-v1.md"
    ).read_bytes()


@pytest.mark.parametrize("verdict", ["revise", "reject"])
def test_educational_issue_retained_without_automatic_correction(verdict):
    result, fake = run_review({**PASS, "verdict": verdict, "issues": [issue()]})
    assert not result.approved and result.error_code is None
    assert result.issues[0].message == issue()["message"]
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "value",
    [
        {**PASS, "extra": "text"},
        {**PASS, "review_version": "other"},
        {**PASS, "issues": [issue()]},
        {**PASS, "verdict": "reject"},
        {**PASS, "verdict": "revise", "issues": [issue(action_index=True)]},
        {**PASS, "verdict": "revise", "issues": [issue(action_index=1.0)]},
        {**PASS, "verdict": "revise", "issues": [issue(action_index=11)]},
        {**PASS, "verdict": "revise", "issues": [issue(action_index=-1)]},
        {**PASS, "verdict": "revise", "issues": [issue(message=" ")]},
        {**PASS, "verdict": "revise", "issues": [issue(message="a" * 241)]},
        {**PASS, "verdict": "revise", "issues": [issue(message="e\u0301")]},
        {**PASS, "verdict": "revise", "issues": [issue(message="text\u202esecret")]},
        {**PASS, "verdict": "revise", "issues": [issue(message="https://private.invalid/secret")]},
        {**PASS, "verdict": "revise", "issues": [issue(message="sk-secretcontent123")]},
        {**PASS, "verdict": "revise", "issues": [issue(message="person@example.invalid")]},
        {**PASS, "verdict": "revise", "issues": [issue(message="See /Users/private/file")]},
        {
            **PASS,
            "verdict": "revise",
            "issues": [
                issue(),
            ]
            * 17,
        },
        {**PASS, "verdict": "unknown"},
    ],
)
def test_bad_output_unavailable_not_factual_rejection(value):
    result, fake = run_review(value)
    assert result.verdict == "unavailable" and not result.approved and result.issues == ()
    assert result.error_code == "DSL_REVIEW_UNAVAILABLE" and len(fake.calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        ProviderError(ProviderErrorCode.TIMEOUT),
        ProviderError(ProviderErrorCode.INVALID_OUTPUT),
        ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE),
    ],
)
def test_gateway_error_single_attempt(error):
    result, fake = run_review(gateway=FakeGateway(error=error))
    assert result.verdict == "unavailable" and len(fake.calls) == 1


def test_wrong_model_attribution_rejected():
    result, _ = run_review(gateway=FakeGateway(model_id="not-actual"))
    assert result.verdict == "unavailable"


def test_reference_missing_oversize_never_sent():
    for ref in (
        replace(reference(), serialized=""),
        replace(
            reference(),
            serialized=canonical(
                {"context_version": "animation-dsl-reference-v1", "text": "中" * 3000}
            ),
        ),
    ):
        result, fake = run_review(ref=ref)
        assert result.verdict == "unavailable" and fake.calls == []


def test_invalid_candidate_never_sent_and_no_code_execution(tmp_path):
    fake = FakeGateway()
    raw = json.loads(RAW)
    raw["actions"][0]["op"] = "exec"
    with pytest.raises(DSLValidationError):
        run_review(raw=canonical(raw), gateway=fake)
    assert fake.calls == []
    raw = json.loads(RAW)
    raw["actions"][0]["caption"] = "exec('raise RuntimeError()')"
    result, fake = run_review(raw=canonical(raw))
    assert result.approved and len(fake.calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_id", "https://secret.invalid"),
        ("adapter_version", "sk-secret"),
        ("target_sha256", "unknown"),
        ("provider_type", "unknown"),
        ("model_revision", "has spaces"),
    ],
)
def test_sources_closed_and_safe(field, value):
    with pytest.raises(ValueError, match="DSL_SOURCE_INVALID"):
        replace(SOURCE, **{field: value})


async def target(sessions):
    async with sessions() as db, db.begin():
        user = User(is_guest=True)
        db.add(user)
        await db.flush()
        unit = LearningUnit(user_id=user.id, knowledge_point_id="array", status="ready")
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
        return user.id, unit.id, scene.id


async def reviewed(sessions, ids, value=None):
    owner, unit, scene = ids
    async with sessions() as db:
        ref = await build_dsl_reference(
            db, GRAPH, owner=owner, unit_id=unit, scene_id=scene, version=1
        )
    return await AnimationDSLReviewAgent(FakeGateway(value)).review(
        RAW.replace('"arrays"', '"array"'), reference=ref, generation_source=GENERATION
    )


async def save(sessions, ids, result):
    owner, unit, scene = ids
    async with sessions() as db, db.begin():
        return await save_dsl_review(
            db, GRAPH, owner=owner, unit_id=unit, scene_id=scene, version=1, outcome=result
        )


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_candidate_owner_hash_immutability_failure_minimization_and_revoke():
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db, db.begin():
                policy = await admit_current_policy(db)
            ids = await target(sessions)
            result = await reviewed(sessions, ids)
            record, candidate = await save(sessions, ids, result)
            assert candidate is not None
            assert candidate.canonical_dsl == result.compiled.validated.canonical_json
            async with sessions() as db:
                found = await qualified_candidate(
                    db, GRAPH, owner=ids[0], candidate_id=candidate.id
                )
                assert found.id == candidate.id
                with pytest.raises(DSLCandidateUnavailable):
                    await qualified_candidate(db, GRAPH, owner=uuid4(), candidate_id=candidate.id)
            rejected = await reviewed(
                sessions, ids, {**PASS, "verdict": "reject", "issues": [issue()]}
            )
            failure, none = await save(sessions, ids, rejected)
            assert none is None and failure.issue_positions == [
                {"area": "complexity", "severity": "major", "action_index": 10}
            ]
            assert "message" not in canonical(failure.issue_positions)
            assert issue()["message"] not in canonical(failure.evidence)
            for statement in (
                "UPDATE animation_dsl_candidates SET canonical_dsl='{}' WHERE id=:id",
                "UPDATE animation_dsl_reviews SET verdict='pass' WHERE id=:review",
                "UPDATE animation_dsl_policies SET manifest='{}' WHERE id=:policy",
            ):
                async with sessions() as db:
                    with pytest.raises(DBAPIError, match="DSL_IMMUTABLE"):
                        await db.execute(
                            text(statement),
                            {"id": candidate.id, "review": failure.id, "policy": policy},
                        )
                    await db.rollback()
            async with sessions() as db, db.begin():
                await revoke_candidate(db, GRAPH, owner=ids[0], candidate_id=candidate.id)
            async with sessions() as db:
                with pytest.raises(DSLCandidateUnavailable):
                    await qualified_candidate(db, GRAPH, owner=ids[0], candidate_id=candidate.id)
                with pytest.raises(DBAPIError, match="DSL_REVOCATION_IMMUTABLE"):
                    await db.execute(
                        text(
                            "DELETE FROM animation_dsl_candidate_revocations WHERE candidate_id=:id"
                        ),
                        {"id": candidate.id},
                    )
                await db.rollback()
            # Same immutable bytes remain; no rewrite of historical pass after withdrawal.
            async with sessions() as db:
                assert (
                    await db.get(DSLCandidate, candidate.id)
                ).canonical_dsl == candidate.canonical_dsl
                assert (await db.get(DSLReviewRecord, record.id)).verdict == "pass"
            async with sessions() as db, db.begin():
                from sqlalchemy import delete

                await db.execute(delete(User).where(User.id == ids[0]))
            async with sessions() as db:
                assert await db.get(DSLCandidate, candidate.id) is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_repeat_is_new_review_and_changes_cannot_reuse_pass(monkeypatch):
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db, db.begin():
                await admit_current_policy(db)
            ids = await target(sessions)
            result = await reviewed(sessions, ids)
            values = await asyncio.gather(save(sessions, ids, result), save(sessions, ids, result))
            assert len({r.id for r, c in values}) == 2 and len({c.id for r, c in values}) == 2
            async with sessions() as db:
                with pytest.raises(DSLCandidateUnavailable):
                    await qualified_candidate(
                        db,
                        replace(GRAPH, graph_version="new-graph"),
                        owner=ids[0],
                        candidate_id=values[0][1].id,
                    )
            from app.services import animation_dsl_candidates as service

            original = service.policy_manifest
            with monkeypatch.context() as changed_policy:
                changed_policy.setattr(
                    service, "policy_manifest", lambda: {**original(), "version": "next-policy"}
                )
                async with sessions() as db:
                    with pytest.raises(DSLCandidateUnavailable):
                        await qualified_candidate(
                            db, GRAPH, owner=ids[0], candidate_id=values[0][1].id
                        )
            # Tampered source or binding cannot borrow old pass, even before DB insertion.
            for forged in (
                replace(result, binding_sha256="f" * 64),
                replace(
                    result, compiled=replace(result.compiled, source=result.compiled.source + "\n")
                ),
                replace(result, generation_source=replace(GENERATION, sampling_sha256="f" * 64)),
            ):
                with pytest.raises(DSLCandidateUnavailable):
                    await save(sessions, ids, forged)
            async with sessions() as db, db.begin():
                scene = await db.get(LearningScene, ids[2])
                scene.scene_key = "changed-target"
            with pytest.raises(DSLCandidateUnavailable):
                await save(sessions, ids, result)
            async with sessions() as db:
                with pytest.raises(DSLCandidateUnavailable):
                    await qualified_candidate(db, GRAPH, owner=ids[0], candidate_id=values[0][1].id)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_compound_foreign_keys_and_qualification_lock_race():
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db, db.begin():
                await admit_current_policy(db)
            ids = await target(sessions)
            other = await target(sessions)
            result = await reviewed(sessions, ids)
            record, candidate = await save(sessions, ids, result)
            async with sessions() as db:
                with pytest.raises(DBAPIError):
                    db.add(
                        DSLCandidate(
                            id=uuid4(),
                            user_id=other[0],
                            learning_unit_id=ids[1],
                            scene_id=ids[2],
                            scene_version=1,
                            review_id=record.id,
                            verdict="pass",
                            binding_sha256=record.binding_sha256,
                            policy_id=candidate.policy_id,
                            canonical_dsl=candidate.canonical_dsl,
                            trace_json=candidate.trace_json,
                            dsl_sha256=candidate.dsl_sha256,
                            trace_sha256=candidate.trace_sha256,
                        )
                    )
                    await db.flush()
                await db.rollback()
            # Qualification holds target/candidate/policy in publication order. Withdrawal waits.
            async with sessions() as held:
                await qualified_candidate(
                    held, GRAPH, owner=ids[0], candidate_id=candidate.id, lock=True
                )
                entered = asyncio.Event()

                async def revoke():
                    async with sessions() as db, db.begin():
                        entered.set()
                        await revoke_candidate(db, GRAPH, owner=ids[0], candidate_id=candidate.id)

                job = asyncio.create_task(revoke())
                await entered.wait()
                await asyncio.sleep(0.05)
                assert not job.done()
                await held.commit()
                await asyncio.wait_for(job, 2)
            async with sessions() as db:
                with pytest.raises(DSLCandidateUnavailable):
                    await qualified_candidate(db, GRAPH, owner=ids[0], candidate_id=candidate.id)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_changed_candidate_and_generation_versions_get_distinct_review_bindings():
    first, _ = run_review()
    raw = json.loads(RAW)
    raw["actions"][0]["caption"] = "创建第一个节点，值保持不变。"
    second, fake = run_review(raw=canonical(raw))
    assert second.approved and len(fake.calls) == 1
    assert second.binding_sha256 != first.binding_sha256
    assert second.review_sha256 != first.review_sha256

    async def changed():
        return await AnimationDSLReviewAgent(FakeGateway()).review(
            RAW,
            reference=reference(),
            generation_source=replace(GENERATION, prompt_sha256="f" * 64),
        )

    assert asyncio.run(changed()).binding_sha256 != first.binding_sha256


def test_cancelled_review_propagates_without_converting_to_pass():
    class Waiting:
        async def review_structured(self, request):
            await asyncio.sleep(3600)

    async def exercise():
        task = asyncio.create_task(
            AnimationDSLReviewAgent(Waiting()).review(
                RAW, reference=reference(), generation_source=GENERATION
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_source_safe_failure_positions_and_insert_binding_constraints():
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db, db.begin():
                await admit_current_policy(db)
            ids = await target(sessions)
            result = await reviewed(sessions, ids)
            record, candidate = await save(sessions, ids, result)
            raw = json.loads(candidate.canonical_dsl)
            raw["title"] = "changed after review"
            changed = canonical(raw)
            async with sessions() as db:
                with pytest.raises(DBAPIError, match="DSL_BINDING_MISMATCH"):
                    db.add(
                        DSLCandidate(
                            id=uuid4(),
                            user_id=ids[0],
                            learning_unit_id=ids[1],
                            scene_id=ids[2],
                            scene_version=1,
                            review_id=record.id,
                            verdict="pass",
                            binding_sha256=record.binding_sha256,
                            policy_id=candidate.policy_id,
                            canonical_dsl=changed,
                            trace_json=candidate.trace_json,
                            dsl_sha256=hashlib.sha256(changed.encode()).hexdigest(),
                            trace_sha256=candidate.trace_sha256,
                        )
                    )
                    await db.flush()
                await db.rollback()
                with pytest.raises(DBAPIError):
                    db.add(
                        DSLReviewRecord(
                            id=uuid4(),
                            user_id=ids[0],
                            learning_unit_id=ids[1],
                            scene_id=ids[2],
                            scene_version=1,
                            verdict="reject",
                            binding_sha256="a" * 64,
                            review_sha256="b" * 64,
                            evidence={},
                            issue_positions=[{**issue(), "message": "unreviewed private passage"}],
                        )
                    )
                    await db.flush()
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_policy_revoke_and_no_secret_readmission():
    # Last PG case retires this exact policy; future tests must use a fresh isolated DB.
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db, db.begin():
                policy = await admit_current_policy(db)
            ids = await target(sessions)
            result = await reviewed(sessions, ids)
            _, candidate = await save(sessions, ids, result)
            async with sessions() as db, db.begin():
                await revoke_policy(db, policy)
            async with sessions() as db:
                with pytest.raises(DSLCandidateUnavailable):
                    await qualified_candidate(db, GRAPH, owner=ids[0], candidate_id=candidate.id)
                with pytest.raises(DSLCandidateUnavailable):
                    await admit_current_policy(db)
                await db.rollback()
            with pytest.raises(DSLCandidateUnavailable):
                await save(sessions, ids, result)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
@pytest.mark.parametrize("deny_budget", [False, True])
def test_pg_selected_review_route_real_adapter_mock_only(
    setup_api,  # noqa: F811 -- shared fixture
    monkeypatch,
    deny_budget,
):
    import httpx
    from test_model_preferences import internal
    from test_provider_connection_test_api import Budget, create, output
    from test_provider_connections_api import guest

    from app.services.animation_dsl_review_gateway import SelectedDSLReviewGateway
    from app.services.provider_connection_dispatch import (
        ConnectionConsent,
        ConnectionRoute,
        DispatchRequest,
        ModelCapabilities,
    )

    client, users, dns = setup_api
    token, headers = guest(client, users)
    cid = create(client, headers)
    saved = client.put(
        "/api/model-preferences/review",
        headers=headers,
        json={
            "expected_version": 0,
            "route": {
                "connection_id": cid,
                "config_version": 1,
                "model_id": "review-model",
                "data_categories": ["content_for_review"],
            },
            "fallbacks": [],
            "consent_accepted": True,
        },
    )
    assert saved.status_code == 200, saved.text
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    budget = Budget(deny_attempt=deny_budget)
    sent = []

    def handler(request):
        sent.append(request)
        value = output(json.dumps(PASS))
        value["model"] = "review-model"
        return httpx.Response(200, json=value)

    # setup_api forbids unmocked HTTP. This test alone restores normal send with MockTransport.
    monkeypatch.setattr(httpx.AsyncClient, "send", ORIGINAL_SEND)

    async def exercise(store, identity):
        from uuid import UUID

        route = ConnectionRoute(UUID(cid), 1, "review-model", frozenset({"content_for_review"}))
        capabilities = ModelCapabilities(
            UUID(cid), 1, "review-model", "explicit-test-v1", structured_output=True
        )
        dispatch = DispatchRequest(
            identity, route, ConnectionConsent(route, True), capabilities, uuid4()
        )
        gateway = SelectedDSLReviewGateway(
            store, dispatch, budget.authorize_attempt, transport=httpx.MockTransport(handler)
        )
        return await AnimationDSLReviewAgent(gateway).review(
            RAW, reference=reference(), generation_source=GENERATION
        )

    result = internal(users, token, exercise)
    if deny_budget:
        assert not result.approved and result.error_code == "DSL_REVIEW_UNAVAILABLE" and not sent
    else:
        assert result.approved and len(sent) == 1 and len(budget.attempts) == 1
        assert result.review_source.provider_type == "openai-compatible"
        assert result.review_source.adapter_version.startswith("sha256:")
        assert result.review_source.capability_version == "explicit-test-v1"
        provenance = (
            canonical(result.review_source.__dict__)
            if hasattr(result.review_source, "__dict__")
            else str(result.review_source)
        )
        assert "provider.test" not in provenance and "TEST_ONLY" not in provenance
        assert json.loads(sent[0].content)["model"] == "review-model"


def test_reference_content_missing_mismatched_or_extra_fails_closed():
    for value in (
        {"context_version": "animation-dsl-reference-v1"},
        {**reference().payload(), "chat": "private"},
        {**reference().payload(), "known_profile": {"difficulty": "novice"}},
        {**reference().payload(), "target": {"scene_version": 2}},
    ):
        result, fake = run_review(ref=replace(reference(), serialized=canonical(value)))
        assert result.error_code == "DSL_REVIEW_UNAVAILABLE" and not fake.calls


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_read_refreshes_scene_qualification():
    # This test needs no admitted policy; checking target eligibility precedes policy lookup.
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids = await target(sessions)
            async with sessions() as held:
                scene = await held.get(LearningScene, ids[2])
                assert scene.review_status == "passed"
                async with sessions() as other, other.begin():
                    changed = await other.get(LearningScene, ids[2])
                    changed.review_status = "rejected"
                with pytest.raises(DSLCandidateUnavailable):
                    await build_dsl_reference(
                        held, GRAPH, owner=ids[0], unit_id=ids[1], scene_id=ids[2], version=1
                    )
                assert scene.review_status == "rejected"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")
def test_pg_migration_downgrade_refuses_existing_review_data():
    import re
    import subprocess
    import sys
    from urllib.parse import urlsplit

    assert re.fullmatch(r"/edumind_catalog_phase1_t025_[a-z0-9_]+", urlsplit(URL).path)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
    }
    response = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0022_animation_attempts"],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert response.returncode != 0 and "DSL_CANDIDATES_REQUIRE_DRAIN" in response.stderr

    async def exercise():
        engine = create_database_engine(URL)
        try:
            async with engine.connect() as db:
                assert (
                    await db.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0023_animation_dsl_reviews"
                )
                assert await db.scalar(text("SELECT count(*) FROM animation_dsl_reviews")) > 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())
