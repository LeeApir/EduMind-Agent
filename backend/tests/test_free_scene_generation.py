"""Mock generation and actual private PG audit; no model-quality or public-ready claim."""

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_free_course_planning import candidate as plan_candidate

from app.agents.free_scene_generation import SCHEMA, generate_once
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, WriteFence
from app.services.free_scene_generation import load_inputs, persist_outcome
from app.services.learning_stage_gateway import LearningStageGateway
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredResult,
    TokenUsage,
)

ROOT = Path(__file__).resolve().parents[2]
GOAL = "学习数组与单链表，解释代码并完成练习"


def response(forms=None):
    forms = set(forms or ["text", "code", "exercise", "visualization"])
    blocks = [dict(kind="text", anchor_id="t", markdown="合成教学正文；不是已验证的真实课程。")]
    if "code" in forms:
        blocks.append(dict(kind="code", anchor_id="c", language="c", source="int value = 1;"))
    if "exercise" in forms:
        blocks.append(
            dict(
                kind="exercise",
                anchor_id="e",
                exercise_key="practice",
                question="合成题组",
                items=[
                    dict(
                        question_id=f"q{i}",
                        question=f"合成题{i}",
                        input_type="short_text",
                        answer_key=f"{i}",
                        solution="合成参考解释",
                    )
                    for i in range(2)
                ],
            )
        )
    if "visualization" in forms:
        blocks.append(
            dict(
                kind="visualization",
                anchor_id="v",
                visualization_type="array",
                text_alternative="一个元素",
                steps=[
                    dict(
                        caption="显示元素",
                        elements=[dict(id="x", label="1", next_id=None)],
                        highlight_ids=["x"],
                    )
                ],
            )
        )
    return dict(
        blocks=blocks, actions=[dict(type="highlight_block", anchor_id="t", step_index=None)]
    )


def inputs(n=3, forms=None):
    plan = plan_candidate(n, GOAL)["plan"]
    for i, s in enumerate(plan["scenes"]):
        s["scene_id"] = str(uuid4())
        s["forms"] = forms or ["text", "code", "exercise", "visualization"]
        s["depends_on"] = [] if i == 0 else [plan["scenes"][i - 1]["scene_id"]]
    rid = str(uuid4())
    return dict(
        request=dict(
            original_goal=GOAL,
            teaching_language="zh-CN",
            code_language="C",
            learner_evidence={"knowledge_base": None},
            request_sources={"request_1": dict(text=GOAL, request_id=rid, version=1)},
        ),
        plan=plan,
        scene_id=plan["scenes"][-1]["scene_id"],
        expected_head=None,
        upstream=[],
        lease_epoch=1,
    )


class Gateway:
    def __init__(self, value=None, error=None, delay=0, usage=None):
        self.value = deepcopy(response() if value is None else value)
        self.error = error
        self.delay = delay
        self.usage = usage
        self.requests = []

    async def generate_structured(self, request, *, retry_safe=False):
        assert retry_safe is False
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return StructuredResult(deepcopy(self.value), "synthetic-test-provider", usage=self.usage)


async def authorize(_request):
    """Mock reservation only, not the T014 durable budget/attempt implementation."""


@pytest.mark.parametrize("n", range(1, 9))
def test_variable_scene_request_preserves_goals_shared_conventions_and_private_forms(n):
    data = inputs(n)
    g = Gateway()
    result = asyncio.run(generate_once(g, data, authorize_send=authorize))
    assert result.state == "candidate" and result.sent_attempts == 1 and result.usage is None
    assert len(g.requests) == 1 and g.requests[0].stage == "free_scene_generation"
    req = g.requests[0]
    assert req.prompt.max_output_tokens == 8000
    payload = json.loads(req.prompt.messages[1].content)
    assert payload["request"]["original_goal"] == GOAL
    assert payload["request"]["learner_evidence"]["knowledge_base"] is None
    assert payload["plan"]["shared_example"] == data["plan"]["shared_example"]
    assert payload["plan"]["terminology"] == data["plan"]["terminology"]
    assert payload["plan"]["conventions"] == data["plan"]["conventions"]
    assert payload["scene_id"] == data["scene_id"]
    assert {b["kind"] for b in result.response["blocks"]} == {
        "text",
        "code",
        "exercise",
        "visualization",
    }
    assert result.response["blocks"][2]["items"][0]["answer_key"] == "0"


