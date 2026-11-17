"""Exact evidence-bound two-field revision; fixtures are never counted as model success."""

import asyncio
import hashlib
import json
import os
import time
from copy import deepcopy
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.main import app
from app.services import head_course_evidence_publication as publication
from app.services import head_course_evidence_revision as f
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import head_course_fact_revision as entry
from scripts import head_course_goal_fixture as fixture


def replacements():
    data = f.inputs()
    # Explicit test-only output, no saved teaching replacement or Provider response.
    return dict(
        failure_scope="离线夹具：两次成功分配，两次判空继续；未演示掩码不分配或真实malloc失败。",
        paragraph_5=dict(
            text=data["parent_candidate"]["raw_output"]["paragraphs"][5]["text"],
            fact_ids=data["revision_scope"]["required_fact_ids"]["paragraph_5"],
        ),
    )


def test_exact_request_and_only_allowed_merge():
    data = f.inputs()
    parent = deepcopy(data["parent_candidate"])
    snapshot = canonical(parent)
    request = f.body()
    assert json.loads(request["input"][1]["content"]) == data
    assert set(request["text"]["format"]["schema"]["properties"]) == {
        "failure_scope",
        "paragraph_5",
    }
    c = f.merge(parent, replacements())
    assert canonical(parent) == snapshot and c["parent_digest"] == parent["candidate_digest"]
    assert (
        c["payload"]["teaching_evidence"]["evidence_digest"]
        == data["revision_scope"]["evidence_digest"]
    )
    assert c["raw_output"]["paragraphs"][5]["text"] == parent["raw_output"]["paragraphs"][5]["text"]
    f.validate_immutable(parent, c, data)
    assert f.assemble(c)["blocks"][-2]["markdown"] == parent["raw_output"]["learning_summary"]
    assert (
        next(b for b in f.assemble(c)["blocks"] if b["kind"] == "visualization")["text_alternative"]
        == parent["raw_output"]["learning_summary"]
    )
    for part in ("step_notes", "questions", "learning_summary", "lifecycle", "prerequisites"):
        assert c["raw_output"][part] == parent["raw_output"][part]


@pytest.mark.parametrize(
    "kind",
    ["missing", "extra", "fact", "empty", "copy", "outside", "payload", "evidence", "parent"],
)
def test_refuse_wrong_scope_and_drift(kind):
    data = f.inputs()
    parent = deepcopy(data["parent_candidate"])
    out = replacements()
    if kind == "missing":
        del out["failure_scope"]
    if kind == "extra":
        out["learning_summary"] = "extra"
    if kind == "fact":
        out["paragraph_5"]["fact_ids"] = ["obs_allocation_failures"]
    if kind == "empty":
        out["paragraph_5"]["text"] = ""
    if kind == "copy":
        out["paragraph_5"]["text"] = parent["raw_output"]["paragraphs"][4]["text"]
    if kind == "parent":
        parent["raw_output"]["learning_summary"] = "changed"
    if kind in ("outside", "payload", "evidence"):
        c = f.merge(parent, out)
        if kind == "outside":
            c["raw_output"]["step_notes"][0]["note"] = "changed"
        if kind == "payload":
            c["payload"]["materials"]["answers"]["normal_values"] = "[]"
        if kind == "evidence":
            c["payload"]["teaching_evidence"]["facts"][
                "head_evidence_v1.discard_return_comparison"
            ]["displayed_in_main_player"] = True
        with pytest.raises(SnapshotError):
            f.assemble(c)
    else:
        with pytest.raises(Exception):
            f.merge(parent, out)


