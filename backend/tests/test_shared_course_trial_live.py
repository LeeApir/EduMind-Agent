"""Test the T127 gates and real-path wiring without any Provider request."""

import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_head_course_empty import empty_text, empty_wire_plan
from test_head_course_fixed import with_direct_echo
from test_shared_course_trial_revision import finding, record_for, teaching_review
from test_stack_course_trial import teaching_fixture

from app.main import app
from app.services import course_trial_publication as publication
from app.services import course_trial_revision as revision
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts import course_trial_live as live
from scripts import head_course_goal_fixture as fixture
from scripts.prepare_head_course_empty import inputs


def test_frozen_requests():
    profiles = publication.LIVE_REUSE
    manifest = {trial.package_digest(profile) for profile in profiles.values()}
    assert len(manifest) == 1
    package = trial.package_path(profiles["head"])
    approved = trial.read(package / "approval.template.json")
    assert approved == live.approval_values(
        "<APPROVED_MANIFEST_SHA256>", "<APPROVED_OWNER_UUID>", approved=False
    )
    planning_inputs = inputs()
    payload = profiles["head"].materials.content_payload(
        planning_inputs, empty_wire_plan()["plans"][0],
    )
    payload["plan"] = "<APPROVED_PLAN_FROM_THIS_T127_OPERATION>"
    requests = {
        "head-plan.template": trial.planning_body(planning_inputs),
        "head-generate.template": profiles["head"].request({"head_payload": payload}),
        **{f"{topic}-generate": profiles[topic].request() for topic in profiles if topic != "head"},
    }
    for name, request in requests.items():
        assert (package / "requests" / f"{name}.json").read_bytes() == canonical(request)
        assert request["model"] == "deepseek-flash"
        if name != "head-plan.template":
            assert "course-question-stem-v2" in request["input"][0]["content"]


def test_exact_approval_window_and_fixture_isolation(tmp_path, monkeypatch):
    head = publication.LIVE_REUSE["head"]
    fixture_profile = publication.REVISION_FIXTURES["head"]
    monkeypatch.setattr(live, "root", lambda: tmp_path / "live")
    url = f"postgresql+asyncpg://127.0.0.1:15437/{head.database}"
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    manifest = trial.package_digest(head)
    approval = live.approval_values(manifest, uuid4(), approved=True)
    for change in (
        dict(manifest_sha256="0" * 64), dict(max_http_requests=10),
        dict(max_revisions_per_topic=2), dict(offline_fixture=True),
        dict(accept_T127_scope_and_batch_C2=False), dict(explicit_user_authorization=False),
        dict(stage_budgets={"plan": 1, "generate": 5, "revise": 3}),
    ):
        with pytest.raises(SnapshotError, match="LIVE_EXACT_AUTHORIZATION_REQUIRED"):
            live.start(dict(approval, **change), manifest)
        assert not live.root().exists()
    with pytest.raises(SnapshotError, match="DEVELOPMENT_DATABASE_REQUIRED"):
        publication.require_database(url + "_test", profile=head)
    with pytest.raises(SnapshotError, match="OFFLINE_ONLY"):
        trial.check_stage("revise", fixture_profile, False)
    with pytest.raises(SnapshotError, match="OFFLINE_ONLY"):
        trial.check_stage("revise", publication.NEW_BATCHES["head"], False)
    with pytest.raises(SnapshotError, match="LIVE_FIXTURE_FORBIDDEN"):
        trial.check_stage("revise", head, True)

    run = live.start(approval, manifest)
    assert live.load(manifest, active=True, profile=head) == run
    with pytest.raises(FileExistsError):
        live.start(approval, manifest)
    assert live.load(manifest, active=False) == run
    old = datetime.now(UTC) - timedelta(seconds=publication.LIVE_WINDOW_SECONDS + 1)
    (live.root() / "batch.json").write_bytes(canonical(dict(
        run, starts_at=old.isoformat(), expires_at=(old + timedelta(
            seconds=publication.LIVE_WINDOW_SECONDS,
        )).isoformat(),
    )))
    with pytest.raises(SnapshotError, match="LIVE_WINDOW_CLOSED"):
        live.load(manifest, active=True, profile=head)
    assert asyncio.run(trial.stop(trial.vault_path(head), profile=head)) == {
        "batch": publication.LIVE_BATCH, "halted": True,
    }
    with pytest.raises(SnapshotError, match="LIVE_BATCH_STOPPED"):
        live.load(manifest, active=True, profile=head)


