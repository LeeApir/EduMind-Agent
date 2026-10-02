"""Candidate content checks, explicitly not a substitute for human course review."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from app.services.catalog_package import load_package, validate_package
from app.services.quiz_scoring import score_exercise_content

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "data/course_catalog/linear-v1"
C_IMAGE = "sha256:1851e4b5119c3ea2793190ab40c13167d4aac84bb271a2ab34c3b6248c43c6bf"
NODES = tuple(json.loads((DIRECTORY / "manifest.json").read_text())["nodes"])


def test_candidate_remains_unapproved_complete_and_normalization_stable() -> None:
    package = load_package(DIRECTORY)
    status = json.loads((DIRECTORY / "review-status.json").read_text())
    assert status["state"] == "PENDING_HUMAN_REVIEW"
    assert status["human_reviewer"] is None and status["human_reviewed_at"] is None
    assert status["manifest_digest"] == package.digest
    assert validate_package(package.payload()).payload() == package.payload()
    assert len(package.nodes) == 10
    assert sum(len(v["exercise"]["items"]) for v in package.nodes.values()) == 30
    assert not (DIRECTORY / "approval.json").exists()


@pytest.mark.parametrize("node_id", NODES)
def test_fixed_answer_keys_match_existing_server_scoring(node_id: str) -> None:
    from uuid import uuid4
    content = load_package(DIRECTORY).nodes[node_id]["exercise"]
    score = score_exercise_content(resource_id=uuid4(), resource_version=1, content=content,
        answers=[{"question_id": q["id"], "answer": q["answer"]} for q in content["items"]])
    assert score.correct_count == 3 and score.score == 1


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="restricted Docker opt-in")
@pytest.mark.parametrize("node_id", NODES)
def test_complete_c_example_compiles_and_runs_with_sanitizers(
    node_id: str, tmp_path: Path
) -> None:
    code = load_package(DIRECTORY).nodes[node_id]["code"]
    result = run_c(code["source"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == code["expected_output"]


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="restricted Docker opt-in")
@pytest.mark.parametrize("node_id", [
    "single-linked-list", "linked-list-insertion", "linked-list-deletion"])
@pytest.mark.parametrize("fail_after", [0, 1, 2])
def test_allocation_failure_retains_ownership_without_leak(
    node_id: str, fail_after: int, tmp_path: Path
) -> None:
    code = load_package(DIRECTORY).nodes[node_id]["code"]
    result = run_c(code["source"], tmp_path, fail_after=fail_after)
    assert result.returncode == 0, result.stderr
    assert "AddressSanitizer" not in result.stderr and "runtime error" not in result.stderr
    assert result.stdout.strip() in {"allocation unavailable", code["expected_output"]}


def run_c(
    source: str, directory: Path, *, fail_after: int = -1
) -> subprocess.CompletedProcess[str]:
    # Only committed fixed candidate source enters this helper, never API/user input.
    path = directory / "example.c"
    path.write_text(source)
    flags = f"-DEDUMIND_ALLOC_FAIL_AFTER={fail_after}"
    command = (
        "cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined "
        f"-fno-omit-frame-pointer -g {flags} /source/example.c -o /tmp/example "
        "&& ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 /tmp/example")
    return subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only",
        "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "256m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,exec,size=64m,mode=1777", "--mount",
        f"type=bind,source={directory},target=/source,readonly", "--entrypoint", "sh", C_IMAGE,
        "-c", command], capture_output=True, text=True, timeout=20, check=False)
