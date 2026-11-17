"""Check the exact r02 request, approval and private projection through the shared flow."""

import asyncio
import os
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from test_head_course_fixed import with_direct_echo
from test_stack_course_trial import teaching_fixture

from app.core.database import create_database_engine
from app.main import app
from app.services import course_trial_publication as publication
from app.services import stack_course_profile_pair as pair
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.profile_updates import persist_profile_version
from scripts import course_trial_generation as trial
from scripts.head_course_goal_fixture import envelope


@pytest.mark.parametrize("topic", publication.STACK_PROFILE_V2_LIVE)
def test_v2_one_body_with_exact_request_and_new_private_source(monkeypatch, tmp_path, topic):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    profile = publication.STACK_PROFILE_V2_LIVE[topic]
    case = profile.learner_case
    old = publication.STACK_PROFILE_LIVE[topic.removesuffix("-v2")]
    assert trial.vault_path(profile) != trial.vault_path(old)
    options = dict(fixture=True, profile=profile)
    approval = trial.approval_values(profile, fixture=True)
    wrong = dict(approval, batch=old.batch, request_sha256=trial.sha(canonical(old.request())))
    vault = tmp_path / "r02"
    request = profile.request()
    response = with_direct_echo(request, envelope(teaching_fixture()))
    calls = []

    async def seed(owner):
        engine = create_database_engine()
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                row = await persist_profile_version(
                    db, owner_id=owner, profile=pair.profile_snapshot(case)
                )
                return row.id
        finally:
            await engine.dispose()

    def handle(request):
        calls.append(request.content)
        return httpx.Response(200, stream=httpx.ByteStream(response))

    with TestClient(app, base_url="https://testserver") as client:
        owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
        pid = asyncio.run(seed(owner))
        with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
            asyncio.run(trial.prepare(vault, owner, wrong, profile_id=pid, **options))
        assert not vault.exists()
        ctx = asyncio.run(trial.prepare(vault, owner, approval, profile_id=pid, **options))
        transport = httpx.MockTransport(handle)
        candidate = trial.send(vault, profile=profile, transport=transport, key="fixture-key")
        assert calls == [trial.request_path(profile).read_bytes()]
        assert trial.replay(vault, **options) == candidate
        with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
            trial.send(vault, profile=profile, transport=transport, key="fixture-key")
        assert len(calls) == 1
        review = dict(
            candidate_digest=candidate["candidate_digest"], parent_digest=None, verdict="pass",
            independent_evaluator="fixture-only", full_lesson_reviewed=True,
            evidence_kind="offline_fixture", checks=dict.fromkeys(profile.checks, True),
            blocking_findings=[],
        )
        trial.save(vault, "review.json", review)
        result = trial.publish(vault, **options)
        cid = result["course_id"]
        scene = client.get(f"/api/free-courses/{cid}/versions/2/scenes/{ctx['scene_id']}")
        assert scene.status_code == 200, scene.text
        source = scene.json()["generation_source"]
        assert source["batch"] == profile.batch and source["prompt_version"] == pair.PROMPT_V2
        assert source["learner_case"] == case and source["evidence_kind"] == "offline_fixture"
        assert source["source_request_sha256"] == trial.sha(calls[0])
        assert source["review_sha256"] == trial.sha(canonical(review))
        assert "answer_key" not in scene.text and '"solution"' not in scene.text
