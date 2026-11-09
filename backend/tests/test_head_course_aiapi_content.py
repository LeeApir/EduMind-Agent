"""Targeted AIAPI batch checks. All HTTP Provider traffic uses MockTransport."""

import asyncio
import os
from copy import deepcopy
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.main import app
from app.services import head_course_aiapi_content as batch
from app.services import head_course_reuse as reuse
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import head_course_aiapi_content as runner
from scripts import head_course_goal_fixture as fixture


@pytest.fixture(scope="module")
def source():
    return batch.source()


def envelope(source, *, missing_lf=True, omit_unique=True):
    payload, request = source
    value = fixture.content(payload)
    for key, question in value["questions"].items():
        variant = "discarded" if key in ("discarded_values", "unreachable_count") else "normal"
        code = payload["materials"]["transfer"][variant]["code"]["source"]
        question["stem"] = "请推导这个情境。\n" + (code[:-1] if missing_lf else code)
    text = canonical(value).decode()
    echo = deepcopy(request["text"])
    if omit_unique:
        del echo["format"]["schema"]["properties"]["paragraphs"]["items"]["properties"]["fact_ids"][
            "uniqueItems"
        ]
    body = dict(
        object="response",
        status="completed",
        text=echo,
        output=[
            dict(
                type="message",
                role="assistant",
                status="completed",
                phase="final_answer",
                content=[dict(type="output_text", text=text)],
            )
        ],
        output_text=text,
        usage=dict(
            input_tokens=9772,
            output_tokens=6659,
            total_tokens=16431,
            output_tokens_details=dict(reasoning_tokens=303),
        ),
    )
    return body, value


@pytest.mark.parametrize("missing_lf,omit_unique", [(True, True), (False, False)])
def test_compatible_response_preserves_original(source, missing_lf, omit_unique):
    body, value = envelope(source, missing_lf=missing_lf, omit_unique=omit_unique)
    if not omit_unique:
        body.update(
            max_output_tokens=None, reasoning=dict(effort="low", mode="standard", summary=None)
        )
        body["output"][0].pop("phase")
    raw = canonical(body)
    payload, request = source
    result = batch.record(payload, request, raw, "offline_fixture")
    assert result["raw_response"].encode() == raw
    assert result["candidate"]["raw_output"] == value
    assert result["candidate"]["recovery"] is None
    assert result["usage"]["reasoning_tokens"] == 303
    assert result["observation"]["requested"]["store"] is False
    assert "model" not in result["observation"]["reported"]
    assert ("max_output_tokens" in result["observation"]["reported"]) is not omit_unique


