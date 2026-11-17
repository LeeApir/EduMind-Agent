"""Exercise the exact T130 entry with a socket-free Provider fixture and private DB."""

import asyncio
import os
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from test_binary_search_course_trial import teaching
from test_head_course_fixed import with_direct_echo

from app.main import app
from app.services.binary_search_course_frames import materials
from app.services.course_trial_publication import BINARY_SEARCH_FRAMES as PROFILE
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts.head_course_goal_fixture import envelope


@pytest.mark.parametrize("invalid", [False, True])
def test_single_sealed_new_body(monkeypatch, tmp_path, invalid):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    vault = tmp_path / "vault"
    wire = PROFILE.request()
    request_bytes = canonical(wire)
    assert request_bytes == (trial.package_path(PROFILE) / "request.json").read_bytes()
    options = dict(fixture=True, profile=PROFILE)
    approval = trial.approval_values(PROFILE, fixture=True)
    raw = teaching()
    if not invalid:
        del raw["step_notes"]
    response = with_direct_echo(wire, envelope(raw))
    calls = []

    def handle(request):
        assert request.content == request_bytes
        calls.append(request.content)
        return httpx.Response(200, stream=httpx.ByteStream(response))

    send = dict(transport=httpx.MockTransport(handle), key="fixture-key", profile=PROFILE)
    with (
        TestClient(app, base_url="https://testserver") as client,
        TestClient(app, base_url="https://testserver") as other,
    ):
        owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
        other.post("/api/auth/guest")
        for wrong in (
            trial.approval_values(PROFILE), dict(approval, max_http_requests=2),
            dict(approval, request_sha256="0" * 64),
        ):
            with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
                asyncio.run(trial.prepare(vault, owner, wrong, **options))
        assert not vault.exists()
        ctx = asyncio.run(trial.prepare(vault, owner, approval, **options))
        route = f"/api/free-courses/{ctx['course_id']}"
        op = client.get(f"{route}/operations/{ctx['operation_id']}").json()
        assert op["execution_mode"] == "finite_binary_search_foreground" and op["budget"] is None
        for stage in ("plan", "revise"):
            with pytest.raises(SnapshotError):
                trial.send(vault, stage=stage, **send)
        assert calls == []
        if invalid:
            with pytest.raises(trial.raw_io.wire.PilotError, match="ROLE_SCHEMA"):
                trial.send(vault, **send)
            assert trial.read(vault / "generate.failure.json") == dict(
                attempted=True, code="ROLE_SCHEMA", error_type="PilotError"
            )
            _, cipher = trial.local_gate(vault, **options)
            assert trial.raw_io.decrypt(vault / "generate.raw.enc", cipher) == response
            assert (vault / "STOP").exists()
            assert not (vault / "generate.candidate.json").exists()
            with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
                trial.send(vault, **send)
            with pytest.raises(SnapshotError, match="SAVED_BINDING"):
                trial.publish(vault, **options)
            assert len(calls) == 1 and client.get(route).json()["head"]["version"] == 1
            return

        child = trial.send(vault, **send)
        assert child["raw_output"] == raw
        assert child["materials_digest"] == materials()["materials_digest"]
        assert trial.replay(vault, **options) == child
        with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
            trial.send(vault, **send)
        assert len(calls) == 1
        review = dict(
            candidate_digest=child["candidate_digest"],
            parent_digest=None,
            verdict="pass",
            full_lesson_reviewed=True,
            independent_evaluator="fixture-only",
            blocking_findings=[],
            checks=dict.fromkeys(PROFILE.checks, True),
        )
        review_path = vault / "review.json"
        archived_review = trial.read(
            trial.ROOT / "docs/acceptance/phase-1.5-binary-search-frames-t129/assessment.json"
        )
        for wrong in (
            archived_review,
            dict(review, full_lesson_reviewed=False),
            dict(
                review,
                checks={**review["checks"], "lesson_prose_matches_program_iterations": False},
            ),
        ):
            review_path.write_bytes(canonical(wrong))
            with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
                trial.publish(vault, **options)
        assert client.get(route).json()["head"]["version"] == 1
        review_path.write_bytes(canonical(review))
        ready = trial.publish(vault, **options)
        scene_path = f"{route}/versions/2/scenes/{ctx['scene_id']}"
        scene = client.get(scene_path)
        assert scene.status_code == 200, scene.text
        assert other.get(scene_path).status_code == 404
        assert '"answer_key"' not in scene.text and '"solution"' not in scene.text
        assert scene.json()["scene_version_id"] == ready["scene_version_id"]
        source = scene.json()["generation_source"]
        assert source["evidence_kind"] == "offline_fixture" and source["parent_digest"] is None
        assert source["source_request_sha256"] == trial.sha(request_bytes)
        assert source["source_response_sha256"] == trial.sha(response)
        assert source["review_sha256"] == trial.sha(canonical(review))
        steps = next(b["steps"] for b in scene.json()["blocks"] if b["kind"] == "visualization")
        frames = [step["binary_search_frame"] for step in steps]
        assert [(f["iteration"], f["comparison_frame_id"]) for f in frames] == [
            (None, None), (1, "f1"), (1, "f1"), (2, "f3"), (2, "f3"), (3, "f5"),
        ]
        assert "尚未重新计算" in frames[2]["note"] and "尚未重新计算" in frames[4]["note"]
