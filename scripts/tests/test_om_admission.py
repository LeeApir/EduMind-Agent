"""Offline admission guard tests; synthetic keys/approvals, no real network or env."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import prepare_om_admission as prepare  # noqa: E402
import run_om_admission as runner  # noqa: E402
from acceptance_support.om_diagnostic import (  # noqa: E402
    BASE,
    PRIVATE,
    SLOTS,
    inputs,
    plan_draft,
    price,
    stable,
    valid_review,
)
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from app.core.config import ProviderSettings  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    return prepare.build()


def test_preparation_is_reproducible_and_has_separate_new_examples(prepared):
    assert prepared == prepare.build()
    p = prepared["proposal.json"]
    assert p["requests"] == 4 and p["requests_authorized"] == 0
    assert p["fees_authorized"] == 0
    assert p["cost_micro_cny"] == sum(price(s["wire_bytes"]) for s in p["slots"])
    assert list(prepared["cases.json"]) == list(SLOTS)
    assert p["formal_envelope_separate"]["status"] == "NOT_EXECUTABLE_NOT_AUTHORIZED"
    for c in prepared["cases.json"].values():
        raw = bytes.fromhex(c["wire_hex"])
        b = json.loads(raw)
        assert b["reasoning"] == {"effort": "none"}
        assert b["temperature"] == 0 and b["max_output_tokens"] == 2048
        assert "expected_automatic_result" not in raw.decode()
        assert not any(k in b for k in ("tools", "previous_response_id", "input_image"))


def test_runtime_needs_explicit_new_approval_before_key_dns_or_ledger(
    tmp_path, monkeypatch, prepared
):
    base = tmp_path / BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps(prepared["proposal.json"]))
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("premature key read")
    )
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        asyncio.run(
            runner.step(tmp_path, resolver=lambda *_: pytest.fail("premature DNS"))
        )
    assert not (tmp_path / PRIVATE).exists()


@pytest.mark.parametrize(
    "slot,verdict",
    [
        ("correct-unit", "reject"),
        ("reachable-safety", "pass"),
        ("fact-contradiction", "needs_human"),
    ],
)
def test_known_admission_failures_stop(slot, verdict, prepared):
    c = prepared["cases.json"][slot]
    value = valid_review(c["scope"])
    value["verdict"] = verdict
    if verdict == "needs_human":
        value["unresolved"] = ["unknown"]
    if verdict == "reject":
        value["findings"] = [
            {
                "category": "fact",
                "severity": "major",
                "anchors": [c["anchors"][0]["anchor_id"]],
                "condition_or_counterexample": "The actual claim has a contradiction.",
                "impact": "The returned result is wrong.",
            }
        ]
    with pytest.raises((GateFailure, ValueError)):
        asyncio.run(runner.assess(c, value, slot))


def test_category_alone_never_claims_semantic_detection(prepared):
    c = prepared["cases.json"]["reachable-safety"]
    v = valid_review("resource")
    v.update(
        verdict="reject",
        findings=[
            {
                "category": "fact",
                "severity": "major",
                "anchors": [c["anchors"][0]["anchor_id"]],
                "condition_or_counterexample": "Synthetic unrelated condition needs independent review.",
                "impact": "Synthetic unrelated effect needs independent review.",
            }
        ],
    )
    r = asyncio.run(runner.assess(c, v, "reachable-safety"))
    assert r["proposed_category_seen"] is False
    assert r["human_concrete_detection_check_required"] is True


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    p, data = deepcopy(prepared["proposal.json"]), deepcopy(prepared["cases.json"])
    p["execution_root"] = str(tmp_path.resolve())
    # Isolated synthetic prerequisite closure; no forged real approval file is written.
    paths = list(p["sources"])
    p["sources"] = {
        name: stable(name)
        for name in paths
        if name
        in (
            "backend/app/services/deepseek_responses.py",
            "docs/ADR/0015-approval-20261015.json",
            "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
        )
    }
    for name in p["sources"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(runner.canonical(name))
    base = tmp_path / BASE
    base.mkdir(parents=True)
    for name, value in prepared.items():
        (base / name).write_text(json.dumps(p if name == "proposal.json" else value))
    monkeypatch.setattr(runner, "load", lambda root: (p, {"synthetic": True}, data))
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda root: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    assess = runner.assess

    async def use_real_inputs(case, value, slot, root):
        return await assess(case, value, slot, ROOT)

    monkeypatch.setattr(runner, "assess", use_real_inputs)
    return tmp_path, p, data


class Stream(httpx.AsyncByteStream):
    def __init__(self, payload):
        self.payload = payload

    async def __aiter__(self):
        yield self.payload


def fake_transport(value, *, usage=True):
    calls = []

    def send(request):
        calls.append(request)
        result = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
        }
        if usage:
            result["usage"] = {"input_tokens": 90, "output_tokens": 30}
        return httpx.Response(200, stream=Stream(json.dumps(result).encode()))

    return httpx.MockTransport(send), calls


def test_reserves_before_send_and_requires_human_before_next(execution, monkeypatch):
    root, p, _ = execution
    transport, calls = fake_transport(plan_draft(inputs()))

    def credential(root):
        import sqlite3

        with sqlite3.connect(root / PRIVATE / "budget.sqlite") as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM attempts WHERE state='reserved'"
                ).fetchone()[0]
                == 1
            )
        return ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        )

    monkeypatch.setattr(runner, "credentials", credential)
    r = asyncio.run(
        runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
    )
    assert r["slot"] == "plan" and r["t040_passed"] is False and len(calls) == 1
    assert (root / PRIVATE / "plan.json").stat().st_mode & 0o077 == 0
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|HUMAN_CHECK_REQUIRED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["usage_unknown", "timeout", "reflection"])
def test_failure_halts_without_retry_or_refund(execution, mode):
    root, p, _ = execution
    value = plan_draft(inputs())
    if mode == "reflection":
        value["objectives"][0]["text"] = "SYNTHETIC_PRIVATE_KEY"
    transport, calls = fake_transport(value, usage=mode != "usage_unknown")
    if mode == "timeout":

        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout("SYNTHETIC_PRIVATE_KEY")

        transport = httpx.MockTransport(timeout)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    assert len(calls) == 1
    import sqlite3

    with sqlite3.connect(root / PRIVATE / "budget.sqlite") as db:
        n, cost = db.execute("SELECT count(*),sum(cost_micro) FROM attempts").fetchone()
        assert n == 1 and cost > 2000000
    assert not (root / PRIVATE / "plan.json").exists()


def test_exact_wire_drift_rejected_before_network(prepared):
    raw = bytes.fromhex(prepared["cases.json"]["plan"]["wire_hex"])
    audit = runner.ExactAudit(raw)
    request = httpx.Request("POST", "https://8.8.8.8/responses", content=raw + b" ")
    with pytest.raises(GateFailure, match="FREEZE_CHANGED"):
        asyncio.run(audit.handle_async_request(request))
    assert audit.sent == 0
    asyncio.run(audit.aclose())


def test_new_roster_does_not_reuse_formal_fixture_material(prepared):
    formal = json.loads(
        (
            ROOT / "docs/acceptance/phase-1-om-implementation/benchmark-materials.json"
        ).read_text()
    )
    new = json.dumps(prepared["cases.json"], ensure_ascii=False)
    assert (
        "{2,5,9}" in bytes.fromhex(prepared["cases.json"]["plan"]["wire_hex"]).decode()
    )
    assert "new-severe-" not in new and "new-correct-" not in new
    assert formal


def test_decoded_secret_reflection_is_rejected_even_when_json_escaped():
    value = json.loads('{"text":"SYNTHETIC_\\u0050RIVATE_KEY"}')
    assert runner.reflected(value, "SYNTHETIC_PRIVATE_KEY")
    assert not runner.reflected(
        {"text": "safe synthetic content"}, "SYNTHETIC_PRIVATE_KEY"
    )


@pytest.mark.parametrize("change", ["fee", "root", "labels", "expiry", "source"])
def test_new_approval_cannot_change_fee_root_labels_or_source(
    tmp_path, prepared, monkeypatch, change
):
    import time

    p = deepcopy(prepared["proposal.json"])
    p["execution_root"] = str(tmp_path.resolve())
    p["sources"] = {"sentinel": runner.sha(b"frozen")}
    (tmp_path / "sentinel").write_bytes(b"changed" if change == "source" else b"frozen")
    if change == "expiry":
        p["expiry_local"] = "2000-01-01T00:00:00+08:00"
    a = {
        "version": "om-admission-human-approval-v1",
        "proposal_sha256": stable(p),
        "requests": 4,
        "cost_micro_cny": p["cost_micro_cny"],
        "labels_sha256": p["labels_sha256"],
        "confirmed_by": "Lee",
        "user_confirmation": "synthetic-only",
        "source_message_id": "synthetic-only-not-real-authorization",
        "terms_verified_on": time.strftime("%Y-%m-%d"),
    }
    if change == "fee":
        a["cost_micro_cny"] += 1
    elif change == "root":
        a["proposal_sha256"] = "0" * 64
    elif change == "labels":
        a["labels_sha256"] = "0" * 64
    base = tmp_path / BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps(p))
    (base / "run-approval.json").write_text(json.dumps(a))
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("key before approval")
    )
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|FREEZE_CHANGED"):
        asyncio.run(runner.step(tmp_path))
    assert not (tmp_path / PRIVATE).exists()


def test_all_four_probes_need_exact_human_receipts_and_cannot_start_formal(execution):
    root, p, data = execution
    private = root / PRIVATE
    for slot in SLOTS:
        if slot == "plan":
            value = plan_draft(inputs())
        else:
            value = valid_review(data[slot]["scope"])
            if slot != "correct-unit":
                value.update(
                    verdict="reject",
                    findings=[
                        {
                            "category": "code_safety"
                            if slot == "reachable-safety"
                            else "fact",
                            "severity": "major",
                            "anchors": [data[slot]["anchors"][0]["anchor_id"]],
                            "condition_or_counterexample": "Synthetic exact condition for routing only.",
                            "impact": "Synthetic exact effect; not human-confirmed detection.",
                        }
                    ],
                )
        transport, calls = fake_transport(value)
        result = asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
        assert result["slot"] == slot and len(calls) == 1
        receipt = runner.read(private / (slot + ".json"))
        runner.private_write(
            private / (slot + "-human.json"),
            {
                "proposal_sha256": stable(p),
                "receipt_sha256": stable(receipt),
                "decision": "continue",
                "reviewer": "Lee",
                "source_message_id": "synthetic-only",
            },
        )
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(runner.step(root))
    assert not any(
        runner.read(private / (slot + ".json"))["t040_passed"] for slot in SLOTS
    )


def test_missing_ledger_and_interrupted_reservation_cannot_restart(execution):
    root, p, _ = execution
    private = root / PRIVATE
    private.mkdir(parents=True, mode=0o700)
    runner.private_write(private / "enrollment.json", {"proposal_sha256": stable(p)})
    with pytest.raises(GateFailure, match="LEDGER_MISSING"):
        asyncio.run(runner.step(root))


def test_interrupted_reserved_attempt_never_gets_replayed(execution, monkeypatch):
    root, p, data = execution
    private = root / PRIVATE
    private.mkdir(parents=True, mode=0o700)
    runner.private_write(private / "enrollment.json", {"proposal_sha256": stable(p)})
    m = runner.manifest(p, root)
    gate = runner.FrozenBudget(
        m,
        private / "budget.sqlite",
        root=root,
        approval=runner.Approval(
            stable(m),
            "diagnostic",
            4,
            p["cost_micro_cny"],
            stable({"synthetic": True}),
            True,
        ),
    )
    gate.reserve(
        "plan",
        "probe",
        next(iter(m["targets"])),
        bytes.fromhex(data["plan"]["wire_hex"]),
        resource="unit",
    )
    monkeypatch.setattr(
        runner, "credentials", lambda _: pytest.fail("interrupted request retried")
    )
    with pytest.raises(GateFailure, match="SEND_STATE_UNCERTAIN"):
        asyncio.run(runner.step(root))
    assert len(gate.snapshot()["attempts"]) == 1


@pytest.mark.parametrize("changed", [False, True])
def test_real_credential_reader_binds_metadata_without_printing_secret(
    tmp_path, changed
):
    path = tmp_path / ".env"
    path.write_text(
        "EDUMIND_PROVIDER_BASE_URL=https://api.deepseek.com\n"
        "EDUMIND_PROVIDER_MODEL=deepseek-flash\n"
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=responses_json_schema\n"
        "EDUMIND_PROVIDER_API_KEY=SYNTHETIC_PRIVATE_KEY\n"
    )
    path.chmod(0o600)
    st = path.stat()
    meta = {
        k: getattr(st, k)
        for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    }
    base = tmp_path / BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps({"credential_file_metadata": meta}))
    if changed:
        path.write_text(path.read_text() + "# changed\n")
        with pytest.raises(GateFailure, match="TARGET_CHANGED"):
            runner.credentials(tmp_path)
    else:
        settings = runner.credentials(tmp_path)
        assert settings.model == "deepseek-flash"


def test_wrong_control_retains_private_failure_evidence_and_halts(execution):
    root, p, data = execution
    # First plan is valid and separately acknowledged in this isolated synthetic test.
    transport, _ = fake_transport(plan_draft(inputs()))
    asyncio.run(runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"]))
    private = root / PRIVATE
    runner.private_write(
        private / "plan-human.json",
        {
            "proposal_sha256": stable(p),
            "receipt_sha256": stable(runner.read(private / "plan.json")),
            "decision": "continue",
            "reviewer": "Lee",
            "source_message_id": "synthetic-only",
        },
    )
    v = valid_review("unit")
    v["verdict"] = "needs_human"
    v["unresolved"] = ["Synthetic unknown"]
    transport, _ = fake_transport(v)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, transport=transport, resolver=lambda *_: ["8.8.8.8"])
        )
    failed = runner.read(private / "correct-unit-failed.json")
    assert failed["value"] == v and failed["input_tokens"] == 90
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
