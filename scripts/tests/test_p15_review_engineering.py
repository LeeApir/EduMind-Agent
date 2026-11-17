"""Real-size offline regressions; no provider calls or changes to frozen evidence."""

import hashlib
import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.isolated_diagnostics import p15_review_engineering as e
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_combined_candidate_contract as old_contract
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.isolated_diagnostics.p15_pilot_wire import PilotError
from scripts.tests.test_p15_combined_candidate_contract import response

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01/results"
RAW_REVIEW = ROOT / "docs/acceptance/phase-1.5-course-review-once-r01/response.bin"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def example():
    artifact = json.loads((RESULT / "candidate.json").read_text())
    catalog = c.make_catalog(old_contract.SPEC)
    raw, binding = e.build_review(artifact, catalog)
    return raw, binding, artifact, catalog


def test_real_candidate_compact_preserves_all_content_and_targets():
    raw, binding, artifact, catalog = example()
    payload = json.loads(json.loads(raw)["input"][1]["content"])
    assert len(raw) == 59507 and len(raw) < e.POLICY.request_bytes
    assert (
        payload["artifact"] == artifact and payload["reference"] == catalog["example"]
    )
    assert (
        set(payload["target_catalog"]) == set(binding["targets"])
        and len(binding["targets"]) == 181
    )
    for key, row in binding["targets"].items():
        assert payload["target_catalog"][key] == {
            "path": row["path"],
            "text": row["text"],
        }


def test_one_policy_controls_request_and_postresponse_tokens():
    raw, binding, artifact, catalog = example()
    with pytest.raises(c.ContractError, match="REVIEW_REQUEST_SIZE"):
        e.build_review(artifact, catalog, replace(e.POLICY, request_bytes=len(raw) - 1))
    opinion = dict(
        candidate_id=binding["candidate_id"], verdict="pass", uncertainty="", issues=[]
    )
    v = json.loads(response(raw, opinion))
    v["usage"]["input_tokens"] = e.POLICY.input_tokens
    v["usage"]["total_tokens"] = e.POLICY.input_tokens + v["usage"]["output_tokens"]
    assert e.observe_review(raw, canonical(v), binding)[0] == opinion
    v["usage"]["input_tokens"] += 1
    v["usage"]["total_tokens"] += 1
    with pytest.raises(c.ContractError, match="REVIEW_TOKEN_BOUND"):
        e.observe_review(raw, canonical(v), binding)


def test_real_response_bounded_quarantine_preserves_original_and_remains_over_budget():
    raw, binding, _, _ = example()
    original = RAW_REVIEW.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    v = json.loads(original)
    with pytest.raises(c.ContractError, match="REVIEW_TOKEN_BOUND"):
        e.observe_review(raw, original, binding)
    v["usage"]["input_tokens"] = 32768
    v["usage"]["total_tokens"] = 32768 + v["usage"]["output_tokens"]
    result, obs = e.observe_review(raw, canonical(v), binding)
    assert (
        result["verdict"] == "pass"
        and obs["encrypted_content_quarantined"]
        and not obs["semantic_pass"]
    )
    assert hashlib.sha256(RAW_REVIEW.read_bytes()).hexdigest() == sha


@pytest.mark.parametrize(
    "kind",
    [
        "oversized",
        "wrongtype",
        "unknownfield",
        "badphase",
        "wrongcandidate",
        "badquote",
        "missingecho",
        "outputbudget",
    ],
)
def test_invalid_protocol_never_passes(kind):
    raw, binding, _, _ = example()
    target, entry = next(
        (k, v)
        for k, v in binding["targets"].items()
        if v["path"] == "/raw_output/paragraphs/0/text"
    )
    opinion = dict(
        candidate_id=binding["candidate_id"],
        verdict="revise",
        uncertainty="",
        issues=[
            dict(
                severity="minor",
                area="difficulty",
                target_id=target,
                evidence_quote=entry["text"][:8],
                reason="Clarify wording",
            )
        ],
    )
    v = json.loads(response(raw, opinion))
    reason = dict(
        type="reasoning",
        id="reason",
        summary=[],
        content=[],
        encrypted_content="x" * 10,
    )
    v["output"].insert(0, reason)
    if kind == "oversized":
        reason["encrypted_content"] = "x" * (e.POLICY.encrypted_reasoning_chars + 1)
    if kind == "wrongtype":
        reason["encrypted_content"] = ["x"]
    if kind == "unknownfield":
        reason["unapproved"] = "x"
    if kind == "badphase":
        v["output"][1]["phase"] = "commentary"
    if kind == "wrongcandidate":
        opinion["candidate_id"] = "candidate_other"
    if kind == "badquote":
        opinion["issues"][0]["evidence_quote"] = "not present anywhere xyz"
    if kind in ("wrongcandidate", "badquote"):
        v["output"][1]["content"][0]["text"] = json.dumps(opinion)
    if kind == "missingecho":
        del v["text"]
    if kind == "outputbudget":
        v["usage"]["output_tokens"] = 8001
        v["usage"]["total_tokens"] = v["usage"]["input_tokens"] + 8001
    with pytest.raises((ValueError, PilotError, c.ContractError)):
        e.observe_review(raw, canonical(v), binding)


