"""Exact foreground path using MockTransport and the existing private course API."""

import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo

from app.main import app
from app.services import stack_multiscene as stack
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical
from scripts import stack_multiscene_trial as trial
from scripts.head_course_goal_fixture import envelope


def output(stage, payload):
    if stage == "plan":
        normal, full, empty = [
            clause for goals in payload["supported_material"]["scene_goal_excerpts"].values()
            for clause in goals
        ]
        return dict(
            protocol_version=stack.PLAN_WIRE, needs_clarification=False, questions=[],
            source_keys=[], reason="", plans=[dict(
                title="固定容量栈", shared_example=trial.basis.VERSION,
                objectives=[
                    dict(id=f"g{i}", description=clause, source="user_requirement",
                         source_key="request_1", source_excerpt=clause)
                    for i, clause in enumerate((normal, full, empty))
                ],
                terminology=[], conventions=["固定容量 3"],
                scenes=[
                    dict(scene_key=key, title=title, purpose=title, forms=list(trial.basis.FORMS),
                         objective_ids=ids, depends_on=deps)
                    for key, title, ids, deps in (
                        ("normal", "成功操作", ["g0"], []),
                        ("rejections", "两种拒绝", ["g1", "g2"], ["normal"]),
                    )
                ],
            )],
        )
    material = payload["scene_material"]
    return dict(
        paragraphs=[
            dict(text=material[field], fact_ids=["order"])
            for field in ("demonstrated", "text_only")
        ],
        explanations={q["key"]: "仅用于接线检查的解析夹具。" for q in material["questions"]},
    )


def approval(stage, candidates):
    return dict(
        verdict="pass", reviewer="offline fixture only", candidates=candidates,
        checks=dict.fromkeys(trial.CHECKS[stage], "pass"), notes="仅验证接线。",
    )


