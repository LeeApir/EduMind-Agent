import json
import os
from copy import deepcopy
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from test_head_course_fixed import with_direct_echo
from test_stack_goal_selection import fixture
from test_stack_multiscene import practice_fixture

from app.main import app
from app.models.free_course_planning import FreeCoursePlanningResult
from app.services import stack_goal_evidence as evidence
from app.services import stack_goal_selection as previous
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from scripts import stack_goal_continuation as continuation
from scripts import stack_goal_selection_trial as original
from scripts import stack_multiscene_trial as stack
from scripts.head_course_goal_fixture import envelope

HASHES = dict(request_sha256="a" * 64, response_sha256="b" * 64)


def quote(kind, excerpt, key="request_1"):
    return dict(kind=kind, source_key=key, source_excerpt=excerpt)


def case():
    inputs, raw = fixture("理解栈操作和动态扩容", "out_of_scope", ("动态扩容",))
    raw["evidence"].insert(0, quote("normal", "理解栈操作"))
    return inputs, raw


def review_of(record, *, semantics="pass"):
    return dict(
        replay_digest=record["replay_digest"], verdict=semantics, reviewer="fixture reviewer",
        notes="checked full source context",
        checks={**dict.fromkeys(evidence.CHECKS, "pass"), "selection_semantics": semantics},
    )


def test_scope_allows_accurate_supported_evidence_but_never_allocates_body():
    inputs, raw = case()
    original = deepcopy(raw)
    with pytest.raises(SnapshotError, match="STACK_SELECTION_EVIDENCE"):
        previous.normalize(raw, inputs)
    record = evidence.inspect_scope(raw, inputs, **HASHES)
    assert "outcome" not in record
    result = evidence.reviewed_scope(raw, inputs, review=review_of(record), **HASHES)
    assert result["raw_output"] == original == raw
    assert result["outcome"] == dict(
        needs_clarification=True, plan=None, questions=[previous.OUT_OF_SCOPE],
        reason="out_of_scope", source_keys=["request_1"],
    )
    assert result["body_allowed"] is False


def test_v2_request_explicitly_allows_three_optional_supported_kinds():
    inputs, _ = case()
    request = evidence.build_request(inputs)
    payload = json.loads(request.prompt.messages[1].content)
    assert payload["prompt_version"] == evidence.VERSION
    assert payload["required_evidence"]["out_of_scope"] == ["unsupported"]
    assert payload["optional_evidence"]["out_of_scope"] == ["normal", "full_push", "empty_pop"]
    assert request.json_schema["properties"]["evidence"]["maxItems"] == 4
    assert "full source context" in request.prompt.messages[0].content


@pytest.mark.parametrize(("entries", "error"), [
    ([quote("normal", "理解栈操作")], "STACK_SELECTION_EVIDENCE"),
    ([quote("unsupported", "递归")], "STACK_SELECTION_EVIDENCE"),
    ([quote("unsupported", "动态扩容", "request_2")], "STACK_SELECTION_SCHEMA"),
    ([quote("unsupported", "动态扩容")] * 2, "STACK_SELECTION_EVIDENCE"),
    ([quote("unsupported", "动态扩容"), quote("normal", "动态扩容")], "STACK_SELECTION_EVIDENCE"),
])
def test_scope_rejects_missing_forged_and_duplicate_citations(entries, error):
    inputs, raw = case()
    with pytest.raises(SnapshotError, match=error):
        evidence.inspect_scope(dict(raw, evidence=entries), inputs, **HASHES)


def test_semantic_negation_rejection_and_review_binding():
    inputs, raw = fixture("理解栈操作，不用讲动态扩容", "out_of_scope", ("动态扩容",))
    # A literal substring is insufficient when the surrounding clause negates the topic.
    record = evidence.inspect_scope(raw, inputs, **HASHES)
    with pytest.raises(SnapshotError, match="STACK_REVIEW_REQUIRED"):
        evidence.reviewed_scope(raw, inputs, review=review_of(record, semantics="fail"), **HASHES)
    real_inputs, real_raw = case()
    valid_review = review_of(evidence.inspect_scope(real_raw, real_inputs, **HASHES))
    with pytest.raises(SnapshotError, match="STACK_REVIEW_REQUIRED"):
        evidence.reviewed_scope(raw, inputs, review=valid_review, **HASHES)
    with pytest.raises(SnapshotError, match="STACK_REVIEW_REQUIRED"):
        evidence.reviewed_scope(real_raw, real_inputs, review=valid_review,
                                request_sha256=HASHES["request_sha256"], response_sha256="c" * 64)


