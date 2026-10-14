"""Diagnostic execution boundaries with synthetic data only; no actual network or key."""

import asyncio
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_t040_diagnostics as runner  # noqa: E402
from acceptance_support.phase1_budget import (  # noqa: E402
    Approval,
    FrozenBudget,
    GateFailure,  # noqa: E402
    canonical,
    sha,
)


def review(verdict="reject", area="fact"):
    return {
        "review_version": "resource-review-v3",
        "verdict": verdict,
        "issues": []
        if verdict == "pass"
        else [{"area": area, "severity": "major", "message": "Synthetic concrete issue."}],
    }


def test_fact_classification_is_not_mistaken_for_memory_safety():
    assert runner.coarse_quality_failure("classification", review(), "fact") is None
    assert (
        runner.coarse_quality_failure("classification", review(), "code_safety")
        == "ADMISSION_FAILED"
    )
    assert (
        runner.coarse_quality_failure("classification", review(area="code_safety"), "code_safety")
        is None
    )


def test_known_error_pass_or_control_rejection_halts():
    assert (
        runner.coarse_quality_failure("error_detection", review("pass"), "fact")
        == "CONCRETE_DEFECT_MISSED"
    )
    assert runner.coarse_quality_failure("correct_control", review(), "pass") == "CONTROL_REJECTED"
    assert runner.coarse_quality_failure("long_review", review(), "structured_result") is None
    assert runner.coarse_quality_failure("error_detection", review(), "fact") is None
    # None means no certain automated failure, never human-confirmed detection.


def test_missing_approval_stops_before_key_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "BASE", tmp_path)
    (tmp_path / "proposal.json").write_text(json.dumps({"groups": []}))
    (tmp_path / "diagnostic-approval.json").write_text(json.dumps({"approved": False}))
    monkeypatch.setattr(
        runner, "configured", lambda *_: pytest.fail("key/config accessed before approval")
    )
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        asyncio.run(runner.run_one("error_detection"))


def test_later_group_requires_human_evidence(monkeypatch):
    class Gate:
        def snapshot(self):
            return {"halted": None, "unattempted_slots": ["unfinished"]}

    monkeypatch.setattr(runner, "budget", lambda _: Gate())
    with pytest.raises(GateFailure, match="PREREQUISITE_MISSING"):
        runner.require_prior_group("classification")


def test_private_evidence_is_not_overwritten_or_symlinked(tmp_path):
    path = tmp_path / "result.json"
    runner.private_write(path, {"synthetic": True})
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        runner.private_write(path, {"changed": True})
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        runner.private_write(link, {})


def test_vendor_error_body_never_persisted_as_raw_evidence():
    assert runner.retain_generated_response(b'{"status":"failed","error":"PRIVATE"}') is None
    assert runner.retain_generated_response(b"non-json PRIVATE") is None
    data = {
        "status": "completed",
        "model": "synthetic",
        "output": [],
        "usage": {},
        "arbitrary_header": "PRIVATE",
    }
    retained = runner.retain_generated_response(json.dumps(data).encode())
    assert "arbitrary_header" not in retained and retained["output"] == []


@pytest.mark.parametrize("usage_known", [True, False])
def test_full_sender_reserves_before_key_and_production_http_parser(
    tmp_path, monkeypatch, usage_known
):
    original_base = runner.BASE
    body = runner.read(original_base / "requests.json")["error_detection:01"]
    slot = "error_detection:01"
    model_response = {
        "status": "completed",
        "model": "deepseek-flash",
        "error": None,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(review())}],
            }
        ],
    }
    if usage_known:
        model_response["usage"] = {"input_tokens": 100, "output_tokens": 40}
    template = runner.read(
        runner.ROOT / "docs/acceptance/phase-1-deepseek-connection-v1/run-r01.json"
    )
    manifest = copy.deepcopy(template)
    (tmp_path / "approved.txt").write_text("synthetic offline approval")
    digest = sha((tmp_path / "approved.txt").read_bytes())
    target_id, target = next(iter(manifest["targets"].items()))
    target.update(max_wire_bytes=len(canonical(body)), max_total_output_tokens=4096)
    manifest.update(
        phase="diagnostic",
        files={"approved.txt": digest},
        required_evidence=["adr", "connection"],
        evidence={"adr": digest, "connection": digest},
        slots=[
            {
                "id": slot,
                "input_sha256": sha(canonical(body)),
                "attempts": 1,
                "stages": ["review"],
                "resources": ["unit"],
                "targets": [target_id],
            }
        ],
    )
    manifest["bounds"].update(requests=1, cost_micro=60000, timeout_seconds=60)
    gate = FrozenBudget(
        manifest,
        tmp_path / "budget.sqlite",
        root=tmp_path,
        approval=Approval(sha(canonical(manifest)), "diagnostic", 1, 60000, "a" * 64, True),
    )
    (tmp_path / "requests.json").write_text(json.dumps({slot: body}))
    monkeypatch.setattr(runner, "BASE", tmp_path)
    monkeypatch.setattr(runner, "RAW", tmp_path / "raw")
    monkeypatch.setattr(runner, "budget", lambda _: gate)
    monkeypatch.setattr(runner, "require_prior_group", lambda _: None)
    monkeypatch.setattr(
        runner,
        "approval_record",
        lambda: (
            {
                "groups": [
                    {
                        "slots": [
                            {
                                "slot": slot,
                                "historical_case_id": "linked-list-concept:explanation:1",
                            }
                        ]
                    }
                ]
            },
            {},
        ),
    )
    configured_values = {
        "EDUMIND_PROVIDER_BASE_URL": "https://api.deepseek.com",
        "EDUMIND_PROVIDER_MODEL": "deepseek-flash",
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT": "responses_json_schema",
        "EDUMIND_PROVIDER_API_KEY": "synthetic-secret",
    }

    def configured(name):
        if name.endswith("API_KEY"):
            assert len(gate.snapshot()["attempts"]) == 1
        return configured_values[name]

    monkeypatch.setattr(runner, "configured", configured)
    real_guard = runner.ProviderTargetGuard
    monkeypatch.setattr(
        runner,
        "ProviderTargetGuard",
        lambda url, policy: real_guard(url, policy, resolver=lambda *_: ("8.8.8.8",)),
    )
    audits = []
    original_audit = runner.Audit

    class ResponseBytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(model_response).encode()

    def audit(body):
        value = original_audit(body)
        value.inner = httpx.MockTransport(lambda _: httpx.Response(200, stream=ResponseBytes()))
        audits.append(value)
        return value

    monkeypatch.setattr(runner, "Audit", audit)
    asyncio.run(runner.run_one("error_detection"))
    assert audits[0].sent == 1
    state = gate.snapshot()
    assert len(state["attempts"]) == 1
    assert state["halted"] == (None if usage_known else "USAGE_UNKNOWN")
    saved = runner.read(tmp_path / "raw/error_detection/error_detection-01.json")
    assert saved["protocol_passed"] and saved["human_confirmed"] is False
    assert "synthetic-secret" not in json.dumps(saved)
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED|RUN_HALTED"):
        asyncio.run(runner.run_one("error_detection"))
    assert audits[0].sent == 1
