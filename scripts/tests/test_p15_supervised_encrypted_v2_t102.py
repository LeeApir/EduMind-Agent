"""Synthetic process, authenticated vault, stop, and recovery tests."""

import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts.isolated_diagnostics import p15_controlled_mock_v2 as base
from scripts.isolated_diagnostics import p15_encrypted_controller_v2 as encrypted
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_supervised_mock_v2 as supervised
from scripts.isolated_diagnostics import p15_synthetic_guard_v2 as guard
from scripts.isolated_diagnostics import p15_synthetic_vault_v1 as vault_module
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant, package_grant
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC

KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}


def new_controller(path, *, arm="B", scenario="chain", package=None, marker=None, wall=30.0):
    transport = supervised.SupervisedMockTransport(KEYS, scenario=scenario, marker_dir=marker, wall_seconds=wall)
    args = {"selected": ("slot", arm)} if package is not None else {}
    instance = encrypted.EncryptedController(path, package or grant(arm, path), transport, **args)
    return instance, transport


def assert_no_synthetic_provider_keys(root):
    for file in root.rglob("*"):
        if file.is_file() and not file.is_symlink():
            raw = file.read_bytes()
            assert all(key.encode() not in raw for key in KEYS.values()), file.name


def seed_synthetic_proof(instance):
    instance.transport.audit.append(dict(
        pid=12345, role="generation", stage="B_generate", ordinal=0,
        target="https://api.deepseek.com/responses", ip="1.1.1.1", host="api.deepseek.com",
        sni="api.deepseek.com", request_sha256=hashlib.sha256(b"{}").hexdigest(),
        credential_roles=["generation"], provider_env_present=False,
        transport_kind="httpx-async-http-transport-core-intercepted",
        tls_verification_configured=True, retries=0,
    ))


def test_complete_both_arms_use_nine_real_subprocesses_and_encrypted_receipts(tmp_path, monkeypatch):
    def no_fork(*_args, **_kwargs):
        raise AssertionError("fork fallback used in controller")

    monkeypatch.setattr(subprocess, "_fork_exec", no_fork)
    monkeypatch.setattr(os, "fork", no_fork)
    monkeypatch.setenv("EDUMIND_DEEPSEEK_COMPAT_API_KEY", "synthetic-must-not-inherit-a")
    monkeypatch.setenv("EDUMIND_AIAPI_REVIEW_API_KEY", "synthetic-must-not-inherit-b")
    path = tmp_path / "ledger.db"
    package = package_grant(path)
    instance, transport = new_controller(path, package=package)
    results = {}
    for arm in ("B", "C"):
        if arm == "C":
            instance.select_slot("slot", "C")
        results[arm] = asyncio.run(instance.run(attest))
        assert results[arm]["status"] == "mock_advisory_pass"
        assert results[arm]["opinions"][0]["issues"]
        assert results[arm]["versions"][1]["identity"]["parent_digest"] == results[arm]["versions"][0]["artifact_digest"]
    assert instance.batch_status() == "complete" and len(transport.audit) == 9
    assert len({item["pid"] for item in transport.audit}) == 9
    assert all(item["pid"] != os.getpid() and item["provider_env_present"] is False for item in transport.audit)
    assert all(item["credential_roles"] == [item["role"]] for item in transport.audit)
    rows = list(instance.db.execute("SELECT rowid,* FROM attempts ORDER BY rowid"))
    assert len(rows) == 9 and [row["rowid"] for row in rows] == list(range(1, 10))
    for row, observed in zip(rows, transport.audit):
        reference = json.loads(bytes(row["response"]))
        assert reference["version"] == vault_module.VERSION and reference["counter"] == row["rowid"]
        assert reference["transport_proof"] == observed
        assert row["request_sha"] == observed["request_sha256"]
        raw = instance._restore_response(row)
        assert hashlib.sha256(raw).hexdigest() == row["response_sha"]
        assert b'"output"' in raw and b'"output"' not in bytes(row["response"])
    assert instance.fixed_denominator_summary()["denominator"] == 2
    assert_no_synthetic_provider_keys(tmp_path)
    instance.close()
    reopened, _ = new_controller(path, package=package)
    assert reopened.batch_status() == "complete"
    assert len(list(reopened.db.execute("SELECT * FROM attempts"))) == 9
    assert asyncio.run(reopened.run(attest)) == results["B"]
    assert not reopened.transport.audit
    reopened.close()


