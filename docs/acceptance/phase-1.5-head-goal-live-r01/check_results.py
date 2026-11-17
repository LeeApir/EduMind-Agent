"""Offline T108 stopped-batch evidence check; no Provider calls or terminal reads."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from scripts import head_course_goal as entry  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

HERE = Path(__file__).resolve().parent
VAULT = Path("/Users/apir/.local/share/edumind/head-goal-r01")
SHA = "ee8f8b7fc97c8d7855bf25b06a024fdf9f1ab798d84d84f77ea1a6d0b45a746a"


def read(path):
    return json.loads(path.read_text())


def main():
    assert entry.package_digest() == SHA
    approval = read(VAULT / "approval.json")
    window = read(HERE / "execution-window.json")
    assert approval["package_sha256"] == SHA
    assert approval["expires_epoch"] - approval["starts_epoch"] == 600
    assert (
        window["requests_attempted"] == 1
        and window["remaining_requests_invalidated"] == 2
    )
    assert window["generated_plans"] == window["generated_complete_courses"] == 0
    assert (
        window["stopped"] and (VAULT / "STOP").exists() and (VAULT / "ACTIVE").exists()
    )
    assert len(list(VAULT.glob("*.attempt.json"))) == 1
    context = read(VAULT / "context.json")
    request = read(VAULT / "plan.request.json")
    assert request == entry.planning_body(context["planning_inputs"])
    attempt = read(VAULT / "plan.attempt.json")
    assert attempt["evidence_kind"] == "actual_provider_response"
    assert (
        attempt["request_sha256"]
        == hashlib.sha256(entry.canonical(request)).hexdigest()
    )
    originals = read(HERE / "originals-manifest.json")
    for name, sha in originals["files"].items():
        assert hashlib.sha256((VAULT / name).read_bytes()).hexdigest() == sha, name
    for name in (
        "plan.request.json",
        "plan.attempt.json",
        "plan.body.json",
        "plan.failure.json",
    ):
        assert (HERE / name).read_bytes() == (VAULT / name).read_bytes(), name
    raw = entry.raw_io.decrypt(
        VAULT / "plan.raw.enc", Fernet((VAULT / "raw.key").read_bytes())
    )
    body = read(VAULT / "plan.body.json")
    assert body["http_status"] == 400 and body["body_complete"]
    assert len(raw) == body["raw_bytes"] == 206
    assert hashlib.sha256(raw).hexdigest() == body["raw_sha256"]
    assert not any(
        (VAULT / name).exists()
        for name in (
            "plan.output.json",
            "generate.record.json",
            "repair.record.json",
            "published.json",
        )
    )
    app = read(HERE / "app-stop-result.json")
    assert app["state"] == "failed" and app["reason_code"] == "PROVIDER_REJECTED"
    assert app["planning_results"] == app["scene_generation_results"] == 0
    assert app["head_version"] is None
    print(
        "PASS: 1 HTTP400; complete encrypted body verified; 0 plan/course; STOP retained; unused2 invalidated. Provider calls in this check:0."
    )


if __name__ == "__main__":
    main()