def test_live_parent_and_private_admission(tmp_path, monkeypatch):
    # Exercise the actual-mode gates, but redirect to the dedicated _test database
    # and force MockTransport at the last I/O boundary. No mock is accepted by the live CLI.
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    db_name = url.rsplit("/", 1)[-1]
    assert db_name == "edumind_catalog_p15_t127_reuse_test"
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(live, "root", lambda: tmp_path / "live")
    for topic, profile in publication.LIVE_REUSE.items():
        isolated = replace(profile, database=db_name)
        monkeypatch.setitem(publication.LIVE_REUSE, topic, isolated)
        monkeypatch.setitem(publication.FOREGROUND_BATCHES, isolated.batch, isolated)
    head, stack, queue, binary = publication.LIVE_REUSE.values()
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    real_resolve, real_send = trial.transport_io.resolve_target, trial.transport_io.send_and_seal
    calls, expected = [], {}

    def handler(actual):
        assert actual.method == "POST" and actual.url.path == "/responses"
        assert actual.content == canonical(expected["request"])
        calls.append(actual.content)
        raw = with_direct_echo(expected["request"], fixture.envelope(expected["output"]))
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    mock = httpx.MockTransport(handler)

    def resolve(transport):
        assert transport is None
        return real_resolve(mock)

    def send_and_seal(*args, transport, **kwargs):
        assert transport is None
        return real_send(*args, transport=mock, **kwargs)

    monkeypatch.setattr(trial.transport_io, "resolve_target", resolve)
    monkeypatch.setattr(trial.transport_io, "send_and_seal", send_and_seal)
    monkeypatch.setattr(trial.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(trial.getpass, "getpass", lambda _: "isolated-not-a-real-key")

    def prepare(profile):
        return asyncio.run(trial.prepare(trial.vault_path(profile), None, None, profile=profile))

    def send(profile, stage, request, output):
        expected.update(request=request, output=output)
        return trial.send(trial.vault_path(profile), profile=profile, stage=stage)

    with TestClient(app, base_url="https://testserver") as client:
        owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
        with pytest.raises(SnapshotError, match="LIVE_AUTHORIZATION_REQUIRED"):
            prepare(head)
        manifest = trial.package_digest(head)
        run = live.start(live.approval_values(manifest, owner, approved=True), manifest)
        with pytest.raises(SnapshotError, match="LIVE_PRIOR_TOPIC_REQUIRED"):
            prepare(stack)
        vault = trial.vault_path(head)
        vault.mkdir()
        trial.save(vault, "published.json", dict(topic="head", run_sha256="0" * 64))
        with pytest.raises(SnapshotError, match="LIVE_PRIOR_TOPIC_REQUIRED"):
            prepare(stack)
        (vault / "published.json").unlink()
        vault.rmdir()
        ctx = prepare(head)
        assert ctx["live_run"]["run_sha256"] == trial.sha(canonical(run))
        plan_request = trial.planning_body(ctx["planning_inputs"])
        request_dir = trial.package_path(head) / "requests"
        plan_template = (request_dir / "head-plan.template.json").read_bytes()
        for key in ("course_id", "operation_id", "request_id"):
            plan_template = plan_template.replace(
                f"<ACTUAL_{key.upper()}_UUID>".encode(), ctx[key].encode(),
            )
        assert plan_template == canonical(plan_request)
        with pytest.raises(SnapshotError, match="PLAN_REQUIRED"):
            trial.send(vault, profile=head)
        planned = send(head, "plan", plan_request, empty_wire_plan())
        payload = planned["payload"]
        trial.save(vault, "plan-review.json", dict(
            candidate_digest=planned["candidate_digest"], plan_digest=planned["plan_digest"],
            verdict="pass", independent_evaluator="offline-fixture", blocking_findings=[],
            planning_basis_binding=payload["planning_basis"]["binding"],
            checks=dict(empty_goal_and_sequence=True, same_example_and_caller_comparison=True),
        ))
        ctx = trial.read(vault / "plan.ready.json")
        draft_request = head.request(ctx)
        draft_template = trial.read(request_dir / "head-generate.template.json")
        material = json.loads(draft_template["input"][1]["content"])
        material["plan"] = payload["plan"]
        material["source_binding"] = {key: ctx[key] for key in material["source_binding"]}
        draft_template["input"][1]["content"] = canonical(material).decode()
        assert draft_request == draft_template
        parent = send(head, "generate", draft_request, empty_text(payload))
        review = teaching_review(parent, head, [
            finding(["failure_scope"], parent["raw_output"]["failure_scope"])
        ])
        trial.save(vault, "review.json", review)
        first_response = (vault / "generate.raw.enc").read_bytes()
        with pytest.raises(SnapshotError, match="REVISION_AUTHORIZATION_REQUIRED"):
            trial.send(vault, profile=head, stage="revise")
        assert len(calls) == 2
        record = dict(
            record_for(head, parent, review), offline_fixture=False,
            run_sha256=ctx["live_run"]["run_sha256"],
        )
        request = revision.request(head, parent, review, record)
        record.update(approved=True, request_sha256=revision.checksum(request))
        for change, code in (
            (dict(run_sha256="0" * 64), "REVISION_PARENT_BINDING"),
            (dict(offline_fixture=True), "REVISION_PARENT_BINDING"),
            (dict(parent_digest="0" * 64), "REVISION_PARENT_BINDING"),
            (dict(review_sha256="0" * 64), "REVISION_REVIEW_BINDING"),
            (dict(allowed_paths=[["questions"]]), "REVISION_SCOPE"),
        ):
            with pytest.raises(SnapshotError, match=code):
                trial.prepare_revision(vault, dict(record, **change), profile=head)
        assert trial.prepare_revision(vault, record, profile=head) == request
        replacement = {"failure_scope": "仅用于测试的修订文字。"}
        child = send(head, "revise", request, replacement)
        assert child["raw_output"] == dict(parent["raw_output"], **replacement)
        assert trial.replay(vault, profile=head, stage="revise") == child
        assert (vault / "generate.raw.enc").read_bytes() == first_response
        assert trial.read(vault / "review.json") == review
        with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
            trial.send(vault, profile=head, stage="revise")
        with pytest.raises(SnapshotError, match="REVISION_REVIEW_REQUIRED"):
            trial.publish(vault, profile=head)
        review_path = vault / "revision-review.json"
        final_review = teaching_review(child, head)
        trial.save(vault, review_path.name, dict(
            final_review, candidate_digest=parent["candidate_digest"],
        ))
        with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
            trial.publish(vault, profile=head, stage="revise")
        review_path.write_bytes(canonical(final_review))
        admitted = trial.publish(vault, profile=head, stage="revise")
        route = f"/api/free-courses/{admitted['course_id']}/versions/2"
        route += f"/scenes/{admitted['scene_id']}"
        view = client.get(route)
        assert view.status_code == 200, view.text
        source = view.json()["generation_source"]
        assert source["parent_digest"] == parent["candidate_digest"]
        assert source["candidate_digest"] == child["candidate_digest"]
        assert source["plan_source"] == "model_planned"
        assert source["evidence_kind"] == "actual_provider_response"
        api = trial.read(trial.ROOT / "backend/app/contracts/free_course.openapi.json")
        validator = Draft202012Validator(dict(
            components=api["components"],
            **{"$ref": "#/components/schemas/SharedTrialGenerationSource"},
        ))
        assert validator.is_valid(source)
        assert not validator.is_valid(dict(source, evidence_kind="offline_fixture"))
        assert not validator.is_valid(dict(source, batch=stack.batch))
        assert not validator.is_valid(dict(source, batch="head-revision-fixture-r01"))
        assert validator.is_valid(dict(
            source, batch="head-revision-fixture-r01", evidence_kind="offline_fixture",
        ))
        assert '"answer_key"' not in view.text and '"solution"' not in view.text

        prepare(stack)
        stack_vault = trial.vault_path(stack)
        stack_first = send(stack, "generate", stack.request(), teaching_fixture())
        trial.save(stack_vault, "review.json", teaching_review(stack_first, stack))
        stack_published = trial.publish(stack_vault, profile=stack)
        assert stack_published["candidate_digest"] == stack_first["candidate_digest"]
        prepare(queue)
        with pytest.raises(ValueError, match="ROLE_SCHEMA"):
            send(queue, "generate", queue.request(), {})
        queue_vault = trial.vault_path(queue)
        assert trial.read(queue_vault / "generate.failure.json")["attempted"]
        assert json.loads((queue_vault / "generate.body.json").read_bytes())["complete"]
        assert (queue_vault / "generate.raw.enc").exists()
        assert (live.root() / "HALT").exists()
        with pytest.raises(SnapshotError, match="LIVE_BATCH_STOPPED"):
            prepare(binary)
        with pytest.raises(SnapshotError, match="LIVE_BATCH_STOPPED"):
            trial.publish(stack_vault, profile=stack)
        assert len(calls) == 5