@pytest.mark.parametrize(
    "forms", [["text"], ["code"], ["exercise"], ["visualization"], ["text", "exercise"]]
)
def test_forms_mix_is_assigned_not_fixed_to_three_scenes(forms):
    g = Gateway(response(forms))
    result = asyncio.run(generate_once(g, inputs(forms=forms), authorize_send=authorize))
    assert result.state == "candidate"
    assert {b["kind"] for b in result.response["blocks"]} == set(forms) | {"text"}


def test_schema_shared_blocks_match_approved_contract():
    approved = json.loads((ROOT / "docs/api/phase-1.5-generation.openapi.json").read_text())[
        "components"
    ]["schemas"]
    for key in [
        "TextBlock",
        "CodeBlock",
        "VisualElement",
        "VisualStep",
        "VisualizationBlock",
        "Action",
    ]:
        actual = json.loads(
            json.dumps(SCHEMA["$defs"][key]).replace("#/$defs/", "#/components/schemas/")
        )
        assert actual == approved[key]


@pytest.mark.parametrize(
    "mode",
    [
        "blank",
        "no_text",
        "extra",
        "wrong_language",
        "too_many_blocks",
        "too_many_questions",
        "missing_answer",
        "duplicate_question",
        "duplicate_exercise",
        "oversize",
        "unplanned",
        "no_code",
        "missing_form",
        "too_many_steps",
        "too_many_elements",
    ],
)
def test_malformed_candidates_are_retained_privately_without_fake_ready(mode):
    raw = response()
    data = inputs()
    if mode == "blank":
        raw["blocks"][0]["markdown"] = " "
    if mode == "no_text":
        raw["blocks"] = raw["blocks"][1:]
    if mode == "extra":
        raw["owner_id"] = str(uuid4())
    if mode == "wrong_language":
        raw["blocks"][1]["language"] = "python"
    if mode == "too_many_blocks":
        raw["blocks"] = raw["blocks"] * 9
    if mode == "too_many_questions":
        raw["blocks"][2]["items"] *= 3
    if mode == "missing_answer":
        raw["blocks"][2]["items"][0].pop("answer_key")
    if mode == "duplicate_question":
        raw["blocks"][2]["items"][1]["question_id"] = "q0"
    if mode == "duplicate_exercise":
        raw["blocks"].append(deepcopy(raw["blocks"][2]))
    if mode == "oversize":
        raw["blocks"][0]["markdown"] = "x" * 65536
    if mode == "unplanned":
        data = inputs(forms=["text"])
    if mode == "no_code":
        data["request"]["code_language"] = None
    if mode == "missing_form":
        raw["blocks"].pop(1)
    if mode == "too_many_steps":
        raw["blocks"][3]["steps"] *= 51
    if mode == "too_many_elements":
        raw["blocks"][3]["steps"][0]["elements"] *= 33
    g = Gateway(raw)
    result = asyncio.run(generate_once(g, data, authorize_send=authorize))
    assert (
        result.state == "failed"
        and result.reason_code == "SCHEMA_INVALID"
        and result.sent_attempts == 1
    )
    assert len(g.requests) == 1
    assert result.response == (None if mode == "oversize" else raw)


