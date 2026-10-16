"""Mock-only proof of candidate routing, frozen variables and non-bypassable screening."""

# ruff: noqa: E402
import asyncio
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "scripts/tests"),
    str(ROOT / "backend"),
]
import run_review_replacement
import run_evidence_v45 as historical
import test_review_suite as oldfixture
from test_evidence_v45 import answer, confirm, transport
from prepare_review_replacement import BASE, PRIOR, build, review_document
from acceptance_support.phase1_budget import GateFailure
from acceptance_support.review_replacement import (
    CandidateReviewGateway,
    candidate_config,
)
from app.services.learning_policy import active_policy_digest

r = run_review_replacement.core


@pytest.fixture(scope="module")
def prepared():
    return build()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    monkeypatch.setattr(oldfixture, "r", r)
    monkeypatch.setattr(oldfixture, "review_document", review_document)
    root, values = oldfixture.execution.__wrapped__(tmp_path, monkeypatch, prepared)
    path = root / BASE / "run-approval.json"
    a = r.read(path)
    a["requests"] = 4
    path.write_text(json.dumps(a))
    prior = root / PRIOR / "cases.json"
    prior.parent.mkdir(parents=True)
    prior.write_bytes((ROOT / PRIOR / "cases.json").read_bytes())
    # Helper functions operate on the isolated kernel, never the historical module instance.
    import test_evidence_v45

    monkeypatch.setattr(test_evidence_v45, "r", r)
    return root, values


def test_real_entry_capture_all_four_exact_single_variable_and_policy(prepared):
    old = r.read(ROOT / PRIOR / "cases.json")
    for slot, c in prepared["cases.json"].items():
        before, after = deepcopy(old[slot]), deepcopy(c)
        left = json.loads(bytes.fromhex(before.pop("wire_hex")))
        right = json.loads(bytes.fromhex(after.pop("wire_hex")))
        assert before == after
        assert left.pop("reasoning") == {"effort": "low"}
        assert right.pop("reasoning") == {"effort": "high"}
        assert left == right
        capture = prepared["offline-capture.json"][slot]
        assert capture["actual_wire_sha256"] == r.sha(bytes.fromhex(c["wire_hex"]))
        assert (
            capture["policy_digest"]
            == active_policy_digest()
            == c["material"]["binding"]["policy_digest"]
        )
        assert capture["kind"] == "OFFLINE_SYNTHETIC_NOT_QUALITY_EVIDENCE"
    p = prepared["proposal.json"]
    assert p["requests"] == 4 and p["cost_micro_cny"] == 9010516
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert p["candidate_config_sha256"] == r.stable(candidate_config())
    assert build() == prepared
    assert historical.BASE == PRIOR and historical.PRIVATE != r.PRIVATE


def test_preparation_cannot_read_credentials_or_access_dns(monkeypatch, prepared):
    read_text = Path.read_text
    read_bytes = Path.read_bytes

    def safe_text(path, *a, **kw):
        assert path.name != ".env"
        return read_text(path, *a, **kw)

    def safe_bytes(path, *a, **kw):
        assert path.name != ".env"
        return read_bytes(path, *a, **kw)

    monkeypatch.setattr(Path, "read_text", safe_text)
    monkeypatch.setattr(Path, "read_bytes", safe_bytes)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS in preparation")
    )
    assert build() == prepared


def test_candidate_name_only_or_wrong_effort_is_rejected():
    from app.core.config import ProviderSettings

    config = candidate_config()
    config["reasoning_effort"] = "low"
    with pytest.raises(ValueError, match="CANDIDATE_CONFIG_MISMATCH"):
        CandidateReviewGateway(
            config,
            ProviderSettings("https://api.deepseek.com", "SYNTHETIC", "deepseek-flash"),
            None,
            transport=None,
        )


def test_unapproved_gate_before_credentials_dns_and_private_dir(
    tmp_path, prepared, monkeypatch
):
    base = tmp_path / BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps(prepared["proposal.json"]))
    monkeypatch.setattr(r, "credentials", lambda *_: pytest.fail("Key before approval"))
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        asyncio.run(
            r.step(tmp_path, resolver=lambda *_: pytest.fail("DNS before approval"))
        )
    assert not (tmp_path / r.PRIVATE).exists()


def test_actual_replay_four_mock_calls_equal_review_entry_capture(execution):
    root, values = execution
    calls = []
    for slot, c in values["cases.json"].items():
        result = asyncio.run(
            r.step(
                root,
                transport=transport(answer(c), calls),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
        assert (
            result["slot"] == slot
            and len(calls) == list(values["cases.json"]).index(slot) + 1
        )
        assert calls[-1] == bytes.fromhex(c["wire_hex"])
        assert (
            r.sha(calls[-1])
            == values["offline-capture.json"][slot]["actual_wire_sha256"]
        )
        receipt = r.read(root / r.PRIVATE / (slot + ".json"))
        assert not receipt["human_confirmed"] and not receipt["t040_passed"]
        if slot != r.SLOT_IDS[-1]:
            with pytest.raises(GateFailure):
                asyncio.run(
                    r.step(root, resolver=lambda *_: pytest.fail("before human check"))
                )
        confirm(root, values, slot)
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 4


@pytest.mark.parametrize(
    "badflag",
    [
        "completeness_checked",
        "all_assertions_checked",
        "all_citations_checked",
        "issues",
    ],
)
def test_any_failed_independent_check_blocks_next(execution, badflag):
    root, values = execution
    calls = []
    slot = r.SLOT_IDS[0]
    asyncio.run(
        r.step(
            root,
            transport=transport(answer(values["cases.json"][slot]), calls),
            resolver=lambda *_: ["8.8.8.8"],
        )
    )
    confirm(
        root,
        values,
        slot,
        **{badflag: ["unsupported assertion"] if badflag == "issues" else False},
    )
    with pytest.raises(GateFailure, match="HUMAN_CHECK_REQUIRED"):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert len(calls) == 1


def test_candidate_protocol_failure_halts_without_retry_or_next(execution):
    root, values = execution
    calls = []
    bad = answer(values["cases.json"][r.SLOT_IDS[0]])
    bad["unresolved"] = [{"invalid": "type"}]
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            r.step(
                root, transport=transport(bad, calls), resolver=lambda *_: ["8.8.8.8"]
            )
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("retry DNS")))
    assert len(calls) == 1


