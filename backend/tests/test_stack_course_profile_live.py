"""Paired single-send slots with real admission code and isolated offline evidence."""

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


def test_profile_pair_review_admission_preserves_individual_and_pair_results(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    profiles = list(publication.STACK_PROFILE_LIVE.values())
    approvals = [trial.approval_values(profile, fixture=True) for profile in profiles]
    earlier_review = None

    async def seed(owner, case):
        engine = create_database_engine()
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                result = await persist_profile_version(
                    db, owner_id=owner, profile=pair.profile_snapshot(case)
                )
                return result.id
        finally:
            await engine.dispose()

    with TestClient(app, base_url="https://testserver") as other:
        other.post("/api/auth/guest")
        for index, profile in enumerate(profiles):
            with TestClient(app, base_url="https://testserver") as client:
                owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
                pid = asyncio.run(seed(owner, profile.learner_case))
                vault = tmp_path / str(index)
                options = dict(fixture=True, profile=profile)
                for wrong in (
                    approvals[1 - index],
                    dict(approvals[index], pair_max_http_requests=3),
                ):
                    with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
                        asyncio.run(trial.prepare(vault, owner, wrong, profile_id=pid, **options))
                ctx = asyncio.run(trial.prepare(
                    vault, owner, approvals[index], profile_id=pid, **options
                ))
                response = with_direct_echo(profile.request(ctx), envelope(teaching_fixture()))
                calls = []

                def handle(request):
                    calls.append(request.content)
                    return httpx.Response(200, stream=httpx.ByteStream(response))

                send = dict(
                    transport=httpx.MockTransport(handle), key="fixture-key", profile=profile
                )
                candidate = trial.send(vault, **send)
                assert calls == [trial.request_path(profile).read_bytes()]
                assert trial.replay(vault, **options) == candidate
                for stage, message in (("generate", "BATCH_STOPPED"), ("revise", "STAGE_REQUIRED")):
                    with pytest.raises(SnapshotError, match=message):
                        trial.send(vault, stage=stage, **send)
                with pytest.raises(SnapshotError, match="VAULT_REQUIRED"):
                    trial.replay(vault, profile=profile)
                assert len(calls) == 1

                checks = dict.fromkeys(profile.checks, True)
                checks["teaching_depth_matches_profile"] = False
                review = dict(
                    candidate_digest=candidate["candidate_digest"], parent_digest=None,
                    verdict="pass", independent_evaluator="fixture-only",
                    full_lesson_reviewed=True, evidence_kind="offline_fixture",
                    checks=checks, blocking_findings=[],
                )
                for rejected in (dict(review, evidence_kind="actual_provider_response"),
                                 dict(review, full_lesson_reviewed=False), earlier_review):
                    if rejected is not None:
                        (vault / "review.json").write_bytes(canonical(rejected))
                        with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
                            trial.publish(vault, **options)
                earlier_review = review
                (vault / "review.json").write_bytes(canonical(review))
                result = trial.publish(vault, **options)
                course = result["course_id"]
                route = f"/api/free-courses/{course}/versions/2/scenes/{ctx['scene_id']}"
                scene = client.get(route)
                assert scene.status_code == 200, scene.text
                assert other.get(route).status_code == 404
                assert '"answer_key"' not in scene.text and '"solution"' not in scene.text
                source = scene.json()["generation_source"]
                assert source["learner_case"] == profile.learner_case
                assert source["review_sha256"] == trial.sha(canonical(review))
                assert source["source_response_sha256"] == trial.sha(response)
                assert source["source_request_sha256"] == trial.sha(calls[0])
                assert source["evidence_kind"] == "offline_fixture"
