"""Generate inspectable synthetic B/C evidence; no real credentials or network.

The temporary AES key stays in the private temporary vault and is not exported.
Archived plaintext is synthetic fixture data checked by the offline guard.
"""

import asyncio
import base64
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

from scripts.isolated_diagnostics import p15_controlled_mock_v2 as controlled
from scripts.isolated_diagnostics import p15_encrypted_controller_v2 as encrypted
from scripts.isolated_diagnostics import p15_supervised_mock_v2 as supervised
from scripts.isolated_diagnostics import p15_synthetic_guard_v2 as guard
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_controlled_mock_v1 import attest, package_grant

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/acceptance/phase-1.5-isolated-blockers-t102"
SYNTHETIC_KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "batch.db"
        transport = supervised.SupervisedMockTransport(SYNTHETIC_KEYS, wall_seconds=30.0)
        instance = encrypted.EncryptedController(
            path, package_grant(path), transport, selected=("slot", "B")
        )
        try:
            results = {}
            for arm in ("B", "C"):
                if arm == "C":
                    instance.select_slot("slot", "C")
                results[arm] = asyncio.run(instance.run(attest))
            attempts = []
            for row in instance.db.execute("SELECT rowid,* FROM attempts ORDER BY rowid"):
                raw = instance._restore_response(row)
                guard.check(raw, list(SYNTHETIC_KEYS.values()))
                reference = json.loads(bytes(row["response"]))
                ciphertext = (instance.vault.directory / reference["file"]).read_bytes()
                assert hashlib.sha256(ciphertext).hexdigest() == reference["ciphertext_sha256"]
                attempts.append(dict(
                    counter=row["rowid"], slot=row["slot"], arm=row["arm"], ordinal=row["ordinal"],
                    stage=row["stage"], state=row["state"], http_status=row["http_status"],
                    request=bytes(row["request"]).decode("utf-8"), request_sha256=row["request_sha"],
                    previous_receipt_digest=row["previous_receipt"], input_reserved=row["input_reserved"],
                    output_reserved=row["output_reserved"], input_used=row["input_used"], output_used=row["output_used"],
                    raw_response=raw.decode("utf-8"), response_sha256=row["response_sha"],
                    ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"), reference=reference,
                    aad=instance._aad(row),
                ))
            data = dict(
                version="isolated-blockers-offline-evidence-v2",
                scope="Synthetic fixture outputs; not a model baseline, independent truth, live grant, or teaching result.",
                real_provider_calls=0,
                synthetic_aes_key_exported=False,
                package=instance.package,
                summary=instance.fixed_denominator_summary(),
                results=results,
                attempts=attempts,
                feedback_attestation=json.loads(bytes(instance.db.execute(
                    "SELECT value FROM attestation WHERE slot='slot' AND arm='B'"
                ).fetchone()[0])),
                ledger_state=controlled.ledger_state(instance.db),
                anchor_lines=Path(str(path) + ".anchor").read_text().splitlines(),
                note="AES-GCM decryption was verified in the temporary run; archived ciphertext has no exported key.",
            )
            encoded = canonical(data)
            assert all(key.encode() not in encoded for key in SYNTHETIC_KEYS.values())
            with (OUTPUT / "offline-evidence.json.gz").open("wb") as raw_file:
                with gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as compressed:
                    compressed.write(encoded)
            print("B/C 9 supervised synthetic HTTP attempts; 9 encrypted responses verified; Provider 0")
        finally:
            instance.close()


if __name__ == "__main__":
    main()
