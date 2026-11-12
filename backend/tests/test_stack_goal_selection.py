"""Offline selector contracts and reuse of private planning and scene admission."""

import asyncio
import json
import os
from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from test_stack_multiscene import PLANNING_INPUT, practice_fixture

from app.agents import free_course_planning as planner
from app.agents.free_scene_generation import SceneOutcome
from app.core.database import create_database_engine
from app.main import app
from app.models.free_course_planning import FreeCoursePlanningResult
from app.services import free_course_planning as plans
from app.services import free_scene_availability as availability
from app.services import free_scene_generation as scenes
from app.services import stack_goal_selection as selector
from app.services import stack_multiscene as stack
from app.services import stack_multiscene_materials as basis
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest
from app.services.free_scene_validation import validate_candidate

CASES = [
    ("理解栈操作和 LIFO", "operations", ("栈操作和 LIFO",)),
    ("想懂压栈、弹栈和后来压进去的先出来，不用讲动态扩容。", "operations",
     ("压栈、弹栈和后来压进去的先出来",)),
    ("理解正常操作及满栈、空栈拒绝", "operations_and_rejections",
     ("正常操作", "满栈、空栈拒绝", "空栈拒绝")),
    ("先学压入弹出，再看塞满时压不进、一个也没有时弹不出的原因。", "operations_and_rejections",
     ("压入弹出", "塞满时压不进", "一个也没有时弹不出")),
    ("理解栈操作和动态扩容", "out_of_scope", ("动态扩容",)),
    ("学会让数组栈满了以后自动把容量翻倍。", "out_of_scope", ("自动把容量翻倍",)),
]


def fixture(goal, selection, excerpts):
    inputs = deepcopy(PLANNING_INPUT)
    inputs["original_goal"] = inputs["request_sources"]["request_1"]["text"] = goal
    inputs["stack_boundaries"] = basis.SELECTION_BATCH
    response = dict(selection=selection, evidence=[
        dict(kind=kind, source_key="request_1", source_excerpt=excerpt)
        for kind, excerpt in zip(selector.REQUIRED[selection], excerpts, strict=True)
    ])
    return inputs, response


@pytest.mark.parametrize(("goal", "selection", "excerpts"), CASES)
def test_goal_selection_contract(goal, selection, excerpts):
    inputs, raw = fixture(goal, selection, excerpts)
    request = selector.build_request(inputs)
    payload = json.loads(request.prompt.messages[1].content)
    assert payload["original_goal"] == goal and payload["request_sources"] == {"request_1": goal}
    assert set(request.json_schema["properties"]) == {"selection", "evidence"}
    assert basis.VERSION not in request.prompt.messages[1].content
    normalized = selector.normalize(raw, inputs)
    if selection == "out_of_scope":
        assert normalized == dict(needs_clarification=True, plan=None,
                                  questions=[selector.OUT_OF_SCOPE], reason="out_of_scope",
                                  source_keys=["request_1"])
        return
    plan = normalized["plan"]
    expected = ["normal"] if selection == "operations" else ["normal", "rejections"]
    assert [s["scene_key"] for s in plan["scenes"]] == expected
    assert plan["scenes"][-1]["depends_on"] == ([] if len(expected) == 1 else ["normal"])
    assert plan["shared_example"] == basis.VERSION
    assert [o["source_excerpt"] for o in plan["objectives"]] == list(excerpts)
    selector.check_outline(normalized, inputs)


def test_goal_selection_rejects_fabricated_fields_and_evidence():
    inputs, raw = fixture(*CASES[2])
    for bad in (
        dict(raw, material_id="made-up"), dict(raw, scenes=["custom"]), dict(raw, code="C"),
    ):
        with pytest.raises(SnapshotError, match="STACK_SELECTION_SCHEMA"):
            selector.normalize(bad, inputs)
    forged = deepcopy(raw)
    forged["evidence"][0]["source_excerpt"] = "引文不在原文中"
    for bad in (
        forged,
        dict(raw, evidence=raw["evidence"][:2]),
        dict(raw, evidence=raw["evidence"][:1] * 3),
    ):
        with pytest.raises(SnapshotError, match="STACK_SELECTION_EVIDENCE"):
            selector.normalize(bad, inputs)
    valid = selector.normalize(raw, inputs)
    valid["plan"]["scenes"][1]["depends_on"] = []
    with pytest.raises(SnapshotError, match="STACK_SELECTION_OUTLINE"):
        selector.check_outline(valid, inputs)


