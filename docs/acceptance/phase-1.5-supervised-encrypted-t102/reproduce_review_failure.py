"""Reproduce the final independent-review gaps; synthetic fixtures only.

Exit 2 means both known failures were reproduced. No real Provider is called.
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

from scripts.isolated_diagnostics import p15_encrypted_controller_v1 as encrypted
from scripts.isolated_diagnostics import p15_supervised_mock_v1 as supervised
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant

KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}


def missing_response(root: Path) -> None:
    path = root / "summary.db"
    instance = encrypted.EncryptedController(path, grant("B", path), supervised.SupervisedMockTransport(KEYS))
    try:
        asyncio.run(instance.run(attest))
        row = instance.db.execute("SELECT rowid,response FROM attempts ORDER BY rowid LIMIT 1").fetchone()
        cipher = instance.vault.directory / json.loads(bytes(row["response"]))["file"]
        cipher.unlink()
        instance.db.execute(
            "UPDATE attempts SET response=NULL,response_sha=NULL,http_status=NULL,input_used=NULL,output_used=NULL WHERE rowid=?",
            (row["rowid"],),
        )
        # Explicitly model a recomputed local SHA seal to test the semantic
        # contradiction, not an attack outside the trusted local directory.
        instance._seal()
        summary = instance.fixed_denominator_summary()
        assert not cipher.exists()
        assert summary["batch_status"] == "complete"
        assert summary["slots"][0]["outcome"] == "mechanical_complete"
        assert summary["evidence_integrity"] == "verified"
        print("SUMMARY_GAP: responded row without response/ciphertext still reported complete and verified")
    finally:
        instance.close()


async def late_dispatch(root: Path) -> None:
    path = root / "deadline.db"
    limits = grant("B", path)
    limits["deadline"] = int(time.time()) + 5
    transport = supervised.SupervisedMockTransport(
        KEYS, scenario="delayed_dispatch", marker_dir=root, wall_seconds=30.0
    )
    instance = encrypted.EncryptedController(path, limits, transport)
    task = asyncio.create_task(instance.run(attest))
    try:
        end = time.monotonic() + 4
        while not (root / "before-dispatch").exists() and time.monotonic() < end:
            await asyncio.sleep(0.02)
        assert (root / "before-dispatch").exists()
        # Model a blocked parent event loop; the child watchdog has its own clock.
        time.sleep(11)
        sent = root / "dispatched"
        assert sent.exists() and sent.stat().st_mtime > limits["deadline"]
        try:
            await task
        except Exception:
            pass
        print("DEADLINE_GAP: first synthetic Mock dispatch occurred after batch deadline")
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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        missing_response(root)
        asyncio.run(late_dispatch(root))
    print("Known final-review gaps reproduced; real transport remains disabled.")
    raise SystemExit(2)