def configured(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir(mode=0o700)
    (vault / "raw.key").write_bytes(Fernet.generate_key())
    (vault / "raw.key").chmod(0o600)
    sha = hashlib.sha256((f.PACKAGE / "manifest.json").read_bytes()).hexdigest()
    monkeypatch.setattr(entry, "f", f)
    monkeypatch.setattr(entry, "PACKAGE", f.PACKAGE)
    monkeypatch.setattr(entry, "VAULT", vault)
    monkeypatch.setattr(entry, "package_digest", lambda: sha)
    data = f.inputs()
    start = int(time.time()) - 1
    approval = dict(
        manifest_sha256=sha,
        parent_digest=data["parent_candidate"]["candidate_digest"],
        evidence_digest=data["teaching_evidence"]["evidence_digest"],
        protocol_version=f.VERSION,
        explicit_user_authorization=True,
        accept_ADR0054_scope_and_batch_C2=True,
        max_http_requests=1,
        starts_epoch=start,
        expires_epoch=start + 600,
    )
    (vault / "approval.json").write_bytes(canonical(approval))
    return vault, approval


@pytest.mark.parametrize("mode", ["success", "phase", "duplicate", "overbudget"])
def test_actual_single_request_entry(tmp_path, monkeypatch, mode):
    vault, approval = configured(tmp_path, monkeypatch)
    calls = []
    value = replacements()
    raw = fixture.envelope(value, phase="analysis" if mode == "phase" else "final_answer")
    if mode == "overbudget":
        obj = json.loads(raw)
        obj["usage"] = dict(input_tokens=10, output_tokens=4001, total_tokens=4011)
        raw = canonical(obj)
    if mode == "duplicate":
        obj = json.loads(raw)
        text = canonical(value).decode()
        obj["output"][0]["content"][0]["text"] = (
            text[:-1]
            + ',"failure_scope":'
            + json.dumps(value["failure_scope"], ensure_ascii=False)
            + "}"
        )
        raw = canonical(obj)

    def respond(request):
        calls.append(1)
        assert json.loads(request.content) == f.body()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    if mode == "success":
        entry.send(vault, approval, transport=httpx.MockTransport(respond), key="fake-test-only")
        record = entry.read_saved(vault)
        assert record["candidate"] == f.merge(f.inputs()["parent_candidate"], value)
        publication.validate_record(record)
        assert (vault / "STOP").exists() and not (vault / "ACTIVE").exists()
    else:
        with pytest.raises(Exception):
            entry.send(
                vault, approval, transport=httpx.MockTransport(respond), key="fake-test-only"
            )
        assert (vault / "STOP").exists() and (vault / "ACTIVE").exists()
        assert (
            entry.old.raw_io.decrypt(
                vault / "revision.raw.enc", Fernet((vault / "raw.key").read_bytes())
            )
            == raw
        )
    with pytest.raises(SnapshotError):
        entry.send(vault, approval, transport=httpx.MockTransport(respond), key="fake-test-only")
    assert len(calls) == 1


def test_private_import_exact_projection_and_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_HEAD_GOAL_DEVELOPMENT", "1")
    vault, approval = configured(tmp_path, monkeypatch)
    mock = httpx.MockTransport(
        lambda request: httpx.Response(
            200, stream=httpx.ByteStream(fixture.envelope(replacements()))
        )
    )
    entry.send(vault, approval, transport=mock, key="fake-test-only")
    record = entry.read_saved(vault)
    c = record["candidate"]
    review = dict(
        candidate_digest=c["candidate_digest"],
        parent_digest=c["parent_digest"],
        verdict="pass",
        independent_evaluator="offline_fixture_only",
        evidence_digest=c["payload"]["teaching_evidence"]["evidence_digest"],
        planning_basis_binding=c["payload"]["planning_basis"]["binding"],
        blocking_findings=[],
        checks={
            key: True
            for key in (
                "full_lesson",
                "fact_citations",
                "paragraph_responsibilities",
                "no_neighbour_copy",
                "no_omitted_explanation",
                "code_trace_answers",
                "no_answer_hints",
                "display_scope",
                "paragraph_algorithm_preserved",
            )
        },
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])

        async def imported(db):
            return await publication.import_course(db, owner, record, review)

        result = asyncio.run(entry.old.database(imported))
        assert asyncio.run(entry.old.database(imported)) == result
        route = f"/api/free-courses/{result['course_id']}/versions/2/scenes/{result['scene_id']}"
        response = client.get(route)
        assert response.status_code == 200, response.text
        scene = response.json()
        assert "answer_key" not in response.text and "solution" not in response.text
        assert scene["generation_source"]["candidate_digest"] == c["candidate_digest"]
        assert (
            scene["generation_source"]["teaching_evidence_digest"]
            == f.inputs()["teaching_evidence"]["evidence_digest"]
        )
        assert scene["generation_source"]["evidence_kind"] == "offline_fixture"
        op = client.get(
            f"/api/free-courses/{result['course_id']}/operations/{result['operation_id']}"
        ).json()
        assert op["execution_mode"] == "finite_head_foreground" and op["budget"] is None
        exercise = scene["blocks"][-1]
        answers = dict(
            course_version=2,
            scene_id=result["scene_id"],
            scene_version_id=scene["scene_version_id"],
            exercise_id=exercise["exercise_id"],
            exercise_version_id=exercise["exercise_version_id"],
            answers=[
                dict(question_id=k, answer=v)
                for k, v in c["payload"]["materials"]["answers"].items()
            ],
        )
        attempt = client.post(
            f"/api/free-courses/{result['course_id']}/attempts",
            json=answers,
            headers={
                "X-CSRF-Token": auth["csrf_token"],
                "Idempotency-Key": "evidence-revision-test",
            },
        )
        assert attempt.status_code == 201, attempt.text
        path = f"/api/free-courses/{result['course_id']}/attempts/{attempt.json()['attempt_id']}"
        feedback = client.get(path).json()
        assert feedback["comparison_score"] == 1 and feedback["mastery_effect"] == "course_only"
        assert client.get(path).json() == feedback and client.get(route).json() == scene
        bad = deepcopy(review)
        bad["checks"]["paragraph_algorithm_preserved"] = False
        with pytest.raises(SnapshotError):
            publication.assembled(record, bad)