def test_encoded_synthetic_key_is_only_in_encrypted_original_and_stops(tmp_path):
    path = tmp_path / "ledger.db"
    instance, transport = new_controller(path, scenario="encoded_key")
    with pytest.raises(c.ContractError, match="GUARD_UNSAFE"):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
    raw = instance._restore_response(row)
    assert guard.classify(raw, list(KEYS.values())) == "unsafe"
    assert json.loads(bytes(row["response"]))["version"] == vault_module.VERSION
    assert instance.batch_status() == "stopped" and len(transport.audit) == 1
    assert instance.fixed_denominator_summary()["slots"][0]["outcome"] == "failed_or_unknown"
    assert_no_synthetic_provider_keys(tmp_path)
    assert b"\\\\u0073" not in path.read_bytes()
    instance.close()


def test_deep_encoded_key_fails_closed_with_encrypted_original(tmp_path):
    path = tmp_path / "ledger.db"
    instance, transport = new_controller(path, scenario="deep_encoded_key")
    with pytest.raises(c.ContractError, match="GUARD_UNKNOWN"):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
    raw = instance._restore_response(row)
    assert guard.classify(raw, list(KEYS.values())) == "unknown"
    assert instance.batch_status() == "stopped" and len(transport.audit) == 1
    assert_no_synthetic_provider_keys(tmp_path)
    instance.close()


def test_non_200_response_is_encrypted_before_usage_failure(tmp_path):
    path = tmp_path / "ledger.db"
    instance, transport = new_controller(path, scenario="http_error")
    with pytest.raises(c.ContractError, match="MOCK_USAGE_UNKNOWN"):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
    assert row["http_status"] == 503 and instance._restore_response(row) == b'{"error":"synthetic"}'
    assert instance.batch_status() == "stopped" and len(transport.audit) == 1
    instance.close()


def test_redirect_is_recorded_and_not_followed_through_supervised_httpx(tmp_path):
    path = tmp_path / "ledger.db"
    instance, transport = new_controller(path, scenario="redirect", marker=tmp_path)
    with pytest.raises(c.ContractError):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
    assert row["http_status"] == 302 and instance._restore_response(row) == b'{"error":"redirect"}'
    assert (tmp_path / "dispatch-count").read_text().splitlines() == ["1"]
    assert len(transport.audit) == 1 and instance.batch_status() == "stopped"
    instance.close()


@pytest.mark.parametrize("scenario", ["oversize", "invalid_json"])
def test_response_limit_or_invalid_json_stops_and_retains_reservation(tmp_path, scenario):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path, scenario=scenario)
    with pytest.raises(c.ContractError):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
    assert row["input_reserved"] > 0 and instance.batch_status() == "stopped"
    if scenario == "oversize":
        assert row["state"] == "unknown" and row["response"] is None
    else:
        assert instance._restore_response(row) == b"synthetic-invalid-json"
    instance.close()


def test_supervisor_policy_is_bound_and_not_mutable_after_package_creation(tmp_path):
    path = tmp_path / "ledger.db"
    instance, transport = new_controller(path, scenario="delayed_dns")
    with pytest.raises(AttributeError):
        transport.wall_seconds = 59.0
    policy = transport.policy()
    policy["wall_seconds"] = 59.0
    transport._policy_bytes = canonical(policy)  # Simulate untrusted local mutation.
    with pytest.raises(c.ContractError, match="MOCK_RUNTIME_BINDING"):
        asyncio.run(instance.run(attest))
    assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    assert instance.batch_status() == "stopped"
    instance.close()


