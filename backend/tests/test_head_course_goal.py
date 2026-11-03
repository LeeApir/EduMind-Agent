"""Finite goal bridge: actual private PG/API plus mock transport; never real generation."""

import asyncio
import json
import os
import time
from copy import deepcopy
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.free_course_planning import validate_response
from app.main import app
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services import head_course_generation as g
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError
from scripts import head_course_goal as entry
from scripts import head_course_goal_fixture as fixture


def run(action):
    return asyncio.run(entry.database(action))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_HEAD_GOAL_DEVELOPMENT", "1")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("No Provider allowed"),
    )


def create(client):
    auth = client.post("/api/auth/guest").json()
    h = {"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())}
    response = client.post(
        "/api/free-courses", json={"goal": m.GOAL, "code_language": "c"}, headers=h
    )
    assert response.status_code == 201, response.text
    value = response.json()
    return UUID(auth["user"]["id"]), value, h


@pytest.mark.parametrize("key", list(m.SPECS))
def test_goal_plan_private_course_and_feedback(key):
    with (
        TestClient(app, base_url="https://testserver") as client,
        TestClient(app, base_url="https://testserver") as other,
    ):
        owner, created, headers = create(client)
        other.post("/api/auth/guest")
        cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
        from app.services.free_course_contract import validate

        operation = client.get(f"/api/free-courses/{cid}/operations/{oid}")
        assert operation.status_code == 200, operation.text
        op = operation.json()
        assert op["execution_mode"] == "finite_head_foreground" and op["budget"] is None
        with pytest.raises(SnapshotError):
            validate("Operation", {k: v for k, v in op.items() if k != "execution_mode"})
        context = asyncio.run(entry.prepare(owner, cid, oid))
        assert context["planning_inputs"]["original_goal"] == m.GOAL
        assert context["planning_inputs"]["learner_evidence"] == {}
        assert context["planning_inputs"]["request_sources"]["request_1"]["text"] == m.GOAL
        request = entry.planning_body(context["planning_inputs"])
        assert json.loads(request["input"][1]["content"])["head_support"] == m.SUPPORT
        assert (
            client.post(
                "/api/free-courses", json={"goal": m.GOAL, "code_language": "c"}, headers=headers
            ).json()
            == created
        )
        result = asyncio.run(fixture.populate(owner, cid, oid, key))
        route = f"/api/free-courses/{cid}/versions/2/scenes/{result['scene_id']}"
        response = client.get(route)
        assert response.status_code == 200, response.text
        view = response.json()
        assert "replay_source" not in view
        assert view["generation_source"]["origin"] == m.ORIGIN
        assert view["generation_source"]["evidence_kind"] == "offline_fixture"
        assert "answer_key" not in response.text and "solution" not in response.text
        assert other.get(route).status_code == 404
        exercise = view["blocks"][-1]
        body = dict(
            course_version=2,
            scene_id=result["scene_id"],
            scene_version_id=view["scene_version_id"],
            exercise_id=exercise["exercise_id"],
            exercise_version_id=exercise["exercise_version_id"],
            answers=[
                dict(question_id=k, answer=v)
                for k, v in {
                    "link_target": "i0",
                    "normal_values": "[11, 30, 40]",
                    "discarded_values": "[30,40]",
                    "unreachable_count": "1",
                }.items()
            ],
        )
        root = f"/api/free-courses/{cid}"
        assert (
            client.post(
                root + "/attempts", json=body, headers={"Idempotency-Key": str(uuid4())}
            ).status_code
            == 403
        )
        partial = client.post(
            root + "/attempts",
            json={**body, "answers": body["answers"][:1]},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert partial.status_code == 201, partial.text
        a = client.get(root + "/attempts/" + partial.json()["attempt_id"]).json()
        assert a["comparison_score"] is None and a["question_results"] == []
        full = client.post(
            root + "/attempts", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
        )
        assert full.status_code == 201, full.text
        attempt = client.get(root + "/attempts/" + full.json()["attempt_id"]).json()
        assert attempt["comparison_score"] == 1 and attempt["mastery_effect"] == "course_only"
        assert client.get(route).json() == view
        assert (
            client.post(
                root + "/attempts",
                json={**body, "course_version": 1},
                headers={**headers, "Idempotency-Key": str(uuid4())},
            ).status_code
            == 409
        )

        async def audit(db):
            row = await db.scalar(
                select(FreeSceneGenerationResult).where(FreeSceneGenerationResult.course_id == cid)
            )
            assert row.origin_type == m.ORIGIN and row.sent_attempts == 1
            actual = row.input_snapshot["inputs"]
            assert g.validate_generation(row, actual)["state"] == "accepted"
            for field, val in [
                ("sent_attempts", 0),
                ("origin_type", "existing_real_candidate_replay"),
                ("request_digest", "0" * 64),
            ]:
                old = getattr(row, field)
                setattr(row, field, val)
                with pytest.raises(SnapshotError):
                    g.validate_generation(row, actual)
                setattr(row, field, old)
            raw = row.input_snapshot["generation"]["candidate"]["raw_output"]
            assert raw["prerequisites"] == view["blocks"][0]["markdown"]
            assert (
                row.input_snapshot["generation"]["candidate"]["payload"]["materials"][
                    "selected_example"
                ]
                == key
            )

        run(audit)


@pytest.mark.parametrize(
    "mutation", ["old_example", "two_scenes", "lost_form", "orphan", "false_scope"]
)
def test_planning_refuses_scope_without_rewriting(mutation):
    inputs = dict(
        course_id=str(uuid4()),
        operation_id=str(uuid4()),
        request_id=str(uuid4()),
        original_goal=m.GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={"request_1": dict(request_id=str(uuid4()), version=1, text=m.GOAL)},
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.SUPPORT,
    )
    value = fixture.plan()
    if mutation == "old_example":
        value["plan"]["shared_example"] = "C01"
    if mutation == "two_scenes":
        value["plan"]["scenes"].append(deepcopy(value["plan"]["scenes"][0]))
    if mutation == "lost_form":
        value["plan"]["scenes"][0]["forms"] = ["text"]
    if mutation == "orphan":
        value["plan"]["scenes"][0]["objective_ids"] = ["link"]
    if mutation == "false_scope":
        inputs["original_goal"] = "排序"
    with pytest.raises(SnapshotError):
        from app.agents.free_course_planning import snapshot_input

        validate_response(value, snapshot_input(inputs))


@pytest.mark.parametrize("mutation", ["frame", "fact", "scenario", "missing"])
def test_teaching_refuses_missing_or_wrong_material(mutation):
    payload = m.content_payload(
        dict(
            original_goal=m.GOAL,
            course_id="offline-fixture-course",
            operation_id="offline-fixture-operation",
            request_id="offline-fixture-request",
        ),
        fixture.plan()["plan"],
    )
    value = fixture.content(payload)
    if mutation == "frame":
        value["step_notes"][0]["frame_id"] = "bad"
    if mutation == "fact":
        value["paragraphs"][0]["fact_ids"] = ["bad"]
    if mutation == "scenario":
        value["questions"]["normal_values"]["stem"] = "没有情境"
    if mutation == "missing":
        del value["lifecycle"]
    with pytest.raises(Exception):
        m.validate_content(payload, value)


@pytest.mark.parametrize("bad_kind", ["phase", "invalid_json"])
def test_exact_entry_mock_transport_and_raw_failures(tmp_path, monkeypatch, bad_kind):
    monkeypatch.setattr(entry, "package_digest", lambda: "a" * 64)
    with TestClient(app, base_url="https://testserver") as client:
        owner, created, _ = create(client)
        context = asyncio.run(
            entry.prepare(owner, UUID(created["course_id"]), UUID(created["operation_id"]))
        )
        vault = tmp_path / "vault"
        vault.mkdir(mode=0o700)
        (vault / "raw.key").write_bytes(Fernet.generate_key())
        (vault / "raw.key").chmod(0o600)
        (vault / "context.json").write_bytes(entry.canonical(context))
        approval = dict(
            package_sha256="a" * 64,
            version=m.VERSION,
            explicit_user_authorization=True,
            accept_ADR0052_A_D_and_batch_C2=True,
            starts_epoch=int(time.time()) - 1,
            expires_epoch=int(time.time()) - 1 + 600,
        )
        count = []

        def transport(request):
            count.append(1)
            body = json.loads(request.content)
            payload = json.loads(body["input"][1]["content"])
            value = fixture.plan() if len(count) == 1 else fixture.content(payload)
            return httpx.Response(200, stream=httpx.ByteStream(fixture.envelope(value)))

        mock = httpx.MockTransport(transport)
        entry.send("plan", vault, approval, transport=mock, key="fake-not-a-key")
        (vault / "plan-review.json").write_bytes(
            entry.canonical(
                dict(
                    plan_digest=entry.digest("head-plan", plan=fixture.plan()["plan"]),
                    verdict="pass",
                    independent_evaluator="offline_fixture",
                )
            )
        )
        entry.send("generate", vault, approval, transport=mock, key="fake-not-a-key")
        rec = entry.verify_saved(vault, "generate", Fernet((vault / "raw.key").read_bytes()))
        assert len(count) == 2 and rec["evidence_kind"] == "offline_fixture"
        # An unknown phase is rejected by the actual entry after saving encrypted original.
        issues = [dict(path=["lifecycle"], quote="离线夹具", severity="minor", area="difficulty")]
        (vault / "repair-review.json").write_bytes(
            entry.canonical(
                dict(
                    candidate_digest=rec["candidate"]["candidate_digest"],
                    verdict="ordinary_wording_repair",
                    independent_evaluator="fixture",
                    issues=issues,
                )
            )
        )
        bad = (
            fixture.envelope(rec["candidate"]["raw_output"], phase="analysis")
            if bad_kind == "phase"
            else b'{"bad":'
        )
        with pytest.raises(Exception):
            entry.send(
                "repair",
                vault,
                approval,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, stream=httpx.ByteStream(bad))
                ),
                key="fake-not-a-key",
            )
        assert (
            entry.raw_io.decrypt(vault / "repair.raw.enc", Fernet((vault / "raw.key").read_bytes()))
            == bad
        )
        assert (vault / "STOP").exists() and not (vault / "repair.record.json").exists()
        with pytest.raises(SnapshotError):
            entry.send("plan", vault, approval, transport=mock, key="fake-not-a-key")
        assert len(count) == 2


def test_wrong_goal_refused_no_provider():
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        h = {"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())}
        r = client.post("/api/free-courses", json={"goal": "排序", "code_language": "c"}, headers=h)
        assert r.status_code in (400, 409, 422), r.text
