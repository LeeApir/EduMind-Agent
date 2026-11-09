"""T118 independent C/material expectations and zero-outbound application smoke."""

import asyncio
import json
import os
import subprocess
from copy import deepcopy
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from jsonschema.exceptions import ValidationError
from test_head_course_fixed import fixed_review, with_direct_echo
from test_head_course_reuse import duplicate_envelope

from app.agents import head_course_planning_wire as wire
from app.main import app
from app.services import head_course_materials as m
from app.services import head_course_reuse as reuse
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.head_course_teaching_evidence import DISCARDED, DISPLAYED
from scripts import head_course_deepseek_wire as direct
from scripts import head_course_goal as entry
from scripts import head_course_goal_fixture as fixture
from scripts import prepare_head_course_empty as package


def empty_payload():
    return m.content_payload(package.inputs(), empty_wire_plan()["plans"][0])


def empty_wire_plan():
    value = fixture.wire_plan(m.EMPTY_EXAMPLE)
    for objective, excerpt in zip(
        value["plans"][0]["objectives"],
        ["首次插入如何形成链表", "调用者接收、忽略返回值的区别"],
        strict=True,
    ):
        objective["source_excerpt"] = excerpt
        objective["description"] = excerpt
    return value


def empty_text(payload):
    raw = fixture.content(payload)
    for i, k in enumerate(m.QKEYS):
        raw["questions"][k]["stem"] = f"离线夹具：假定两次分配成功，情境题 {i + 1}。"
    raw["paragraphs"][0]["fact_ids"] = ["trace_step_03", "trace_step_08"]
    raw["paragraphs"][1]["fact_ids"] = [DISCARDED]
    raw["paragraphs"][2]["fact_ids"] = [DISPLAYED]
    return raw


def test_independent_materials_and_c():
    ref = entry.read(package.HERE / "independent-reference.json")
    p = empty_payload()
    mat = p["materials"]
    main = mat["catalog"]["example"]
    assert main["spec"]["initial_values"] == ref["initial"]
    assert main["spec"]["insert_values"] == ref["insertions"]
    assert main["spec"]["allocation_success"] == [True, True]
    for e in mat["transfer"].values():
        assert e["spec"]["initial_values"] == ref["transfer"]["initial"]
        assert e["spec"]["insert_values"] == ref["transfer"]["insertions"]
        assert e["spec"]["allocation_success"] == [True, True]
    assert mat["answers"] == ref["transfer"]["answers"]
    basis = p["planning_basis"]["evidence"]
    assert [s["name"] for s in basis["variable_scopes"]] == [
        "head",
        "value",
        "allocation_success",
        "p",
        "caller_head",
    ]
    assert (
        basis["function_interface"] == "Node *insert(Node *head, int value, int allocation_success)"
    )
    facts = p["teaching_evidence"]["facts"]
    assert [c["frame_id"] for c in facts[DISPLAYED]["value"]["null_condition_evaluations"]] == [
        "f02",
        "f08",
    ]
    assert all(
        c["condition_evaluated"] and not c["condition_result"] and not c["early_return_taken"]
        for c in facts[DISPLAYED]["value"]["null_condition_evaluations"]
    )
    assert facts[DISPLAYED]["value"]["allocation_success_count"] == 2
    assert facts[DISPLAYED]["value"]["no_allocation_frame_ids"] == []
    assert facts[DISCARDED]["displayed_in_main_player"] is False
    assert main["code"]["source"].splitlines()[10:13] == [
        "    Node *caller_head = NULL;",
        "    caller_head = insert(caller_head, 4, 1);",
        "    caller_head = insert(caller_head, 7, 1);",
    ]
    for variant, spec_key in (
        ("receive_return", "receive_return"),
        ("ignore_return", "discard_return"),
    ):
        actual, expected = basis[variant], ref[spec_key]
        assert actual["observation"]["caller_head"] == expected["caller_head"]
        assert actual["observation"]["reachable_prefix"] == expected["reachable"]
        assert actual["observation"]["unreachable_allocated_ids"] == expected["unreachable"]
        assert actual["observation"]["traversal_status"] == "terminated"
        assert {row["p"]: row["p_next"] for row in actual["calls"]} == expected["next"]
    for source in (
        main["code"]["source"],
        facts[DISCARDED]["source_code"],
        m.scenario_code(mat, "normal_values"),
        m.scenario_code(mat, "discarded_values"),
    ):
        # Compile only program-owned material. Never run provider text as code.
        subprocess.run(
            ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", "-x", "c", "-"],
            input=source,
            text=True,
            check=True,
        )
    assembled = m.assemble(p, empty_text(p), {})
    rows = [s["head_frame"] for s in assembled["blocks"][-5]["steps"]]
    assert [r["frame_id"] for r in rows] == [f"f{i:02}" for i in range(13)]
    assert [
        [
            r["line"],
            r["kind"],
            s["caller_head"],
            s["local_head"],
            s["p"],
            s["returned"],
            {k: [v["data"], v["next"]] for k, v in s["nodes"].items()},
            r["locals_scope"],
        ]
        for r in rows
        for s in (r["state"],)
    ] == ref["frames"]