def test_fixed_28_denominator_preserves_unsafe_failure_and_unrun(tmp_path):
    path = tmp_path / "ledger.db"
    slots = []
    for index in range(14):
        spec = deepcopy(SPEC)
        kind = "supported" if index < 10 else "refusal"
        if kind == "refusal":
            spec["variant"] = "unsupported"
        for arm in ("B", "C"):
            slots.append(dict(slot=f"dev-{index:02}", arm=arm, spec=spec, kind=kind, question=None))
    package = dict(
        batch="fixed-denominator-dev", ledger_path=str(path.absolute()), slots=slots,
        calls=90, input=1_080_737_280, output=720_000, request_bytes=12_000_000,
        deadline=4_000_000_000,
    )
    transport = supervised.SupervisedMockTransport(KEYS, scenario="encoded_key", wall_seconds=30)
    instance = encrypted.EncryptedController(path, package, transport, selected=("dev-00", "B"))
    with pytest.raises(c.ContractError, match="GUARD_UNSAFE"):
        asyncio.run(instance.run(attest))
    summary = instance.fixed_denominator_summary()
    assert summary["denominator"] == 28 and summary["evidence_integrity"] == "verified"
    assert sum(row["kind"] == "supported" for row in summary["slots"]) == 20
    assert sum(row["kind"] == "refusal" for row in summary["slots"]) == 8
    assert sum(row["outcome"] == "failed_or_unknown" for row in summary["slots"]) == 1
    assert sum(row["outcome"] == "not_run" for row in summary["slots"]) == 27
    assert len(transport.audit) == 1
    instance.close()


def test_changing_http_status_breaks_authenticated_response_binding(tmp_path):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path, scenario="http_error")
    with pytest.raises(c.ContractError):
        asyncio.run(instance.run(attest))
    instance.db.execute("UPDATE attempts SET http_status=200")
    instance._seal()  # Simulate a recomputed local seal; AES-GCM AAD must still reject.
    row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
    with pytest.raises(c.ContractError, match="VAULT_AAD"):
        instance._restore_response(row)
    instance.close()


@pytest.mark.parametrize("scenario,marker", [("delayed_dispatch", "before-dispatch"), ("slow_stream", "dispatched")])
def test_stop_kills_and_reaps_before_return_and_never_advances(tmp_path, scenario, marker):
    async def run():
        path = tmp_path / "ledger.db"
        instance, transport = new_controller(path, scenario=scenario, marker=tmp_path)
        task = asyncio.create_task(instance.run(attest))
        deadline = time.monotonic() + 5
        while not (tmp_path / marker).exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert (tmp_path / marker).exists()
        await instance.stop()
        with pytest.raises(c.ContractError):
            await task
        assert instance.batch_status() == "stopped"
        row = instance.db.execute("SELECT * FROM attempts").fetchone()
        assert row["state"] == "unknown" and row["input_reserved"] > 0
        if scenario == "delayed_dispatch":
            assert not (tmp_path / "dispatched").exists()
        await asyncio.sleep(0.15)
        if scenario == "delayed_dispatch":
            assert not (tmp_path / "dispatched").exists()
        assert transport._process is None or transport._process.poll() is not None
        instance.close()

    asyncio.run(run())


def test_failed_termination_is_explicit_unknown_and_never_restarts(tmp_path, monkeypatch):
    async def run():
        path = tmp_path / "ledger.db"
        instance, transport = new_controller(path, scenario="delayed_dispatch", marker=tmp_path)
        task = asyncio.create_task(instance.run(attest))
        deadline = time.monotonic() + 5
        while not (tmp_path / "before-dispatch").exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert (tmp_path / "before-dispatch").exists()
        original = transport.stop_and_confirm
        monkeypatch.setattr(transport, "stop_and_confirm", lambda timeout: False)
        with pytest.raises(c.ContractError, match="STOP_UNCONFIRMED"):
            await instance.stop()
        assert instance.batch_status() == "stop_unconfirmed"
        assert original(supervised.STOP_GRACE)
        monkeypatch.setattr(transport, "stop_and_confirm", original)
        with pytest.raises(c.ContractError):
            await task
        assert not (tmp_path / "dispatched").exists()
        instance.close()

    asyncio.run(run())


