"""Exercise the frozen six-step foreground package with no Provider traffic."""

import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo
from test_stack_goal_selection import CASES, fixture
from test_stack_multiscene import practice_fixture

from app.main import app
from app.services.free_course_snapshots import SnapshotError
from scripts import stack_goal_selection_trial as goal
from scripts import stack_multiscene_trial as stack
from scripts.head_course_goal_fixture import envelope

PLAN_FIXTURES = {"A": CASES[1], "B": CASES[3], "C": CASES[4]}


@pytest.mark.parametrize("failure", [None, "wrong_unit", "failed_review", "unknown"])
def test_goal_batch_gates(monkeypatch, tmp_path, failure):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    goal.require_database(url, fixture=True)
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    calls = []
    candidates = {}
    manifest = stack.read(goal.MANIFEST)

    def mock(request):
        slot, stage = goal.SEQUENCE[len(calls)]
        body = json.loads(request.content)
        payload = json.loads(body["input"][1]["content"])
        if stage == "plan":
            assert stack.sha(request.content) == manifest["selection_http_sha256"][slot]
            assert payload["original_goal"] == PLAN_FIXTURES[slot][0]
            _, raw = fixture(*PLAN_FIXTURES[slot])
            if failure == "wrong_unit" and slot == "C":
                raw = {"selection": "operations", "evidence": [{
                    "kind": "normal", "source_key": "request_1", "source_excerpt": "栈操作",
                }]}
        else:
            assert payload["plan_source"] == "goal_selected"
            assert payload["materials_digest"] == manifest["materials_digest"]
            if stage == "rejections":
                admitted = stack.read(batch.vault / "B" / "normal.admitted.json")
                upstream = payload["upstream_context"][0]
                assert upstream["scene_version_id"] == admitted["scene_version_id"]
                assert upstream["digest"] == admitted["scene_digest"]
            raw = practice_fixture(payload)
        calls.append((slot, stage))
        if failure == "unknown" and slot == "C":
            raise httpx.ReadTimeout("test unknown result", request=request)
        return httpx.Response(
            200, stream=httpx.ByteStream(with_direct_echo(body, envelope(raw))),
        )

    with (
        TestClient(app, base_url="https://testserver") as a,
        TestClient(app, base_url="https://testserver") as b,
        TestClient(app, base_url="https://testserver") as c,
    ):
        clients = {"A": a, "B": b, "C": c}
        owners = {slot: client.post("/api/auth/guest").json()["user"]["id"]
                  for slot, client in clients.items()}
        batch = goal.Batch(tmp_path / "batch", url, transport=httpx.MockTransport(mock))
        approval = goal.approval_values(owners, fixture=True)
        with pytest.raises(SnapshotError, match="STACK_EXACT_AUTHORIZATION_REQUIRED"):
            batch.start(dict(approval, selection_budget=4))
        run = batch.start(approval)
        with pytest.raises(SnapshotError, match="STACK_SELECTOR_ORDER"):
            batch.perform("send", "A", "normal", key="fixture-secret")
        with pytest.raises(SnapshotError, match="STACK_STAGE_NOT_AUTHORIZED"):
            batch.perform("send", "C", "normal", key="fixture-secret")
        for slot, stage in goal.SEQUENCE:
            if failure == "unknown" and (slot, stage) == ("C", "plan"):
                with pytest.raises(httpx.ReadTimeout):
                    batch.perform("send", slot, stage, key="fixture-secret")
                assert (batch.vault / slot / "plan.attempt.json").exists()
                assert not (batch.vault / slot / "plan.admitted.json").exists()
                break
            if failure == "wrong_unit" and (slot, stage) == ("C", "plan"):
                with pytest.raises(SnapshotError, match="STACK_SELECTOR_WRONG_UNIT"):
                    batch.perform("send", slot, stage, key="fixture-secret")
                assert (batch.vault / slot / "plan.raw.enc").exists()
                break
            candidate = batch.perform("send", slot, stage, key="fixture-secret")
            inspected = batch.perform("inspect", slot, stage)
            assert inspected["candidate"]["candidate_digest"] == candidate
            if (slot, stage) == ("C", "plan"):
                with pytest.raises(SnapshotError, match="STACK_SELECTOR_ORDER"):
                    batch.perform("send", "A", "normal", key="fixture-secret")
            checks = dict.fromkeys(inspected["required_checks"], "pass")
            bindings = [candidate]
            if stage == "rejections":
                bindings.insert(0, candidates[(slot, "normal")])
            review = dict(candidates=bindings, verdict="pass", checks=checks,
                          reviewer="offline fixture only", notes="检查绑定")
            if failure == "failed_review" and (slot, stage) == ("C", "plan"):
                checks["scope_complete"] = "fail"
                with pytest.raises(SnapshotError, match="STACK_REVIEW_REQUIRED"):
                    batch.perform("review", slot, stage, review=review)
                break
            batch.perform("review", slot, stage, review=review)
            candidates[(slot, stage)] = candidate
        assert (batch.vault / "STOP").exists()
        with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
            batch.perform("send", "A", "normal", key="fixture-secret")
        if failure:
            assert calls == list(goal.SEQUENCE[:3])
            return
        assert calls == list(goal.SEQUENCE)
        for slot, client in clients.items():
            ids = run["courses"][slot]
            root = f"/api/free-courses/{ids['course_id']}"
            op = client.get(f"{root}/operations/{ids['operation_id']}").json()
            response = client.get(root)
            assert response.status_code == 200
            head = response.json()["head"]
            if slot == "C":
                assert head is None and op["state"] == "awaiting_clarification"
            else:
                assert op["state"] == "succeeded" and head["complete"]
                assert head["version"] == {"A": 2, "B": 3}[slot]