def test_exact_new_requests_and_closed_content():
    inputs = package.inputs()
    plan = empty_wire_plan()
    local = wire.to_local(plan, inputs)
    with pytest.raises(SnapshotError, match="SCHEMA_INVALID"):
        wire.to_local(fixture.wire_plan(m.FIXED_EXAMPLE), inputs)
    p = m.content_payload(inputs, local["plan"])
    request = entry.planning_body(inputs)
    assert set(
        json.loads(request["input"][1]["content"])["planning_example_basis"]["examples"]
    ) == {m.EMPTY_EXAMPLE}
    assert "this nonempty example" not in request["input"][0]["content"]
    body = m.body(p)
    assert "Each stem is one line of Chinese prose only" in body["input"][0]["content"]
    assert "Initial i nodes" not in body["input"][0]["content"]
    assert "Prerequisites are unknown." in body["input"][0]["content"]
    assert p["prerequisite_evidence"]["self_reported"] == []
    assert json.loads(body["input"][1]["content"]) == p
    raw = empty_text(p)
    assembly = m.assemble(p, raw, {})
    for q in assembly["blocks"][-1]["items"]:
        k = q["question_id"]
        assert q["question"] == raw["questions"][k]["stem"] + "\n\n" + m.scenario_code(
            p["materials"], k
        )
        assert q["answer_key"] == p["materials"]["answers"][k]
    bad = deepcopy(raw)
    bad["questions"]["link_target"]["stem"] += "\n" + m.scenario_code(p["materials"], "link_target")
    with pytest.raises(SnapshotError, match="HEAD_QUESTION_PROSE_REQUIRED"):
        m.validate_content(p, bad)
    bad = deepcopy(raw)
    bad["paragraphs"][0]["fact_ids"] *= 2
    with pytest.raises(ValidationError):
        m.validate_content(p, bad)
    bad["paragraphs"][0]["fact_ids"] = ["not_a_fact"]
    with pytest.raises(SnapshotError, match="HEAD_FACT_REFERENCE"):
        m.validate_content(p, bad)
    with pytest.raises(SnapshotError, match="HEAD_EMPTY_REVISION_FORBIDDEN"):
        m.body(p, raw, [])


