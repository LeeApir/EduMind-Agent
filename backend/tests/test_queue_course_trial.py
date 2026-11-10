"""Fixed queue reference, shared foreground admission and answer isolation."""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo

from app.main import app
from app.services import queue_course_materials as queue
from app.services.course_trial_publication import QUEUE
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as generation
from scripts import head_course_goal_fixture as fixtures

PACKAGE = generation.package_path(QUEUE)


def reference():
    return generation.read(PACKAGE / "independent-reference.json")


def test_fifo_materials_and_c_against_independent_reference(tmp_path: Path):
    mat = queue.materials()
    ref = reference()
    assert mat["main"]["frames"] == ref["frames"]
    assert {
        key: item["private_answer"] for key, item in mat["transfer"]["questions"].items()
    } == ref["transfer"]
    lines = mat["main"]["source"].splitlines()
    for frame in reversed(ref["frames"]):
        assertions = [f"    assert(q.count == {len(frame['values'])});"]
        assertions.extend(
            f"    assert(q.data[{i}] == {value});" for i, value in enumerate(frame["values"])
        )
        if frame["dequeued"] is not None:
            assertions.append(f"    assert(value == {frame['dequeued']});")
        lines[frame["line"] : frame["line"]] = assertions
    source = "#include <assert.h>\n" + "\n".join(lines) + "\n"
    source = source.replace("int main(void)", "static int example(void)")
    source += """
int main(void) {
    assert(example() == 0);
    Queue q = {{0}, 0};
    int value = 99;
    assert(!dequeue(&q, &value) && value == 99 && q.count == 0);
    assert(enqueue(&q, -4) && enqueue(&q, 6) && enqueue(&q, 2));
    assert(!enqueue(&q, 1) && q.count == 3);
    assert(q.data[0] == -4 && q.data[1] == 6 && q.data[2] == 2);
    assert(dequeue(&q, &value) && value == -4 && q.count == 2);
    assert(q.data[0] == 6 && q.data[1] == 2 && enqueue(&q, 9));
    assert(q.count == 3 && q.data[2] == 9);
    assert(dequeue(&q, &value) && value == 6);
    assert(dequeue(&q, &value) && value == 2 && q.count == 1 && q.data[0] == 9);
    assert(dequeue(&q, &value) && value == 9);
    assert(!dequeue(&q, &value) && value == 9 && q.count == 0);
}
"""
    path = tmp_path / "test.c"
    binary = tmp_path / "test"
    path.write_text(source)
    subprocess.run(
        ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def teaching():
    return dict(
        paragraphs=[
            dict(text="离线测试讲解", fact_ids=[fact])
            for fact in ("order", "enqueue", "dequeue", "fifo")
        ],
        step_notes=[dict(frame_id=f"f{i}", note=f"离线帧 {i}") for i in range(5)],
        questions={
            key: dict(stem=f"根据下方代码填写{target}。", explanation="离线测试解析")
            for key, (target, _) in queue.QUESTIONS.items()
        },
        summary="离线测试总结",
    )


def test_mechanical_validation_rejects_non_queue_fact_and_wrong_frame():
    raw = teaching()
    raw["paragraphs"][0]["fact_ids"] = ["lifo"]
    with pytest.raises(SnapshotError, match="QUEUE_FACT_REFERENCE"):
        queue.validate_content(raw, queue.materials())
    raw = teaching()
    raw["step_notes"].reverse()
    with pytest.raises(SnapshotError, match="QUEUE_FRAME_BINDING"):
        queue.validate_content(raw, queue.materials())


@pytest.mark.parametrize("wrong_phase", [False, True])
def test_shared_queue_flow(monkeypatch, tmp_path, wrong_phase):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    with (
        TestClient(app, base_url="https://testserver") as client,
        TestClient(app, base_url="https://testserver") as other,
    ):
        auth = client.post("/api/auth/guest").json()
        other.post("/api/auth/guest")
        owner = UUID(auth["user"]["id"])
        vault = tmp_path / "vault"
        approval = generation.approval_values(QUEUE)
        with pytest.raises(SnapshotError, match="QUEUE_EXACT_AUTHORIZATION_REQUIRED"):
            asyncio.run(
                generation.prepare(
                    vault,
                    owner,
                    dict(approval, batch="stack-lifo-deepseek-r01"),
                    fixture=True,
                    profile=QUEUE,
                )
            )
        assert not vault.exists()
        context = asyncio.run(
            generation.prepare(vault, owner, approval, fixture=True, profile=QUEUE)
        )
        cid, oid, sid = (context[key] for key in ("course_id", "operation_id", "scene_id"))
        route = f"/api/free-courses/{cid}"
        operation = client.get(f"{route}/operations/{oid}").json()
        assert (
            operation["execution_mode"] == "finite_queue_foreground" and operation["budget"] is None
        )

        reply = json.loads(with_direct_echo(queue.request(), fixtures.envelope(teaching())))
        reply["output"][0]["phase"] = "invalid" if wrong_phase else "final_answer"
        original = canonical(reply)
        calls = []

        def handle(request):
            calls.append(request.content)
            assert request.content == (PACKAGE / "request.json").read_bytes()
            return httpx.Response(200, stream=httpx.ByteStream(original))

        mock = httpx.MockTransport(handle)
        kwargs = dict(transport=mock, key="offline-fixture-key", profile=QUEUE)
        if wrong_phase:
            with pytest.raises(ValueError, match="WIRE_MESSAGE_PHASE"):
                generation.send(vault, **kwargs)
            assert generation.read(vault / "generate.failure.json")["code"] == "WIRE_MESSAGE_PHASE"
            assert not (vault / "generate.candidate.json").exists()
            assert client.get(route).json()["head"]["version"] == 1
        else:
            candidate = generation.send(vault, **kwargs)
            assert generation.replay(vault, fixture=True, profile=QUEUE) == candidate
            review = dict(
                candidate_digest=candidate["candidate_digest"],
                verdict="pass",
                independent_evaluator="fixture-only",
                blocking_findings=[],
                checks=dict.fromkeys(QUEUE.checks, True),
            )
            review_path = vault / "review.json"
            review_path.write_bytes(canonical(dict(review, candidate_digest="0" * 64)))
            with pytest.raises(SnapshotError, match="QUEUE_REVIEW_REQUIRED"):
                generation.publish(vault, fixture=True, profile=QUEUE)
            assert client.get(route).json()["head"]["version"] == 1
            review_path.write_bytes(canonical(review))
            published = generation.publish(vault, fixture=True, profile=QUEUE)
            scene_route = f"{route}/versions/2/scenes/{sid}"
            result = client.get(scene_route)
            assert result.status_code == 200, result.text
            view = result.json()
            assert view["generation_source"]["origin"] == queue.ORIGIN
            assert view["generation_source"]["evidence_kind"] == "offline_fixture"
            assert '"answer_key"' not in result.text and '"solution"' not in result.text
            assert other.get(scene_route).status_code == 404
            visual = next(block for block in view["blocks"] if block["kind"] == "visualization")
            assert [step["queue_frame"]["dequeued"] for step in visual["steps"]] == [
                None,
                None,
                None,
                3,
                None,
            ]
            assert [[int(e["label"]) for e in step["elements"]] for step in visual["steps"]] == [
                frame["values"] for frame in reference()["frames"]
            ]
            exercise = view["blocks"][-1]
            for answers, score in (
                (dict.fromkeys(queue.QUESTIONS, 999), 0),
                (reference()["transfer"], 1),
            ):
                posted = client.post(
                    f"{route}/attempts",
                    json=dict(
                        course_version=2,
                        scene_id=sid,
                        scene_version_id=published["scene_version_id"],
                        exercise_id=exercise["exercise_id"],
                        exercise_version_id=exercise["exercise_version_id"],
                        answers=[
                            dict(question_id=key, answer=canonical(value).decode())
                            for key, value in answers.items()
                        ],
                    ),
                    headers={"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())},
                )
                assert posted.status_code == 201, posted.text
                attempt = posted.json()["attempt_id"]
                feedback = client.get(f"{route}/attempts/{attempt}").json()
                assert feedback["comparison_score"] == score
                assert len(feedback["question_results"]) == 4
                assert other.get(f"{route}/attempts/{attempt}").status_code == 404
            assert client.get(scene_route).json() == view

        _, cipher = generation.local_gate(vault, fixture=True, profile=QUEUE)
        assert generation.raw_io.decrypt(vault / "generate.raw.enc", cipher) == original
        with pytest.raises(SnapshotError, match="QUEUE_BATCH_STOPPED"):
            generation.send(vault, **kwargs)
        assert len(calls) == 1
