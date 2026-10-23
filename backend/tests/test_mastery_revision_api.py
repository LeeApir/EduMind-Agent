"""Actual owner HTTP/PG history, including real qualified admission and atomic revocation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from test_free_course_api import api as _api
from test_free_course_api import dbwork, ready
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_evidence import qualify
from test_free_course_feedback import applied, draft
from test_free_course_revision import start
from test_free_course_scheduler import PROOF
from test_free_scene_generation import response

from app.main import app
from app.models.learning import LearningUnit
from app.models.learning_state import LearningEvidence, NodeMasteryRevision
from app.services.free_course_contract import validate
from app.services.free_course_quality import Maintenance, local_authority
from app.services.free_course_revision import Revisions
from app.services.free_course_scheduler import Reply, Scheduler

api = _api
URL = "/api/mastery/nodes/array/revisions"


def test_auth_limits_node_validation_and_empty_historical_node(api):
    client, _, _ = api()
    with TestClient(app, base_url="https://testserver") as noauth:
        assert noauth.get(URL).status_code == 401
    for params in [{"limit": 0}, {"limit": 51}, {"before_revision": 0}, {"before_revision": "bad"}]:
        assert client.get(URL, params=params).status_code == 422
    assert client.get("/api/mastery/nodes/INVALID_NODE/revisions").status_code == 422
    page = client.get("/api/mastery/nodes/retired-node/revisions")
    assert page.status_code == 200 and page.json() == {
        "node_id": "retired-node",
        "items": [],
        "next_before_revision": None,
    }
    assert page.headers["cache-control"] == "no-store"
    validate("RevisionPage", page.json())


@pytest.mark.parametrize("cause", ["confirmed_defect", "atomic_revision"])
def test_admission_and_revocation_trace_exact_old_attempt_with_no_new_scoring(
    api, monkeypatch, cause
):
    client, owner, headers = api()
    other, _, _ = api()
    cid, manifest, body, adapter = ready(owner)
    root = f"/api/free-courses/{cid}"

    async def qualify_first(sessions):
        await qualify(sessions, owner, cid, body)

    dbwork(qualify_first)
    receipt = client.post(root + "/attempts", json=body, headers=headers)
    assert receipt.status_code == 201, receipt.text
    aid = receipt.json()["attempt_id"]
    before = client.get(URL)
    assert before.status_code == 200, before.text
    validate("RevisionPage", before.json())
    first = before.json()["items"][0]
    assert first["score"] == 0.55 and first["source"]["protocol"] == "free-course-v1"
    ref = first["source"]["reference"]
    assert ref == {
        "kind": "free_course_attempt",
        "course_id": str(cid),
        "attempt_id": aid,
        **{
            key: body[key]
            for key in [
                "course_version",
                "scene_id",
                "scene_version_id",
                "exercise_id",
                "exercise_version_id",
            ]
        },
    }
    assert client.get(root + "/attempts/" + aid).json()["mastery_effect"] == "admitted"

    async def revoke(sessions):
        if cause == "confirmed_defect":
            decision = draft(cid, manifest, index=0)
            decision.update(
                scope="exercise",
                exercise_id=body["exercise_id"],
                exercise_version_id=body["exercise_version_id"],
            )
            await applied(Maintenance(sessions, local_authority()), owner, decision)
        else:
            scheduler = Scheduler(sessions, graph_version="mvp-0.2.0")
            await start(Revisions(sessions), owner, cid, manifest, index=0)
            changed = response(["text", "exercise"])
            changed["blocks"][1]["items"][0]["answer_key"] = "changed"
            adapter.replies = [
                Reply("complete_response", PROOF, changed, 100, 100),
                Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100),
            ]
            lease = await scheduler.claim()
            assert lease
            for _ in range(3):
                await scheduler.run_once(lease, adapter)

    dbwork(revoke)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    history = client.get(URL, params={"limit": 1})
    assert history.status_code == 200, history.text
    validate("RevisionPage", history.json())
    correction = history.json()["items"][0]
    assert correction["revision"] == 2 and correction["recomputed_from_revision"] == 1
    assert correction["score"] == 0 and correction["status"] == "unseen"
    assert correction["source"]["protocol"] == "free-course-correction-v1"
    assert correction["source"]["reference"] == ref
    assert correction["source"]["evidence_id"] != first["source"]["evidence_id"]
    assert history.json()["next_before_revision"] == 2
    old = client.get(URL, params={"limit": 1, "before_revision": 2}).json()
    assert old["items"] == [first] and old["next_before_revision"] is None
    assert client.get(URL, params={"before_revision": 1}).json()["items"] == []
    assert other.get(URL, params={"before_revision": 999999}).json()["items"] == []
    attempt = client.get(root + "/attempts/" + aid).json()
    assert attempt["answers"] == body["answers"] and attempt["mastery_effect"] == "revoked"
    assert attempt["comparison_score"] is None and not attempt["question_results"]
    state = next(
        i for i in client.get("/api/mastery").json()["items"] if i["knowledge_node_id"] == "array"
    )
    assert state["revision"] == 2 and state["status"] == "unseen"
    assert "payload" not in history.text and "answer_key" not in history.text

    async def count(sessions):
        async with sessions() as db:
            return await db.scalar(
                select(func.count())
                .select_from(NodeMasteryRevision)
                .where(NodeMasteryRevision.user_id == owner)
            )

    assert dbwork(count) == 2  # history GETs must not append/recompute anything


def test_legacy_empty_refs_and_unavailable_owner_node_sources_are_not_invented(api):
    client, owner, _ = api()
    other, other_owner, _ = api()
    evidence_id = uuid4()
    foreign_id = uuid4()
    mismatch_id = uuid4()

    async def insert(sessions):
        async with sessions() as db:
            for identity, user in [
                (evidence_id, owner),
                (foreign_id, other_owner),
                (mismatch_id, owner),
            ]:
                db.add(
                    LearningEvidence(
                        id=identity,
                        user_id=user,
                        idempotency_key=str(identity),
                        request_digest="a" * 64,
                        evidence_type="explicit_feedback",
                        knowledge_node_id="different-node"
                        if identity == mismatch_id
                        else "retired-node",
                        schema_version=1,
                        rule_version="mastery-v1",
                        payload={
                            "action": "mark_known",
                            "private_test_marker": "never project payload",
                        },
                    )
                )
            await db.flush()
            db.add_all(
                [
                    NodeMasteryRevision(
                        user_id=owner,
                        knowledge_node_id="retired-node",
                        revision=1,
                        previous_score=0,
                        score=0,
                        status="unseen",
                        rule_version="mastery-v1",
                        evidence_id=evidence_id,
                        evidence_summary=[],
                    ),
                    # Explicit historical node mismatch: do not invent a source association.
                    NodeMasteryRevision(
                        user_id=owner,
                        knowledge_node_id="retired-node",
                        revision=2,
                        previous_score=0,
                        score=0,
                        status="unseen",
                        rule_version="mastery-v1",
                        evidence_id=mismatch_id,
                        evidence_summary=[],
                    ),
                ]
            )
            await db.flush()
            with pytest.raises(IntegrityError, match="fk_node_mastery_evidence_owner"):
                async with db.begin_nested():
                    db.add(
                        NodeMasteryRevision(
                            user_id=owner,
                            knowledge_node_id="retired-node",
                            revision=3,
                            previous_score=0,
                            score=0,
                            status="unseen",
                            rule_version="mastery-v1",
                            evidence_id=foreign_id,
                            evidence_summary=[],
                        )
                    )
                    await db.flush()
            await db.commit()

    dbwork(insert)
    response = client.get("/api/mastery/nodes/retired-node/revisions")
    assert response.status_code == 200, response.text
    validate("RevisionPage", response.json())
    missing, legacy = response.json()["items"]
    assert missing["source"] == {"protocol": "unavailable", "evidence_id": None, "reference": None}
    assert legacy["source"] == {
        "protocol": "legacy",
        "evidence_id": str(evidence_id),
        "reference": {
            "kind": "legacy_evidence",
            "resource_id": None,
            "resource_version": None,
            "learning_unit_id": None,
        },
    }
    assert "private_test_marker" not in response.text and str(foreign_id) not in response.text
    assert other.get("/api/mastery/nodes/retired-node/revisions").json()["items"] == []


def test_legacy_owned_unit_reference_exposes_no_private_body(api):
    client, owner, _ = api()
    unit_id = uuid4()
    evidence_id = uuid4()

    async def insert(sessions):
        async with sessions() as db:
            db.add(LearningUnit(id=unit_id, user_id=owner, title="TEST_ONLY private title"))
            await db.flush()
            db.add(
                LearningEvidence(
                    id=evidence_id,
                    user_id=owner,
                    idempotency_key=str(evidence_id),
                    request_digest="b" * 64,
                    evidence_type="explicit_feedback",
                    knowledge_node_id="old-node",
                    learning_unit_id=unit_id,
                    schema_version=1,
                    rule_version="mastery-v1",
                    payload={"action": "mark_known", "private": "must not project"},
                )
            )
            await db.flush()
            db.add(
                NodeMasteryRevision(
                    user_id=owner,
                    knowledge_node_id="old-node",
                    revision=1,
                    previous_score=0,
                    score=0,
                    status="unseen",
                    rule_version="mastery-v1",
                    evidence_id=evidence_id,
                    evidence_summary=[],
                )
            )
            await db.commit()

    dbwork(insert)
    result = client.get("/api/mastery/nodes/old-node/revisions")
    assert result.status_code == 200, result.text
    validate("RevisionPage", result.json())
    assert result.json()["items"][0]["source"]["reference"] == {
        "kind": "legacy_evidence",
        "resource_id": None,
        "resource_version": None,
        "learning_unit_id": str(unit_id),
    }
    assert "private" not in result.text and "payload" not in result.text
