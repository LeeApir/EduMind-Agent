"""Independent material checks and the shared foreground admission path."""

import asyncio
import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_head_course_fixed import with_direct_echo

from app.main import app
from app.services import binary_search_course_materials as binary
from app.services.course_trial_publication import BINARY_SEARCH
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts import head_course_goal_fixture as fixtures

PACKAGE = trial.package_path(BINARY_SEARCH)


def reference():
    return trial.read(PACKAGE / "independent-reference.json")


def teaching():
    return dict(
        paragraphs=[
            dict(text=f"离线夹具讲解 {key}。", fact_ids=[key])
            for key in ("order", "mid", "smaller", "larger", "termination", "duplicates")
        ],
        step_notes=[dict(frame_id=f"f{i}", note=f"离线夹具帧 {i}。") for i in range(6)],
        questions={
            key: dict(
                stem=f"根据下方代码，填写{goal}。输入格式为"
                f"{' JSON 整数数组 [left,right]' if kind == 'json_integer_array' else '整数'}。",
                explanation="离线夹具解析。",
            )
            for key, (goal, kind) in binary.QUESTIONS.items()
        },
        summary="离线夹具总结。",
    )


def run_c(source, tmp_path: Path):
    path, output = tmp_path / "example.c", tmp_path / "example"
    path.write_text(source)
    subprocess.run(
        ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(output)],
        check=True,
    )
    return subprocess.check_output([str(output)], text=True).splitlines()


def test_independent_frames_transfers_and_boundaries(tmp_path):
    expected = reference()
    materials = binary.materials()
    main = materials["main"]
    assert {key: main[key] for key in expected["main"]} == expected["main"]
    assert {
        key: row["private_answer"] for key, row in materials["transfer"]["questions"].items()
    } == expected["transfer"]

    # Observe C variables as they stand at the listed boundaries of the fixed function.
    trace = {
        4: 'printf("initial 4 %d %d -1 0\\n", left, right);',
        8: 'printf("found 8 %d %d %d 0\\n", left, right, mid);',
        10: 'printf("compare 10 %d %d %d %d\\n", left, right, mid, values[mid] - target);',
        11: 'printf("narrowed 11 %d %d %d %d\\n", left, right, mid, values[mid] - target);',
        13: 'printf("narrowed 13 %d %d %d %d\\n", left, right, mid, values[mid] - target);',
    }

    def instrument(source):
        lines = []
        for i, line in enumerate(source.splitlines(), 1):
            if i in (8, 10):
                lines.append("        " + trace[i])
            lines.append(line)
            if i in (4, 11, 13):
                lines.append("        " + trace[i])
        return "\n".join(lines) + "\n"

    printed = run_c(instrument(main["source"]), tmp_path)
    assert int(printed[-1]) == expected["main"]["result"]
    for row, frame in zip(printed[:-1], expected["main"]["frames"], strict=True):
        phase, *numbers = row.split()
        line, left, right, mid, comparison = map(int, numbers)
        relation = "less" if comparison < 0 else "greater" if comparison > 0 else "equal"
        assert (phase, line, left, right, None if mid < 0 else mid) == (
            frame["phase"],
            frame["line"],
            frame["left"],
            frame["right"],
            frame["mid"],
        )
        assert (None if phase == "initial" else relation) == frame["comparison"]
    transfer = run_c(instrument(materials["transfer"]["source"]), tmp_path)
    updates = [list(map(int, row.split()[2:4])) for row in transfer if row.startswith("narrowed ")]
    assert updates == [[4, 7], [6, 7], [0, 2], [2, 2], [3, 2]]
    assert list(map(int, transfer[-1].split())) == [6, -1]
    edge = (
        binary.CODE
        + """
#include <assert.h>
int main(void) {
    const int one[] = {5};
    const int duplicate[] = {5, 5, 5};
    assert(binary_search(NULL, 0, 5) == -1);
    assert(binary_search(one, 1, 5) == 0);
    assert(binary_search(one, 1, 4) == -1);
    assert(binary_search(one, 1, 6) == -1);
    assert(binary_search(duplicate, 3, 5) == 1);
    return 0;
}
"""
    )
    assert run_c(edge, tmp_path) == []


