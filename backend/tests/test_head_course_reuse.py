"""T109-only binding/recovery/revision regressions. Fixtures never count as model success."""

import asyncio
import json
import os
import time
from copy import deepcopy
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.agents import free_course_planning as local
from app.agents import head_course_planning_wire as wire
from app.main import app
from app.services import head_course_generation as g
from app.services import head_course_materials as m
from app.services import head_course_reuse as r
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from scripts import head_course_goal as entry
from scripts import head_course_goal_fixture as fixture


def inputs():
    cid, oid, rid = (str(uuid4()) for _ in range(3))
    return dict(
        course_id=cid,
        operation_id=oid,
        request_id=rid,
        original_goal=m.REUSE_GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={"request_1": dict(request_id=rid, version=1, text=m.REUSE_GOAL)},
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.support_for_goal(m.REUSE_GOAL),
    )


def setup_candidate():
    payload = m.content_payload(inputs(), fixture.plan("head-new-B")["plan"])
    raw = fixture.content(payload)
    for i, p in enumerate(raw["paragraphs"]):
        p["text"] += f"：段落{i}"
    return r.candidate(payload, raw)


def opinion(c, verdict="pass"):
    return dict(
        candidate_digest=c["candidate_digest"],
        parent_digest=c["parent_digest"],
        verdict=verdict,
        independent_evaluator="offline_fixture_only",
        planning_basis_binding=c["payload"]["planning_basis"]["binding"],
        blocking_findings=[],
        checks={
            k: True
            for k in (
                "full_lesson",
                "fact_citations",
                "paragraph_responsibilities",
                "no_neighbour_copy",
                "no_omitted_explanation",
                "code_trace_answers",
                "no_answer_hints",
            )
        },
    )


def repair_review(c, i=0):
    review = opinion(c, "needs_revision")
    review["findings"] = [
        dict(
            id="new-finding",
            path=["paragraphs", i],
            quote=c["raw_output"]["paragraphs"][i]["text"],
            issue="测试措辞，不是真实缺陷",
            area="teaching_expression",
            repairable=True,
            teaching_responsibility="原段教学职责：测试",
        )
    ]
    return review


def duplicate_envelope(value, *, conflict=False, outside=False):
    view = json.loads(fixture.envelope(value))
    text = canonical(value).decode()
    q = canonical(value["questions"]).decode()
    k = m.QKEYS[0]
    second = deepcopy(value["questions"][k])
    if conflict:
        second["explanation"] += "冲突"
    text = text.replace(q, q[:-1] + ',"' + k + '":' + canonical(second).decode() + "}")
    if outside:
        text = (
            text[:-1] + ',"lifecycle":' + json.dumps(value["lifecycle"], ensure_ascii=False) + "}"
        )
    view["output"][0]["content"][0]["text"] = text
    return canonical(view)


def test_actual_request_fixed_input_and_local_planning_checks():
    data = inputs()
    request = entry.planning_body(data)
    sent = json.loads(request["input"][1]["content"])
    assert sent["original_goal"] == m.REUSE_GOAL
    assert sent["head_support"]["examples"] == {"head-new-B": m.SPECS["head-new-B"]}
    evidence = sent["planning_example_basis"]["examples"]["head-new-B"]
    assert (
        evidence
        == m.content_payload(data, fixture.plan("head-new-B")["plan"])["planning_basis"]["evidence"]
    )
    assert evidence["receive_return"]["observation"]["reachable_prefix"] == [0, 6, -8]
    assert evidence["ignore_return"]["observation"]["reachable_prefix"] == [-8]
    assert wire.to_local(fixture.wire_plan("head-new-B"), data) == fixture.plan("head-new-B")
    with pytest.raises(SnapshotError):
        wire.to_local(fixture.wire_plan("head-new-A"), data)
    value = fixture.wire_plan("head-new-B")
    for field in ("source_key", "source_excerpt"):
        bad = deepcopy(value)
        bad["plans"][0]["objectives"][0][field] = "unknown"
        with pytest.raises(SnapshotError):
            wire.to_local(bad, data)
    orphan = deepcopy(value)
    orphan["plans"][0]["scenes"][0]["objective_ids"] = ["link"]
    with pytest.raises(SnapshotError):
        wire.to_local(orphan, data)
    clarify = dict(
        protocol_version=wire.VERSION,
        needs_clarification=True,
        plans=[],
        questions=["测试真实缺失材料？"],
        reason="required_material_missing",
        source_keys=["request_1"],
    )
    assert wire.to_local(clarify, data)["needs_clarification"] is True
    bad = deepcopy(data)
    bad["head_support"]["examples"]["head-new-B"]["insert_values"] = [0, 6]
    with pytest.raises(SnapshotError):
        local.snapshot_input(bad)