@pytest.mark.parametrize("mode", ["ready", "duplicate_stop"])
def test_actual_empty_entry_and_private_application(monkeypatch, tmp_path, mode):
    assert direct.EMPTY_DATABASE in os.environ["EDUMIND_TEST_DATABASE_URL"]
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_HEAD_GOAL_DEVELOPMENT", "1")
    monkeypatch.setenv("EDUMIND_HEAD_DEEPSEEK_DEVELOPMENT", "1")
    monkeypatch.setattr(entry, "PACKAGE", entry.EMPTY_PACKAGE)
    monkeypatch.setattr(entry, "EMPTY_VAULT", tmp_path)
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        headers = {"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())}
        result = client.post("/api/free-courses", json={"goal": m.EMPTY_GOAL}, headers=headers)
        assert result.status_code == 201, result.text
        cid, oid = (UUID(result.json()[k]) for k in ("course_id", "operation_id"))
        context = asyncio.run(entry.prepare(UUID(auth["user"]["id"]), cid, oid))
        context_raw = canonical(context)
        prepared = entry.planning_body(context["planning_inputs"])
        for name, data in {
            "context.json": context_raw,
            "plan.prepared-request.json": canonical(prepared),
            "raw.key": Fernet.generate_key(),
        }.items():
            entry.raw_io.exclusive(tmp_path / name, data)
        cipher = Fernet((tmp_path / "raw.key").read_bytes())
        approval = dict(
            package_sha256=entry.package_digest(),
            version=m.FIXED_VERSION,
            batch=direct.EMPTY_BATCH,
            context_sha256=reuse.sha(context_raw),
            explicit_user_authorization=True,
            accept_T118_and_batch_C2=True,
            max_http_requests=2,
            execution_window=context["execution_window"],
            planning_wire_version=wire.VERSION,
            planning_prompt_version=wire.PROMPT_VERSION,
        )
        sent, received = [], []

        def send(stage, raw):
            def transport(req):
                assert req.headers["Host"] == "api.deepseek.com" and req.url.path == "/responses"
                sent.append(json.loads(req.content))
                received.append(with_direct_echo(sent[-1], raw))
                return httpx.Response(200, stream=httpx.ByteStream(received[-1]))

            entry.send(
                stage,
                tmp_path,
                approval,
                transport=httpx.MockTransport(transport),
                key="offline-fixture",
            )

        with pytest.raises(SnapshotError, match="HEAD_EXACT_AUTHORIZATION_REQUIRED"):
            entry.approval_check(tmp_path, {**approval, "max_http_requests": 3})
        with pytest.raises(SnapshotError, match="HEAD_REQUEST_CHANGED"):
            entry.verify_empty_request(
                "plan", {**prepared, "temperature": 0.3}, context["planning_inputs"]
            )
        status = client.get(f"/api/free-courses/{cid}/operations/{oid}").json()
        assert status["execution_mode"] == "finite_head_foreground" and status["budget"] is None
        send("plan", fixture.envelope(empty_wire_plan()))
        assert sent == [prepared]
        plan = entry.verify_saved(tmp_path, "plan", cipher)["plan"]
        payload = m.content_payload(context["planning_inputs"], plan)
        p_review = dict(
            plan_digest=digest("head-plan", plan=plan),
            verdict="pass",
            independent_evaluator="offline_fixture",
            planning_basis_binding=payload["planning_basis"]["binding"],
            blocking_findings=[],
        )
        with pytest.raises(SnapshotError, match="REUSE_PLAN_REVIEW"):
            reuse.validate_plan_review(p_review, payload)
        p_review["checks"] = dict(
            empty_goal_and_sequence=True, same_example_and_caller_comparison=True
        )
        entry.raw_io.exclusive(tmp_path / "plan-review.json", canonical(p_review))
        raw = empty_text(payload)
        if mode == "duplicate_stop":
            with pytest.raises(direct.wire.PilotError, match="DUPLICATE_JSON_KEY"):
                send("generate", duplicate_envelope(raw))
            assert entry.raw_io.decrypt(tmp_path / "generate.raw.enc", cipher) == received[-1]
            assert entry.read(tmp_path / "generate.failure.json")["code"] == "DUPLICATE_JSON_KEY"
            assert not (tmp_path / "generate.record.json").exists()
            with pytest.raises(SnapshotError, match="HEAD_VAULT_STOPPED_OR_UNSAFE"):
                send("generate", fixture.envelope(raw))
            assert len(sent) == 2 and (tmp_path / "STOP").exists()
            closed = client.post(
                f"/api/free-courses/{cid}/operations/{oid}/cancel",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={},
            )
            assert closed.status_code == 200 and closed.json()["state"] == "cancel_requested"
            assert closed.json()["head_version"] == 1
            with pytest.raises(SnapshotError, match="HEAD_OPERATION_STOPPED"):
                asyncio.run(entry.prepare(UUID(auth["user"]["id"]), cid, oid))
            return

        send("generate", fixture.envelope(raw))
        assert sent == [prepared, m.body(payload)]
        c = entry.verify_saved(tmp_path, "generate", cipher)["candidate"]
        assert c["raw_output"] == raw and c["recovery"] is None and c["parent_digest"] is None
        review = fixed_review(c)
        with pytest.raises(SnapshotError, match="REUSE_FULL_REVIEW_REQUIRED"):
            reuse.require_full_review(review, c)
        review["checks"].update(
            empty_first_and_second_links=True,
            question_conditions_and_unique_answers=True,
        )
        entry.raw_io.exclusive(tmp_path / "final-review.json", canonical(review))
        result = entry.publish_saved(tmp_path, approval)
        assert result["version"] == 2 and (tmp_path / "STOP").exists()
        route = f"/api/free-courses/{cid}/versions/2/scenes/{result['scene_id']}"
        scene = client.get(route)
        assert scene.status_code == 200, scene.text
        assert "answer_key" not in scene.text and "solution" not in scene.text
        view = scene.json()
        assert view["generation_source"]["batch"] == direct.EMPTY_BATCH
        assert view["generation_source"]["evidence_kind"] == "offline_fixture"
        assert view["generation_source"]["candidate_digest"] == c["candidate_digest"]
        assert view["generation_source"]["teaching_evidence_digest"] == review["evidence_digest"]
        exercise = view["blocks"][-1]
        for item in exercise["items"]:
            k = item["question_id"]
            assert item["question"] == raw["questions"][k]["stem"] + "\n\n" + m.scenario_code(
                payload["materials"], k
            )
        for score, answers in (
            (0, dict(zip(m.QKEYS, ["t0", "[]", "[8]", "1"], strict=True))),
            (1, payload["materials"]["answers"]),
        ):
            attempt = client.post(
                f"/api/free-courses/{cid}/attempts",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json=dict(
                    course_version=2,
                    scene_id=result["scene_id"],
                    scene_version_id=view["scene_version_id"],
                    exercise_id=exercise["exercise_id"],
                    exercise_version_id=exercise["exercise_version_id"],
                    answers=[dict(question_id=k, answer=v) for k, v in answers.items()],
                ),
            )
            assert attempt.status_code == 201, attempt.text
            reply = client.get(
                f"/api/free-courses/{cid}/attempts/{attempt.json()['attempt_id']}"
            ).json()
            assert reply["comparison_score"] == score
            assert len(reply["question_results"]) == 4
            assert all(q["matches_reference"] == bool(score) for q in reply["question_results"])
        assert client.get(route).json() == view
