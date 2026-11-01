"""Regression cases from fd9105f; synthetic keys and HTTP only."""

import asyncio
import json
import os
import subprocess
import sys
import time

import pytest

from scripts.isolated_diagnostics import p15_encrypted_controller_v2 as encrypted
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_spawn_isolation_v2 as spawn
from scripts.isolated_diagnostics import p15_supervised_mock_v2 as supervised
from scripts.isolated_diagnostics import p15_synthetic_guard_v2 as guard
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant

KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}


def controller(path, *, deadline=None, marker=None, scenario="chain"):
    limits = grant("B", path)
    if deadline is not None:
        limits["deadline"] = deadline
    transport = supervised.SupervisedMockTransport(KEYS, scenario=scenario, marker_dir=marker, wall_seconds=30.0)
    return encrypted.EncryptedController(path, limits, transport), transport


def test_spawn_only_explicit_fds_and_no_fork_fallback(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("fork fallback used")

    monkeypatch.setattr(subprocess, "_fork_exec", forbidden)
    monkeypatch.setattr(os, "fork", forbidden)
    read_fd, write_fd = os.pipe()
    os.set_inheritable(write_fd, True)
    try:
        script = (
            "import os,sys\n"
            "try: os.fstat(int(sys.argv[1])); print('leaked')\n"
            "except OSError: print('closed')\n"
        )
        child = spawn.SpawnOnlyPopen(
            [sys.executable, "-c", script, str(write_fd)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath}, close_fds=True, start_new_session=True,
        )
        output, _ = child.communicate(input=b"", timeout=3)
        assert child.returncode == 0 and output == b"closed\n"
        with pytest.raises(OSError, match="unsupported spawn policy"):
            spawn.SpawnOnlyPopen(
                [sys.executable, "-c", "pass"], env={"PATH": os.defpath},
                close_fds=False, start_new_session=True,
            )
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_original_missing_response_counterexample_is_not_complete(tmp_path):
    instance, transport = controller(tmp_path / "ledger.db")
    try:
        asyncio.run(instance.run(attest))
        row = instance.db.execute("SELECT rowid,response FROM attempts ORDER BY rowid LIMIT 1").fetchone()
        cipher = instance.vault.directory / json.loads(bytes(row["response"]))["file"]
        cipher.unlink()
        instance.db.execute(
            "UPDATE attempts SET response=NULL,response_sha=NULL,http_status=NULL,input_used=NULL,output_used=NULL WHERE rowid=?",
            (row["rowid"],),
        )
        # Same as the original reproduction: explicitly recompute the local
        # digest so semantic contradictions cannot hide behind seal checking.
        instance._seal()
        summary = instance.fixed_denominator_summary()
        assert summary["batch_status"] == "stopped"
        assert summary["slots"][0]["outcome"] == "evidence_unknown"
        assert summary["evidence_integrity"] == "unknown"
        assert summary["denominator"] == 1 and len(transport.audit) == 4
    finally:
        instance.close()


@pytest.mark.parametrize("corruption", ["usage_missing", "usage_changed", "digest", "missing_attempt"])
def test_completed_slot_cannot_hide_partial_or_missing_response_evidence(tmp_path, corruption):
    instance, _ = controller(tmp_path / "ledger.db")
    try:
        asyncio.run(instance.run(attest))
        row = instance.db.execute("SELECT rowid,response FROM attempts ORDER BY rowid LIMIT 1").fetchone()
        if corruption == "usage_missing":
            instance.db.execute("UPDATE attempts SET input_used=NULL,output_used=NULL WHERE rowid=?", (row["rowid"],))
        elif corruption == "usage_changed":
            instance.db.execute("UPDATE attempts SET input_used=input_used+1 WHERE rowid=?", (row["rowid"],))
        elif corruption == "digest":
            instance.db.execute("UPDATE attempts SET response_sha=? WHERE rowid=?", ("0" * 64, row["rowid"]))
        else:
            (instance.vault.directory / json.loads(bytes(row["response"]))["file"]).unlink()
            instance.db.execute("DELETE FROM attempts WHERE rowid=?", (row["rowid"],))
        instance._seal()
        summary = instance.fixed_denominator_summary()
        assert summary["batch_status"] == "stopped"
        assert summary["evidence_integrity"] == "unknown"
        assert summary["slots"][0]["outcome"] == "evidence_unknown"
        assert summary["denominator"] == 1
    finally:
        instance.close()


def test_each_secret_checker_receives_only_one_role_key(monkeypatch):
    seen = []
    monkeypatch.setattr(guard, "_check_one", lambda raw, key: seen.append((raw, key)))
    guard.check(b'{}', list(KEYS.values()))
    assert seen == [(b'{}', key) for key in KEYS.values()]
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join((str(supervised.ROOT / "backend"), str(supervised.ROOT))),
        "LANG": "C.UTF-8",
    }
    child = spawn.SpawnOnlyPopen(
        [sys.executable, "-m", "scripts.isolated_diagnostics.p15_synthetic_guard_v2", "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=env, close_fds=True, start_new_session=True,
    )
    output, _ = child.communicate(
        input=json.dumps({"raw_b64": "e30=", "keys": list(KEYS.values())}).encode(), timeout=5
    )
    assert child.returncode != 0 and output == b""


def test_bound_batch_deadline_cannot_be_silently_replaced(tmp_path):
    deadline = int(time.time()) + 60
    instance, transport = controller(tmp_path / "ledger.db", deadline=deadline)
    try:
        original = transport._batch_mono_deadline
        transport._batch_deadline = deadline + 100
        with pytest.raises(c.ContractError, match="SUPERVISOR_POLICY"):
            transport._verify_policy()
        transport._batch_deadline = deadline
        assert transport._batch_mono_deadline == original
        transport._verify_policy()
    finally:
        instance.close()


def test_original_blocked_parent_cannot_dispatch_after_batch_deadline(tmp_path):
    async def run():
        deadline = int(time.time()) + 5
        instance, transport = controller(
            tmp_path / "ledger.db", deadline=deadline, marker=tmp_path, scenario="delayed_dispatch"
        )
        task = asyncio.create_task(instance.run(attest))
        try:
            end = time.monotonic() + 4
            while not (tmp_path / "before-dispatch").exists() and time.monotonic() < end:
                await asyncio.sleep(0.02)
            assert (tmp_path / "before-dispatch").exists()
            # Exactly the original adversarial condition: block the parent's
            # event loop longer than the worker's delayed first dispatch.
            time.sleep(11)
            assert not (tmp_path / "dispatched").exists()
            with pytest.raises(c.ContractError):
                await task
            assert not transport.audit
            assert instance.batch_status() in ("stopped", "stop_unconfirmed")
            assert instance.fixed_denominator_summary()["slots"][0]["outcome"] == "failed_or_unknown"
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            if not await instance.drain_late(2):
                instance.abandon_pending()
            else:
                instance.close()

    asyncio.run(run())
