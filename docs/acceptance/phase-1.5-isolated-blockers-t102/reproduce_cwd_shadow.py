"""Offline T102 cwd-shadow reproduction; synthetic material only."""
import asyncio
import os
import tempfile
import time
from pathlib import Path

from scripts.isolated_diagnostics.p15_encrypted_controller_v2 import EncryptedController
from scripts.isolated_diagnostics.p15_supervised_mock_v2 import SupervisedMockTransport
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant

KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}


async def run(root):
    path = root / "ledger.db"
    cfg = grant("B", path)
    cfg["deadline"] = int(time.time()) + 20
    transport = SupervisedMockTransport(KEYS, wall_seconds=10.0)
    instance = EncryptedController(path, cfg, transport)
    try:
        try:
            await instance.run(attest)
        except Exception as exc:
            print("controller_result", str(exc), "batch", instance.batch_status())
        marker = root / "shadow-worker-received"
        print("shadow_watchdog_ran", marker.exists(),
              "received_current_role_synthetic_key", marker.read_text() if marker.exists() else "no")
    finally:
        if not await instance.drain_late(2):
            instance.abandon_pending()
        else:
            instance.close()


with tempfile.TemporaryDirectory(prefix="p15-shadow-") as folder:
    root = Path(folder)
    target = root / "scripts" / "isolated_diagnostics"
    target.mkdir(parents=True)
    (target.parent / "__init__.py").write_text("")
    (target / "__init__.py").write_text("")
    (target / "p15_synthetic_guard_v2.py").write_text(
        "import sys\nsys.stdin.buffer.read()\nsys.stdout.write('safe\\n')\n"
    )
    (target / "p15_supervised_mock_v2.py").write_text(
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "os.write(int(sys.argv[4]),b'R')\n"
        "if os.read(int(sys.argv[2]),1)==b'G':\n"
        " job=json.load(sys.stdin); Path('shadow-worker-received').write_text(str(job.get('role_key')=='synthetic-generation-key-901'))\n"
        "os.write(int(sys.argv[5]),b'A')\n"
        "sys.stdout.write('{}')\n"
    )
    print("precondition: inherited cwd contains an attacker-controlled scripts package")
    os.chdir(root)
    asyncio.run(run(root))
