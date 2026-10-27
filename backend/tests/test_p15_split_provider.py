"""Real isolated PG and product scheduler; both providers are explicit HTTPX mocks."""

import json
import socket
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_planning import candidate, clarify
from test_free_scene_generation import response

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from isolated_diagnostics import p15_split_provider as p  # noqa: E402

from app.models.free_course import (  # noqa: E402
    FreeCourse,
    FreeCourseSceneVersion,
    FreeCourseVersion,
)
from app.services.free_course_snapshots import SnapshotError  # noqa: E402


@pytest.fixture(autouse=True)
def only_pg_network(monkeypatch):
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def guarded(sock, address):
        assert address[:2] == ("127.0.0.1", 15437), "Only isolated test PG may use sockets"
        return original(sock, address)

    def guarded_ex(sock, address):
        assert address[:2] == ("127.0.0.1", 15437), "Only isolated test PG may use sockets"
        return original_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_ex)


def reply(request, value):
    body = p.parse(request.content)
    return httpx.Response(
        200,
        json={
            "object": "response",
            "status": "completed",
            "model": body["model"],
            "store": False,
            "max_output_tokens": body["max_output_tokens"],
            "instructions": "\n\n".join(
                m["content"] for m in body["input"] if m["role"] == "system"
            ),
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 100, "total_tokens": 200},
        },
    )


class FixtureSchedulerAdapter:
    """Synthetic-only bound for the deterministic Mock response, never real Provider proof."""

    def __init__(self, router, identity):
        self.bound = router.bound(identity)
        self.policy = replace(self.bound.policy, bounded_output_verified=True)

    def input_upper_bound(self, request):
        # This constant bounds the fixture's declared input=100, not DeepSeek tokenization.
        return 32000

    async def send(self, request, *, retry_safe):
        return await self.bound.send(request, retry_safe=retry_safe)


@pytest.fixture
def setup(tmp_path):
    j = p.Journal.create_mock(tmp_path / "wire", batch="TEST_ONLY_SPLIT_PG_" + uuid4().hex)
    current = {"goal": "合成数组目标", "negative": False, "known": False, "n": 2}
    generation_calls = []
    review_calls = []

    def generation(request):
        assert request.headers["authorization"] == "Bearer TEST_ONLY_DEEPSEEK_KEY"
        assert request.headers["host"] == "api.deepseek.com"
        body = p.parse(request.content)
        generation_calls.append(body)
        if "needs_clarification" in body["text"]["format"]["schema"]["properties"]:
            value = (
                clarify("requirements_conflict", current["goal"])
                if current["negative"]
                else candidate(current["n"], current["goal"])
            )
            if not current["negative"]:
                for s in value["plan"]["scenes"]:
                    s["forms"] = ["text", "code", "exercise", "visualization"]
        else:
            value = response()
        return reply(request, value)

    def review(request):
        assert request.headers["authorization"] == "Bearer TEST_ONLY_AIAPI_KEY"
        assert request.headers["host"] == "aiapi.world"
        body = p.parse(request.content)
        review_calls.append(body)
        if "source_sha256" in body["text"]["format"]["schema"]["properties"]:
            source = p.parse(body["input"][-1]["content"])
            assert "answer_key" in json.dumps(source["source"]["scene"])
            assert bool("TEST_ONLY_LEARNER" in json.dumps(source)) == current["known"]
            value = {
                "source_sha256": source["source_sha256"],
                "scope_status": "complete",
                "uncertain_reason": None,
                "verdict": "pass",
                "issues": [],
            }
        else:
            value = {"review_version": "resource-review-v3", "verdict": "pass", "issues": []}
        return reply(request, value)

    router = p.Router(
        j,
        {"generation": httpx.MockTransport(generation), "review": httpx.MockTransport(review)},
        {"generation": "TEST_ONLY_DEEPSEEK_KEY", "review": "TEST_ONLY_AIAPI_KEY"},
    )
    try:
        yield j, router, current, generation_calls, review_calls
    finally:
        j.ledger.close()


def course_slot(name, known=False):
    return {
        "kind": "course",
        "slot_id": name,
        "original_goal": "合成数组目标",
        "scene_count_range": [2, 2],
        "learner_evidence": {"knowledge_base": {"self_report": "TEST_ONLY_LEARNER"}}
        if known
        else {},
    }


async def generation_only(sessions, j, router, slot):
    owner = uuid5(NAMESPACE_URL, j.batch + "/" + slot["slot_id"])
    initial = p.Identity(slot["slot_id"], str(owner), "TEST_ONLY_PENDING_COURSE")
    j.bind(initial)
    result = await p.run_slot(
        slot, sessions, FixtureSchedulerAdapter(router, initial), j.ledger, j.batch, j.package
    )
    assert result["engineering_pass"], result
    cid = str(result["tables"]["free_course_plans"][0]["course_id"])
    exact = p.Identity(slot["slot_id"] + ":scene-review", str(owner), cid)
    j.bind(exact)
    return exact, await p.load_targets(sessions, exact)


