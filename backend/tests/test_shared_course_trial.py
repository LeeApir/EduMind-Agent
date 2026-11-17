"""Offline exchanges against the four-topic foreground entry and private PG read path."""

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from app.main import app
from app.services.course_trial_publication import NEW_BATCHES
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.head_course_materials import body as legacy_head_body
from app.services.head_course_reuse import candidate as head_lesson
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_binary_search_course_trial import teaching as binary_text
from test_head_course_empty import empty_text, empty_wire_plan
from test_head_course_fixed import fixed_review, with_direct_echo
from test_queue_course_trial import teaching as queue_text
from test_stack_course_trial import teaching_fixture as stack_text

from scripts import course_trial_generation as trial
from scripts import head_course_goal_fixture as fixture


@pytest.mark.parametrize("topic", NEW_BATCHES)
@pytest.mark.parametrize("halt", [False, True], ids=["publish", "halt"])
def test_shared_first_draft(topic, halt, monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    profile = NEW_BATCHES[topic]
    wrong = NEW_BATCHES["queue" if topic == "stack" else "stack"]
    options = dict(profile=profile, fixture=True)
    vault = tmp_path / "sealed"
    calls = []

    def transport(request, output):
        original = with_direct_echo(request, fixture.envelope(output))

        def handle(actual):
            assert actual.method == "POST" and actual.url.path == "/responses"
            assert actual.content == canonical(request)
            calls.append(actual.content)
            return httpx.Response(200, stream=httpx.ByteStream(original))

        return httpx.MockTransport(handle)

    with TestClient(app, base_url="https://testserver") as client:
        owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
        approval = trial.approval_values(profile, fixture=True)
        assert approval["explicit_user_authorization"] is False
        historical = json.loads(
            (trial.ROOT / "docs/ADR/0059-t119-approval-20261110.json").read_text()
        )
        old_approval = {
            key: historical[key]
            for key in (
                "manifest_sha256", "batch", "explicit_user_authorization",
                "accept_T119_scope_and_batch_C2", "max_http_requests", "window_seconds",
            )
        }
        for invalid in (old_approval, trial.approval_values(wrong, fixture=True)):
            with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
                asyncio.run(trial.prepare(vault, owner, invalid, **options))
            assert not vault.exists()
        ctx = asyncio.run(trial.prepare(vault, owner, approval, **options))
        route = f"/api/free-courses/{ctx['course_id']}"
        operation = f"{route}/operations/{ctx['operation_id']}"
        assert client.get(operation).json()["budget"] is None
        assert ctx["plan_source"] == ("model_planned" if topic == "head" else "fixed_outline")
        with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
            trial.replay(vault, profile=wrong, fixture=True)
        with pytest.raises(SnapshotError, match="VAULT_REQUIRED"):
            trial.replay(vault, profile=profile, fixture=False)

        if topic == "head":
            assert "plan_id" not in ctx
            plan = empty_wire_plan()
            mock = transport(trial.planning_body(ctx["planning_inputs"]), plan)
            with pytest.raises(SnapshotError, match="PLAN_REQUIRED"):
                trial.send(vault, profile=profile, transport=mock, key="offline-fixture-key")
            planned = trial.send(
                vault, profile=profile, stage="plan", transport=mock, key="offline-fixture-key"
            )
            assert trial.replay(vault, stage="plan", **options) == planned
            with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
                trial.send(
                    vault, profile=profile, stage="plan", transport=mock, key="offline-fixture-key"
                )
            payload = planned["payload"]
            assert payload["plan"]["title"] == plan["plans"][0]["title"]
            ctx = trial.read(vault / "plan.ready.json")
            review = dict(
                candidate_digest=planned["candidate_digest"],
                plan_digest=planned["plan_digest"],
                verdict="pass",
                independent_evaluator="offline-fixture",
                planning_basis_binding=payload["planning_basis"]["binding"],
                blocking_findings=[],
                checks=dict(empty_goal_and_sequence=True, same_example_and_caller_comparison=True),
            )
            review_file = vault / "plan-review.json"
            with pytest.raises(SnapshotError, match="PLAN_REVIEW_REQUIRED"):
                trial.send(vault, profile=profile, transport=mock, key="offline-fixture-key")
            review_file.write_bytes(canonical(dict(review, candidate_digest="0" * 64)))
            with pytest.raises(SnapshotError, match="PLAN_REVIEW_REQUIRED"):
                trial.send(vault, profile=profile, transport=mock, key="offline-fixture-key")
            assert len(calls) == 1
            review_file.write_bytes(canonical(review))
            original_request, output = legacy_head_body(payload), empty_text(payload)
        else:
            original_request = profile.materials.request()
            text = {"stack": stack_text, "queue": queue_text, "binary-search": binary_text}[topic]
            output = text()

        request = profile.request(ctx)
        assert request["text"] == original_request["text"]
        assert request["input"][1] == original_request["input"][1]
        prompt = request["input"][0]["content"]
        assert "[QUESTION STEM FORMAT course-question-stem-v2]" in prompt
        assert "'#include', '```', '~~~', '{', '}', ';'" in prompt
        send_options = dict(
            transport=transport(request, output), profile=profile, key="offline-fixture-key"
        )
        candidate = trial.send(vault, **send_options)
        assert calls[-1] == (vault / "generate.request.json").read_bytes() == canonical(request)
        assert trial.replay(vault, **options) == candidate
        with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
            trial.send(vault, **send_options)
        assert len(calls) == (2 if topic == "head" else 1)

        if topic == "head":
            review = fixed_review(head_lesson(ctx["head_payload"], output))
            review["checks"].update(
                empty_first_and_second_links=True, question_conditions_and_unique_answers=True
            )
        else:
            review = dict(
                verdict="pass", blocking_findings=[], checks=dict.fromkeys(profile.checks, True)
            )
        review.update(candidate_digest=candidate["candidate_digest"],
                      independent_evaluator="offline-fixture")
        review_file = vault / "review.json"
        with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
            trial.publish(vault, **options)
        review_file.write_bytes(canonical(dict(review, candidate_digest="0" * 64)))
        with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
            trial.publish(vault, **options)
        assert client.get(route).json()["head"]["version"] == 1
        review_file.write_bytes(canonical(review))
        scene_route = f"{route}/versions/2/scenes/{ctx['scene_id']}"
        if halt:
            stopped = asyncio.run(trial.stop(vault, **options))
            assert stopped["state"] == "cancel_requested"
            assert trial.replay(vault, **options) == candidate
            with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
                trial.publish(vault, **options)
            assert client.get(scene_route).status_code == 404
            return

        published = trial.publish(vault, **options)
        response = client.get(scene_route)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["scene_version_id"] == published["scene_version_id"]
        source = view["generation_source"]
        assert "replay_source" not in view
        assert source["evidence_kind"] == "offline_fixture"
        assert source["plan_source"] == ctx["plan_source"]
        assert source["stem_prompt_version"] == "course-question-stem-v2"
        assert source["candidate_digest"] == candidate["candidate_digest"]
        assert source["materials_digest"] == candidate["materials_digest"]
        assert source["plan_digest"] == candidate["plan_digest"]
        assert '"answer_key"' not in response.text and '"solution"' not in response.text
        contract = trial.ROOT / "backend/app/contracts/free_course.openapi.json"
        spec = json.loads(contract.read_text())
        Draft202012Validator(dict(
            components=spec["components"], **{"$ref": "#/components/schemas/SceneProjection"}
        )).validate(view)
        if destination := os.environ.get("EDUMIND_T125_PLAYER_PROJECTIONS"):
            (Path(destination) / f"{topic}.json").write_bytes(canonical(view))