@pytest.mark.parametrize(
    "mode", ["normal", "identical", "conflict", "outside", "unknown_phase", "truncated"]
)
def test_strict_first_and_exact_recovery(mode):
    c = setup_candidate()
    raw = fixture.envelope(c["raw_output"])
    if mode in ("identical", "conflict", "outside"):
        raw = duplicate_envelope(
            c["raw_output"], conflict=mode == "conflict", outside=mode == "outside"
        )
    if mode == "unknown_phase":
        raw = fixture.envelope(c["raw_output"], phase="analysis")
    if mode == "truncated":
        raw = raw[:-2]
    if mode not in ("normal", "identical"):
        with pytest.raises(Exception):
            r.record(
                c["payload"],
                m.body(c["payload"]),
                raw,
                entry.raw_io,
                evidence_kind="offline_fixture",
            )
        return
    rec = r.record(
        c["payload"], m.body(c["payload"]), raw, entry.raw_io, evidence_kind="offline_fixture"
    )
    assert rec["candidate"]["raw_output"] == c["raw_output"]
    assert (rec["strict_failure"] is None) == (mode == "normal")
    assert bool(rec["candidate"]["recovery"]) == (mode == "identical")
    assert rec["raw_response"].encode() == raw
    r.validate_record(rec, c["payload"], entry.raw_io)


def test_dynamic_revision_text_citations_and_materials_immutable():
    c = setup_candidate()
    review = repair_review(c, 1)
    review["findings"].append(
        dict(
            id="summary",
            path=["learning_summary"],
            quote=c["raw_output"]["learning_summary"],
            issue="总结措辞测试",
            area="citation",
            repairable=True,
            teaching_responsibility="归纳连接和返回值",
        )
    )
    body = r.revision_body(c, review)
    assert set(body["text"]["format"]["schema"]["properties"]) == {
        "paragraph_1",
        "learning_summary",
    }
    replacements = dict(
        paragraph_1=dict(text="修订夹具：保持职责，不算教学成果", fact_ids=["trace_step_01"]),
        learning_summary="修订总结夹具",
    )
    merged = r.merge(c, review, replacements)
    assert c == setup_stable_parent(c)
    assert merged["parent_digest"] == c["candidate_digest"]
    assert merged["payload"] == c["payload"]
    restored = deepcopy(merged["raw_output"])
    restored["paragraphs"][1] = c["raw_output"]["paragraphs"][1]
    restored["learning_summary"] = c["raw_output"]["learning_summary"]
    assert restored == c["raw_output"]
    rec = r.record(
        c["payload"],
        body,
        fixture.envelope(replacements),
        entry.raw_io,
        evidence_kind="offline_fixture",
        parent=c,
        review=review,
    )
    assert rec["candidate"] == merged
    assembled = r.assembled([dict(candidate=c), rec], opinion(merged))
    assert assembled["blocks"][-2]["markdown"] == "修订总结夹具"
    assert (
        next(b for b in assembled["blocks"] if b["kind"] == "visualization")["text_alternative"]
        == "修订总结夹具"
    )
    for mutation in ("fact", "copy", "extra", "missing"):
        bad = deepcopy(replacements)
        if mutation == "fact":
            bad["paragraph_1"]["fact_ids"] = ["unknown"]
        if mutation == "copy":
            bad["paragraph_1"]["text"] = c["raw_output"]["paragraphs"][0]["text"]
        if mutation == "extra":
            bad["questions"] = {}
        if mutation == "missing":
            del bad["learning_summary"]
        with pytest.raises(Exception):
            r.merge(c, review, bad)


def setup_stable_parent(c):
    return r.candidate(c["payload"], c["raw_output"])


@pytest.mark.parametrize("mutation", ["digest", "quote", "path", "area", "repairable", "basis"])
def test_review_scope_refuses_drift(mutation):
    c = setup_candidate()
    review = repair_review(c)
    if mutation == "digest":
        review["candidate_digest"] = "0" * 64
    if mutation == "quote":
        review["findings"][0]["quote"] = "不在父稿"
    if mutation == "path":
        review["findings"][0]["path"] = ["questions", "link_target"]
    if mutation == "area":
        review["findings"][0]["area"] = "program_materials"
    if mutation == "repairable":
        review["findings"][0]["repairable"] = False
    if mutation == "basis":
        review["planning_basis_binding"] = {}
    with pytest.raises(SnapshotError):
        r.revision_body(c, review)