@pytest.mark.parametrize(
    "code,reason",
    [
        (ProviderErrorCode.AUTHENTICATION_FAILED, "PROVIDER_REJECTED"),
        (ProviderErrorCode.CAPABILITY_UNAVAILABLE, "PROVIDER_REJECTED"),
        (ProviderErrorCode.INVALID_OUTPUT, "SCHEMA_INVALID"),
        (ProviderErrorCode.RATE_LIMITED, "OUTCOME_UNKNOWN"),
        (ProviderErrorCode.TIMEOUT, "OUTCOME_UNKNOWN"),
        (ProviderErrorCode.TEMPORARILY_UNAVAILABLE, "OUTCOME_UNKNOWN"),
    ],
)
def test_provider_failures_do_not_retry_or_fallback(code, reason):
    g = Gateway(error=ProviderError(code))
    result = asyncio.run(generate_once(g, inputs(), authorize_send=authorize))
    assert result.state == "failed" and result.reason_code == reason and result.response is None
    assert result.usage is None and len(g.requests) == result.sent_attempts == 1


def test_timeout_cancel_and_authorization_do_not_create_hidden_sends():
    g = Gateway(delay=0.05)
    result = asyncio.run(
        generate_once(g, inputs(), authorize_send=authorize, timeout_seconds=0.001)
    )
    assert result.reason_code == "OUTCOME_UNKNOWN" and len(g.requests) == 1
    cancelled = Gateway(error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(generate_once(cancelled, inputs(), authorize_send=authorize))
    denied = Gateway()

    async def deny(_request):
        raise SnapshotError("BUDGET_EXHAUSTED")

    with pytest.raises(SnapshotError, match="BUDGET_EXHAUSTED"):
        asyncio.run(generate_once(denied, inputs(), authorize_send=deny))
    assert not denied.requests

    async def change(request):
        request.json_schema["additionalProperties"] = True

    with pytest.raises(SnapshotError, match="SCENE_REQUEST_CHANGED"):
        asyncio.run(generate_once(denied, inputs(), authorize_send=change))
    assert not denied.requests


def test_large_context_is_refused_without_truncation_or_send():
    data = inputs()
    data["request"]["original_goal"] = "x" * 128001
    g = Gateway()
    with pytest.raises(SnapshotError, match="SCENE_INPUT_TOO_LARGE"):
        asyncio.run(generate_once(g, data, authorize_send=authorize))
    assert not g.requests


@pytest.mark.parametrize("field,value", [("teaching_language", "en"), ("code_language", "Python")])
def test_unsupported_languages_are_rejected_before_send(field, value):
    data = inputs()
    data["request"][field] = value
    g = Gateway()
    with pytest.raises(SnapshotError, match="SCENE_LANGUAGE_UNSUPPORTED"):
        asyncio.run(generate_once(g, data, authorize_send=authorize))
    assert not g.requests


def test_usage_is_exact_or_unknown_and_stage_is_generation_only():
    generation = Gateway(usage=TokenUsage(input_tokens=123, output_tokens=456))
    review = Gateway(error=AssertionError("no review"))
    result = asyncio.run(
        generate_once(LearningStageGateway(generation, review), inputs(), authorize_send=authorize)
    )
    assert result.usage == dict(input_tokens=123, output_tokens=456) and not review.requests


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual dedicated PG required, no skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t010_")
    return value


@pytest.fixture(scope="module", autouse=True)
def migrate_database():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def exercise(action):
    async def run():
        engine = create_database_engine(database_url())
        owners = [uuid4(), uuid4()]
        try:
            async with AsyncSession(engine) as db:
                db.add_all([User(id=u, is_guest=True) for u in owners])
                await db.commit()
            await action(engine, *owners)
        finally:
            async with engine.begin() as conn:
                for u in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
            await engine.dispose()

    asyncio.run(run())


async def prepare(db, owner, *, ready=2):
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(GOAL, key="create")
    cid = UUID(created["course_id"])
    oid = UUID(created["operation_id"])
    fence = await repo.acquire_write_fence(cid, oid)
    plan = plan_candidate(4, GOAL)["plan"]
    for s in plan["scenes"]:
        s["forms"] = ["text", "code", "exercise", "visualization"]
    plan["scenes"][3]["depends_on"] = []
    result = await repo.store_plan(cid, fence, expected_head=None, key="plan", candidate=plan)
    pid = UUID(result["plan_id"])
    stored = await repo.get_plan(cid, pid)
    bindings = []
    dependency_refs = {}
    for i, s in enumerate(stored["scenes"]):
        if i < ready:
            saved = await repo.store_scene(
                cid,
                fence,
                expected_head=None,
                key=f"scene-{i}",
                plan_id=pid,
                scene_id=UUID(s["scene_id"]),
                content=dict(
                    blocks=[dict(kind="text", anchor_id="t", markdown=f"actual upstream {i}")]
                ),
                actions=[],
                dependencies=[dependency_refs[d] for d in s["depends_on"]],
            )
            version_id = UUID(saved["scene_version_id"])
            row = await db.get(FreeCourseSceneVersion, version_id)
            dependency_refs[s["scene_id"]] = dict(
                scene_id=s["scene_id"],
                scene_version_id=str(version_id),
                content_digest=row.content_digest,
            )
            bindings.append(version_id)
        else:
            bindings.append(None)
    await repo.commit_manifest(
        cid, fence, expected_head=None, key="manifest", plan_id=pid, bindings=bindings
    )
    await db.commit()
    return repo, cid, fence, pid, stored, bindings


def test_actual_upstream_and_private_candidate_audit_survive_replay_without_publishing():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, plan, bindings = await prepare(db, owner)
            sid = UUID(plan["scenes"][2]["scene_id"])
            data = await load_inputs(
                db, owner, cid, fence.operation_id, plan_id=pid, scene_id=sid, expected_head=1
            )
            assert len(data["upstream"]) == 2
            assert data["upstream"][0]["content"]["blocks"][0]["markdown"] == "actual upstream 0"
            assert data["upstream"][1]["content"]["blocks"][0]["markdown"] == "actual upstream 1"
        g = Gateway(usage=TokenUsage(input_tokens=123, output_tokens=456))
        result = await generate_once(g, data, authorize_send=authorize)
        assert json.loads(g.requests[0].prompt.messages[1].content)["upstream"] == data["upstream"]
        async with AsyncSession(engine) as db:
            saved = await persist_outcome(
                db, owner, cid, fence, call_key="primary", inputs=data, outcome=result
            )
            again = await persist_outcome(
                db, owner, cid, fence, call_key="primary", inputs=data, outcome=result
            )
            assert saved == again and len(g.requests) == 1
            await db.commit()
        async with AsyncSession(engine) as db:
            row = await db.get(FreeSceneGenerationResult, UUID(saved["result_id"]))
            assert row.state == "candidate" and row.sent_attempts == 1
            assert row.response_json == response() and row.input_snapshot == data
            assert row.usage_json == dict(input_tokens=123, output_tokens=456)
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 2
            operation = await db.get(FreeCourseOperation, fence.operation_id)
            assert operation.state == "running"
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "UPDATE free_course_scene_generation_results "
                            "SET state='failed' WHERE id=:i"
                        ),
                        {"i": row.id},
                    )
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(
                        text("DELETE FROM free_course_scene_generation_results WHERE id=:i"),
                        {"i": row.id},
                    )
        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0036_free_course_planning"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            downgrade.returncode != 0 and "free course data prevents downgrade" in downgrade.stderr
        )

    exercise(action)


