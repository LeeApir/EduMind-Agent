"""T111 exact input, evidence, scoped revision and vault-to-application regressions."""

import asyncio
import json
import os
import time
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_head_course_reuse import duplicate_envelope, inputs, opinion, repair_review

from app.agents import head_course_planning_wire as wire
from app.main import app
from app.services import head_course_materials as materials
from app.services import head_course_reuse as reuse
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.head_course_teaching_evidence import DISCARDED, DISPLAYED
from scripts import head_course_deepseek_wire as direct
from scripts import head_course_goal as entry
from scripts import head_course_goal_fixture as fixture


def fixed_inputs():
    data = inputs()
    data["original_goal"] = data["request_sources"]["request_1"]["text"] = materials.FIXED_GOAL
    data["head_support"] = materials.support_for_goal(materials.FIXED_GOAL)
    return data


def fixed_review(candidate, verdict="pass"):
    value = opinion(candidate, verdict)
    value["evidence_digest"] = candidate["payload"]["teaching_evidence"]["evidence_digest"]
    value["checks"].update({check: True for check in reuse.FIXED_REVIEW_CHECKS})
    return value


def replacement_review(candidate):
    value = fixed_review(candidate, "needs_revision")
    findings = repair_review(candidate, 1)["findings"]
    for key, role in (
        ("learning_summary", "同时归纳连接旧首与接收返回值"),
        ("failure_scope", "区分实际成功演示、静态代码与未显示分支"),
    ):
        findings.append(
            dict(
                id=key,
                path=[key],
                quote=candidate["raw_output"][key],
                issue="离线修订路径夹具",
                area="fact",
                repairable=True,
                teaching_responsibility=role,
            )
        )
    value.update(findings=findings, blocking_findings=deepcopy(findings))
    return value


def replacements():
    return dict(
        paragraph_1=dict(text="离线夹具：忽略返回的说明", fact_ids=[DISCARDED]),
        learning_summary="离线夹具：新总结",
        failure_scope="离线夹具：新范围",
    )


def test_exact_first_request_carries_new_materials_and_historical_requests_match():
    data = fixed_inputs()
    raw_plan = fixture.wire_plan(materials.FIXED_EXAMPLE)
    plan = wire.to_local(raw_plan, data)["plan"]
    with pytest.raises(SnapshotError):
        wire.to_local(fixture.wire_plan("head-new-B"), data)
    payload = materials.content_payload(data, plan)
    sent = json.loads(entry.planning_body(data)["input"][1]["content"])
    with pytest.raises(SnapshotError, match="HEAD_FIXED_PROFILE_NOT_EMPTY"):
        entry.planning_body({**data, "learner_evidence": {"unrelated": True}})
    basis = sent["planning_example_basis"]
    assert list(basis["examples"]) == [materials.FIXED_EXAMPLE]
    assert basis["basis_digest"] == payload["planning_basis"]["binding"]["basis_digest"]
    req = materials.body(payload)
    assert json.loads(req["input"][1]["content"]) == payload
    assert req["text"]["format"]["schema"] == materials.SCHEMA
    evidence = payload["teaching_evidence"]["facts"]
    shown = evidence[DISPLAYED]["value"]
    ignored = evidence[DISCARDED]["value"]["observation"]
    assert shown["frame_ids"] == [f"f{i:02d}" for i in range(13)]
    assert [e["frame_id"] for e in shown["allocation_events"]] == ["f01", "f07"]
    assert [
        (e["frame_id"], e["condition_result"]) for e in shown["null_condition_evaluations"]
    ] == [("f02", False), ("f08", False)]
    assert not shown["no_allocation_frame_ids"] and not shown["actual_malloc_failure_displayed"]
    assert ignored["caller_head"] == "i0" and ignored["reachable_prefix"] == [5]
    assert ignored["unreachable_allocated_ids"] == ["t0", "t1"]
    assert payload["materials"]["catalog"]["example"]["observation"]["reachable_prefix"] == [
        9,
        -2,
        5,
    ]
    assert evidence[DISCARDED]["displayed_in_main_player"] is False
    assert evidence[DISCARDED]["main_frame_ids"] == []
    assert "Neither that path nor actual malloc failure is animated" in req["input"][0]["content"]
    for package in (entry.PACKAGE, entry.REUSE_PACKAGE):
        saved = json.loads((package / "planning-input.template.json").read_bytes())
        assert entry.planning_body(saved) == json.loads(
            (package / "planning-request.template.json").read_bytes()
        )