@pytest.mark.parametrize("case", (1, 3, 5), ids=("normal", "both", "out-of-scope"))
def test_selected_course_private_admission(monkeypatch, case):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    assert url.endswith("/edumind_catalog_p15_t145_test")
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    goal, selection, _ = CASES[case]
    _, raw = fixture(*CASES[case])
    with TestClient(app, base_url="https://testserver") as client:
        guest = client.post("/api/auth/guest").json()
        owner = UUID(guest["user"]["id"])

        async def stage():
            engine = create_database_engine(url)
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
                    repo = SnapshotRepository(db, owner)
                    created = await repo.create_course(
                        goal, key="t145", config={"prompt_version": basis.SELECTION_BATCH},
                    )
                    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
                    fence = await repo.acquire_write_fence(cid, oid)
                    inputs = await plans.load_inputs(db, owner, cid, oid)
                    req = selector.build_request(inputs)
                    state = "needs_clarification" if selection == "out_of_scope" else "ready"
                    outcome = planner.PlanningOutcome(
                        state, None, digest("planning-input", snapshot=inputs),
                        planner.request_digest(req), raw,
                    )
                    stored = await plans.persist_outcome(
                        db, owner, cid, fence, expected_head=None, call_key="selector",
                        inputs=inputs, outcome=outcome,
                    )
                    record = await db.get(FreeCoursePlanningResult, UUID(stored["result_id"]))
                    assert record is not None and record.response_json == raw
                    if selection == "out_of_scope":
                        assert stored["plan_id"] is None
                        return cid, oid, None, []
                    pid = UUID(stored["plan_id"])
                    outline = await availability.commit_outline(
                        db, owner, cid, fence, plan_id=pid, key="outline",
                    )
                    plan = await repo.get_plan(cid, pid)
                    selected = plan["scenes"]
                    head = outline["version"]
                    if len(selected) == 2:
                        with pytest.raises(SnapshotError, match="DEPENDENCY_UNAVAILABLE"):
                            await scenes.load_inputs(
                                db, owner, cid, oid, plan_id=pid,
                                scene_id=UUID(selected[1]["scene_id"]), expected_head=head,
                            )
                    first_version = None
                    for row in selected:
                        head, version = await admit_fixture(
                            db, owner, cid, oid, fence, pid, head, row, first_version,
                        )
                        if first_version is None:
                            first_version = version
                    return cid, oid, head, selected
            finally:
                await engine.dispose()

        cid, oid, head, selected = asyncio.run(stage())
        root = f"/api/free-courses/{cid}"
        course = client.get(root)
        assert course.status_code == 200
        if selection == "out_of_scope":
            assert course.json()["head"] is None
            operation = client.get(f"{root}/operations/{oid}").json()
            assert operation["state"] == "awaiting_clarification"
            assert operation["clarification_questions"] == [selector.OUT_OF_SCOPE]
            return
        manifest = course.json()["head"]
        assert manifest["version"] == head == len(selected) + 1
        assert manifest["complete"]
        assert [s["scene_id"] for s in manifest["scenes"]] == [s["scene_id"] for s in selected]
        for row in selected:
            response = client.get(f"{root}/versions/{head}/scenes/{row['scene_id']}")
            assert response.status_code == 200, response.text
            view = response.json()
            assert view["generation_source"]["plan_source"] == "goal_selected"
            visual = next(b for b in view["blocks"] if b["kind"] == "visualization")
            exercise = next(b for b in view["blocks"] if b["kind"] == "exercise")
            expected = (5, 2) if row["scene_key"] == "normal" else (9, 4)
            assert (len(visual["steps"]), len(exercise["items"])) == expected
            assert "answer_key" not in response.text and '"solution"' not in response.text


async def admit_fixture(db, owner, cid, oid, fence, pid, head, row, first_version):
    sid = UUID(row["scene_id"])
    inputs = await scenes.load_inputs(
        db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=head,
    )
    key = row["scene_key"]
    request = stack.bound_scene_request(inputs)
    payload = json.loads(request.prompt.messages[1].content)
    assert payload["materials_digest"] == basis.materials_digest(basis.EVIDENCE_BATCH)
    if key == "rejections":
        assert payload["upstream_context"][0]["scene_version_id"] == first_version
    else:
        assert not payload["upstream_context"]
    source = dict(
        origin="stack_boundaries_model_generation", batch=basis.SELECTION_BATCH,
        model="deepseek-flash", prompt_version=stack.EVIDENCE_PROMPT, plan_source="goal_selected",
        plan_digest=inputs["plan"]["digest"], materials_digest=payload["materials_digest"],
        candidate_digest="a"*64, review_sha256="b"*64, evidence_kind="offline_fixture",
        scene_key=key, parent_digest=None, source_request_sha256="c"*64,
        source_response_sha256="d"*64,
    )
    outcome = SceneOutcome(
        "candidate", None, digest("scene-generation-input", snapshot=inputs),
        planner.request_digest(request),
        dict(raw_output=practice_fixture(payload), generation_source=source), None,
    )
    stored = await scenes.persist_outcome(
        db, owner, cid, fence, call_key=key, inputs=inputs, outcome=outcome,
    )
    checked = await validate_candidate(db, owner, cid, fence, result_id=UUID(stored["result_id"]))
    ready = await availability.commit_scene(
        db, owner, cid, fence, validation_id=UUID(checked["validation_id"]),
        expected_head=head, key=key,
    )
    return ready["version"], ready["scene_version_id"]
