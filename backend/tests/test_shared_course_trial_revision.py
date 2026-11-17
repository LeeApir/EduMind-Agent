"""Exercise exact parent/review records against the shared offline revision path."""

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from app.main import app
from app.services import course_trial_publication as publication
from app.services import course_trial_revision as revision
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.head_course_reuse import candidate as head_lesson
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_head_course_empty import empty_payload, empty_text, empty_wire_plan
from test_head_course_fixed import fixed_review, with_direct_echo
from test_stack_course_trial import teaching_fixture

from scripts import course_trial_generation as trial
from scripts import head_course_goal_fixture as fixture


def mock(request, output):
    reply = with_direct_echo(request, fixture.envelope(output))

    def respond(actual):
        assert actual.content == canonical(request)
        return httpx.Response(200, stream=httpx.ByteStream(reply))

    return httpx.MockTransport(respond)


def finding(path, quote):
    return dict(
        path=path,
        quote=quote,
        area="citation" if path[-1] == "fact_ids" else "teaching_expression",
        severity="minor", repairable=True, issue="离线定位夹具",
        teaching_responsibility="保留原段职责",
    )


def teaching_review(parent, profile, findings=None):
    raw = parent["raw_output"]
    if profile.model_planned:
        lesson = head_lesson(
            parent["context"]["head_payload"], raw, parent=parent.get("parent_digest")
        )
        review = fixed_review(lesson)
        review["checks"].update(
            empty_first_and_second_links=True, question_conditions_and_unique_answers=True
        )
    else:
        review = dict(checks=dict.fromkeys(profile.checks, True))
    return dict(
        review,
        candidate_digest=parent["candidate_digest"],
        parent_digest=parent.get("parent_digest"),
        independent_evaluator="offline-fixture",
        full_lesson_reviewed=True,
        verdict="needs_revision" if findings else "pass",
        findings=findings or [],
        blocking_findings=findings or [],
    )


def record_for(profile, parent, review):
    return dict(
        version=revision.VERSION, topic=profile.topic, batch=profile.batch,
        parent_digest=parent["candidate_digest"], review_sha256=revision.checksum(review),
        allowed_paths=[item["path"] for item in review["findings"]], max_http_requests=1,
        offline_fixture=True, approved=False, request_sha256=None,
    )


@pytest.mark.parametrize("topic", publication.REVISION_FIXTURES)
def test_topic_scope_does_not_come_from_review(topic):
    profile = publication.REVISION_FIXTURES[topic]
    ctx = dict(topic=topic, batch=profile.batch, evidence_kind="offline_fixture")
    if profile.model_planned:
        payload = empty_payload()
        ctx["head_payload"] = payload
        raw = empty_text(payload)
    else:
        # The narrow allowlist can be tested without constructing a stored draft.
        raw = dict(summary="总结", paragraphs=[dict(text="讲解", fact_ids=["order"])])
    parent = dict(context=ctx, raw_output=raw, candidate_digest="a" * 64)
    valid = [finding(["paragraphs", 0, "text"], raw["paragraphs"][0]["text"])]
    review = teaching_review(parent, profile, valid)
    assert set(revision.contract(profile, parent, review, record_for(profile, parent, review))[
        "schema"
    ]["properties"]) == {"paragraph_0_text"}
    for path in (
        ["questions", "link_target", "stem"], ["questions", "link_target", "explanation"],
        ["step_notes", 0, "note"], ["code"], ["trace"], ["answers"],
        ["paragraphs", 0], ["paragraphs", True, "text"], ["paragraphs", 0, "fact_ids", 0],
        ["failure_scope"] if topic != "head" else ["lifecycle"],
    ):
        review = teaching_review(parent, profile, [finding(path, "被禁止")])
        with pytest.raises(SnapshotError, match="REVISION_SCOPE"):
            revision.contract(profile, parent, review, record_for(profile, parent, review))
    for paths in (valid + valid, [dict(valid[0], severity="major")]):
        review = teaching_review(parent, profile, paths)
        with pytest.raises(SnapshotError, match="REVISION_SCOPE|REVISION_QUOTE_OR_DUPLICATE"):
            revision.contract(profile, parent, review, record_for(profile, parent, review))


