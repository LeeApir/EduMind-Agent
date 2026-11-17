"""T119: independent material expectations and MockTransport through private PG/API."""

import asyncio
import json
import os
import subprocess
from copy import deepcopy
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo

from app.main import app
from app.services import stack_course_materials as m
from app.services import stack_course_publication as p
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import head_course_goal_fixture as fixtures
from scripts import stack_course_trial as trial


def reference():
    return trial.read(trial.PACKAGE / "independent-reference.json")


def test_program_materials_against_independent_reference_and_compiled_c(tmp_path):
    mat, ref = m.materials(), reference()
    assert mat["main"]["frames"] == ref["main"]
    assert mat["capacity"] == ref["boundary"]["capacity"]
    assert mat["order"] == ref["logical_order"]
    expected = ref["transfer"]
    transfer = m.example(m.TRANSFER)
    assert {k: [f[k] for f in transfer["frames"]] for k in ("values", "top", "popped")} == {
        k: expected[k] for k in ("values", "top", "popped")
    }
    assert {
        key: q["private_answer"] for key, q in mat["transfer"]["questions"].items()
    } == expected["answers"]
    assert transfer["source"] == mat["transfer"]["source"]

    def run(source, name):
        path, exe = tmp_path / f"{name}.c", tmp_path / name
        path.write_text(source)
        subprocess.run(
            ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(exe)],
            check=True,
        )
        subprocess.run([str(exe)], check=True)

    for name, source, commands, values, popped in (
        (
            "main",
            mat["main"]["source"],
            ["push(&s, 3)", "push(&s, 8)", "pop(&s, &value)", "push(&s, 5)"],
            [f["values"] for f in ref["main"]],
            [f["popped"] for f in ref["main"]],
        ),
        (
            "transfer",
            transfer["source"],
            [
                "push(&s, -4)",
                "push(&s, 6)",
                "push(&s, 2)",
                "pop(&s, &value)",
                "push(&s, 9)",
                "pop(&s, &value)",
                "pop(&s, &value)",
            ],
            expected["values"],
            expected["popped"],
        ),
    ):
        caller = source.split("int main(void) {", 1)[1].splitlines()
        actual_calls = [line for line in caller if line.startswith("    if (!")]
        assert actual_calls == [f"    if (!{command}) return 1;" for command in commands]
        snapshots = iter(zip(values[1:], popped[1:], strict=True))
        instrumented = ["#include <assert.h>"]
        for line in source.splitlines():
            instrumented.append(line)
            if line == "    Stack s = {{0}, 0};":
                instrumented.append("    assert(s.count == 0);")
            elif line in actual_calls:
                stack, result = next(snapshots)
                checks = [f"s.count == {len(stack)}"]
                checks.extend(f"s.data[{i}] == ({value})" for i, value in enumerate(stack))
                if result is not None:
                    checks.append(f"value == {result}")
                instrumented.append("    assert(" + " && ".join(checks) + ");")
        assert next(snapshots, None) is None
        run("\n".join(instrumented) + "\n", name)

    base = mat["main"]["source"].split("int main(void) {")[0]
    run(
        "#include <assert.h>\n"
        + base
        + """
int main(void) {
    Stack s = {{0}, 0};
    int value = 77;
    assert(!pop(&s, &value) && value == 77 && s.count == 0);
    assert(push(&s, 1) && push(&s, 2) && push(&s, 3));
    assert(!push(&s, 4) && s.count == 3);
    assert(s.data[0] == 1 && s.data[1] == 2 && s.data[2] == 3);
    assert(pop(&s, &value) && value == 3 && s.count == 2 && s.data[2] == 3);
    return 0;
}
""",
        "boundaries",
    )


def teaching_fixture():
    return dict(
        paragraphs=[
            dict(text="离线接线夹具正文", fact_ids=[k]) for k in ("order", "push", "pop", "lifo")
        ],
        step_notes=[dict(frame_id=f"f{i}", note="离线接线夹具步骤") for i in range(5)],
        questions={
            key: dict(stem=f"{target}？", explanation="离线接线夹具解析")
            for key, (target, _) in m.QUESTIONS.items()
        },
        summary="离线接线夹具总结",
    )


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda raw: raw.update(answer=8), "STACK_TEACHING_SCHEMA"),
        (lambda raw: raw["paragraphs"][0]["fact_ids"].append("order"), "STACK_TEACHING_SCHEMA"),
        (lambda raw: raw["paragraphs"][0].update(fact_ids=["unknown"]), "STACK_FACT_REFERENCE"),
        (lambda raw: raw["step_notes"].reverse(), "STACK_FRAME_BINDING"),
        (
            lambda raw: raw["questions"]["first_pop"].update(stem="说明\n#include"),
            "STACK_QUESTION_PROSE_REQUIRED",
        ),
    ],
)
def test_model_cannot_change_materials_or_reference_unknown(change, error):
    raw = teaching_fixture()
    change(raw)
    with pytest.raises(SnapshotError, match=error):
        m.validate_content(raw, m.materials())