@pytest.mark.parametrize("mode", ["direct", "recovered", "revised", "refused_repair", "overbudget"])
def test_actual_entry_and_private_application(tmp_path, monkeypatch, mode):
    """Actual entry + PG + API. No Provider; no fabricated real course/evaluation."""
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_HEAD_GOAL_DEVELOPMENT", "1")
    monkeypatch.setattr(entry, "PACKAGE", entry.REUSE_PACKAGE)
    monkeypatch.setattr(entry, "package_digest", lambda: "a" * 64)
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        headers = {"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())}
        created = client.post(
            "/api/free-courses", json=dict(goal=m.REUSE_GOAL, code_language="c"), headers=headers
        )
        assert created.status_code == 201, created.text
        owner, cid, oid = (
            UUID(auth["user"]["id"]),
            *(UUID(created.json()[k]) for k in ("course_id", "operation_id")),
        )
        context = asyncio.run(entry.prepare(owner, cid, oid))
        vault = tmp_path / "vault"
        vault.mkdir(mode=0o700)
        (vault / "raw.key").write_bytes(Fernet.generate_key())
        (vault / "raw.key").chmod(0o600)
        cipher = Fernet((vault / "raw.key").read_bytes())
        (vault / "context.json").write_bytes(canonical(context))
        start = int(time.time()) - 1
        approval = dict(
            package_sha256="a" * 64,
            version=r.VERSION,
            accept_ADR0053_and_batch_C2=True,
            explicit_user_authorization=True,
            max_http_requests=3,
            starts_epoch=start,
            expires_epoch=start + 600,
            planning_wire_version=wire.VERSION,
            planning_prompt_version=wire.PROMPT_VERSION,
        )
        replies = [fixture.envelope(fixture.wire_plan("head-new-B"))]
        sent = []

        def transport(req):
            sent.append(json.loads(req.content))
            return httpx.Response(200, stream=httpx.ByteStream(replies.pop(0)))

        mock = httpx.MockTransport(transport)
        entry.send("plan", vault, approval, transport=mock, key="fake-key-only")
        planning = entry.verify_saved(vault, "plan", cipher)["plan"]
        payload = m.content_payload(context["planning_inputs"], planning)
        plan_review = dict(
            plan_digest=digest("head-plan", plan=planning),
            verdict="pass",
            independent_evaluator="offline_fixture",
            planning_basis_binding=payload["planning_basis"]["binding"],
        )
        (vault / "plan-review.json").write_bytes(canonical(plan_review))
        raw = fixture.content(payload)
        for i, paragraph in enumerate(raw["paragraphs"]):
            paragraph["text"] += str(i)
        replies.append(duplicate_envelope(raw) if mode == "recovered" else fixture.envelope(raw))
        entry.send("generate", vault, approval, transport=mock, key="fake-key-only")
        records = [entry.verify_saved(vault, "generate", cipher)]
        assert records[0]["evidence_kind"] == "offline_fixture"
        if mode in ("revised", "refused_repair", "overbudget"):
            review = repair_review(records[0]["candidate"], 2)
            (vault / "repair-review.json").write_bytes(canonical(review))
            replacements = dict(paragraph_2=dict(text="修订夹具2", fact_ids=["trace_step_01"]))
            revision_response = fixture.envelope(
                replacements, phase="analysis" if mode == "refused_repair" else "final_answer"
            )
            if mode == "overbudget":
                budget_view = json.loads(revision_response)
                budget_view["usage"] = dict(input_tokens=10, output_tokens=4001, total_tokens=4011)
                revision_response = canonical(budget_view)
            replies.append(revision_response)
            if mode in ("refused_repair", "overbudget"):
                with pytest.raises(Exception):
                    entry.send("repair", vault, approval, transport=mock, key="fake-key-only")
                assert (vault / "STOP").exists() and (vault / "ACTIVE").exists()
                assert entry.raw_io.decrypt(vault / "repair.raw.enc", cipher)
                failure = entry.read(vault / "repair.failure.json")
                assert failure["code"] == (
                    "REUSE_USAGE" if mode == "overbudget" else "WIRE_MESSAGE_PHASE"
                )
                with pytest.raises(SnapshotError):
                    entry.send("repair", vault, approval, transport=mock, key="fake-key-only")
                assert len(sent) == 3
                return
            entry.send("repair", vault, approval, transport=mock, key="fake-key-only")
            records.append(entry.verify_saved(vault, "repair", cipher))
        chain = dict(
            context=context,
            plan_request=sent[0],
            plan_raw_response=entry.raw_io.decrypt(vault / "plan.raw.enc", cipher).decode(),
            plan_review=plan_review,
            records=records,
            final_review=opinion(records[-1]["candidate"]),
        )

        async def publish(db):
            return await r.publish(db, owner, cid, oid, chain)

        result = asyncio.run(entry.database(publish))
        route = f"/api/free-courses/{cid}/versions/2/scenes/{result['scene_id']}"
        scene = client.get(route)
        assert scene.status_code == 200, scene.text
        view = scene.json()
        assert "answer_key" not in scene.text and "solution" not in scene.text
        assert (
            view["generation_source"]["candidate_digest"]
            == records[-1]["candidate"]["candidate_digest"]
        )
        assert view["generation_source"]["prompt_version"] == r.VERSION
        assert view["blocks"][1]["markdown"] == raw["paragraphs"][0]["text"]
        assert view["generation_source"]["evidence_kind"] == "offline_fixture"
        if mode == "recovered":
            assert (
                view["generation_source"]["format_recovery"]["model_first_structure_pass"] is False
            )
        exercise = view["blocks"][-1]
        attempt_body = dict(
            course_version=2,
            scene_id=result["scene_id"],
            scene_version_id=view["scene_version_id"],
            exercise_id=exercise["exercise_id"],
            exercise_version_id=exercise["exercise_version_id"],
            answers=[
                dict(question_id=k, answer=v) for k, v in payload["materials"]["answers"].items()
            ],
        )
        submitted = client.post(
            f"/api/free-courses/{cid}/attempts",
            json=attempt_body,
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert submitted.status_code == 201, submitted.text
        url = f"/api/free-courses/{cid}/attempts/{submitted.json()['attempt_id']}"
        feedback = client.get(url).json()
        assert feedback["comparison_score"] == 1 and feedback["mastery_effect"] == "course_only"
        assert client.get(url).json() == feedback and client.get(route).json() == view
        assert len(sent) == (3 if mode == "revised" else 2)

        async def check(db):
            from sqlalchemy import select

            from app.models.free_scene_generation import FreeSceneGenerationResult

            row = await db.scalar(
                select(FreeSceneGenerationResult).where(FreeSceneGenerationResult.course_id == cid)
            )
            actual = row.input_snapshot["inputs"]
            assert g.validate_generation(row, actual)["state"] == "accepted"
            for change in ("response", "request", "review", "materials"):
                original = deepcopy(row.input_snapshot)
                if change == "response":
                    row.response_json = {**row.response_json, "actions": []}
                if change == "request":
                    row.input_snapshot["reuse_chain"]["records"][-1]["request"]["temperature"] = 0.9
                if change == "review":
                    row.input_snapshot["reuse_chain"]["final_review"]["checks"][
                        "fact_citations"
                    ] = False
                if change == "materials":
                    row.input_snapshot["reuse_chain"]["records"][-1]["candidate"]["payload"][
                        "materials"
                    ]["answers"]["normal_values"] = "[]"
                with pytest.raises(Exception):
                    g.validate_generation(row, actual)
                row.input_snapshot = original
                row.response_json = r.assembled(records, chain["final_review"])

        asyncio.run(entry.database(check))


def test_historical_requests_and_contract_remain_exact():
    from pathlib import Path

    from app.services import head_course_fact_publication as old

    root = Path(__file__).resolve().parents[2]
    saved = root / "docs/acceptance/phase-1.5-head-goal-t108-r03"
    historic_inputs = json.loads((saved / "planning-input.template.json").read_text())
    assert entry.planning_body(historic_inputs) == json.loads(
        (saved / "planning-request.template.json").read_text()
    )
    record, _ = (
        old.mapping()
    )  # Original file hashes, parent, four-text merge and review still pinned.
    assert (
        record["candidate"]["candidate_digest"]
        == "4db6214e41291b7aa07f852914eccb56455a6c722a5d976e38764a283b936c8a"
    )
    import subprocess

    historical = json.loads(
        subprocess.check_output(
            ["git", "show", "09c5067:backend/app/contracts/free_course.openapi.json"], cwd=root
        )
    )
    current = json.loads((root / "backend/app/contracts/free_course.openapi.json").read_text())
    assert (
        current["components"]["schemas"]["HeadGenerationSourceLegacy"]
        == historical["components"]["schemas"]["HeadGenerationSource"]
    )