def test_actual_terminal_summary_does_not_regenerate_oversized_next_request():
    rawdir = RESULT / "originals"
    grant = json.loads((rawdir / "grant.json").read_text())
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in rawdir.iterdir()
    }
    summary = e.stopped_summary(rawdir, grant["package_sha256"], grant)
    assert (
        summary["outcome"] == "stopped"
        and len(summary["validated"]) == 9
        and summary["workflow_stage_at_stop"] == "course_review_0"
    )
    assert (
        summary["unknown_sent"] == 0
        and not summary["resumed"]
        and not summary["teaching_evaluated"]
    )
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in rawdir.iterdir()
    }


def test_reject_extra_response_field_even_if_otherwise_quarantined():
    raw, binding, _, _ = example()
    v = json.loads(
        response(
            raw,
            dict(
                candidate_id=binding["candidate_id"],
                verdict="pass",
                uncertainty="",
                issues=[],
            ),
        )
    )
    v["output"].insert(
        0,
        dict(
            type="reasoning",
            id="r",
            summary=[],
            content=[],
            encrypted_content="cipher",
            unexpected="x",
        ),
    )
    with pytest.raises(PilotError):
        e.observe_review(raw, canonical(v), binding)


def test_attempt_reservation_and_response_use_identical_policy_and_are_single_use():
    raw, binding, artifact, catalog = example()
    attempt = e.ReviewAttempt(artifact, catalog)
    assert attempt.request == raw and attempt.reservation == dict(
        input_tokens=32768,
        output_tokens=8000,
        request_bytes=65536,
        response_bytes=65536,
    )
    opinion = dict(
        candidate_id=binding["candidate_id"],
        verdict="unknown",
        uncertainty="Not enough context",
        issues=[],
    )
    value, obs = attempt.observe(response(raw, opinion))
    assert value == opinion and not obs["semantic_pass"]
    with pytest.raises(c.ContractError, match="ATTEMPT_CLOSED"):
        attempt.observe(response(raw, opinion))
    with pytest.raises(c.ContractError, match="UNDERLYING_WIRE_LIMIT"):
        e.ReviewAttempt(artifact, catalog, replace(e.POLICY, response_bytes=65537))


def test_stopped_summary_rejects_unbound_file_and_modified_response(tmp_path):
    import shutil

    rawdir = RESULT / "originals"
    dest = tmp_path / "copy"
    shutil.copytree(rawdir, dest)
    grant = json.loads((dest / "grant.json").read_text())
    (dest / "course_repair-request.json").write_text("{}")
    with pytest.raises(c.ContractError, match="UNBOUND_RESULT_FILE"):
        e.stopped_summary(dest, grant["package_sha256"], grant)
    (dest / "course_repair-request.json").unlink()
    file = dest / "S1-response.bin"
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(ValueError, match="COMBINED_RESPONSE_BINDING"):
        e.stopped_summary(dest, grant["package_sha256"], grant)


def test_all_compact_targets_remain_quoteable_with_full_local_binding():
    raw, binding, _, _ = example()
    payload = json.loads(json.loads(raw)["input"][1]["content"])
    for target, row in binding["targets"].items():
        quote = row["text"][:1]
        assert quote and quote in payload["target_catalog"][target]["text"]
        opinion = dict(
            candidate_id=binding["candidate_id"],
            verdict="revise",
            uncertainty="",
            issues=[
                dict(
                    severity="minor",
                    area="difficulty",
                    target_id=target,
                    evidence_quote=quote,
                    reason="synthetic location",
                )
            ],
        )
        c.validate("review_C", opinion, binding=binding)