@pytest.mark.parametrize("protocol_failure", [False, True])
def test_actual_foreground_entry_and_private_course(monkeypatch, tmp_path, protocol_failure):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **kw: pytest.fail("Provider forbidden"),
    )
    with (
        TestClient(app, base_url="https://testserver") as client,
        TestClient(app, base_url="https://testserver") as other,
    ):
        auth = client.post("/api/auth/guest").json()
        other.post("/api/auth/guest")
        owner = UUID(auth["user"]["id"])
        vault = tmp_path / "vault"
        approval = trial.approval_values()
        with pytest.raises(SnapshotError, match="STACK_EXACT_AUTHORIZATION_REQUIRED"):
            asyncio.run(
                trial.prepare(
                    vault, owner, dict(approval, explicit_user_authorization=False), fixture=True
                )
            )
        ctx = asyncio.run(trial.prepare(vault, owner, approval, fixture=True))
        cid, oid, sid = (ctx[key] for key in ("course_id", "operation_id", "scene_id"))
        course_route = f"/api/free-courses/{cid}"
        op = client.get(f"{course_route}/operations/{oid}").json()
        assert op["execution_mode"] == "finite_stack_foreground" and op["budget"] is None
        assert client.get(course_route).json()["head"]["version"] == 1

        request = m.request()
        envelope = json.loads(with_direct_echo(request, fixtures.envelope(teaching_fixture())))
        envelope["output"][0]["phase"] = "invalid" if protocol_failure else "final_answer"
        original = canonical(envelope)
        calls = []

        def handler(req):
            calls.append(req.content)
            assert req.url.path == "/responses" and req.headers["Host"] == "api.deepseek.com"
            assert req.content == (trial.PACKAGE / "request.json").read_bytes()
            return httpx.Response(200, stream=httpx.ByteStream(original))

        transport = httpx.MockTransport(handler)
        if protocol_failure:
            with pytest.raises(ValueError, match="WIRE_MESSAGE_PHASE"):
                trial.send(vault, transport=transport, key="offline-key")
            assert trial.read(vault / "generate.failure.json")["code"] == "WIRE_MESSAGE_PHASE"
            _, cipher = trial.local_gate(vault, fixture=True)
            assert trial.raw_io.decrypt(vault / "generate.raw.enc", cipher) == original
            assert client.get(course_route).json()["head"]["complete"] is False
            with pytest.raises(SnapshotError, match="STACK_SAVED_BINDING"):
                trial.replay(vault, fixture=True)
        else:
            c = trial.send(vault, transport=transport, key="offline-key")
            assert trial.replay(vault, fixture=True) == c
            assert c["raw_output"] == teaching_fixture()
            review = dict(
                candidate_digest=c["candidate_digest"],
                verdict="pass",
                independent_evaluator="offline_fixture_only",
                blocking_findings=[],
                checks=dict.fromkeys(p.CHECKS, True),
            )
            path = vault / "review.json"
            path.write_bytes(canonical(dict(review, candidate_digest="0" * 64)))
            with pytest.raises(SnapshotError, match="STACK_REVIEW_REQUIRED"):
                trial.publish(vault, fixture=True)
            assert client.get(course_route).json()["head"]["version"] == 1
            path.write_bytes(canonical(review))
            v2 = trial.publish(vault, fixture=True)
            assert v2["version"] == 2 and v2["candidate_digest"] == c["candidate_digest"]

            route = f"{course_route}/versions/2/scenes/{sid}"
            result = client.get(route)
            assert result.status_code == 200, result.text
            view = result.json()
            assert '"answer_key"' not in result.text and '"solution"' not in result.text
            assert view["generation_source"]["evidence_kind"] == "offline_fixture"
            assert (
                view["generation_source"]["materials_digest"] == m.materials()["materials_digest"]
            )
            assert view["blocks"][-1]["items"][0]["question"].endswith(
                m.materials()["transfer"]["source"]
            )
            assert other.get(route).status_code == 404

            exercise = view["blocks"][-1]
            keys = reference()["transfer"]["answers"]
            body = dict(
                course_version=2,
                scene_id=sid,
                scene_version_id=v2["scene_version_id"],
                exercise_id=exercise["exercise_id"],
                exercise_version_id=exercise["exercise_version_id"],
                answers=[
                    dict(question_id=k, answer=canonical(value).decode())
                    for k, value in keys.items()
                ],
            )
            wrong = deepcopy(body)
            for item in wrong["answers"]:
                item["answer"] = "999"
            for request_body, score in ((wrong, 0), (body, 1)):
                posted = client.post(
                    f"{course_route}/attempts",
                    json=request_body,
                    headers={"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())},
                )
                assert posted.status_code == 201, posted.text
                aid = posted.json()["attempt_id"]
                feedback = client.get(f"{course_route}/attempts/{aid}").json()
                assert feedback["comparison_score"] == score
                assert feedback["mastery_effect"] == "course_only"
                assert len(feedback["question_results"]) == 4
                assert other.get(f"{course_route}/attempts/{aid}").status_code == 404
            assert client.get(route).json() == view

        with pytest.raises(SnapshotError, match="STACK_BATCH_STOPPED"):
            trial.send(vault, transport=transport, key="offline-key")
        assert len(calls) == 1