def test_complete_child_response_after_stop_is_encrypted_as_late(tmp_path, monkeypatch):
    async def run():
        path = tmp_path / "ledger.db"
        instance, transport = new_controller(path)
        entered, release = threading.Event(), threading.Event()
        original = transport._send

        def delayed_return(request):
            response = original(request)
            entered.set()
            assert release.wait(3)
            return response

        monkeypatch.setattr(transport, "_send", delayed_return)
        task = asyncio.create_task(instance.run(attest))
        assert await asyncio.to_thread(entered.wait, 5)
        await instance.stop()
        release.set()
        with pytest.raises(c.ContractError, match="MOCK_LATE_RESPONSE"):
            await task
        row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
        assert row["state"] == "late" and row["input_used"] == 10 and row["output_used"] == 20
        assert json.loads(bytes(row["response"]))["version"] == vault_module.VERSION
        assert b'"output"' in instance._restore_response(row)
        assert len(transport.audit) == 1 and instance.batch_status() == "stopped"
        instance.close()

    asyncio.run(run())


def test_unconfirmed_status_survives_vault_integrity_failure(tmp_path):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path)
    instance.db.execute("UPDATE batch SET status='stop_unconfirmed'")
    instance._seal()
    (instance.vault.directory / "orphan.aesgcm").write_bytes(b"synthetic")
    instance.close()
    with pytest.raises(c.ContractError, match="VAULT_ORPHAN_OR_MISSING"):
        new_controller(path)
    db = sqlite3.connect(path)
    try:
        assert db.execute("SELECT status FROM batch").fetchone()[0] == "stop_unconfirmed"
    finally:
        db.close()


def test_missing_ciphertext_downgrades_summary_without_changing_denominator(tmp_path):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path)
    asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT response FROM attempts ORDER BY rowid LIMIT 1").fetchone()
    filename = json.loads(bytes(row[0]))["file"]
    (instance.vault.directory / filename).unlink()
    summary = instance.fixed_denominator_summary()
    assert summary["denominator"] == 1 and summary["batch_status"] == "stopped"
    assert summary["evidence_integrity"] == "unknown"
    assert summary["slots"][0]["outcome"] == "evidence_unknown"
    instance.close()


def test_vault_aad_and_ciphertext_tampering_are_detected(tmp_path):
    directory = tmp_path / "vault"
    store = vault_module.SyntheticVault(directory, "a" * 64, create=True)
    aad = {"package_sha256": "a" * 64, "counter": 1, "slot": "B", "stage": "generation"}
    reference = store.seal(1, b'{"original":"synthetic"}', aad)
    assert store.open_response(reference, aad) == b'{"original":"synthetic"}'
    with pytest.raises(c.ContractError, match="VAULT_NONCE_OR_INPUT"):
        store.seal(1, b"another", aad)
    with pytest.raises(c.ContractError, match="VAULT_AAD"):
        store.open_response(reference, {**aad, "slot": "C"})
    with pytest.raises(c.ContractError, match="VAULT_REFERENCE"):
        store.open_response(reference, {**aad, "counter": 2})
    item = json.loads(reference)
    file = directory / item["file"]
    ciphertext = bytearray(file.read_bytes())
    ciphertext[0] ^= 1
    file.write_bytes(ciphertext)
    with pytest.raises(c.ContractError, match="VAULT_CIPHERTEXT"):
        store.open_response(reference, aad)
    reopened = vault_module.SyntheticVault(directory, "a" * 64, create=False)
    with pytest.raises(c.ContractError, match="VAULT_NONCE_OR_INPUT"):
        reopened.seal(2, b"x", {**aad, "counter": 2})


@pytest.mark.parametrize("field", ["slot", "arm", "stage", "ordinal", "request_sha256", "previous_receipt_digest"])
def test_aad_rejects_each_cross_version_or_cross_arm_change(tmp_path, field):
    store = vault_module.SyntheticVault(tmp_path / "vault", "a" * 64, create=True)
    aad = {
        "package_sha256": "a" * 64, "counter": 1, "slot": "slot", "arm": "B", "stage": "B_generate",
        "ordinal": 0, "request_sha256": "b" * 64, "previous_receipt_digest": None,
    }
    reference = store.seal(1, b'{"original":"synthetic"}', aad)
    changed = {**aad, field: "wrong"}
    with pytest.raises(c.ContractError, match="VAULT_AAD"):
        store.open_response(reference, changed)


