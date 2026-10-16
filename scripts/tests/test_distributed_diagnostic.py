"""One immutable original request, isolated approval and no second send, using Mock HTTP."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]

from acceptance_support.om_diagnostic import stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from prepare_distributed_diagnostic import build, review_document  # noqa: E402
from run_distributed_diagnostic import BASE, PRIVATE, SLOT, runtime  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    return build()


def test_freeze_has_one_byte_identical_case_and_exact_original_limits(prepared):
    prior = json.loads(
        (ROOT / "docs/acceptance/phase-1-review-config-r01/cases.json").read_text()
    )
    data = prepared["cases.json"]
    assert tuple(data) == (SLOT,)
    assert data[SLOT] == prior[SLOT]
    body = json.loads(bytes.fromhex(data[SLOT]["wire_hex"]))
    assert body["model"] == "deepseek-flash"
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 2048
    assert "tools" not in body and "previous_response_id" not in body
    p = prepared["proposal.json"]
    assert p["requests"] == 1 and p["requests_authorized"] == p["fees_authorized"] == 0
    assert p["cost_micro_cny"] == 2198030
    assert p["cost_micro_cny"] == 2 * (1048576 + p["slots"][0]["wire_bytes"]) + 8 * 2048
    assert build() == prepared


def test_default_and_old_runner_globals_are_never_retargeted():
    import run_review_config_comparison as old
    import run_review_config_observed as observed

    first, second = runtime(), runtime()
    assert first is not second
    assert first.REQUESTS == 1 and first.SLOT_IDS == (SLOT,)
    assert first.BASE == BASE and first.PRIVATE == PRIVATE
    assert observed.REQUESTS == 14 and observed.BASE.endswith("review-config-r02")
    assert old.BASE.endswith("review-config-r01")


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    runner = runtime()
    values = deepcopy(prepared)
    p, data = values["proposal.json"], values["cases.json"]
    p["execution_root"] = str(tmp_path.resolve())
    p["expiry_local"] = "2099-01-01T00:00:00+08:00"
    values["token-cost-proof.json"]["checked_on"] = runner.time.strftime("%Y-%m-%d")
    p["proof_sha256"] = stable(values["token-cost-proof.json"])
    names = (
        "backend/app/services/deepseek_responses.py",
        "docs/ADR/0015-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    )
    p["sources"] = {n: stable(n) for n in names}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(runner.canonical(name))
    base = tmp_path / BASE
    base.mkdir(parents=True)
    for name, value in values.items():
        (base / name).write_text(json.dumps(value))
    (base / "human-review.md").write_text(review_document(data))
    (base / "run-approval.json").write_text(
        json.dumps(
            {
                "version": "om-admission-human-approval-v1",
                "proposal_sha256": stable(p),
                "requests": 1,
                "cost_micro_cny": p["cost_micro_cny"],
                "labels_sha256": p["labels_sha256"],
                "confirmed_by": "Lee",
                "user_confirmation": "SYNTHETIC_ONLY",
                "source_message_id": "synthetic",
                "terms_verified_on": runner.time.strftime("%Y-%m-%d"),
            }
        )
    )
    (base / "labels-human.json").write_text(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "labels_sha256": p["labels_sha256"],
                "case_digests": {n: stable(c["material"]) for n, c in data.items()},
                "decision": "accept_calibration_labels",
                "reviewer": "Lee",
                "source_message_id": "synthetic",
            }
        )
    )
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda _: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    return runner, tmp_path, values


@pytest.mark.parametrize(
    "change", ["approval", "labels", "source", "wire", "readable", "terms"]
)
def test_gates_precede_key_dns_and_ledger(execution, monkeypatch, change):
    runner, root, values = execution
    base = root / BASE
    if change in ("approval", "labels"):
        (
            base
            / ("run-approval.json" if change == "approval" else "labels-human.json")
        ).unlink()
    elif change == "source":
        (root / next(iter(values["proposal.json"]["sources"]))).write_text("changed")
    elif change == "readable":
        (base / "human-review.md").write_text("changed")
    else:
        (
            base / ("cases.json" if change == "wire" else "token-cost-proof.json")
        ).write_text("{}")
    monkeypatch.setattr(runner, "credentials", lambda _: pytest.fail("premature key"))
    with pytest.raises(GateFailure):
        asyncio.run(runner.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / PRIVATE).exists()


def payload():
    return {
        "model": "deepseek-flash",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": json.dumps(valid_review("unit"))}
                ],
            }
        ],
        "usage": {"input_tokens": 90, "output_tokens": 30},
    }


@pytest.mark.parametrize("confirm", [False, True])
def test_success_exhausts_one_slot_even_with_continuation(execution, confirm):
    runner, root, values = execution
    calls = []

    def send(request):
        calls.append(request)
        assert request.content == bytes.fromhex(values["cases.json"][SLOT]["wire_hex"])
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(payload()).encode())
        )

    result = asyncio.run(
        runner.step(
            root, transport=httpx.MockTransport(send), resolver=lambda *_: ["8.8.8.8"]
        )
    )
    assert result["slot"] == SLOT and result["requests_sent_this_step"] == 1
    receipt = runner.read(root / PRIVATE / (SLOT + ".json"))
    assert receipt["local_assessment"]["route"]["verdict"] == "pass"
    assert receipt["local_assessment"]["semantic_detection_confirmed"] is False
    if confirm:
        runner.private_write(
            root / PRIVATE / (SLOT + "-human.json"),
            {
                "proposal_sha256": stable(values["proposal.json"]),
                "receipt_sha256": stable(receipt),
                "decision": "continue",
                "reviewer": "Lee",
                "source_message_id": "synthetic",
            },
        )
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: pytest.fail("second DNS"),
            )
        )
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["cutoff", "network", "semantic"])
def test_failure_keeps_diagnostics_and_cannot_retry(execution, mode):
    runner, root, _ = execution
    value = payload()
    if mode == "cutoff":
        value.update(
            status="incomplete", incomplete_details={"reason": "max_output_tokens"}
        )
        value["usage"]["output_tokens"] = 2048
    if mode == "semantic":
        review = valid_review("unit")
        review.update(
            verdict="needs_human", unresolved=["Synthetic ungrounded uncertainty"]
        )
        value["output"][0]["content"][0]["text"] = json.dumps(review)
    calls = []

    def send(request):
        calls.append(request)
        if mode == "network":
            raise httpx.ConnectError("SYNTHETIC_ERROR_TEXT")
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(value).encode()))

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    path = root / PRIVATE / (SLOT + "-failure-observation.json")
    assert path.stat().st_mode & 0o077 == 0
    observation = runner.read(path)["observation"]
    assert observation["transport_dispatch_count"] == 1
    if mode == "cutoff":
        assert observation["output_failure_reason"] == "OUTPUT_TOKEN_LIMIT"
        assert observation["output_tokens_including_reasoning"] == 2048
    elif mode == "network":
        assert (
            observation["input_tokens"] is None and observation["http_status"] is None
        )
    else:
        assert observation["local_gate_code"] == "CANDIDATE_CRITERION_FAILED"
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["request_count", "slot"])
def test_synthetic_approval_cannot_widen_hard_single_case_boundary(
    execution, monkeypatch, change
):
    runner, root, values = execution
    base = root / BASE
    p, data = values["proposal.json"], values["cases.json"]
    approval = runner.read(base / "run-approval.json")
    labels = runner.read(base / "labels-human.json")
    if change == "request_count":
        p["requests"] = approval["requests"] = 14
    else:
        data["trace-complete:candidate"] = data.pop(SLOT)
        p["slots"][0]["id"] = "trace-complete:candidate"
        p["cases_sha256"] = stable(data)
        labels["case_digests"] = {n: stable(c["material"]) for n, c in data.items()}
        (base / "cases.json").write_text(json.dumps(data))
    approval["proposal_sha256"] = labels["proposal_sha256"] = stable(p)
    for name, value in [
        ("proposal.json", p),
        ("run-approval.json", approval),
        ("labels-human.json", labels),
    ]:
        (base / name).write_text(json.dumps(value))
    monkeypatch.setattr(runner, "credentials", lambda _: pytest.fail("premature key"))
    with pytest.raises(GateFailure):
        asyncio.run(runner.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / PRIVATE).exists()
