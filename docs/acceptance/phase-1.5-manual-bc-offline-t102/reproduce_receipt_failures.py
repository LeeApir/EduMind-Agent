"""Offline reproduction: malformed original lost and late attempt can advance."""

from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.isolated_diagnostics.p15_manual_receipts_v1 import SyntheticReceipts


with TemporaryDirectory(prefix="p15-manual-receipt-") as folder:
    root = Path(folder)
    instance = SyntheticReceipts(root / "originals", root / "witness", b"0" * 32)
    instance.register(1, "slot", "B", "B_generate", b"synthetic request")
    try:
        instance.capture(1, "responded", 200, b"{invalid-json")
    except Exception as exc:
        print("capture_exception=", type(exc).__name__)
    else:
        raise AssertionError("expected malformed response failure")
    response_files = list((root / "originals").glob("response-*.aesgcm"))
    print("response_ciphertext_files=", [path.name for path in response_files])
    print("witness=", sorted(path.name for path in (root / "witness").iterdir()))
    assert not response_files

with TemporaryDirectory(prefix="p15-manual-late-") as folder:
    root = Path(folder)
    instance = SyntheticReceipts(root / "originals", root / "witness", b"0" * 32)
    instance.register(1, "slot", "B", "B_generate", b"r1")
    instance.capture(1, "late", 200, b'{"usage":{"input_tokens":10,"output_tokens":20,"total_tokens":30}}')
    following = instance.register(2, "slot", "C", "C_plan", b"r2")
    print("register_after_late=", following["number"])
    assert following["number"] == 2

print("provider_calls=0")