def test_wrong_encryption_key_does_not_authenticate(tmp_path):
    directory = tmp_path / "vault"
    store = vault_module.SyntheticVault(directory, "a" * 64, create=True)
    aad = {"package_sha256": "a" * 64, "counter": 1, "slot": "B"}
    reference = store.seal(1, b'{"original":"synthetic"}', aad)
    (directory / "synthetic-key.bin").write_bytes(AESGCM.generate_key(bit_length=256))
    reopened = vault_module.SyntheticVault(directory, "a" * 64, create=False)
    with pytest.raises(c.ContractError, match="VAULT_CIPHERTEXT"):
        reopened.open_response(reference, aad)
    store.close()
    reopened.close()


@pytest.mark.parametrize("tamper", ["key", "info", "directory"])
def test_live_vault_metadata_or_directory_tampering_stops(tmp_path, tamper):
    directory = tmp_path / "vault"
    store = vault_module.SyntheticVault(directory, "a" * 64, create=True)
    aad = {"package_sha256": "a" * 64, "counter": 1}
    reference = store.seal(1, b'{"synthetic":true}', aad)
    if tamper == "key":
        (directory / "synthetic-key.bin").write_bytes(AESGCM.generate_key(bit_length=256))
    elif tamper == "info":
        (directory / "info.json").write_text('{}')
    else:
        directory.rename(tmp_path / "old-vault")
        directory.symlink_to(tmp_path / "old-vault", target_is_directory=True)
    with pytest.raises(c.ContractError, match="VAULT_METADATA"):
        store.verify_inventory([(reference, aad)])
    store.close()


def test_vault_constructor_failures_do_not_leak_fds(tmp_path):
    directory = tmp_path / "bad-vault"
    directory.mkdir(mode=0o700)
    before = len(os.listdir("/dev/fd"))
    for _ in range(20):
        with pytest.raises(OSError):
            vault_module.SyntheticVault(directory, "a" * 64, create=False)
    assert len(os.listdir("/dev/fd")) <= before + 1


def test_stopped_supervisor_repeated_rejections_do_not_leak_fds(tmp_path):
    path = tmp_path / "ledger.db"
    instance, transport = new_controller(path)
    asyncio.run(instance.stop())
    request = httpx.Request("POST", "https://api.deepseek.com/responses", content=b"{}")
    request.extensions.update(edumind_stage="B_generate", edumind_ordinal=0, edumind_arm="B")
    before = len(os.listdir("/dev/fd"))
    for _ in range(20):
        with pytest.raises(c.ContractError, match="SUPERVISOR_STOPPED"):
            transport._send(request)
    assert len(os.listdir("/dev/fd")) <= before + 1
    instance.close()


def test_same_reserved_nonce_can_reach_aes_only_once(tmp_path, monkeypatch):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path)
    instance.db.execute(
        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES (?,?,?,?,?,?,?,?,?,'sent')",
        ("slot", "B", 0, "B_generate", b"{}", hashlib.sha256(b"{}").hexdigest(), None, 100, 8000),
    )
    instance._seal()
    seed_synthetic_proof(instance)
    original = AESGCM.encrypt
    used = []

    def counted(self, nonce, data, aad):
        used.append(nonce)
        return original(self, nonce, data, aad)

    monkeypatch.setattr(AESGCM, "encrypt", counted)
    scope = ("slot", "B", 0)
    reference = instance._protect_response(scope, b'{"synthetic":true}', 200)
    instance.db.execute("UPDATE attempts SET response=? WHERE slot=? AND arm=? AND ordinal=?", (reference, *scope))
    instance._seal()
    with pytest.raises(c.ContractError, match="VAULT_NONCE_ALREADY_CLAIMED"):
        instance._protect_response(scope, b'{"synthetic":false}', 200)
    assert len(used) == 1 and used[0] == b"\0" * 11 + b"\1"
    asyncio.run(instance.stop())
    instance.close()