def test_resigned_effort_tamper_rejected_before_credential(execution, monkeypatch):
    root, values = execution
    base = root / BASE
    data = r.read(base / "cases.json")
    slot = r.SLOT_IDS[0]
    body = json.loads(bytes.fromhex(data[slot]["wire_hex"]))
    body["reasoning"] = {"effort": "low"}
    import httpx

    raw = httpx.Request("POST", "https://api.deepseek.com/responses", json=body).content
    data[slot]["wire_hex"] = raw.hex()
    p = r.read(base / "proposal.json")
    p["cases_sha256"] = r.stable(data)
    s = p["slots"][0]
    s.update(
        wire_bytes=len(raw),
        wire_sha256=r.sha(raw),
        cost_micro_cny=2 * (1048576 + len(raw)) + 8 * 8192,
    )
    p["cost_micro_cny"] = sum(s["cost_micro_cny"] for s in p["slots"])
    a = r.read(base / "run-approval.json")
    a.update(proposal_sha256=r.stable(p), cost_micro_cny=p["cost_micro_cny"])
    labels_record = r.read(base / "labels-human.json")
    labels_record["proposal_sha256"] = r.stable(p)
    for name, v in [
        ("cases.json", data),
        ("proposal.json", p),
        ("run-approval.json", a),
        ("labels-human.json", labels_record),
    ]:
        (base / name).write_text(json.dumps(v))
    monkeypatch.setattr(
        r, "credentials", lambda *_: pytest.fail("Key on tampered effort")
    )
    with pytest.raises(GateFailure, match="CANDIDATE_BINDING_CHANGED"):
        asyncio.run(r.step(root))


def test_gateway_rejects_generation_profile_and_wrong_policy(prepared):
    from dataclasses import replace
    import httpx
    from app.core.config import ProviderSettings
    from app.services.provider_gateway import (
        ChatMessage,
        StructuredRequest,
        TaskProfile,
        TextRequest,
    )
    from prepare_review_replacement import OfflineGuard

    case = prepared["cases.json"][r.SLOT_IDS[0]]
    body = json.loads(bytes.fromhex(case["wire_hex"]))
    gateway = CandidateReviewGateway(
        candidate_config(),
        ProviderSettings("https://api.deepseek.com", "SYNTHETIC", "deepseek-flash"),
        OfflineGuard(),
        transport=httpx.MockTransport(
            lambda *_: pytest.fail("invalid request reached HTTP")
        ),
    )
    prompt = TextRequest(
        tuple(ChatMessage(m["role"], m["content"]) for m in body["input"]),
        task_profile=TaskProfile.DEFAULT,
        max_output_tokens=2048,
    )
    with pytest.raises(ValueError, match="NOT_BOUND_REVIEW_REQUEST"):
        asyncio.run(
            gateway.generate_structured(
                StructuredRequest(prompt, body["text"]["format"]["schema"])
            )
        )
    user = json.loads(body["input"][1]["content"])
    user["unit"]["binding"]["policy_digest"] = "0" * 64
    prompt = replace(
        prompt,
        task_profile=TaskProfile.QUALITY,
        messages=(prompt.messages[0], ChatMessage("user", json.dumps(user))),
    )
    with pytest.raises(ValueError, match="NOT_BOUND_REVIEW_REQUEST"):
        asyncio.run(
            gateway.generate_structured(
                StructuredRequest(prompt, body["text"]["format"]["schema"])
            )
        )
    assert gateway.calls == []


def test_semantic_failure_halt_keeps_receipt_and_blocks_remaining(execution):
    import fcntl
    import os
    from acceptance_support.phase1_budget import Approval, FrozenBudget

    root, values = execution
    slot = r.SLOT_IDS[0]
    calls = []
    value = answer(values["cases.json"][slot])
    value["findings"].append(
        {
            **value["findings"][0],
            "category": "fact",
            "condition_or_counterexample": "SYNTHETIC_UNSUPPORTED_NUMERIC_ASSERTION",
        }
    )
    asyncio.run(
        r.step(root, transport=transport(value, calls), resolver=lambda *_: ["8.8.8.8"])
    )
    private = root / r.PRIVATE
    receipt = r.read(private / (slot + ".json"))
    digest = r.stable(receipt)
    assert not receipt["local_assessment"]["semantic_detection_confirmed"]
    fd = os.open(private / "execution.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        p = values["proposal.json"]
        a = r.read(root / BASE / "run-approval.json")
        m = r.manifest(p, root)
        gate = FrozenBudget(
            m,
            private / "budget.sqlite",
            root=root,
            approval=Approval(
                r.stable(m), "diagnostic", 4, p["cost_micro_cny"], r.stable(a), True
            ),
        )
        gate.halt("ADMISSION_FAILED")
        assert gate.snapshot()["attempts"][0][6] == "complete"
    finally:
        os.close(fd)
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(
            r.step(root, resolver=lambda *_: pytest.fail("DNS after elimination"))
        )
    assert r.stable(r.read(private / (slot + ".json"))) == digest and len(calls) == 1