def test_scoped_merge_refuses_wrong_evidence_unknown_targets_and_missing_recheck():
    data = fixed_inputs()
    payload = materials.content_payload(data, fixture.plan(materials.FIXED_EXAMPLE)["plan"])
    raw = fixture.content(payload)
    parent = reuse.candidate(payload, raw)
    review = replacement_review(parent)
    replacement = replacements()
    merged = reuse.merge(parent, review, replacement)
    expected = deepcopy(raw)
    expected["paragraphs"][1] = replacement["paragraph_1"]
    expected.update({k: replacement[k] for k in ("failure_scope", "learning_summary")})
    assert merged["raw_output"] == expected and merged["payload"] == payload
    assert merged["parent_digest"] == parent["candidate_digest"]
    for change in ("evidence", "quote", "outside", "omitted_blocker"):
        bad = deepcopy(review)
        if change == "evidence":
            bad["evidence_digest"] = "0" * 64
        if change == "quote":
            bad["findings"][0]["quote"] = "absent"
        if change == "outside":
            bad["findings"][0]["path"] = ["questions", "link_target"]
        if change != "omitted_blocker":
            bad["blocking_findings"] = deepcopy(bad["findings"])
        else:
            bad["blocking_findings"] = []
        with pytest.raises(SnapshotError):
            reuse.revision_body(parent, bad)
    with pytest.raises(SnapshotError, match="REUSE_COPIED_NEIGHBOUR"):
        reuse.merge(parent, review, {**replacement, "paragraph_1": raw["paragraphs"][0]})
    with pytest.raises(SnapshotError, match="HEAD_FACT_REFERENCE"):
        reuse.merge(
            parent, review, {**replacement, "paragraph_1": dict(text="夹具", fact_ids=["wrong"])}
        )
    req = materials.body(payload)
    first = reuse.record(
        payload, req, fixture.envelope(raw), entry.raw_io, evidence_kind="offline_fixture"
    )
    incomplete = fixed_review(first["candidate"])
    incomplete["checks"]["return_contrast"] = False
    with pytest.raises(SnapshotError, match="REUSE_FULL_REVIEW_REQUIRED"):
        reuse.validate_final([first], incomplete, payload, entry.raw_io)


def with_direct_echo(request, raw):
    response = json.loads(raw)
    response.update(
        object="response",
        id="offline-response",
        created_at=0,
        reasoning={"effort": "none"},
        temperature=0.2,
        max_output_tokens=request["max_output_tokens"],
        text=request["text"],
    )
    response["usage"]["output_tokens_details"] = {"reasoning_tokens": 0}
    return canonical(response)


