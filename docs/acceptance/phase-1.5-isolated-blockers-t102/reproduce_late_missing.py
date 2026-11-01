"""Synthetic, offline reproduction: stopped batch reports missing late evidence verified."""
import asyncio
import json
import tempfile
import threading
from pathlib import Path

from scripts.isolated_diagnostics import p15_encrypted_controller_v2 as encrypted
from scripts.isolated_diagnostics import p15_minimal_contract as contract
from scripts.isolated_diagnostics import p15_supervised_mock_v2 as supervised
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant

KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}


async def reproduce(root):
    path = root / "ledger.db"
    transport = supervised.SupervisedMockTransport(KEYS)
    instance = encrypted.EncryptedController(path, grant("B", path), transport)
    ready = threading.Event()
    release = threading.Event()
    original = transport._send

    def delayed_return(request):
        response = original(request)
        ready.set()
        if not release.wait(5):
            raise AssertionError("synthetic response was not released")
        return response

    transport._send = delayed_return
    task = asyncio.create_task(instance.run(attest))
    try:
        assert await asyncio.to_thread(ready.wait, 5)
        await instance.stop()
        release.set()
        try:
            await task
            raise AssertionError("late response unexpectedly advanced")
        except contract.ContractError as exc:
            assert str(exc) == "MOCK_LATE_RESPONSE"
            print("late_result:", str(exc))

        row = instance.db.execute("SELECT rowid,* FROM attempts").fetchone()
        assert row["state"] == "late" and row["response"] is not None
        assert (row["input_used"], row["output_used"]) == (10, 20)
        print("before: state=late response_present=true input=10 output=20")

        reference = json.loads(bytes(row["response"]))
        (instance.vault.directory / reference["file"]).unlink()
        instance.db.execute(
            "UPDATE attempts SET response=NULL,response_sha=NULL,http_status=NULL,"
            "input_used=NULL,output_used=NULL WHERE rowid=?",
            (row["rowid"],),
        )
        # Simulate a locally recomputed SHA seal to isolate semantic validation.
        instance._seal()
        summary = instance.fixed_denominator_summary()
        row = instance.db.execute("SELECT state,response FROM attempts").fetchone()
        assert row["state"] == "late" and row["response"] is None
        assert summary["batch_status"] == "stopped"
        assert summary["slots"][0]["outcome"] == "failed_or_unknown"
        assert summary["evidence_integrity"] == "verified"
        assert summary["denominator"] == 1
        print("after: state=late response_present=false")
        print("summary: batch=stopped slot=failed_or_unknown denominator=1 evidence_integrity=verified")
    finally:
        release.set()
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


with tempfile.TemporaryDirectory(prefix="edumind-late-repro-") as temporary:
    asyncio.run(reproduce(Path(temporary)))