def test_orphan_ciphertext_or_claim_crash_stops_reopen_without_reuse(tmp_path):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path)
    instance.db.execute(
        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES (?,?,?,?,?,?,?,?,?,'sent')",
        ("slot", "B", 0, "B_generate", b"{}", hashlib.sha256(b"{}").hexdigest(), None, 100, 8000),
    )
    instance._seal()
    seed_synthetic_proof(instance)
    reference = instance._protect_response(("slot", "B", 0), b'{"synthetic":true}', 200)
    orphan = instance.vault.directory / json.loads(reference)["file"]
    assert orphan.exists()
    instance.close()
    with pytest.raises(c.ContractError, match="VAULT_INCOMPLETE"):
        new_controller(path)
    assert orphan.exists()
    db = sqlite3.connect(path)
    try:
        assert db.execute("SELECT status FROM batch").fetchone()[0] == "stop_unconfirmed"
        assert db.execute("SELECT state FROM attempts").fetchone()[0] == "unknown"
    finally:
        db.close()


def test_rowid_nonce_is_part_of_sealed_ledger_state(tmp_path):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path)
    instance.db.execute(
        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES (?,?,?,?,?,?,?,?,?,'reserved')",
        ("slot", "B", 0, "B_generate", b"{}", hashlib.sha256(b"{}").hexdigest(), None, 100, 8000),
    )
    instance._seal()
    instance.db.execute("UPDATE attempts SET rowid=99 WHERE slot='slot' AND arm='B'")
    with pytest.raises(c.ContractError, match="MOCK_LEDGER_ROLLBACK"):
        instance._verify_seal()
    # This deliberately corrupts only the temporary test ledger.
    instance.db.close()
    os.close(instance._lock_fd)


def test_ciphertext_written_but_ledger_not_sealed_cannot_resume(tmp_path):
    path = tmp_path / "ledger.db"
    instance, _ = new_controller(path)
    instance.db.execute(
        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES (?,?,?,?,?,?,?,?,?,'sent')",
        ("slot", "B", 0, "B_generate", b"{}", hashlib.sha256(b"{}").hexdigest(), None, 100, 8000),
    )
    instance._seal()
    seed_synthetic_proof(instance)
    reference = instance._protect_response(("slot", "B", 0), b'{"synthetic":true}', 200)
    orphan = instance.vault.directory / json.loads(reference)["file"]
    instance.db.execute("UPDATE attempts SET response=? WHERE slot='slot' AND arm='B'", (reference,))
    # Crash between database write and anchor seal; do not forge a seal here.
    instance.close()
    with pytest.raises(c.ContractError, match="MOCK_LEDGER_ROLLBACK"):
        new_controller(path)
    assert orphan.exists()


def test_plain_supervisor_cannot_bypass_encrypted_controller(tmp_path):
    path = tmp_path / "ledger.db"
    transport = supervised.SupervisedMockTransport(KEYS)
    with pytest.raises(c.ContractError, match="ENCRYPTED_CONTROLLER_REQUIRED"):
        base.Controller(path, grant("B", path), transport)
    assert not path.exists()


def test_unsafe_or_unknown_checker_refuses_without_persisting_input():
    key = KEYS["EDUMIND_DEEPSEEK_COMPAT_API_KEY"]
    escaped = "".join("\\\\u%04x" % ord(char) for char in key)
    body = canonical({"text": "echo " + escaped})
    assert guard.classify(body, list(KEYS.values())) == "unsafe"
    with pytest.raises(c.ContractError, match="GUARD_UNSAFE"):
        guard.check(body, list(KEYS.values()))
    with pytest.raises(c.ContractError, match="GUARD_UNKNOWN"):
        guard.check(b"not json", list(KEYS.values()))


