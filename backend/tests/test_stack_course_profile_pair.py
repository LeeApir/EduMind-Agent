"""Verify the paired profile snapshots reach the shared wire and candidate gates."""

import asyncio
import json
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

CASES = publication.STACK_PROFILE_CASES


def test_frozen_requests_only_differ_in_learner_evidence():
    common_requests = []
    for case, profile in CASES.items():
        request = profile.request()
        package = trial.package_path(profile)
        assert canonical(request) == (package / "request.json").read_bytes()
        exact_input = trial.read(package / "input.json")
        payload = json.loads(request["input"][1]["content"])
        evidence = payload.pop("learner_evidence")
        assert evidence == pair.learner_input(case) == exact_input["learner_evidence"]
        assert exact_input["profile_snapshot"] == pair.profile_snapshot(case)
        assert evidence["evidence"]["engineering_preference"] is None
        assert evidence["evidence"]["professional_background"] is None
        assert evidence["evidence"]["extended_dimensions"] is None
        assert payload == {
            "goal": exact_input["goal"],
            "plan": exact_input["plan"],
            "materials": profile.materials.materials(),
        }
        request["input"][1]["content"] = canonical(payload).decode()
        common_requests.append(canonical(request))
    assert len(set(common_requests)) == 1
    legacy = publication.STACK.request()
    assert "learner_evidence" not in json.loads(legacy["input"][1]["content"])
    legacy_request = trial.package_path(publication.STACK) / "request.json"
    assert canonical(legacy) == legacy_request.read_bytes()


def test_persisted_profiles_reach_transport_and_bind_to_candidates(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    results = []

    async def seed(owner, case):
        engine = create_database_engine()
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                row = await persist_profile_version(
                    db, owner_id=owner, profile=pair.profile_snapshot(case)
                )
                return row.id
        finally:
            await engine.dispose()

    def review(candidate, profile):
        return dict(
            candidate_digest=candidate["candidate_digest"], parent_digest=None, verdict="pass",
            independent_evaluator="fixture-only", full_lesson_reviewed=True,
            checks=dict.fromkeys(profile.checks, True), blocking_findings=[],
        )

    for case, profile in CASES.items():
        with TestClient(app, base_url="https://testserver") as client:
            owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
        pid = asyncio.run(seed(owner, case))
        other = next(p for key, p in CASES.items() if key != case)
        offline = dict(fixture=True, profile=profile)
        with pytest.raises(SnapshotError, match="OFFLINE_ONLY"):
            trial.approval_values(profile)
        with pytest.raises(SnapshotError, match="PROFILE_BINDING"):
            asyncio.run(trial.prepare(
                tmp_path / f"wrong-{case}", owner, trial.approval_values(other, fixture=True),
                profile_id=pid, fixture=True, profile=other,
            ))

        vault = tmp_path / case
        ctx = asyncio.run(trial.prepare(
            vault, owner, trial.approval_values(profile, fixture=True), profile_id=pid, **offline,
        ))
        assert ctx["profile_id"] == str(pid)
        assert ctx["learner_evidence"] == pair.evidence(case)
        response = with_direct_echo(profile.request(), envelope(teaching_fixture()))
        calls = []

        def handle(http_request):
            calls.append(http_request.content)
            return httpx.Response(200, stream=httpx.ByteStream(response))

        send = dict(profile=profile, transport=httpx.MockTransport(handle), key="fixture-key")
        with pytest.raises(SnapshotError, match="STAGE_REQUIRED"):
            trial.send(vault, stage="revise", **send)
        candidate = trial.send(vault, **send)
        assert calls == [(trial.package_path(profile) / "request.json").read_bytes()]
        assert trial.replay(vault, **offline) == candidate
        with pytest.raises(SnapshotError, match="OFFLINE_ONLY"):
            trial.send(vault, profile=profile)
        assert candidate["receipt"]["request_sha256"] == trial.sha(calls[0])
        assert candidate["context"] == ctx
        assert candidate["materials_digest"] == trial.read(
            trial.package_path(profile) / "input.json"
        )["materials_digest"]
        wrong = dict(candidate["receipt"], request_sha256=trial.sha(canonical(other.request())))
        with pytest.raises(SnapshotError, match="REQUEST_BINDING"):
            publication.candidate(ctx, teaching_fixture(), wrong, profile=profile)
        changed = dict(ctx, learner_evidence=pair.evidence(other.learner_case))
        with pytest.raises(SnapshotError, match="PROFILE_BINDING"):
            publication.candidate(
                changed, teaching_fixture(), candidate["receipt"], profile=profile
            )
        assessment = review(candidate, profile)
        assembled = publication.assembly(candidate, assessment, profile=profile)
        assert assembled["generation_source"]["evidence_kind"] == "offline_fixture"
        trial.save(vault, "review.json", assessment)
        with pytest.raises(SnapshotError, match="PROFILE_PREPARATION_ONLY"):
            trial.publish(vault, **offline)
        results.append((profile, candidate, assessment, assembled))

    first, second = results
    assert first[1]["materials_digest"] == second[1]["materials_digest"]
    assert first[1]["plan_digest"] == second[1]["plan_digest"]
    assert first[1]["candidate_digest"] != second[1]["candidate_digest"]
    assert first[3]["blocks"] == second[3]["blocks"]
    assert first[3]["actions"] == second[3]["actions"]
    with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
        publication.assembly(second[1], first[2], profile=second[0])
    incomplete = dict(second[2], full_lesson_reviewed=False)
    with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
        publication.assembly(second[1], incomplete, profile=second[0])