@pytest.mark.parametrize("mode", ["provider", "schema", "timeout"])
def test_failed_candidates_are_private_audit_not_operation_success(mode):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, plan, bindings = await prepare(db, owner)
            data = await load_inputs(
                db,
                owner,
                cid,
                fence.operation_id,
                plan_id=pid,
                scene_id=UUID(plan["scenes"][2]["scene_id"]),
                expected_head=1,
            )
        g = (
            Gateway(error=ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED))
            if mode == "provider"
            else Gateway({"blocks": [], "actions": []})
            if mode == "schema"
            else Gateway(delay=0.05)
        )
        result = await generate_once(
            g, data, authorize_send=authorize, timeout_seconds=0.001 if mode == "timeout" else 120
        )
        async with AsyncSession(engine) as db:
            saved = await persist_outcome(
                db, owner, cid, fence, call_key="failed", inputs=data, outcome=result
            )
            await db.commit()
            row = await db.get(FreeSceneGenerationResult, UUID(saved["result_id"]))
            assert row.state == "failed" and row.reason_code in {
                "SCHEMA_INVALID",
                "PROVIDER_REJECTED",
                "OUTCOME_UNKNOWN",
            }
            assert row.response_json == (
                {"blocks": [], "actions": []} if mode == "schema" else None
            )
            assert row.usage_json is None
            assert (await db.get(FreeCourseOperation, fence.operation_id)).state == "running"
            assert (await repo.get_course(cid))["head_version"] == 1

    exercise(action)