def test_guard_large_flat_input_is_bounded_and_timeout_is_unknown(monkeypatch):
    raw = b'{"items":[' + b"0," * 200_000 + b"0]}"
    guard.check(raw, list(KEYS.values()))
    monkeypatch.setattr(guard, "WALL_SECONDS", 0.01)
    with pytest.raises(c.ContractError, match="GUARD_UNKNOWN"):
        guard.check(raw, list(KEYS.values()))
    with pytest.raises(c.ContractError, match="GUARD_INPUT"):
        guard.check(b"x" * (guard.MAX_RAW + 1), list(KEYS.values()))


def test_parent_crash_watchdog_reaps_sender_and_reopen_never_retries(tmp_path):
    root = Path(__file__).resolve().parents[2]
    program = """
import asyncio,sys
from pathlib import Path
from scripts.isolated_diagnostics.p15_encrypted_controller_v2 import EncryptedController
from scripts.isolated_diagnostics.p15_supervised_mock_v2 import SupervisedMockTransport
from scripts.tests.test_p15_controlled_mock_v1 import grant,attest
root=Path(sys.argv[1]); path=root/'ledger.db'
keys={'EDUMIND_DEEPSEEK_COMPAT_API_KEY':'synthetic-generation-key-901','EDUMIND_AIAPI_REVIEW_API_KEY':'synthetic-review-key-902'}
controller=EncryptedController(path,grant('B',path),SupervisedMockTransport(keys,scenario='delayed_dispatch',marker_dir=root,wall_seconds=30))
asyncio.run(controller.run(attest))
"""
    parent = subprocess.Popen(
        [sys.executable, "-c", program, str(tmp_path)],
        cwd=root,
        env={"PATH": os.defpath, "PYTHONPATH": os.pathsep.join((str(root / "backend"), str(root))), "LANG": "C.UTF-8"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 8
        while not (tmp_path / "before-dispatch").exists() and time.monotonic() < deadline:
            assert parent.poll() is None
            time.sleep(0.03)
        assert (tmp_path / "before-dispatch").exists()
        worker_pid = int((tmp_path / "worker-pid").read_text())
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=2)
        path = tmp_path / "ledger.db"
        recovered, _ = new_controller(path, scenario="delayed_dispatch", marker=tmp_path)
        assert recovered.batch_status() == "stop_unconfirmed"
        assert recovered.db.execute("SELECT state FROM attempts").fetchone()[0] == "unknown"
        with pytest.raises(c.ContractError, match="STOP_UNCONFIRMED"):
            asyncio.run(recovered.run(attest))
        recovered.close()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            try:
                os.kill(worker_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.03)
        else:
            pytest.fail("watchdog did not reap synthetic sender")
        assert not (tmp_path / "dispatched").exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=2)


def test_watchdog_crash_is_unconfirmed_across_reopen_while_worker_still_alive(tmp_path):
    async def run():
        path = tmp_path / "ledger.db"
        instance, transport = new_controller(path, scenario="delayed_dispatch", marker=tmp_path)
        task = asyncio.create_task(instance.run(attest))
        deadline = time.monotonic() + 5
        while not (tmp_path / "before-dispatch").exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert (tmp_path / "before-dispatch").exists()
        worker_pid = int((tmp_path / "worker-pid").read_text())
        watcher = transport._process
        assert watcher is not None
        watcher.kill()
        watcher.wait(timeout=2)
        try:
            with pytest.raises(c.ContractError, match="STOP_UNCONFIRMED"):
                await instance.stop()
            assert instance.batch_status() == "stop_unconfirmed"
            os.kill(worker_pid, 0)  # The old in-flight worker is genuinely unconfirmed.
            instance.abandon_pending()
            with pytest.raises(BaseException):
                await task
            recovered, _ = new_controller(path, scenario="delayed_dispatch", marker=tmp_path)
            assert recovered.batch_status() == "stop_unconfirmed"
            with pytest.raises(c.ContractError, match="STOP_UNCONFIRMED"):
                await recovered.run(attest)
            recovered.close()
        finally:
            try:
                os.kill(worker_pid, signal.SIGKILL)  # Synthetic fixture process only.
            except ProcessLookupError:
                pass
        await asyncio.sleep(0.1)
        assert not (tmp_path / "dispatched").exists()

    asyncio.run(run())