@pytest.fixture
def isolated_app(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def prepare_parent(client, vault, profile):
    owner = UUID(client.post("/api/auth/guest").json()["user"]["id"])
    return asyncio.run(trial.prepare(
        vault, owner, trial.approval_values(profile, fixture=True), fixture=True, profile=profile
    ))


@pytest.mark.parametrize("topic", ["head", "stack"])
def test_record_driven_revision(topic, isolated_app, tmp_path):
    client = isolated_app
    profile = publication.REVISION_FIXTURES[topic]
    vault = tmp_path / "vault"
    opts = dict(fixture=True, profile=profile)
    ctx = prepare_parent(client, vault, profile)

    def send(request, output, stage="generate"):
        return trial.send(
            vault, profile=profile, stage=stage, transport=mock(request, output), key="fixture-key"
        )

    if topic == "head":
        plan = send(trial.planning_body(ctx["planning_inputs"]), empty_wire_plan(), "plan")
        payload = plan["payload"]
        trial.save(vault, "plan-review.json", dict(
            candidate_digest=plan["candidate_digest"], plan_digest=plan["plan_digest"],
            verdict="pass", independent_evaluator="offline-fixture", blocking_findings=[],
            planning_basis_binding=payload["planning_basis"]["binding"],
            checks=dict(empty_goal_and_sequence=True, same_example_and_caller_comparison=True),
        ))
        ctx = trial.read(vault / "plan.ready.json")
        raw = empty_text(payload)
        paths = [["paragraphs", 1, "fact_ids"], ["failure_scope"]]
        quotes = [raw["paragraphs"][1]["fact_ids"][0], raw["failure_scope"]]
        replacements = dict(
            paragraph_1_fact_ids=raw["paragraphs"][0]["fact_ids"],
            failure_scope="离线夹具：新失败范围表述。",
        )
    else:
        raw = teaching_fixture()
        paths = [["paragraphs", 0, "text"], ["summary"]]
        quotes = [raw["paragraphs"][0]["text"], raw["summary"]]
        replacements = dict(paragraph_0_text="离线夹具：新段落表述。", summary="离线夹具：新总结。")

    original_request = profile.request(ctx)
    parent = send(original_request, raw)
    review = teaching_review(parent, profile, [finding(p, q) for p, q in zip(paths, quotes)])
    trial.save(vault, "review.json", review)
    with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
        trial.publish(vault, **opts)
    originals = {p.name: p.read_bytes() for p in vault.iterdir() if p.name != "raw.key"}
    record = record_for(profile, parent, review)
    request = revision.request(profile, parent, review, record)
    closed = request["text"]["format"]["schema"]
    assert closed["additionalProperties"] is False
    assert set(closed["required"]) == set(closed["properties"]) == set(replacements)
    assert parent["candidate_digest"] == json.loads(request["input"][1]["content"])["parent_digest"]
    record.update(approved=True, request_sha256=revision.checksum(request))
    for delta, reason in (
        (dict(parent_digest="0" * 64), "REVISION_PARENT_BINDING"),
        (dict(review_sha256="0" * 64), "REVISION_REVIEW_BINDING"),
        (dict(allowed_paths=paths[:1]), "REVISION_SCOPE"),
        (dict(approved=False), "REVISION_AUTHORIZATION_REQUIRED"),
        (dict(max_http_requests=0), "REVISION_AUTHORIZATION_REQUIRED"),
        (dict(max_http_requests=2), "REVISION_BUDGET"),
        (dict(request_sha256="0" * 64), "REVISION_AUTHORIZATION_REQUIRED"),
    ):
        with pytest.raises(SnapshotError, match=reason):
            trial.prepare_revision(vault, dict(record, **delta), profile=profile)
        assert not (vault / "revision.prepared.json").exists()
    with pytest.raises(SnapshotError, match="REVISION_AUTHORIZATION_REQUIRED"):
        send(request, replacements, "revise")
    with pytest.raises(SnapshotError, match="OFFLINE_ONLY"):
        trial.send(vault, stage="revise", profile=profile)
    assert not (vault / "revise.attempt.json").exists()

    record_path = tmp_path / "approval.json"
    record_path.write_bytes(canonical(record))

    def cli(action, *args):
        return subprocess.run(
            [sys.executable, "-m", "scripts.course_trial", action, "--topic", topic,
             "--offline-vault", str(vault), *args],
            cwd=trial.ROOT, capture_output=True, text=True, check=True,
        ).stdout

    preview = json.loads(cli("inspect-revision", "--record", str(record_path)))
    assert preview == dict(request=request, request_sha256=record["request_sha256"])
    cli("prepare-revision", "--record", str(record_path))
    first_review = vault / "review.json"
    first_review.write_bytes(canonical(dict(review, independent_evaluator="wrong-review")))
    with pytest.raises(SnapshotError, match="REVISION_REVIEW_BINDING"):
        send(request, replacements, "revise")
    assert not (vault / "revise.attempt.json").exists()
    first_review.write_bytes(originals["review.json"])
    source = trial.revision_source(vault, profile)
    outside = with_direct_echo(request, fixture.envelope(dict(replacements, questions={})))
    receipt = dict(
        http_status=200, encoding="identity", raw_sha256=trial.sha(outside),
        raw_bytes=len(outside), complete=True,
    )
    with pytest.raises(ValueError, match="ROLE_SCHEMA"):
        trial.observe(ctx, outside, receipt, profile=profile, stage="revise", source=source)
    reply = tmp_path / "mock-response.json"
    reply.write_bytes(with_direct_echo(request, fixture.envelope(replacements)))
    child_digest = cli("send", "--stage", "revise", "--mock-response", str(reply)).strip()
    child = trial.read(vault / "revise.candidate.json")
    assert child_digest == child["candidate_digest"]
    assert (vault / "revise.request.json").read_bytes() == canonical(request)
    assert cli("replay", "--stage", "revise").strip() == child["candidate_digest"]
    assert child["parent_digest"] == parent["candidate_digest"]
    assert child["plan_digest"] == parent["plan_digest"]
    assert child["materials_digest"] == parent["materials_digest"]
    expected = deepcopy(raw)
    for path, value in zip(paths, replacements.values(), strict=True):
        if len(path) == 1:
            expected[path[0]] = value
        else:
            expected[path[0]][path[1]][path[2]] = value
    assert child["raw_output"] == expected
    assert trial.replay(vault, **opts) == parent
    assert originals == {name: (vault / name).read_bytes() for name in originals}
    with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
        send(request, replacements, "revise")
    with pytest.raises(SnapshotError, match="REVISION_REVIEW_REQUIRED"):
        trial.publish(vault, **opts)

    route = f"/api/free-courses/{ctx['course_id']}/versions/2/scenes/{ctx['scene_id']}"
    final = teaching_review(child, profile)
    for invalid in (review, dict(final, full_lesson_reviewed=False)):
        (vault / "revision-review.json").write_bytes(canonical(invalid))
        with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
            trial.publish(vault, stage="revise", **opts)
        assert client.get(route).status_code == 404
    (vault / "revision-review.json").write_bytes(canonical(final))
    published = json.loads(cli("publish", "--stage", "revise"))
    response = client.get(route)
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["scene_version_id"] == published["scene_version_id"]
    metadata = view["generation_source"]
    assert metadata["revision_version"] == revision.VERSION
    assert metadata["evidence_kind"] == "offline_fixture"
    assert metadata["parent_digest"] == parent["candidate_digest"]
    assert metadata["candidate_digest"] == child["candidate_digest"]
    assert '"answer_key"' not in response.text and '"solution"' not in response.text
    spec = json.loads((trial.ROOT / "backend/app/contracts/free_course.openapi.json").read_text())
    Draft202012Validator(dict(
        components=spec["components"], **{"$ref": "#/components/schemas/SceneProjection"}
    )).validate(view)
    if directory := os.environ.get("EDUMIND_T126_PLAYER_PROJECTIONS"):
        (Path(directory) / f"{topic}.json").write_bytes(canonical(view))


def test_schema_rejected_parent_remains_rejected(isolated_app, tmp_path):
    profile = publication.REVISION_FIXTURES["stack"]
    vault = tmp_path / "vault"
    ctx = prepare_parent(isolated_app, vault, profile)
    request = profile.request(ctx)
    output = teaching_fixture()
    del next(iter(output["questions"].values()))["explanation"]
    with pytest.raises(ValueError, match="ROLE_SCHEMA"):
        trial.send(vault, profile=profile, transport=mock(request, output), key="fixture-key")
    with pytest.raises(SnapshotError, match="SAVED_BINDING"):
        trial.prepare_revision(vault, {}, profile=profile)
    assert trial.read(vault / "generate.failure.json")["code"] == "ROLE_SCHEMA"
    assert (vault / "generate.raw.enc").is_file()
    assert not (vault / "generate.candidate.json").exists()
    assert not (vault / "revise.attempt.json").exists()