def test_missing_necessary_dependency_blocks_only_dependent_scene():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, plan, bindings = await prepare(db, owner, ready=0)
            with pytest.raises(SnapshotError, match="DEPENDENCY_UNAVAILABLE"):
                await load_inputs(
                    db,
                    owner,
                    cid,
                    fence.operation_id,
                    plan_id=pid,
                    scene_id=UUID(plan["scenes"][2]["scene_id"]),
                    expected_head=1,
                )
            for i in [0, 3]:
                data = await load_inputs(
                    db,
                    owner,
                    cid,
                    fence.operation_id,
                    plan_id=pid,
                    scene_id=UUID(plan["scenes"][i]["scene_id"]),
                    expected_head=1,
                )
                assert data["upstream"] == []
                result = await generate_once(Gateway(), data, authorize_send=authorize)
                assert result.state == "candidate"

    exercise(action)


@pytest.mark.parametrize(
    "mode",
    [
        "owner",
        "forged_goal",
        "forged_dependency",
        "changed_response",
        "cancel",
        "expired",
        "stale",
        "rollback",
        "new_epoch",
    ],
)
def test_owner_input_result_and_fence_rejection_are_atomic(mode):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, plan, bindings = await prepare(db, owner)
            sid = UUID(plan["scenes"][2]["scene_id"])
            data = await load_inputs(
                db, owner, cid, fence.operation_id, plan_id=pid, scene_id=sid, expected_head=1
            )
        if mode == "forged_goal":
            data["request"]["original_goal"] = "forged"
        if mode == "forged_dependency":
            data["upstream"][0]["content"]["blocks"][0]["markdown"] = "forged"
        result = await generate_once(Gateway(), data, authorize_send=authorize)
        if mode == "changed_response":
            result.response["blocks"][0]["markdown"] = "changed after call"
        async with AsyncSession(engine) as db:
            if mode == "cancel":
                await db.execute(
                    text("UPDATE free_course_operations SET cancel_requested_at=now() WHERE id=:i"),
                    {"i": fence.operation_id},
                )
            if mode == "expired":
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET "
                        "lease_expires_at=now()-interval '1 second' WHERE id=:i"
                    ),
                    {"i": fence.operation_id},
                )
            if mode == "new_epoch":
                token = uuid4()
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET lease_epoch=lease_epoch+1, "
                        "lease_token=:token WHERE id=:i"
                    ),
                    {"i": fence.operation_id, "token": token},
                )
                fence = WriteFence(fence.operation_id, fence.epoch + 1, token)
            if mode == "stale":
                await SnapshotRepository(db, owner).commit_manifest(
                    cid, fence, expected_head=1, key="next", plan_id=pid, bindings=bindings
                )
            await db.commit()
            if mode == "rollback":
                await persist_outcome(
                    db, owner, cid, fence, call_key="primary", inputs=data, outcome=result
                )
                await db.rollback()
            else:
                with pytest.raises(SnapshotError):
                    await persist_outcome(
                        db,
                        other if mode == "owner" else owner,
                        cid,
                        fence,
                        call_key="primary",
                        inputs=data,
                        outcome=result,
                    )
                await db.rollback()
            assert await db.scalar(select(func.count()).select_from(FreeSceneGenerationResult)) == 0
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == (
                2 if mode == "stale" else 1
            )

    exercise(action)
