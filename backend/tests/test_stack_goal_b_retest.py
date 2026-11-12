import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo
from test_stack_multiscene import practice_fixture

from app.main import app
from app.services.free_course_snapshots import SnapshotError
from scripts import stack_goal_b_retest as retest
from scripts import stack_goal_continuation as continuation
from scripts import stack_multiscene_trial as stack
from scripts.head_course_goal_fixture import envelope


@pytest.mark.skipif(
    os.environ.get("EDUMIND_T150_ARCHIVE_CHECK") != "1",
    reason="requires the local T147 and T149 encrypted originals and dedicated PostgreSQL",
)
@pytest.mark.parametrize("unauthorized", [False, True])
def test_only_b_runs_with_reviewed_upstream(monkeypatch, tmp_path, unauthorized):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    archive = continuation.VAULT / "B"
    old_request = stack.read(archive / "normal.request.json")
    old_payload = json.loads(old_request["input"][1]["content"])
    old_approval = stack.read(continuation.VAULT / "batch.json")["approval"]
    source, _ = retest.verify_source()
    calls, admitted = [], {}

    def mock(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][1]["content"])
        stage = retest.STAGES[len(calls)]
        assert payload["scene_key"] == stage
        assert payload["request"]["original_goal"] == old_payload["request"]["original_goal"]
        assert payload["plan"]["candidate"] == old_payload["plan"]["candidate"]
        assert payload["materials_digest"] == old_payload["materials_digest"]
        if stage == "normal":
            assert {k: v for k, v in body.items() if k != "input"} == {
                k: v for k, v in old_request.items() if k != "input"
            }
            assert body["input"][0] == old_request["input"][0]
            for key in ("demonstration", "practice", "prompt_version", "wire_protocol"):
                assert payload[key] == old_payload[key]
            assert payload["request"]["operation_id"] != old_payload["request"]["operation_id"]
        else:
            upstream, = payload["upstream_context"]
            assert upstream["scene_version_id"] == admitted["normal"]["scene_version_id"]
            assert upstream["digest"] == admitted["normal"]["scene_digest"]
        calls.append(stage)
        if unauthorized:
            return httpx.Response(401, stream=httpx.ByteStream(b'{"error":{}}'))
        response = with_direct_echo(body, envelope(practice_fixture(payload)))
        return httpx.Response(200, stream=httpx.ByteStream(response))

    batch = retest.Batch(tmp_path / "batch", url, transport=httpx.MockTransport(mock))
    with TestClient(app, base_url="https://testserver") as client:
        owner = client.post("/api/auth/guest").json()["user"]["id"]
        with pytest.raises(SnapshotError, match="STACK_EXACT_AUTHORIZATION_REQUIRED"):
            batch.start(old_approval)
        run = batch.start(retest.approval_values(owner, fixture=True))
        assert set(run["courses"]) == {"B"}
        bound = stack.read(batch.vault / "B" / "plan.admitted.json")
        assert bound["selection_replay"] == source
        with pytest.raises(SnapshotError, match="STACK_SELECTOR_ORDER"):
            batch.perform("send", "rejections", key="fixture")
        with pytest.raises(SnapshotError, match="STACK_STAGE_NOT_AUTHORIZED"):
            batch.perform("send", "plan", key="fixture")
        if unauthorized:
            with pytest.raises(SnapshotError, match="STACK_BODY_RECEIPT"):
                batch.perform("send", "normal", key="fixture")
            receipt = stack.read(batch.vault / "B" / "normal.body.json")
            assert receipt["http_status"] == 401 and calls == ["normal"]
        else:
            for stage in retest.STAGES:
                candidate = batch.perform("send", stage, key="fixture")
                inspected = batch.perform("inspect", stage)
                bindings = [candidate]
                if stage == "rejections":
                    bindings.insert(0, admitted["normal"]["candidate_digest"])
                admitted[stage] = batch.perform("review", stage, review=dict(
                    candidates=bindings, verdict="pass", reviewer="fixture",
                    checks=dict.fromkeys(inspected["required_checks"], "pass"),
                    notes="checked fixture",
                ))
            assert calls == list(retest.STAGES)
            course_id = run["courses"]["B"]["course_id"]
            head = client.get(f"/api/free-courses/{course_id}").json()["head"]
            assert head["version"] == 3 and head["complete"]
        assert (batch.vault / "STOP").exists()
        with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
            batch.perform("send", "rejections", key="fixture")
    assert retest.verify_source()[0] == source
