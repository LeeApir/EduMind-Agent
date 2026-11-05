"""Read-only T109 stopped batch replay. No Provider, terminal or Provider Key access."""

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from cryptography.fernet import Fernet  # noqa: E402
from scripts import head_course_goal as entry  # noqa: E402
from app.services import head_course_materials as m  # noqa: E402
from app.services import head_course_reuse as reuse  # noqa: E402

HERE = Path(__file__).resolve().parent
VAULT = Path("/Users/apir/.local/share/edumind/head-reuse-r01")
PACKAGE_SHA = "f4c98c1a24d2943dd7f38350095932f1e933a46757eee3896156439d05bd239b"


def read(path):
    return entry.read(path)


def main():
    entry.PACKAGE = entry.REUSE_PACKAGE
    assert entry.package_digest() == PACKAGE_SHA
    approval = read(VAULT / "approval.json")
    window = read(HERE / "execution-window.json")
    assert approval["package_sha256"] == PACKAGE_SHA
    assert approval["accept_ADR0053_and_batch_C2"] is True
    assert approval["max_http_requests"] == 3
    assert approval["expires_epoch"] - approval["starts_epoch"] == 600
    assert window["starts_epoch"] == approval["starts_epoch"]
    assert window["expires_epoch"] == approval["expires_epoch"]
    assert window["actual_http_requests"] == window["provider_calls_attempted"] == 2
    assert window["unused_requests_invalidated"] == 1 and window["stopped"]
    assert window["first_structure_pass"] is True
    assert (
        window["format_recovery_used"] is False
        and window["model_revision_used"] is False
    )
    assert window["assistant_teaching_edits"] == 0
    assert (VAULT / "STOP").exists() and not (VAULT / "ACTIVE").exists()
    assert len(list(VAULT.glob("*.attempt.json"))) == 2
    assert not any(
        (VAULT / n).exists()
        for n in (
            "repair.attempt.json",
            "repair.record.json",
            "published.json",
            "generate.strict-failure.json",
        )
    )
    # This is the local body encryption key, distinct from the Provider Key; never printed/exported.
    cipher = Fernet((VAULT / "raw.key").read_bytes())
    plan = entry.verify_saved(VAULT, "plan", cipher)
    record = entry.verify_saved(VAULT, "generate", cipher)
    context = read(VAULT / "context.json")
    assert context["planning_inputs"]["original_goal"] == m.REUSE_GOAL
    assert list(context["planning_inputs"]["head_support"]["examples"]) == [
        "head-new-B"
    ]
    assert plan["plan"]["shared_example"] == "head-new-B"
    assert (
        record["candidate"]["candidate_digest"]
        == "63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd"
    )
    assert record["evidence_kind"] == "actual_provider_response"
    assert (
        record["candidate"]["recovery"] is None
        and record["candidate"]["parent_digest"] is None
    )
    assert record["candidate"]["payload"] == m.content_payload(
        context["planning_inputs"], plan["plan"]
    )
    assert read(HERE / "teaching.prepared-request.json") == read(
        VAULT / "generate.request.json"
    )
    assert read(HERE / "materials.json") == record["candidate"]["payload"]["materials"]
    for stage, size, sha in (
        (
            "plan",
            7290,
            "31f6111a4cc8ce891674fc2053ffd0dd39a65314e68c9105e2e9cfe376d52e50",
        ),
        (
            "generate",
            17052,
            "b5acad36fceae43082f8facc2c0c14990f98d15715b9610f7da8cca554d9fa95",
        ),
    ):
        raw = entry.raw_io.decrypt(VAULT / (stage + ".raw.enc"), cipher)
        assert raw == (HERE / (stage + ".raw.json")).read_bytes()
        assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
        receipt = read(VAULT / (stage + ".body.json"))
        assert receipt == dict(
            http_status=200, body_complete=True, raw_bytes=size, raw_sha256=sha
        )
        attempt = read(VAULT / (stage + ".attempt.json"))
        assert attempt["package_sha256"] == PACKAGE_SHA
        assert (
            attempt["request_sha256"]
            == hashlib.sha256(
                entry.canonical(read(VAULT / (stage + ".request.json")))
            ).hexdigest()
        )
        assert attempt["evidence_kind"] == "actual_provider_response"
    index = read(HERE / "originals-manifest.json")
    assert index["key_excluded"] and "raw.key" not in index["files"]
    for name, sha in index["files"].items():
        original = (VAULT / name).read_bytes()
        assert hashlib.sha256(original).hexdigest() == sha, name
        if name not in ("plan.raw.enc", "generate.raw.enc"):
            assert (HERE / name).read_bytes() == original, name
    review = read(HERE / "final-review.json")
    assert review["candidate_digest"] == record["candidate"]["candidate_digest"]
    assert (
        review["planning_basis_binding"]
        == record["candidate"]["payload"]["planning_basis"]["binding"]
    )
    assert (
        review["verdict"] == "stop"
        and review["teaching_pass"] is False
        and review["repair_allowed"] is False
    )
    assert [f["id"] for f in review["blocking_findings"]] == ["S01", "C01"]
    for finding in review["blocking_findings"]:
        text = record["candidate"]["raw_output"]
        for key in finding["path"]:
            text = text[key]
        if isinstance(text, dict):
            text = text["text"]
        assert finding["quote"] in text
    assert review["blocking_findings"][0]["path"] == ["failure_scope"]
    try:
        reuse.validate_final(
            [record], review, record["candidate"]["payload"], entry.raw_io
        )
    except Exception as error:
        assert getattr(error, "code", None) == "REUSE_REVIEW_BINDING"
    else:
        raise AssertionError("Nonpass review must never authorize publication")
    app = read(HERE / "app-stop-result.json")
    browser = read(HERE / "app-browser-stop.json")
    assert app["state"] == "failed" and app["reason_code"] == "TEACHING_REVIEW_FAILED"
    assert (
        app["head_version"] == app["planning_results"] == 1
        and app["scene_generation_results"] == 0
    )
    assert (
        browser["operation_status"] == 200 and browser["operation"]["state"] == "failed"
    )
    assert (
        browser["course"]["head"]["version"] == 1
        and not browser["course"]["head"]["complete"]
    )
    assert browser["full_learning_flow_run"] is False
    # Preserve E01 as a failure; this is not the accurate real-request ledger.
    assert "execution_mode" not in browser["operation"]
    assert browser["operation"]["budget"]["attempts_used"] == 0
    assert browser["operation"]["budget"]["attempts_remaining"] == 13
    assert "生成未完成" in browser["screen"]
    print(
        "PASS: exact2HTTP200/raw and candidate replay; strict first pass; independent teaching STOP; no recovery/revision/publication; unused1invalid; v1/failed and E01 preserved. This check calls Provider0."
    )


if __name__ == "__main__":
    main()
