"""Exact T121 parent, single allowed leaf, and offline revised-course admission."""

import asyncio
import json
import os
from copy import deepcopy
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo
from test_queue_course_trial import teaching

from app.main import app
from app.services import queue_course_revision as revision
from app.services.course_trial_publication import QUEUE, QUEUE_REVISION, candidate
from app.services.free_course_contract import validate
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts import head_course_goal_fixture as fixtures

PROFILE = QUEUE_REVISION
# Fixture text for checking the replacement path. It is not a teaching result.
REPLACEMENT = {revision.KEY: "离线测试替换段落"}


@pytest.fixture(autouse=True)
def sealed_fixture(monkeypatch):
    raw = teaching()
    for index, paragraph in enumerate(raw["paragraphs"]):
        paragraph["text"] = f"离线父稿第 {index} 段"
    parent = candidate(
        dict(course_id="fixture-parent-course", operation_id="fixture-parent-operation"),
        raw,
        dict(request_sha256="1" * 64, raw_sha256="2" * 64),
        profile=QUEUE,
    )
    finding = dict(id="Q01", path="raw_output.paragraphs[2].text")
    monkeypatch.setattr(revision, "PARENT", parent["candidate_digest"])
    monkeypatch.setattr(revision, "sealed_parent", lambda: (parent, finding, "3" * 64))


def test_exact_parent_request_and_single_leaf():
    parent, finding, review_sha = revision.sealed_parent()
    request = revision.request()
    scope = json.loads(request["input"][1]["content"])["materials"]
    assert scope["parent_digest"] == parent["candidate_digest"] == revision.PARENT
    assert scope["parent_request_sha256"] == parent["receipt"]["request_sha256"]
    assert scope["parent_response_sha256"] == parent["receipt"]["raw_sha256"]
    assert scope["parent_review_sha256"] == review_sha and scope["finding"] == finding
    assert scope["materials_digest"] == parent["materials_digest"]
    assert scope["plan_digest"] == parent["plan_digest"]
    assert scope["allowed_path"] == ["raw_output", "paragraphs", 2, "text"]
    assert scope["source"] == revision.materials()["main"]["source"]
    assert set(scope["facts"]) == set(parent["raw_output"]["paragraphs"][2]["fact_ids"])
    assert b"private_answer" not in canonical(request)
    assert request["text"]["format"]["schema"] == revision.SCHEMA
    expected = deepcopy(parent["raw_output"])
    expected["paragraphs"][2]["text"] = REPLACEMENT[revision.KEY]
    child = revision.merge(REPLACEMENT)
    assert canonical(child) == canonical(expected)
    original_assembly = revision.assemble(parent["raw_output"], {})
    original_assembly["blocks"][2]["markdown"] = REPLACEMENT[revision.KEY]
    assert revision.assemble(child, {}) == original_assembly


@pytest.mark.parametrize(
    "output",
    [
        {},
        {revision.KEY: 3},
        {revision.KEY: "", "fact_ids": []},
        {**REPLACEMENT, "summary": "changed"},
        {**REPLACEMENT, "questions": {}},
    ],
)
def test_replacement_rejects_outside_schema(output):
    with pytest.raises(SnapshotError, match="QUEUE_REVISION_SCHEMA"):
        revision.merge(output)


def test_replacement_rejects_no_op_neighbor_and_outside_leaf():
    parent, _, _ = revision.sealed_parent()
    for text in (" ", "第一行\n第二行", *(p["text"] for p in parent["raw_output"]["paragraphs"])):
        with pytest.raises(SnapshotError, match="QUEUE_REVISION_TEXT"):
            revision.merge({revision.KEY: text})
    child = revision.merge(REPLACEMENT)
    child["paragraphs"][2]["fact_ids"] = ["order"]
    with pytest.raises(SnapshotError, match="QUEUE_REVISION_OUTSIDE_SCOPE"):
        revision.validate_immutable(child)


def test_shared_revision_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    package = tmp_path / "frozen-fixture"
    package.mkdir()
    (package / "request.json").write_bytes(canonical(revision.request()))
    (package / "manifest.json").write_bytes(canonical(dict(files={})))
    monkeypatch.setattr(trial, "package_path", lambda profile: package)
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        vault = tmp_path / "revision"
        approval = trial.approval_values(PROFILE)
        with pytest.raises(SnapshotError, match="QUEUE_EXACT_AUTHORIZATION_REQUIRED"):
            asyncio.run(
                trial.prepare(
                    vault,
                    owner,
                    dict(approval, batch="queue-fifo-deepseek-r01"),
                    fixture=True,
                    profile=PROFILE,
                )
            )
        assert not vault.exists()
        ctx = asyncio.run(trial.prepare(vault, owner, approval, fixture=True, profile=PROFILE))
        parent, _, _ = revision.sealed_parent()
        assert ctx["operation_id"] != parent["context"]["operation_id"]
        assert ctx["course_id"] != parent["context"]["course_id"]
        route = f"/api/free-courses/{ctx['course_id']}"
        status = client.get(f"{route}/operations/{ctx['operation_id']}").json()
        assert status["execution_mode"] == "finite_queue_foreground" and status["budget"] is None
        raw = with_direct_echo(revision.request(), fixtures.envelope(REPLACEMENT))
        calls = []

        def handle(request):
            calls.append(request.content)
            assert request.content == (trial.package_path(PROFILE) / "request.json").read_bytes()
            return httpx.Response(200, stream=httpx.ByteStream(raw))

        kwargs = dict(
            transport=httpx.MockTransport(handle), key="offline-fixture-key", profile=PROFILE
        )
        child = trial.send(vault, **kwargs)
        assert child["parent_digest"] == revision.PARENT
        assert trial.replay(vault, fixture=True, profile=PROFILE) == child
        review = dict(
            candidate_digest=revision.PARENT,
            verdict="pass",
            independent_evaluator="fixture-only",
            blocking_findings=[],
            checks=dict.fromkeys(PROFILE.checks, True),
        )
        review_path = vault / "review.json"
        review_path.write_bytes(canonical(review))
        with pytest.raises(SnapshotError, match="QUEUE_REVIEW_REQUIRED"):
            trial.publish(vault, fixture=True, profile=PROFILE)
        assert client.get(route).json()["head"]["version"] == 1
        review_path.write_bytes(canonical(dict(review, candidate_digest=child["candidate_digest"])))
        ready = trial.publish(vault, fixture=True, profile=PROFILE)
        view = client.get(f"{route}/versions/2/scenes/{ready['scene_id']}")
        assert view.status_code == 200, view.text
        source = view.json()["generation_source"]
        assert source["parent_digest"] == revision.PARENT
        assert source["batch"] == revision.BATCH and source["evidence_kind"] == "offline_fixture"
        actual = view.json()
        actual["generation_source"]["evidence_kind"] = "evidence_bound_local_revision"
        validate("SceneProjection", actual)
        actual["generation_source"]["parent_digest"] = None
        with pytest.raises(SnapshotError):
            validate("SceneProjection", actual)
        assert view.json()["blocks"][2]["markdown"] == REPLACEMENT[revision.KEY]
        assert '"answer_key"' not in view.text and '"solution"' not in view.text
        with pytest.raises(SnapshotError, match="QUEUE_BATCH_STOPPED"):
            trial.send(vault, **kwargs)
        assert len(calls) == 1
        assert revision.sealed_parent()[0] == parent