def test_pg_known_unknown_negative_probe_and_every_scene_private_review(setup):
    j, router, current, generation_calls, review_calls = setup

    async def run(sessions):
        for known in (True, False):
            current["known"] = known
            slot = course_slot("known" if known else "unknown", known)
            result = await p.run_split_slot(
                slot, sessions, lambda i: FixtureSchedulerAdapter(router, i), router
            )
            assert result["engineering_pass"]
            identity = p.Identity(**result["scene_review_identity"])
            targets = await p.load_targets(sessions, identity)
            assert targets == j.sources(identity)
            assert len(targets) == 2 and len(targets[0]["payload"]["source"]["upstream"]) == 0
            assert len(targets[1]["payload"]["source"]["upstream"]) == 1
            assert targets[1]["payload"]["source"]["scene"]["actions"]
            async with sessions() as db:
                course = await db.get(FreeCourse, UUID(identity.course_id))
                assert course.endorsement == "unendorsed" and course.course_kind == "ai_draft"
            with pytest.raises(SnapshotError):
                await p.load_targets(
                    sessions, p.Identity("wrong", str(uuid4()), identity.course_id)
                )
        current.update(negative=True, known=False)
        result = await p.run_split_slot(
            {"kind": "negative", "slot_id": "N01", "goal": current["goal"]},
            sessions,
            lambda i: FixtureSchedulerAdapter(router, i),
            router,
        )
        assert result["engineering_pass"] and result["operation_state"] == "awaiting_clarification"
        result = await p.run_split_slot(
            {
                "kind": "probe",
                "slot_id": "R01",
                "content": "栈后进先出",
                "proposed_label": "NEVER_SEND_THIS_GOLD",
            },
            sessions,
            lambda i: FixtureSchedulerAdapter(router, i),
            router,
        )
        assert result["engineering_pass"]
        assert len(generation_calls) == 7 and len(review_calls) == 5
        assert len(j.events("scene_review_finished")) == 4
        assert "NEVER_SEND_THIS_GOLD" not in json.dumps(generation_calls + review_calls)

    dbwork(run)


@pytest.mark.parametrize("change", ["head", "content"])
def test_pg_illegal_snapshot_mutation_is_blocked_before_review(setup, change):
    j, router, current, generation_calls, review_calls = setup

    async def run(sessions):
        identity, targets = await generation_only(sessions, j, router, course_slot("changed"))
        j.freeze(identity, targets)
        # The real append-only/forward-only DB guards reject illegal changes.
        # Keep these assertions instead of disabling triggers to set up a stale source.
        with pytest.raises(IntegrityError):
            async with sessions() as db, db.begin():
                if change == "head":
                    course = await db.get(FreeCourse, UUID(identity.course_id))
                    versions = (
                        await db.scalars(
                            select(FreeCourseVersion)
                            .where(FreeCourseVersion.course_id == UUID(identity.course_id))
                            .order_by(FreeCourseVersion.version)
                        )
                    ).all()
                    course.head_version_id = versions[0].id
                else:
                    scene = await db.get(
                        FreeCourseSceneVersion,
                        UUID(targets[0]["payload"]["source"]["scene"]["scene_version_id"]),
                    )
                    scene.content_json = {"blocks": []}
        assert await p.load_targets(sessions, identity) == targets
        assert not review_calls

    dbwork(run)


def test_pg_forward_head_change_invalidates_frozen_review_before_http(setup):
    j, router, _, _, review_calls = setup

    async def run(sessions):
        identity, targets = await generation_only(sessions, j, router, course_slot("new-head"))
        j.freeze(identity, targets)
        async with sessions() as db, db.begin():
            course = await db.get(FreeCourse, UUID(identity.course_id))
            old = await db.get(FreeCourseVersion, course.head_version_id)
            # An additional valid immutable manifest with the same content is enough:
            # review identity must bind its exact version, not only visible prose.
            new = FreeCourseVersion(
                user_id=old.user_id,
                course_id=old.course_id,
                version=old.version + 1,
                schema_version=old.schema_version,
                plan_id=old.plan_id,
                digest=old.digest,
                manifest_json=deepcopy(old.manifest_json),
            )
            db.add(new)
            await db.flush()
            course.head_version_id = new.id

        async def verify(target):
            return target in await p.load_targets(sessions, identity)

        with pytest.raises(p.Refused, match="SOURCE_NO_LONGER_CURRENT"):
            await p.review_pending(router, identity, verify_current=verify)
        assert not review_calls
        assert j.ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"

    dbwork(run)


def test_actual_pg_course_cannot_advance_without_human_and_exact_audit_checkpoint(setup):
    j, router, current, _, _ = setup
    slots = [course_slot("D01"), course_slot("D02")]
    execution = p.SplitExecution(j, slots)

    async def run(sessions):
        async def runner(slot):
            return await p.run_split_slot(
                slot, sessions, lambda i: FixtureSchedulerAdapter(router, i), router
            )

        record = await execution.advance(runner)
        with pytest.raises(p.Refused, match="REVIEW_PENDING"):
            await execution.advance(runner)
        result = p.parse((j.output / "D01.json").read_bytes())
        identity = p.Identity(**result["scene_review_identity"])
        human = {
            "slot_id": "D01",
            "output_sha256": record["sha256"],
            "reviewer": "TEST_ONLY_HUMAN",
            "reviewed_at": "fixture",
            "evidence_ref": "fixture",
            "exhaustive_coverage_attested": True,
            "natural_severe_errors": 0,
            "items": [
                {
                    "area": area,
                    "location": "fixture:/all",
                    "reason": "offline human-report fixture",
                    "verdict": "pass",
                }
                for area in ("requirements", "learnability", "facts", "answers", "profile")
            ],
        }
        with pytest.raises(p.Refused, match="CHECKPOINT"):
            execution.review(human)
        human["scene_review_checkpoint_sha256"] = j.review_checkpoint(identity)
        execution.review(human)
        record2 = await execution.advance(runner)
        assert record2["slot_id"] == "D02"

    dbwork(run)
