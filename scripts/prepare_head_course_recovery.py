"""Read r03 originals, derive a separate course record. Offline only; no vault writes."""

import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from cryptography.fernet import Fernet  # noqa: E402
from scripts import head_course_goal as e  # noqa: E402
from app.services.head_course_duplicate_recovery import VERSION, recover  # noqa: E402

HERE = ROOT / "docs/acceptance/phase-1.5-head-goal-r03-recovery"
OLD = ROOT / "docs/acceptance/phase-1.5-head-goal-live-r03"
VAULT = Path("/Users/apir/.local/share/edumind/head-goal-r03")
PACKAGE = "43ec5edb6eb741cad8c324aae4c8037fe90bc0fb65bd70cd623d81b75b5f0850"
RAW = "4f05e35015c83b5660c3508e3b7e63671036ece326637ffeb56d5cf9d9f169ee"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    return e.raw_io.wire.strict_json(p.read_bytes())


def derive():
    frozen = ROOT / "docs/acceptance/phase-1.5-head-goal-t108-r03/manifest.json"
    assert sha(frozen.read_bytes()) == PACKAGE
    # Historical manifest is checked against its exact approved Git tree, not altered to
    # bless this newly authorized offline implementation.
    for name, h in read(frozen)["files"].items():
        b = subprocess.check_output(["git", "show", "4986af7:" + name], cwd=ROOT)
        assert sha(b) == h, name
    for name, h in read(OLD / "originals-manifest.json")["files"].items():
        assert sha((VAULT / name).read_bytes()) == h, name
    assert (VAULT / "STOP").exists() and (VAULT / "ACTIVE").exists()
    assert len(list(VAULT.glob("*.attempt.json"))) == 2
    cipher = Fernet((VAULT / "raw.key").read_bytes())
    context = read(VAULT / "context.json")
    raw_plan = e.raw_io.decrypt(VAULT / "plan.raw.enc", cipher)
    plan_request = read(VAULT / "plan.request.json")
    assert plan_request == e.planning_body(context["planning_inputs"])
    p, _ = e.raw_io.observe_generation(plan_request, raw_plan)
    assert dict(p.value) == read(VAULT / "plan.output.json")
    mapping = e.plan_wire.mapping_record(dict(p.value), context["planning_inputs"])
    assert mapping == read(VAULT / "plan.mapping.json")
    plan = mapping["value"]["plan"]
    payload = e.m.content_payload(context["planning_inputs"], plan)
    assert payload == read(VAULT / "plan.binding.json")["payload"]
    plan_review = read(VAULT / "plan-review.json")
    assert plan_review["verdict"] == "pass"
    assert plan_review["plan_digest"] == e.digest("head-plan", plan=plan)
    assert plan_review["planning_basis_binding"] == payload["planning_basis"]["binding"]
    for stage, raw in [
        ("plan", raw_plan),
        ("generate", e.raw_io.decrypt(VAULT / "generate.raw.enc", cipher)),
    ]:
        receipt = read(VAULT / f"{stage}.body.json")
        attempt = read(VAULT / f"{stage}.attempt.json")
        request = read(VAULT / f"{stage}.request.json")
        assert receipt == dict(
            http_status=200, raw_sha256=sha(raw), raw_bytes=len(raw), body_complete=True
        )
        assert (
            attempt["package_sha256"] == PACKAGE
            and attempt["evidence_kind"] == "actual_provider_response"
        )
        assert attempt["request_sha256"] == sha(e.canonical(request))
    assert sha(raw) == RAW and len(raw) == 19720
    request = read(VAULT / "generate.request.json")
    assert request == e.m.body(payload)
    try:
        e.raw_io.observe_generation(request, raw)
    except e.raw_io.wire.PilotError as error:
        assert str(error) == "DUPLICATE_JSON_KEY"
    else:
        raise AssertionError("Original should still fail strict parsing")
    envelope = e.raw_io.wire.strict_json(raw)
    text = envelope["output"][0]["content"][0]["text"]
    recovered, changes = recover(text)
    assert len(changes) == 4
    # Validate the full envelope through the unchanged adapter after the explicitly
    # recorded, content-preserving inner-text derivation. Never overwrite raw bytes.
    envelope["output"][0]["content"][0]["text"] = e.canonical(recovered).decode()
    result, observation = e.raw_io.observe_generation(request, e.canonical(envelope))
    assert dict(result.value) == recovered
    e.m.validate_content(payload, recovered)
    recovery = dict(
        rule_version=VERSION,
        source_batch="head-goal-r03",
        original_raw_sha256=RAW,
        original_text_sha256=sha(text.encode()),
        derived_output_sha256=sha(e.canonical(recovered)),
        original_request_sha256=sha(e.canonical(request)),
        duplicates=changes,
        new_provider_calls=0,
        model_first_structure_pass=False,
        assistant_text_edits=0,
    )
    candidate = dict(
        payload=payload,
        raw_output=recovered,
        parent_digest=None,
        candidate_digest=e.digest(
            "head-format-recovered-candidate",
            payload=payload,
            raw=recovered,
            recovery=recovery,
        ),
    )
    record = dict(
        candidate=candidate,
        recovery=recovery,
        original_context=context,
        plan_review=plan_review,
        model=result.model_id,
        usage=dict(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        ),
        request=request,
        receipt=read(VAULT / "generate.body.json"),
        observation=observation,
        evidence_kind="program_format_recovery",
    )
    if (HERE / "final-review.json").exists():
        review = read(HERE / "final-review.json")
        assert review["candidate_digest"] == candidate["candidate_digest"]
        assert review["planning_basis_binding"] == payload["planning_basis"]["binding"]
        assert (
            review["verdict"] in ("pass", "needs_revision")
            and review["independent_evaluator"]
        )
        record["independent_review"] = review
    from app.services.head_course_derivation import source

    assembled = e.m.assemble(payload, recovered, source(record))
    return {
        "original-output.txt": text.encode(),
        "recovered.record.json": e.canonical(record),
        "assembled.private.json": e.canonical(assembled),
    }


def main():
    outputs = derive()
    check = "--check" in sys.argv
    files = {}
    for name, b in outputs.items():
        if check:
            assert (HERE / name).read_bytes() == b, name
        else:
            if name == "original-output.txt" and (HERE / name).exists():
                assert (HERE / name).read_bytes() == b, name
            else:
                (HERE / name).write_bytes(b)
        files[name] = sha(b)
    manifest = e.canonical(dict(rule_version=VERSION, files=files))
    if check:
        assert (HERE / "artifacts.json").read_bytes() == manifest
    else:
        (HERE / "artifacts.json").write_bytes(manifest)
    print(
        "PASS: exact r03 originals/request/plan/materials; four identical duplicates removed; full wire/Schema/facts/scenarios/frames validated; new Provider calls 0."
    )


if __name__ == "__main__":
    main()