@pytest.mark.parametrize(
    "change,code",
    [
        ({"model": "different"}, "HEAD_AIAPI_PARAMETER_CONFLICT"),
        ({"store": 0}, "HEAD_AIAPI_PARAMETER_CONFLICT"),
        ({"store": True}, "HEAD_AIAPI_PARAMETER_CONFLICT"),
        ({"temperature": 1.0}, "HEAD_AIAPI_PARAMETER_CONFLICT"),
        ({"max_output_tokens": 9000}, "HEAD_AIAPI_PARAMETER_CONFLICT"),
        ({"reasoning": {"effort": "none"}}, "HEAD_AIAPI_REASONING_CONFLICT"),
        ({"instructions": "additional instructions"}, "HEAD_AIAPI_INSTRUCTIONS"),
        ({"tools": [{"type": "web_search"}]}, "HEAD_AIAPI_ENVELOPE"),
        ({"tool_usage": 1}, "HEAD_AIAPI_ENVELOPE"),
        ({"background": True}, "HEAD_AIAPI_ENVELOPE"),
        ({"previous_response_id": "prior"}, "HEAD_AIAPI_ENVELOPE"),
        ({"output_text": "conflicting copy"}, "HEAD_AIAPI_OUTPUT"),
        ({"output": [{"type": "reasoning"}]}, "HEAD_AIAPI_OUTPUT"),
        ({"output": [{"content": [{"type": "refusal"}]}]}, "HEAD_AIAPI_REFUSAL"),
        (
            {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
            "HEAD_AIAPI_TRUNCATED",
        ),
        ({"status": "incomplete"}, "HEAD_AIAPI_INCOMPLETE"),
        ({"status": "failed", "error": {"code": "unknown"}}, "HEAD_AIAPI_SERVICE_ERROR"),
    ],
)
def test_conflict_and_abnormal_output(source, change, code):
    body, _ = envelope(source)
    with pytest.raises(SnapshotError, match=code):
        batch.observe(source[1], canonical({**body, **change}))


def test_complete_original_schema_and_usage(source):
    body, output = envelope(source)
    body["text"]["format"]["schema"]["properties"]["paragraphs"].pop("minItems")
    with pytest.raises(SnapshotError, match="HEAD_AIAPI_SCHEMA_ECHO"):
        batch.observe(source[1], canonical(body))
    body, output = envelope(source)
    output["paragraphs"][0]["fact_ids"] *= 2
    body["output_text"] = body["output"][0]["content"][0]["text"] = canonical(output).decode()
    with pytest.raises(batch.wire.PilotError, match="ROLE_SCHEMA"):
        batch.observe(source[1], canonical(body))
    body, _ = envelope(source)
    for outgoing, code in ((8000, "HEAD_AIAPI_OUTPUT_CAP_SUSPECTED"), (8001, "HEAD_AIAPI_USAGE")):
        body["usage"].update(output_tokens=outgoing, total_tokens=9772 + outgoing)
        with pytest.raises(SnapshotError, match=code):
            batch.observe(source[1], canonical(body))


def test_historical_operation_and_plan_cannot_be_rebound(source):
    payload, _ = source
    historical = batch.wire.strict_json(
        (batch.archive.ACCEPTANCE / "phase-1.5-head-fixed-live-r01/context.json").read_bytes()
    )["planning_inputs"]
    with pytest.raises(SnapshotError, match="HEAD_AIAPI_PLAN_BINDING"):
        batch.bound_payload(historical, payload["plan"], payload)
    new = {**historical, **{key: str(uuid4()) for key in payload["source_binding"]}}
    new["request_sources"]["request_1"]["request_id"] = new["request_id"]
    assert batch.bound_payload(new, payload["plan"], payload)["plan"] == payload["plan"]
    with pytest.raises(SnapshotError, match="HEAD_AIAPI_PLAN_BINDING"):
        batch.bound_payload(new, {**payload["plan"], "title": "changed"}, payload)


def independent_review(candidate, binding):
    return dict(
        verdict="pass",
        candidate_digest=candidate["candidate_digest"],
        parent_digest=None,
        independent_evaluator="offline_fixture",
        aiapi_binding=binding,
        planning_basis_binding=candidate["payload"]["planning_basis"]["binding"],
        evidence_digest=candidate["payload"]["teaching_evidence"]["evidence_digest"],
        blocking_findings=[],
        checks=dict.fromkeys(
            (
                "full_lesson",
                "fact_citations",
                "paragraph_responsibilities",
                "no_neighbour_copy",
                "no_omitted_explanation",
                "code_trace_answers",
                "no_answer_hints",
                *reuse.FIXED_REVIEW_CHECKS,
            ),
            True,
        ),
    )


class Interrupted(httpx.SyncByteStream):
    def __iter__(self):
        yield b'{"partial":'
        raise httpx.ReadTimeout("fixture timeout")


@pytest.mark.parametrize("mode", ["pass", "deadline", "partial", "conflict", "spent"])
def test_entry_and_private_course(tmp_path, monkeypatch, source, mode):
    url = os.getenv("EDUMIND_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("dedicated AIAPI test database not configured")
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *args, **kwargs: pytest.fail("Provider forbidden"),
    )
    with TestClient(app, base_url="https://testserver") as api:
        auth = api.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        context = asyncio.run(runner.database(lambda db: runner.prepare_operation(db, owner)))
        assert context["planning_inputs"]["course_id"] != source[0]["source_binding"]["course_id"]
        vault = tmp_path / "vault"
        vault.mkdir(mode=0o700)
        runner.raw_io.exclusive(vault / "raw.key", Fernet.generate_key())
        runner.save(vault, "context.json", context)
        calls = []
        body, value = envelope(source)
        if mode == "conflict":
            body["temperature"] = 1.0
        raw = canonical(body)

        def handler(req):
            calls.append(req)
            assert req.content == (batch.PACKAGE / "request.json").read_bytes()
            assert req.headers["host"] == "aiapi.world" and req.url.path == "/v1/responses"
            return httpx.Response(
                200, stream=Interrupted() if mode == "partial" else httpx.ByteStream(raw)
            )

        mock = httpx.MockTransport(handler)
        with pytest.raises(SnapshotError, match="HEAD_AIAPI_APPROVAL_REQUIRED"):
            runner.send(vault, transport=mock, key="fixture-only")
        assert not calls
        runner.save(
            vault,
            "approval.json",
            dict(
                **runner.approval_fields(vault),
                explicit_user_authorization=True,
                accept_batch_C2=True,
            ),
        )
        if mode == "spent":
            runner.save(vault, "draft.attempt.json", {"state": "attempted_unknown"})
            with pytest.raises(SnapshotError, match="HEAD_AIAPI_ALREADY_STOPPED"):
                runner.send(vault, transport=mock, key="fixture-only")
            assert not calls
            return
        if mode == "deadline":
            deadline = runner.datetime.fromisoformat(context["execution_window"]["expires_at"])
            monkeypatch.setattr(runner, "now", lambda: deadline - timedelta(seconds=299))
            with pytest.raises(SnapshotError, match="HEAD_AIAPI_DEADLINE"):
                runner.send(vault, transport=mock, key="fixture-only")
            assert not calls and not (vault / "draft.attempt.json").exists()
        elif mode == "partial":
            with pytest.raises(httpx.ReadTimeout):
                runner.send(vault, transport=mock, key="fixture-only")
            failure = runner.read(vault / "failure.json")
            assert failure["body_complete"] is False
            assert failure["response_bytes_received"] == len(b'{"partial":')
        elif mode == "conflict":
            with pytest.raises(SnapshotError, match="HEAD_AIAPI_PARAMETER_CONFLICT"):
                runner.send(vault, transport=mock, key="fixture-only")
            assert runner.read(vault / "failure.json")["body_complete"] is True
        else:
            rec = runner.send(vault, transport=mock, key="fixture-only")
            assert rec["raw_response"].encode() == raw and rec["evidence_kind"] == "offline_fixture"
            chain, binding = runner.review_input(vault)
            review = independent_review(rec["candidate"], binding)
            for changed in (
                {**review, "candidate_digest": "0" * 64},
                {**review, "aiapi_binding": {**binding, "raw_response_sha256": "0" * 64}},
            ):
                with pytest.raises(SnapshotError):
                    asyncio.run(
                        runner.database(
                            lambda db: reuse.publish(
                                db, *runner.ids(context), dict(**chain, final_review=changed)
                            )
                        )
                    )
            path = tmp_path / "review.json"
            path.write_bytes(canonical(review))
            deadline = runner.datetime.fromisoformat(context["execution_window"]["expires_at"])
            with monkeypatch.context() as clock:
                clock.setattr(runner, "now", lambda: deadline)
                with pytest.raises(SnapshotError, match="HEAD_AIAPI_DEADLINE"):
                    runner.publish(vault, path)
            saved = runner.publish(vault, path)
            cid = saved["course_id"]
            route = f"/api/free-courses/{cid}/versions/2/scenes/{saved['scene_id']}"
            result = api.get(route)
            assert result.status_code == 200, result.text
            view = result.json()
            assert view["generation_source"]["batch"] == batch.BATCH
            assert view["generation_source"]["evidence_kind"] == "offline_fixture"
            assert "model" in view["generation_source"]["unknown_echoes"]
            exercise = view["blocks"][-1]
            assert (
                exercise["items"][0]["question"]
                == value["questions"][batch.materials.QKEYS[0]]["stem"]
            )
            assert "answer_key" not in result.text and "solution" not in result.text
            attempt = api.post(
                f"/api/free-courses/{cid}/attempts",
                headers={"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())},
                json=dict(
                    course_version=2,
                    scene_id=saved["scene_id"],
                    scene_version_id=view["scene_version_id"],
                    exercise_id=exercise["exercise_id"],
                    exercise_version_id=exercise["exercise_version_id"],
                    answers=[
                        dict(question_id=k, answer=v)
                        for k, v in source[0]["materials"]["answers"].items()
                    ],
                ),
            )
            assert attempt.status_code == 201, attempt.text
            assert (
                api.get(f"/api/free-courses/{cid}/attempts/{attempt.json()['attempt_id']}").json()[
                    "comparison_score"
                ]
                == 1
            )
            assert api.get(route).json() == view
        assert (vault / "STOP").exists()
        with pytest.raises(SnapshotError, match="HEAD_AIAPI_ALREADY_STOPPED"):
            runner.send(vault, transport=mock, key="fixture-only")
        assert len(calls) == (0 if mode == "deadline" else 1)