def test_stack_trial_private_course(monkeypatch, tmp_path):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    calls = []

    def mock(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"][1]["content"])
        stage = trial.STAGES[len(calls)]
        assert body["text"]["format"]["name"].endswith(stage)
        if stage == "rejections":
            assert payload["upstream"][0]["scene_version_id"] == normal["scene_version_id"]
            assert payload["upstream"][0]["digest"] == normal["scene_digest"]
            assert payload["upstream"][0]["content"]["generation_source"]["candidate_digest"] == d2
        calls.append((body, payload))
        raw = with_direct_echo(body, envelope(output(stage, payload)))
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    with TestClient(app, base_url="https://testserver") as client:
        guest = client.post("/api/auth/guest").json()
        owner = UUID(guest["user"]["id"])
        run = trial.Trial(tmp_path / "batch", url, transport=httpx.MockTransport(mock))
        correct = trial.approval_values(owner, trial.manifest_sha(), fixture=True)
        with pytest.raises(SnapshotError, match="STACK_EXACT_AUTHORIZATION_REQUIRED"):
            run.start(dict(correct, manifest_sha256="old"))
        assert not run.vault.exists()
        started = run.start(correct)
        d1 = run.send("plan", key="fixture-secret")
        with pytest.raises(SnapshotError, match="STACK_STAGE_ALREADY_SENT"):
            run.send("plan", key="fixture-secret")
        assert run.inspect("plan")["candidate"]["candidate_digest"] == d1
        run.review("plan", approval("plan", [d1]))
        d2 = run.send("normal", key="fixture-secret")
        normal = run.review("normal", approval("normal", [d2]))
        d3 = run.send("rejections", key="fixture-secret")
        assert run.inspect("rejections")["upstream"][0]["digest"] == normal["scene_digest"]
        full = run.review("rejections", approval("rejections", [d2, d3]))
        assert full["version"] == 3
        assert len(calls) == 3
        assert all("lease_epoch" not in payload for _, payload in calls[1:])
        with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
            run.send("rejections", key="fixture-secret")
        with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
            run.review("rejections", approval("rejections", [d2, d3]))

        root = f"/api/free-courses/{started['course_id']}"
        status = client.get(f"{root}/operations/{started['operation_id']}").json()
        assert status["state"] == "succeeded"
        assert status["execution_mode"] == "finite_stack_foreground" and status["budget"] is None
        for stage, saved, frames, answers, wrong in (
            ("normal", normal, 5, ["2", "-4"], ["9", "6"]),
            ("rejections", full, 9, ["3", "0", "1", "A"], ["2", "1", "-99", "B"]),
        ):
            path = f"{root}/versions/3/scenes/{saved['scene_id']}"
            response = client.get(path)
            assert response.status_code == 200, response.text
            scene = response.json()
            assert scene["scene_version_id"] == saved["scene_version_id"]
            source = scene["generation_source"]
            assert source["evidence_kind"] == "offline_fixture"
            assert source["source_request_sha256"] == trial.sha(
                (run.vault / f"{stage}.request.json").read_bytes()
            )
            assert source["source_response_sha256"] == trial.read(
                run.vault / f"{stage}.body.json"
            )["raw_sha256"]
            assert "answer_key" not in response.text and '"solution"' not in response.text
            assert any(b["anchor_id"] == "practice-code" for b in scene["blocks"])
            visual = next(b for b in scene["blocks"] if b["kind"] == "visualization")
            assert len(visual["steps"]) == len(scene["actions"]) == frames
            if stage == "rejections":
                assert visual["steps"][4]["stack_frame"]["line"] == 9
                empty = visual["steps"][8]
                assert empty["stack_frame"]["line"] == 16 and empty["stack_frame"]["popped"] is None
                assert "value=3" in empty["caption"] and "返回 false" in empty["caption"]
            exercise = next(b for b in scene["blocks"] if b["kind"] == "exercise")
            assert len(exercise["items"]) == len(answers)
            body = dict(
                course_version=3, scene_id=saved["scene_id"],
                scene_version_id=saved["scene_version_id"],
                exercise_id=exercise["exercise_id"],
                exercise_version_id=exercise["exercise_version_id"],
            )
            for values, score in ((wrong, 0), (answers, 1)):
                body["answers"] = [
                    dict(question_id=q["question_id"], answer=value)
                    for q, value in zip(exercise["items"], values, strict=True)
                ]
                response = client.post(f"{root}/attempts", json=body, headers={
                    "X-CSRF-Token": guest["csrf_token"], "Idempotency-Key": str(uuid4()),
                })
                assert response.status_code == 201, response.text
                attempt = client.get(f"{root}/attempts/{response.json()['attempt_id']}").json()
                assert attempt["comparison_score"] == score
                assert attempt["mastery_effect"] == "course_only"
            assert client.get(path).json() == scene
            if directory := os.getenv("EDUMIND_T139_PLAYER_PROJECTIONS"):
                (Path(directory) / f"{stage}.json").write_text(
                    json.dumps(scene, ensure_ascii=False)
                )
        with TestClient(app, base_url="https://testserver") as other:
            other.post("/api/auth/guest")
            assert other.get(f"{root}/versions/3/scenes/{full['scene_id']}").status_code == 404


@pytest.mark.parametrize(
    "failure", ["review", "unknown", "deadline", "early", "request", "upstream"],
)
def test_stack_trial_stops_and_preserves_evidence(monkeypatch, tmp_path, failure):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    calls = []

    def mock(request):
        calls.append(request.content)
        if failure == "unknown":
            raise httpx.ReadTimeout("unknown result")
        body = json.loads(request.content)
        stage = trial.STAGES[len(calls) - 1]
        value = output(stage, json.loads(body["input"][1]["content"]))
        return httpx.Response(200, stream=httpx.ByteStream(with_direct_echo(body, envelope(value))))

    with TestClient(app, base_url="https://testserver") as client:
        owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
    run = trial.Trial(tmp_path / "batch", url, transport=httpx.MockTransport(mock))
    run.start(trial.approval_values(owner, trial.manifest_sha(), fixture=True))
    if failure == "review":
        run.send("plan", key="fixture-secret")
        with pytest.raises(SnapshotError, match="STACK_REVIEW_REQUIRED"):
            run.review("plan", approval("plan", ["wrong-digest"]))
        assert (run.vault / "plan.raw.enc").exists()
        assert (run.vault / "plan.review.json").exists()
    elif failure == "request":
        candidate = run.send("plan", key="fixture-secret")
        with (run.vault / "plan.request.json").open("ab") as path:
            path.write(b" ")
        with pytest.raises(SnapshotError, match="STACK_WIRE_BINDING"):
            run.review("plan", approval("plan", [candidate]))
    elif failure == "upstream":
        plan_digest = run.send("plan", key="fixture-secret")
        run.review("plan", approval("plan", [plan_digest]))
        normal_digest = run.send("normal", key="fixture-secret")
        normal = run.review("normal", approval("normal", [normal_digest]))
        (run.vault / "normal.admitted.json").write_bytes(
            canonical(dict(normal, scene_digest="different-upstream"))
        )
        with pytest.raises(SnapshotError, match="STACK_UPSTREAM_BINDING"):
            run.send("rejections", key="fixture-secret")
    elif failure == "unknown":
        with pytest.raises(httpx.ReadTimeout):
            run.send("plan", key="fixture-secret")
        assert (run.vault / "plan.attempt.json").exists()
        assert not (run.vault / "plan.candidate.json").exists()
    elif failure == "deadline":
        original_now = SnapshotRepository._now

        async def expired(repo):
            return await original_now(repo) + timedelta(seconds=trial.WINDOW)

        monkeypatch.setattr(SnapshotRepository, "_now", expired)
        with pytest.raises(SnapshotError, match="STACK_WINDOW_OR_OPERATION"):
            run.send("plan", key="fixture-secret")
    else:
        with pytest.raises(SnapshotError, match="STACK_STAGE_ORDER"):
            run.send("normal", key="fixture-secret")
    assert (run.vault / "STOP").exists()
    with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
        run.send("plan", key="fixture-secret")
    assert len(calls) == {
        "review": 1, "unknown": 1, "deadline": 0, "early": 0, "request": 1, "upstream": 2,
    }[failure]
    attempt = run.vault / "plan.attempt.json"
    if calls:
        assert trial.read(attempt)["request_sha256"] == trial.sha(calls[0])
    else:
        assert not attempt.exists()