def test_teaching_contract_requires_exact_frames_and_fact_ids():
    raw = teaching()
    raw["step_notes"].reverse()
    with pytest.raises(SnapshotError, match="BINARY_SEARCH_FRAME_BINDING"):
        binary.validate_content(raw, binary.materials())
    raw = teaching()
    raw["paragraphs"][0]["fact_ids"] = ["order", "order"]
    with pytest.raises(SnapshotError, match="BINARY_SEARCH_TEACHING_SCHEMA"):
        binary.validate_content(raw, binary.materials())
    raw["paragraphs"][0]["fact_ids"] = ["lifo"]
    with pytest.raises(SnapshotError, match="BINARY_SEARCH_FACT_REFERENCE"):
        binary.validate_content(raw, binary.materials())


def test_shared_binary_search_trial(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    with (
        TestClient(app, base_url="https://testserver") as client,
        TestClient(app, base_url="https://testserver") as other,
    ):
        auth = client.post("/api/auth/guest").json()
        other.post("/api/auth/guest")
        owner = UUID(auth["user"]["id"])
        vault = tmp_path / "binary-search"
        approval = trial.approval_values(BINARY_SEARCH)
        with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
            asyncio.run(
                trial.prepare(
                    vault,
                    owner,
                    dict(approval, max_http_requests=2),
                    fixture=True,
                    profile=BINARY_SEARCH,
                )
            )
        assert not vault.exists()
        ctx = asyncio.run(
            trial.prepare(vault, owner, approval, fixture=True, profile=BINARY_SEARCH)
        )
        route = f"/api/free-courses/{ctx['course_id']}"
        op = client.get(f"{route}/operations/{ctx['operation_id']}").json()
        assert op["execution_mode"] == "finite_binary_search_foreground" and op["budget"] is None
        response = with_direct_echo(binary.request(), fixtures.envelope(teaching()))
        calls = []

        def handle(request):
            calls.append(request.content)
            assert request.content == (PACKAGE / "request.json").read_bytes()
            return httpx.Response(200, stream=httpx.ByteStream(response))

        args = dict(transport=httpx.MockTransport(handle), key="fixture-key", profile=BINARY_SEARCH)
        child = trial.send(vault, **args)
        assert trial.replay(vault, fixture=True, profile=BINARY_SEARCH) == child
        with pytest.raises(SnapshotError, match="BATCH_STOPPED"):
            trial.send(vault, **args)
        assert len(calls) == 1
        review = dict(
            candidate_digest="0" * 64,
            verdict="pass",
            independent_evaluator="fixture-only",
            blocking_findings=[],
            checks=dict.fromkeys(BINARY_SEARCH.checks, True),
        )
        (vault / "review.json").write_bytes(canonical(review))
        with pytest.raises(SnapshotError, match="REVIEW_REQUIRED"):
            trial.publish(vault, fixture=True, profile=BINARY_SEARCH)
        assert client.get(route).json()["head"]["version"] == 1
        (vault / "review.json").write_bytes(
            canonical(dict(review, candidate_digest=child["candidate_digest"]))
        )
        ready = trial.publish(vault, fixture=True, profile=BINARY_SEARCH)
        scene_path = f"{route}/versions/2/scenes/{ctx['scene_id']}"
        scene = client.get(scene_path)
        assert scene.status_code == 200, scene.text
        assert other.get(scene_path).status_code == 404
        assert '"answer_key"' not in scene.text and '"solution"' not in scene.text
        blocks = scene.json()["blocks"]
        exercise = blocks[-1]
        for values, score in (
            (dict.fromkeys(binary.QUESTIONS, 999), 0),
            (reference()["transfer"], 1),
        ):
            posted = client.post(
                f"{route}/attempts",
                json=dict(
                    course_version=2,
                    scene_id=ctx["scene_id"],
                    scene_version_id=ready["scene_version_id"],
                    exercise_id=exercise["exercise_id"],
                    exercise_version_id=exercise["exercise_version_id"],
                    answers=[
                        dict(question_id=key, answer=canonical(value).decode())
                        for key, value in values.items()
                    ],
                ),
                headers={"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": str(uuid4())},
            )
            assert posted.status_code == 201, posted.text
            attempt = f"{route}/attempts/{posted.json()['attempt_id']}"
            feedback = client.get(attempt).json()
            assert feedback["comparison_score"] == score and len(feedback["question_results"]) == 4
            assert other.get(attempt).status_code == 404
        assert client.get(scene_path).json() == scene.json()
