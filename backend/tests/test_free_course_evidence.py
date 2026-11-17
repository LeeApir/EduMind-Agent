"""Atomic revision sets in real isolated PG with synthetic zero-Provider transport."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_answers import practice
from test_free_course_feedback import applied, draft
from test_free_course_revision import start
from test_free_course_scheduler import PROOF
from test_free_scene_generation import response

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course_evidence import (
    FreeCourseEvidenceAdmission,
    FreeCourseEvidenceRevocation,
)
from app.models.learning_state import (
    LearningEvidence,
    LearningPathCurrent,
    LearningPathVersion,
    NodeMasteryCurrent,
    NodeMasteryRevision,
)
from app.services.free_course_answers import (
    Answers,
    ensure_exercise,
    record_exposure,
)
from app.services.free_course_evidence import Attestations
from app.services.free_course_quality import (
    Maintenance,
    local_authority,
    validate_schema,
)
from app.services.free_course_recovery import Recovery
from app.services.free_course_revision import Revisions
from app.services.free_course_scheduler import Reply, Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from app.services.mastery_updates import apply_mastery_evidence

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t019_")
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
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        owners = [uuid4(), uuid4()]
        try:
            async with sessions() as db:
                db.add_all([User(id=o, is_guest=True) for o in owners])
                await db.commit()
            await action(
                Revisions(sessions),
                Scheduler(sessions, graph_version="mvp-0.2.0"),
                Recovery(sessions),
                sessions,
                *owners,
            )
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE free_course_capacity SET state='free',user_id=NULL,course_id=NULL,"
                        "operation_id=NULL,epoch=NULL,expires_at=NULL,pending_attempt_id=NULL"
                    )
                )
                for o in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:o"), {"o": o})
            await engine.dispose()

    asyncio.run(run())


async def attest(sessions, owner, cid, body, kind, key):
    service = Attestations(sessions, local_authority())
    d = dict(
        decision_key=key,
        course_id=str(cid),
        binding={k: body[k] for k in ["course_version", "scene_id", "scene_version_id"]},
        exercise_id=body["exercise_id"],
        exercise_version_id=body["exercise_version_id"],
        kind=kind,
        node_id="array" if kind == "mapping_attestation" else None,
        graph_version="mvp-0.2.0" if kind == "mapping_attestation" else None,
        content_digest="0" * 64,
        reason="隔离测试：独立人工核对准确题干条件、参考答案与单节点测量，不执行代码",
        basis=[
            dict(
                kind="manual_derivation",
                source_ref="synthetic:independent-check",
                excerpt="测试人工推演证据，不是真实题目签核",
                reason="核对规范化精确比较适用性及节点关联",
            )
        ],
    )
    preview = await service.preview_attestation(owner, d)
    d["content_digest"] = preview["content_digest"]
    receipt = await service.attest(owner, d)
    assert await service.attest(owner, d) == receipt
    return d, receipt


async def qualify(sessions, owner, cid, body):
    await attest(sessions, owner, cid, body, "answer_attestation", "answer")
    await attest(sessions, owner, cid, body, "mapping_attestation", "mapping")


async def mastered(sessions, owner):
    async with sessions() as db:
        return await db.get(NodeMasteryCurrent, (owner, "array"))


def test_exact_qualified_first_complete_admits_once_and_path_stales():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        async with sessions() as db, db.begin():
            path = LearningPathVersion(
                user_id=owner,
                target_node_id="array",
                version=1,
                graph_version="mvp-0.2.0",
                profile_version=1,
                mastery_revision_watermark=0,
                planner_rule_version="path-v1",
                nodes=["array"],
                current_node_id="array",
                prerequisite_node_ids=[],
                next_node_id=None,
                reasons=[],
            )
            db.add(path)
            await db.flush()
            db.add(
                LearningPathCurrent(
                    user_id=owner,
                    target_node_id="array",
                    path_version_id=path.id,
                    replan_required=False,
                )
            )
        await qualify(sessions, owner, cid, body)
        answers = Answers(sessions)
        receipt = await answers.submit(owner, cid, body, key="first")
        read = await answers.read(owner, cid, UUID(receipt["attempt_id"]))
        validate_schema("Attempt", read)
        assert (
            read["reliability"] == "verified"
            and read["mastery_effect"] == "admitted"
            and read["comparison_score"] == 1
        )
        assert (await mastered(sessions, owner)).score == 0.55
        async with sessions() as db:
            assert (await db.get(LearningPathCurrent, (owner, "array"))).replan_required is True
        again = await answers.submit(owner, cid, body, key="repeat")
        assert (await answers.read(owner, cid, UUID(again["attempt_id"])))[
            "mastery_effect"
        ] == "course_only"
        assert (await mastered(sessions, owner)).score == 0.55
        async with sessions() as db:
            evidence = await db.scalar(
                select(LearningEvidence).where(LearningEvidence.user_id == owner)
            )
            admission = await db.scalar(
                select(FreeCourseEvidenceAdmission).where(
                    FreeCourseEvidenceAdmission.user_id == owner
                )
            )
            assert (
                evidence.source_protocol == "free-course-v1"
                and evidence.free_course_attempt_id == UUID(receipt["attempt_id"])
            )
            assert (
                evidence.resource_id is None
                and evidence.learning_unit_id is None
                and admission.evidence_id == evidence.id
            )
            assert admission.rule_version == "free-course-evidence-v1"

    exercise(action)


@pytest.mark.parametrize("missing", ["answer", "mapping", "both", "late", "help"])
def test_missing_late_or_assisted_attestation_never_gets_formal_contribution(missing):
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        if missing not in ["answer", "both", "late"]:
            await attest(sessions, owner, cid, body, "answer_attestation", "answer")
        if missing not in ["mapping", "both", "late"]:
            await attest(sessions, owner, cid, body, "mapping_attestation", "mapping")
        if missing == "help":
            async with sessions() as db, db.begin():
                await SnapshotRepository(db, owner)._owner_lock()
                e = await ensure_exercise(
                    db,
                    owner,
                    cid,
                    {k: body[k] for k in ["course_version", "scene_id", "scene_version_id"]},
                    body["exercise_id"],
                    body["exercise_version_id"],
                )
                await record_exposure(db, owner, e, "help", {})
        first = await answers.submit(owner, cid, body, key="first")
        if missing == "late":
            await qualify(sessions, owner, cid, body)
            first = await answers.submit(owner, cid, body, key="late-repeat")
        read = await answers.read(owner, cid, UUID(first["attempt_id"]))
        assert read["mastery_effect"] == "course_only" and await mastered(sessions, owner) is None
        async with sessions() as db:
            assert (
                await db.scalar(select(func.count()).select_from(FreeCourseEvidenceAdmission)) == 0
            )

    exercise(action)


def test_confirm_revoke_replay_and_later_legacy_write_cannot_resurrect():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await qualify(sessions, owner, cid, body)
        answers = Answers(sessions)
        receipt = await answers.submit(owner, cid, body, key="first")
        d = draft(cid, manifest, index=0)
        d.update(
            scope="exercise",
            exercise_id=body["exercise_id"],
            exercise_version_id=body["exercise_version_id"],
        )
        decision = await applied(Maintenance(sessions, local_authority()), owner, d)
        current = await mastered(sessions, owner)
        assert current.score == 0 and current.status == "unseen" and current.revision == 2
        read = await answers.read(owner, cid, UUID(receipt["attempt_id"]))
        validate_schema("Attempt", read)
        assert (
            read["mastery_effect"] == "revoked"
            and read["reliability"] == "withdrawn"
            and read["comparison_score"] is None
        )
        async with sessions() as db, db.begin():
            await SnapshotRepository(db, owner)._owner_lock()
            old = LearningEvidence(
                user_id=owner,
                idempotency_key="legacy-after-revoke",
                request_digest="a" * 64,
                evidence_type="quiz_attempt",
                knowledge_node_id="array",
                schema_version=1,
                rule_version="mastery-v1",
                payload=dict(score=1),
            )
            db.add(old)
            await db.flush()
            await apply_mastery_evidence(db, old)
        assert (await mastered(sessions, owner)).score == 0.55
        async with sessions() as db:
            assert (
                await db.scalar(select(func.count()).select_from(FreeCourseEvidenceRevocation)) == 1
            )
            revisions = (
                await db.scalars(
                    select(NodeMasteryRevision)
                    .where(NodeMasteryRevision.user_id == owner)
                    .order_by(NodeMasteryRevision.revision)
                )
            ).all()
            assert revisions[1].recomputed_from_id == revisions[0].id and revisions[0].score == 0.55
        corrected = draft(
            cid,
            manifest,
            index=0,
            action="decision_correction",
            target=decision["decision_id"],
            key="correction",
        )
        corrected.update(
            scope="exercise",
            exercise_id=body["exercise_id"],
            exercise_version_id=body["exercise_version_id"],
        )
        await applied(Maintenance(sessions, local_authority()), owner, corrected)
        assert (await answers.read(owner, cid, UUID(receipt["attempt_id"])))[
            "mastery_effect"
        ] == "revoked"

    exercise(action)


def test_changed_replacement_revokes_atomic_keeps_original_answers():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await qualify(sessions, owner, cid, body)
        answers = Answers(sessions)
        receipt = await answers.submit(owner, cid, body, key="first")
        await start(r, owner, cid, manifest, index=0)
        replacement = response(["text", "exercise"])
        replacement["blocks"][1]["items"][0]["answer_key"] = "changed"
        a.replies = [
            Reply("complete_response", PROOF, replacement, 100, 100),
            Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100),
        ]
        lease = await s.claim()
        await s.run_once(lease, a)
        assert (await mastered(sessions, owner)).score == 0.55
        for _ in range(2):
            await s.run_once(lease, a)
        assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
            "state"
        ] == "succeeded"
        assert (await mastered(sessions, owner)).status == "unseen"
        read = await answers.read(owner, cid, UUID(receipt["attempt_id"]))
        assert (
            read["answers"] == body["answers"]
            and not read["question_results"]
            and read["mastery_effect"] == "revoked"
        )

    exercise(action)


def test_unchanged_context_retains_old_contribution_without_new_attestation():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await qualify(sessions, owner, cid, body)
        answers = Answers(sessions)
        receipt = await answers.submit(owner, cid, body, key="first")
        await start(r, owner, cid, manifest, index=1)
        a.replies = [Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100)]
        lease = await s.claim()
        for _ in range(2):
            await s.run_once(lease, a)
        assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
            "state"
        ] == "succeeded"
        assert (await mastered(sessions, owner)).score == 0.55
        assert (await answers.read(owner, cid, UUID(receipt["attempt_id"])))[
            "mastery_effect"
        ] == "admitted"

    exercise(action)


def test_missing_legacy_original_conservatively_denies_new_measurement():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await qualify(sessions, owner, cid, body)
        async with sessions() as db, db.begin():
            db.add(
                LearningEvidence(
                    user_id=owner,
                    idempotency_key="old-missing-snapshot",
                    request_digest="a" * 64,
                    evidence_type="quiz_attempt",
                    knowledge_node_id="stack",
                    schema_version=1,
                    rule_version="mastery-v1",
                    payload=dict(score=1),
                )
            )
        receipt = await Answers(sessions).submit(owner, cid, body, key="first")
        read = await Answers(sessions).read(owner, cid, UUID(receipt["attempt_id"]))
        assert (
            read["reason_code"] == "PRIOR_ASSESSMENT_UNKNOWN"
            and read["mastery_effect"] == "course_only"
            and await mastered(sessions, owner) is None
        )

    exercise(action)


def test_forged_or_incomplete_source_cannot_commit_or_launder():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        for source in ["unknown", "free-course-v1", None]:
            async with sessions() as db:
                record = LearningEvidence(
                    user_id=owner,
                    idempotency_key=str(uuid4()),
                    request_digest="a" * 64,
                    evidence_type="quiz_attempt",
                    knowledge_node_id="array",
                    schema_version=1,
                    rule_version="mastery-v1",
                    payload=dict(score=1),
                    source_protocol=source,
                    free_course_attempt_id=uuid4(),
                )
                db.add(record)
                with pytest.raises(DBAPIError):
                    await db.commit()
        await qualify(sessions, owner, cid, body)
        await Answers(sessions).submit(owner, cid, body, key="first")
        async with sessions() as db:
            with pytest.raises(DBAPIError):
                await db.execute(
                    text(
                        "UPDATE learning_evidence SET source_protocol=NULL,"
                        "free_course_attempt_id=NULL "
                        "WHERE user_id=:u"
                    ),
                    dict(u=owner),
                )
                await db.commit()

    exercise(action)


def test_quality_rollback_preserves_qualification_and_mastery(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("synthetic rollback after revoke")

    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await qualify(sessions, owner, cid, body)
        receipt = await Answers(sessions).submit(owner, cid, body, key="first")
        monkeypatch.setattr("app.services.mastery_updates.apply_mastery_evidence", broken)
        with pytest.raises(RuntimeError, match="synthetic rollback"):
            await applied(
                Maintenance(sessions, local_authority()), owner, draft(cid, manifest, index=0)
            )
        assert (await mastered(sessions, owner)).score == 0.55
        assert (await Answers(sessions).read(owner, cid, UUID(receipt["attempt_id"])))[
            "mastery_effect"
        ] == "admitted"
        async with sessions() as db:
            assert (
                await db.scalar(select(func.count()).select_from(FreeCourseEvidenceRevocation)) == 0
            )

    exercise(action)


def test_cross_course_corrected_answer_same_stems_cannot_reset_independence():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await Answers(sessions).submit(owner, cid, body, key="first-provisional")
        raw = response(["text", "exercise"])
        raw["blocks"][1]["items"][0]["answer_key"] = "corrected"
        cid2, manifest2, body2, a2 = await practice(
            s, sessions, owner, create_key="second-course", raw=raw
        )
        body2["answers"][0]["answer"] = "corrected"
        await qualify(sessions, owner, cid2, body2)
        receipt = await Answers(sessions).submit(owner, cid2, body2, key="first-second-course")
        read = await Answers(sessions).read(owner, cid2, UUID(receipt["attempt_id"]))
        assert (
            read["comparison_score"] == 1
            and read["mastery_effect"] == "course_only"
            and await mastered(sessions, owner) is None
        )

    exercise(action)


def test_known_catalog_same_stems_blocks_even_when_answer_or_display_ids_change():
    from app.models.learning import GeneratedResource, LearningScene, LearningUnit

    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        await qualify(sessions, owner, cid, body)
        async with sessions() as db, db.begin():
            unit = LearningUnit(
                user_id=owner,
                title="synthetic exact retained catalog original",
                knowledge_point_id="array",
                status="published",
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id, scene_key="quiz", scene_order=1, scene_type="exercise"
            )
            db.add(scene)
            await db.flush()
            resource = GeneratedResource(
                user_id=owner,
                learning_unit_id=unit.id,
                scene_id=scene.id,
                resource_type="exercise",
                version=1,
                content=dict(
                    items=[
                        dict(
                            id=f"old{i}",
                            question=f"合成题{i}",
                            answer="different old answer",
                            explanation="retained original",
                        )
                        for i in range(2)
                    ]
                ),
            )
            db.add(resource)
            await db.flush()
            db.add(
                LearningEvidence(
                    user_id=owner,
                    idempotency_key="catalog-original",
                    request_digest="a" * 64,
                    evidence_type="quiz_attempt",
                    knowledge_node_id="array",
                    resource_id=resource.id,
                    resource_version=1,
                    schema_version=1,
                    rule_version="mastery-v1",
                    payload=dict(
                        score=0,
                        answers=[dict(question_id=f"old{i}", answer="completed") for i in range(2)],
                    ),
                )
            )
        receipt = await Answers(sessions).submit(owner, cid, body, key="first")
        read = await Answers(sessions).read(owner, cid, UUID(receipt["attempt_id"]))
        assert read["mastery_effect"] == "course_only" and read["reason_code"] == "PRIOR_ASSESSMENT"

    exercise(action)


def test_attestation_requires_accurate_digest_owner_and_course_association():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        d, receipt = await attest(sessions, owner, cid, body, "answer_attestation", "answer")
        service = Attestations(sessions, local_authority())
        bad = {
            **d,
            "decision_key": "wrong-digest",
            "content_digest": "f" * 64,
            "kind": "mapping_attestation",
            "node_id": "array",
            "graph_version": "mvp-0.2.0",
        }
        with pytest.raises(SnapshotError, match="ATTESTATION_DIGEST_MISMATCH"):
            await service.attest(owner, bad)
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await service.attest(other, d)
        bad.update(node_id="circular-queue")
        with pytest.raises(SnapshotError, match="MAPPING_ASSOCIATION_REQUIRED"):
            await service.preview_attestation(owner, bad)
        bad.update(node_id="array", content_digest=d["content_digest"])
        bad["basis"] = [
            dict(
                kind="mechanical_rule",
                source_ref="model",
                excerpt="model says yes",
                reason="opinion",
            )
        ]
        with pytest.raises(SnapshotError, match="INDEPENDENT_ATTESTATION_REQUIRED"):
            await service.attest(owner, bad)

    exercise(action)
