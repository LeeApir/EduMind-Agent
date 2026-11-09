"""Read-only diagnosis of the sealed T115 response. Writes only a private review input."""

import argparse
from copy import deepcopy
from pathlib import Path

from cryptography.fernet import Fernet

from app.services import head_course_materials as materials, head_course_reuse as reuse
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from scripts import head_course_deepseek_wire as adapter, head_course_goal as entry

ARCHIVE = entry.ROOT / "docs/acceptance/phase-1.5-head-deepseek-live-r01"
RULE = "t115-exact-scenario-terminal-lf-v1"


def diagnostic_stem(stem: str, source: str) -> str:
    """Accept the exact scenario or a terminal scenario missing one LF."""
    marker = "#include <stdlib.h>"
    if not source.startswith(marker) or not source.endswith("\n"):
        raise ValueError("Unsupported program scenario")
    offset = stem.find(marker)
    observed = stem[offset:] if offset >= 0 else ""
    if observed == source:
        return stem
    if observed == source[:-1]:
        return stem + "\n"
    raise ValueError("Scenario bytes differ beyond the terminal LF")


def diagnose():
    entry.PACKAGE = entry.DIRECT_PACKAGE
    vault = entry.DIRECT_VAULT
    manifest = entry.read(ARCHIVE / "originals-manifest.json")
    assert manifest["key_excluded"] is True and manifest["vault"] == str(vault)
    assert {"STOP", "generate.raw.enc", "generate.failure.json"} <= set(
        manifest["files"]
    )
    assert "raw.key" not in manifest["files"]
    assert {
        p.name: reuse.sha(p.read_bytes())
        for p in vault.iterdir()
        if p.is_file() and p.name != "raw.key"
    } == manifest["files"]
    assert (vault / "STOP").read_bytes() == (ARCHIVE / "STOP").read_bytes()

    cipher = Fernet((vault / "raw.key").read_bytes())
    ctx = entry.read(vault / "context.json")
    approval = entry.read(vault / "approval.bound.json")
    package_sha = entry.package_digest()
    assert approval["package_sha256"] == package_sha
    assert approval["context_sha256"] == manifest["files"]["context.json"]
    assert approval["execution_window"] == ctx["execution_window"]
    plan = entry.verify_saved(vault, "plan", cipher)["plan"]
    payload = materials.content_payload(ctx["planning_inputs"], plan)
    review = entry.read(vault / "plan-review.json")
    assert review["plan_digest"] == digest("head-plan", plan=plan)
    assert review["verdict"] == "pass"
    assert review["planning_basis_binding"] == payload["planning_basis"]["binding"]

    raw = entry.raw_io.decrypt(vault / "generate.raw.enc", cipher)
    receipt = entry.read(vault / "generate.body.json")
    attempt = entry.read(vault / "generate.attempt.json")
    request = entry.read(vault / "generate.request.json")
    assert request == materials.body(payload)
    assert attempt["request_sha256"] == reuse.sha(canonical(request))
    assert attempt["approval_sha256"] == reuse.sha(canonical(approval))
    assert attempt["package_sha256"] == package_sha
    assert (
        attempt["stage"] == "generate"
        and attempt["evidence_kind"] == "actual_provider_response"
    )
    assert receipt == dict(
        http_status=200,
        raw_bytes=len(raw),
        raw_sha256=reuse.sha(raw),
        body_complete=True,
    )
    parsed, _ = adapter.observe_generation(request, raw)
    original = parsed.value
    failure = entry.read(vault / "generate.failure.json")
    try:
        reuse.record(
            payload, request, raw, adapter, evidence_kind="actual_provider_response"
        )
    except SnapshotError as exc:
        assert exc.code == failure["code"] == "HEAD_QUESTION_SCENARIO"
    else:
        raise AssertionError("Expected frozen content rejection")

    derived = deepcopy(original)
    findings = entry.read(ARCHIVE / "failure-diagnosis.json")["questions"]
    changes = []
    for key in materials.QKEYS:
        info = findings[key]
        source = payload["materials"]["transfer"][info["variant"]]["code"]["source"]
        stem = original["questions"][key]["stem"]
        normalized = diagnostic_stem(stem, source)
        assert normalized == stem + "\n"
        assert reuse.sha(source.encode()) == info["expected_code_sha256"]
        assert reuse.sha(source[:-1].encode()) == info["observed_code_sha256"]
        derived["questions"][key]["stem"] = normalized
        changes.append(
            dict(
                path=["questions", key, "stem"],
                appended_hex="0a",
                original_stem_sha256=reuse.sha(stem.encode()),
                diagnostic_stem_sha256=reuse.sha(normalized.encode()),
            )
        )
    without_lf = deepcopy(derived)
    for key in materials.QKEYS:
        without_lf["questions"][key]["stem"] = derived["questions"][key]["stem"][:-1]
    assert canonical(without_lf) == canonical(original)

    adapter.wire.check_schema(derived, request["text"]["format"]["schema"])
    candidate = reuse.candidate(payload, derived)
    preview = materials.assemble(payload, derived, {"origin": RULE})
    exercise = next(block for block in preview["blocks"] if block["kind"] == "exercise")
    replay = next(
        block for block in preview["blocks"] if block["kind"] == "visualization"
    )
    assert {
        item["question_id"]: item["answer_key"] for item in exercise["items"]
    } == payload["materials"]["answers"]
    assert len(replay["steps"]) == len(preview["actions"]) == 13
    return dict(
        rule=RULE,
        candidate_digest=candidate["candidate_digest"],
        source_request_sha256=attempt["request_sha256"],
        raw_response_sha256=receipt["raw_sha256"],
        original_output_sha256=reuse.sha(canonical(original)),
        derived_output_sha256=reuse.sha(canonical(derived)),
        materials_digest=payload["materials"]["materials_digest"],
        evidence_digest=payload["teaching_evidence"]["evidence_digest"],
        plan_digest=review["plan_digest"],
        planning_basis_binding=review["planning_basis_binding"],
        originals_manifest_sha256=reuse.sha(
            (ARCHIVE / "originals-manifest.json").read_bytes()
        ),
        original_failure=failure["code"],
        derived_validation="passed",
        changes=changes,
        provider_calls=0,
        admission_eligible=False,
    ), candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if entry.DIRECT_VAULT.resolve() in output.parents or entry.ROOT in output.parents:
        parser.error("Review input must be outside the vault and repository")
    report, candidate = diagnose()
    entry.raw_io.exclusive(
        output, canonical(dict(diagnosis=report, candidate=candidate))
    )
    print(canonical(report).decode())


if __name__ == "__main__":
    main()
