"""Offline r03 original/mapping/duplicate-key/stop audit. Never calls a Provider."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from cryptography.fernet import Fernet  # noqa: E402
from scripts import head_course_goal as entry  # noqa: E402

HERE = Path(__file__).resolve().parent
VAULT = Path("/Users/apir/.local/share/edumind/head-goal-r03")
SHA = "43ec5edb6eb741cad8c324aae4c8037fe90bc0fb65bd70cd623d81b75b5f0850"


def read(path):
    return json.loads(path.read_text())


class Pairs(list):
    """Preserve duplicate fields solely to inspect structure, never form a candidate."""


def main():
    assert entry.package_digest() == SHA
    approval = read(VAULT / "approval.json")
    window = read(HERE / "execution-window.json")
    assert approval["package_sha256"] == SHA
    assert approval["planning_prompt_version"] == entry.plan_wire.PROMPT_VERSION
    assert approval["accept_ADR0052_R03_and_batch_C2"] is True
    assert window["starts_epoch"] == approval["starts_epoch"]
    assert window["expires_epoch"] == approval["expires_epoch"]
    assert approval["expires_epoch"] - approval["starts_epoch"] == 600
    assert (
        window["actual_http_requests"] == 2
        and window["remaining_requests_invalidated"] == 1
    )
    assert window["accepted_plans"] == 1 and window["accepted_teaching_candidates"] == 0
    assert window["generated_complete_courses"] == 0 and window["stopped"]
    assert (VAULT / "STOP").exists() and (VAULT / "ACTIVE").exists()
    assert len(list(VAULT.glob("*.attempt.json"))) == 2
    for name, sha in read(HERE / "originals-manifest.json")["files"].items():
        assert hashlib.sha256((VAULT / name).read_bytes()).hexdigest() == sha, name
    # Only the local body-encryption key is read, never a Provider credential or terminal.
    cipher = Fernet((VAULT / "raw.key").read_bytes())
    plan = entry.verify_saved(VAULT, "plan", cipher)["plan"]
    context = read(VAULT / "context.json")
    payload = entry.m.content_payload(context["planning_inputs"], plan)
    review = read(VAULT / "plan-review.json")
    assert review == read(HERE / "plan-review.json")
    assert review["plan_digest"] == entry.digest("head-plan", plan=plan)
    assert review["verdict"] == "pass"
    assert review["planning_basis_binding"] == payload["planning_basis"]["binding"]
    assert read(VAULT / "plan.binding.json")["payload"] == payload
    assert read(VAULT / "plan.request.json") == entry.planning_body(
        context["planning_inputs"]
    )
    assert read(VAULT / "generate.request.json") == entry.m.body(payload)
    for stage, size in [("plan", 6762), ("generate", 19720)]:
        request = read(VAULT / f"{stage}.request.json")
        attempt = read(VAULT / f"{stage}.attempt.json")
        assert attempt["package_sha256"] == SHA
        assert attempt["evidence_kind"] == "actual_provider_response"
        assert (
            attempt["request_sha256"]
            == hashlib.sha256(entry.canonical(request)).hexdigest()
        )
        raw = entry.raw_io.decrypt(VAULT / f"{stage}.raw.enc", cipher)
        body = read(VAULT / f"{stage}.body.json")
        assert body["http_status"] == 200 and body["body_complete"]
        assert len(raw) == body["raw_bytes"] == size
        assert hashlib.sha256(raw).hexdigest() == body["raw_sha256"]
        for suffix in ("request.json", "attempt.json", "body.json"):
            assert (VAULT / f"{stage}.{suffix}").read_bytes() == (
                HERE / f"{stage}.{suffix}"
            ).read_bytes()
    try:
        entry.raw_io.observe_generation(read(VAULT / "generate.request.json"), raw)
    except entry.raw_io.wire.PilotError as error:
        assert str(error) == "DUPLICATE_JSON_KEY"
    else:
        raise AssertionError("Teaching protocol unexpectedly passed")
    envelope = entry.raw_io.wire.strict_json(raw)
    text = envelope["output"][0]["content"][0]["text"]
    pairs = json.loads(text, object_pairs_hook=Pairs)
    questions = [value for key, value in pairs if key == "questions"]
    assert len(questions) == 1 and isinstance(questions[0], Pairs)
    assert Counter(key for key, value in questions[0]) == Counter(
        {key: 2 for key in entry.m.QKEYS}
    )
    # No duplicate value is chosen, merged, exported as a lesson or passed to assembly.
    assert read(VAULT / "generate.failure.json") == read(HERE / "generate.failure.json")
    assert read(VAULT / "generate-diagnostic.json") == read(
        HERE / "generate-diagnostic.json"
    )
    assert not any(
        (VAULT / name).exists()
        for name in (
            "generate.record.json",
            "repair.attempt.json",
            "repair.record.json",
            "published.json",
        )
    )
    app = read(HERE / "app-stop-result.json")
    assert app["state"] == "failed" and app["reason_code"] == "SCHEMA_INVALID"
    assert app["head_version"] == app["planning_results"] == 1
    assert app["scene_generation_results"] == 0
    print(
        "PASS: 2 HTTP200/complete originals; plan pass/basis bound; teaching duplicate keys "
        "reproduced; STOP/unused1invalidated; 0 complete courses. Provider calls in this check:0."
    )


if __name__ == "__main__":
    main()