@pytest.mark.skipif(
    os.environ.get("EDUMIND_T148_ARCHIVE_CHECK") != "1",
    reason="requires access to the local T147 encrypted originals and dedicated PostgreSQL",
)
@pytest.mark.parametrize("alter_binding", [False, True])
def test_reviewed_archives_bind_only_to_new_operations(monkeypatch, tmp_path, alter_binding):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    original.require_database(url, fixture=True)
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    requests = []
    archive_stop = (original.VAULT / "STOP").read_bytes()
    legacy_approval = stack.read(original.VAULT / "batch.json")["approval"]
    old_trial = original.GoalTrial(original.Batch(
        original.VAULT, make_url(url).set(database=original.DATABASE)
        .render_as_string(hide_password=False),
    ), "A")

    async def old_plans(db):
        result = {}
        for slot in continuation.SLOTS:
            parent, source, owner = continuation.reviewed_parent(slot)
            repo = SnapshotRepository(db, owner)
            cid, oid = UUID(source["course_id"]), UUID(source["operation_id"])
            plan = await repo.get_plan(cid, UUID(source["plan_id"]))
            assert plan["candidate"] == parent and plan["digest"] == source["plan_digest"]
            operation = await repo._operation(cid, oid)
            assert operation.state == "cancelled"
            row = await db.scalar(select(FreeCoursePlanningResult).where(
                FreeCoursePlanningResult.operation_id == oid,
            ))
            assert row is not None and str(row.plan_id) == source["plan_id"]
            assert row.response_json == continuation.read_archive(slot)[3]
            result[slot] = plan
        return result

    old = old_trial.db(old_plans)

    def mock(request):
        slot, stage = continuation.SEQUENCE[len(requests)]
        body = json.loads(request.content)
        payload = json.loads(body["input"][1]["content"])
        assert payload["request"]["original_goal"] == original.SAMPLES[slot][0]
        assert payload["plan_source"] == "goal_selected"
        assert payload["materials_digest"] == stack.read(continuation.MANIFEST)["materials_digest"]
        if stage == "rejections":
            assert payload["upstream_context"][0]["scene_version_id"] == saved["B", "normal"][
                "scene_version_id"
            ]
        requests.append((slot, stage))
        response = with_direct_echo(body, envelope(practice_fixture(payload)))
        return httpx.Response(200, stream=httpx.ByteStream(response))

    batch = continuation.Batch(tmp_path / "batch", url, transport=httpx.MockTransport(mock))
    saved = {}
    with TestClient(app, base_url="https://testserver") as a, TestClient(
        app, base_url="https://testserver",
    ) as b:
        clients = {"A": a, "B": b}
        owners = {slot: client.post("/api/auth/guest").json()["user"]["id"]
                  for slot, client in clients.items()}
        with pytest.raises(SnapshotError, match="STACK_EXACT_AUTHORIZATION_REQUIRED"):
            batch.start(legacy_approval)
        approval = continuation.approval_values(owners, fixture=True)
        run = batch.start(approval)

        async def count_selection_rows(db):
            return await db.scalar(select(func.count()).select_from(FreeCoursePlanningResult).where(
                FreeCoursePlanningResult.operation_id.in_([
                    UUID(row["operation_id"]) for row in run["courses"].values()
                ]),
            ))

        for slot, client in clients.items():
            root = f"/api/free-courses/{run['courses'][slot]['course_id']}"
            body = client.get(root).json()
            assert body["head"]["version"] == 1 and not body["head"]["complete"]
            admitted = stack.read(batch.vault / slot / "plan.admitted.json")
            assert admitted["plan_digest"] != old[slot]["digest"]
            assert admitted["selection_replay"]["plan_digest"] == old[slot]["digest"]
            assert client.get(f"/api/free-courses/{admitted['selection_replay']['course_id']}"
                              ).status_code == 404
        assert continuation.ContinuationTrial(batch, "A").db(count_selection_rows) == 0
        for slot, stage in (("C", "normal"), ("A", "plan")):
            with pytest.raises(SnapshotError, match="STACK_STAGE_NOT_AUTHORIZED"):
                batch.perform("send", slot, stage, key="fixture-secret")
        with pytest.raises(SnapshotError, match="STACK_SELECTOR_ORDER"):
            batch.perform("send", "B", "normal", key="fixture-secret")
        if alter_binding:
            a_plan = batch.vault / "A" / "plan.admitted.json"
            record = stack.read(a_plan)
            record["selection_replay"] = continuation.reviewed_parent("B")[1]
            a_plan.write_bytes(stack.canonical(record))
            with pytest.raises(SnapshotError, match="STACK_ARCHIVE_BINDING"):
                batch.perform("send", "A", "normal", key="fixture-secret")
            assert not requests
        else:
            for slot, stage in continuation.SEQUENCE:
                candidate = batch.perform("send", slot, stage, key="fixture-secret")
                inspected = batch.perform("inspect", slot, stage)
                bindings = [candidate]
                if stage == "rejections":
                    bindings.insert(0, saved["B", "normal"]["candidate_digest"])
                saved[slot, stage] = batch.perform("review", slot, stage, review=dict(
                    candidates=bindings, verdict="pass", reviewer="offline fixture",
                    checks=dict.fromkeys(inspected["required_checks"], "pass"),
                    notes="test binding",
                ))
            assert requests == list(continuation.SEQUENCE)
            for slot, client in clients.items():
                root = f"/api/free-courses/{run['courses'][slot]['course_id']}"
                head = client.get(root).json()["head"]
                assert head["complete"] and head["version"] == {"A": 2, "B": 3}[slot]
                for scene in head["scenes"]:
                    path = f"{root}/versions/{head['version']}/scenes/{scene['scene_id']}"
                    view = client.get(path)
                    assert view.status_code == 200
                    source = view.json()["generation_source"]
                    assert source["evidence_kind"] == "offline_fixture"
                    assert source["plan_digest"] != old[slot]["digest"]
                    assert '"answer_key"' not in view.text and '"solution"' not in view.text
        assert (batch.vault / "STOP").is_file()
        with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
            batch.perform("send", "A", "normal", key="fixture-secret")
    assert old_trial.db(old_plans) == old
    assert (original.VAULT / "STOP").read_bytes() == archive_stop