@pytest.mark.parametrize(
    ("profile", "mode"),
    [
        ("fixed", "direct"),
        ("fixed", "revised"),
        ("fixed", "recovered"),
        ("fixed", "protocol_stop"),
        ("deepseek", "direct"),
        ("deepseek", "revised"),
        ("deepseek", "recovered"),
        ("deepseek", "protocol_stop"),
        ("deepseek", "cutoff"),
        ("deepseek", "late"),
    ],
)
def test_actual_fixed_entry_and_application(tmp_path, monkeypatch, profile, mode):
    official = profile == "deepseek"
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_HEAD_GOAL_DEVELOPMENT", "1")
    monkeypatch.delenv("EDUMIND_HEAD_DEEPSEEK_DEVELOPMENT", raising=False)
    if official:
        monkeypatch.setenv("EDUMIND_HEAD_DEEPSEEK_DEVELOPMENT", "1")
        monkeypatch.setattr(entry, "PACKAGE", entry.DIRECT_PACKAGE)
        monkeypatch.setattr(entry, "DIRECT_VAULT", tmp_path)
    else:
        monkeypatch.setattr(entry, "PACKAGE", entry.FIXED_PACKAGE)
        monkeypatch.setattr(entry, "FIXED_VAULT", tmp_path)
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        headers = {"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())}
        response = client.post(
            "/api/free-courses",
            json=dict(goal=materials.FIXED_GOAL, code_language="c"),
            headers=headers,
        )
        assert response.status_code == 201, response.text
        cid, oid = (UUID(response.json()[k]) for k in ("course_id", "operation_id"))
        context = asyncio.run(entry.prepare(UUID(auth["user"]["id"]), cid, oid))
        context_raw = canonical(context)
        entry.raw_io.exclusive(tmp_path / "context.json", context_raw)
        entry.raw_io.exclusive(
            tmp_path / "plan.prepared-request.json",
            canonical(entry.planning_body(context["planning_inputs"])),
        )
        entry.raw_io.exclusive(tmp_path / "raw.key", Fernet.generate_key())
        cipher = Fernet((tmp_path / "raw.key").read_bytes())
        start = int(time.time()) - 1
        approval = dict(
            package_sha256=entry.package_digest(),
            version=materials.FIXED_VERSION,
            batch=reuse.FIXED_BATCH,
            context_sha256=reuse.sha(context_raw),
            accept_ADR0055_and_batch_C2=True,
            explicit_user_authorization=True,
            max_http_requests=3,
            starts_epoch=start,
            expires_epoch=start + 600,
            planning_wire_version=wire.VERSION,
            planning_prompt_version=wire.PROMPT_VERSION,
        )
        if official:
            for field in ("accept_ADR0055_and_batch_C2", "starts_epoch", "expires_epoch"):
                approval.pop(field)
            approval.update(
                batch=direct.BATCH,
                accept_ADR0058_and_batch_C2=True,
                execution_window=context["execution_window"],
            )
            window = context["execution_window"]
            expires = datetime.fromisoformat(window["expires_at"])
            assert expires - datetime.fromisoformat(window["starts_at"]) == timedelta(minutes=30)
            status = client.get(f"/api/free-courses/{cid}/operations/{oid}").json()
            assert status["deadline_at"] == window["expires_at"]
            with monkeypatch.context() as legacy:
                legacy.setattr(entry, "PACKAGE", entry.FIXED_PACKAGE)
                with pytest.raises(SnapshotError, match="HEAD_DIRECT_WINDOW_MISMATCH"):
                    asyncio.run(entry.prepare(UUID(auth["user"]["id"]), cid, oid))
        with pytest.raises(SnapshotError, match="HEAD_EXACT_AUTHORIZATION_REQUIRED"):
            entry.approval_check(tmp_path, {**approval, "explicit_user_authorization": False})
        with pytest.raises(SnapshotError, match="HEAD_EXACT_AUTHORIZATION_REQUIRED"):
            entry.approval_check(tmp_path, {**approval, "context_sha256": "0" * 64})
        sent, received = [], []

        def send(stage, body):
            def transport(req):
                sent.append(json.loads(req.content))
                assert req.headers["Host"] == "api.deepseek.com"
                assert req.url.path == "/responses" and req.url.scheme == "https"
                raw_response = with_direct_echo(sent[-1], body) if official else body
                received.append(raw_response)
                if mode == "late":
                    monkeypatch.setattr(entry.time, "time", lambda: expires.timestamp() + 1)
                return httpx.Response(200, stream=httpx.ByteStream(raw_response))

            entry.send(
                stage,
                tmp_path,
                approval,
                transport=httpx.MockTransport(transport),
                key="fixture-key-only",
            )

        plan_fixture = fixture.envelope(fixture.wire_plan(materials.FIXED_EXAMPLE))
        if mode in ("cutoff", "late"):
            if mode == "cutoff":
                monkeypatch.setattr(entry.time, "time", lambda: expires.timestamp() - 89)
            code = (
                "HEAD_DIRECT_WINDOW_TOO_SHORT" if mode == "cutoff" else "HEAD_DIRECT_WINDOW_CLOSED"
            )
            with pytest.raises(SnapshotError, match=code):
                send("plan", plan_fixture)
            assert (tmp_path / "STOP").exists()
            assert not (tmp_path / "plan.binding.json").exists()
            assert len(sent) == (1 if mode == "late" else 0)
            if mode == "late":
                assert entry.raw_io.decrypt(tmp_path / "plan.raw.enc", cipher) == received[0]
            return
        send("plan", plan_fixture)
        with pytest.raises(SnapshotError, match="HEAD_EXACT_AUTHORIZATION_REQUIRED"):
            entry.approval_check(
                tmp_path, {**approval, "starts_epoch": start + 1, "expires_epoch": start + 601}
            )
        plan = entry.verify_saved(tmp_path, "plan", cipher)["plan"]
        payload = materials.content_payload(context["planning_inputs"], plan)
        entry.raw_io.exclusive(
            tmp_path / "plan-review.json",
            canonical(
                dict(
                    plan_digest=digest("head-plan", plan=plan),
                    verdict="pass",
                    independent_evaluator="offline_fixture",
                    planning_basis_binding=payload["planning_basis"]["binding"],
                )
            ),
        )
        raw = fixture.content(payload)
        raw["paragraphs"][1]["fact_ids"] = [DISCARDED]
        raw["paragraphs"][0]["fact_ids"] = [DISPLAYED]
        if mode == "protocol_stop":
            bad = fixture.envelope(raw, phase="analysis")
            with pytest.raises(entry.raw_io.wire.PilotError, match="WIRE_MESSAGE_PHASE"):
                send("generate", bad)
            assert entry.raw_io.decrypt(tmp_path / "generate.raw.enc", cipher) == received[-1]
            assert (tmp_path / "STOP").exists()
            assert entry.read(tmp_path / "generate.failure.json")["code"] == "WIRE_MESSAGE_PHASE"
            with pytest.raises(SnapshotError, match="HEAD_VAULT_STOPPED_OR_UNSAFE"):
                send("generate", fixture.envelope(raw))
            assert len(sent) == 2
            return
        send("generate", duplicate_envelope(raw) if mode == "recovered" else fixture.envelope(raw))
        first = entry.verify_saved(tmp_path, "generate", cipher)
        c = first["candidate"]
        assert (
            json.loads(sent[1]["input"][1]["content"])["teaching_evidence"]
            == payload["teaching_evidence"]
        )
        if mode == "revised":
            review = replacement_review(c)
            entry.raw_io.exclusive(tmp_path / "repair-review.json", canonical(review))
            send("repair", fixture.envelope(replacements()))
            c = entry.verify_saved(tmp_path, "repair", cipher)["candidate"]
            assert set(sent[2]["text"]["format"]["schema"]["properties"]) == set(replacements())
            assert c["parent_digest"] == first["candidate"]["candidate_digest"]
        entry.raw_io.exclusive(tmp_path / "final-review.json", canonical(fixed_review(c)))
        binding = entry.publish_saved(tmp_path, approval)
        assert binding["version"] == 2 and (tmp_path / "STOP").exists()
        assert not (tmp_path / "ACTIVE").exists()
        assert len(sent) == (3 if mode == "revised" else 2)
        route = f"/api/free-courses/{cid}/versions/2/scenes/{binding['scene_id']}"
        scene = client.get(route)
        assert scene.status_code == 200, scene.text
        assert "answer_key" not in scene.text and "solution" not in scene.text
        view = scene.json()
        source = view["generation_source"]
        assert source["batch"] == approval["batch"] and source["evidence_kind"] == "offline_fixture"
        assert source["teaching_evidence_digest"] == payload["teaching_evidence"]["evidence_digest"]
        assert source["candidate_digest"] == c["candidate_digest"]
        if mode == "recovered":
            assert source["format_recovery"]["model_first_structure_pass"] is False
            assert source["format_recovery"]["source_batch"] == approval["batch"]
        program = payload["materials"]
        code = next(b for b in view["blocks"] if b["kind"] == "code")
        assert code["source"] == program["catalog"]["example"]["code"]["source"]
        replay = next(b for b in view["blocks"] if b["kind"] == "visualization")
        assert [s["head_frame"]["line"] for s in replay["steps"]] == [
            None,
            4,
            5,
            6,
            7,
            8,
            15,
            4,
            5,
            6,
            7,
            8,
            16,
        ]
        assert replay["text_alternative"] == c["raw_output"]["learning_summary"]
        assert view["blocks"][-4]["markdown"] == c["raw_output"]["failure_scope"]
        op = client.get(f"/api/free-courses/{cid}/operations/{oid}").json()
        assert op["execution_mode"] == "finite_head_foreground" and op["budget"] is None
        exercise = view["blocks"][-1]
        result = client.post(
            f"/api/free-courses/{cid}/attempts",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json=dict(
                course_version=2,
                scene_id=binding["scene_id"],
                scene_version_id=view["scene_version_id"],
                exercise_id=exercise["exercise_id"],
                exercise_version_id=exercise["exercise_version_id"],
                answers=[dict(question_id=k, answer=v) for k, v in program["answers"].items()],
            ),
        )
        assert result.status_code == 201, result.text
        reply = client.get(f"/api/free-courses/{cid}/attempts/{result.json()['attempt_id']}").json()
        assert reply["comparison_score"] == 1 and reply["mastery_effect"] == "course_only"
        assert len(reply["question_results"]) == 4
        assert client.get(route).json() == view
