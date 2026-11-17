"""Synthetic-only independent receipt and encrypted original prototype.

The independent witness directory is a trust assumption, not an external
timestamp or proof against simultaneous rollback of both stores. Keys are
ephemeral, supplied only by synthetic tests, and never written by this class.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts.isolated_diagnostics import p15_manual_evidence_v1 as evidence
from scripts.isolated_diagnostics.p15_pilot_wire import strict_json


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _write(directory: Path, name: str, data: bytes) -> None:
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    rootfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(rootfd)
    finally:
        os.close(rootfd)


class SyntheticReceipts:
    def __init__(self, originals: Path, witness: Path, key: bytes) -> None:
        if originals == witness or len(key) != 32:
            raise ValueError("RECEIPT_CONFIGURATION")
        originals.mkdir(mode=0o700, parents=False, exist_ok=False)
        witness.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.originals = originals
        self.witness = witness
        self._key = key
        self._registered: dict[int, dict[str, Any]] = {}
        self._burned: set[int] = set()
        self._parents: dict[tuple[str, str], str] = {}

    def register(self, number: int, slot: str, arm: str, stage: str, request: bytes) -> dict[str, Any]:
        if number != len(self._registered) + 1 or arm not in ("B", "C") or not slot or not stage:
            raise ValueError("RECEIPT_REGISTRATION")
        if number > 1 and not (self.witness / f"post-{number - 1}.json").is_file():
            raise ValueError("RECEIPT_PREVIOUS_UNKNOWN")
        if type(request) is not bytes or len(request) > 262144:
            raise ValueError("RECEIPT_REQUEST")
        info = dict(number=number, slot=slot, arm=arm, stage=stage,
                    request_sha256=hashlib.sha256(request).hexdigest(),
                    request_original=f"request-{number}.bin", parent_receipt=self._parents.get((slot, arm)))
        _write(self.originals, info["request_original"], request)
        _write(self.witness, f"pre-{number}.json", _canonical(info))
        self._registered[number] = info
        return dict(info)

    def capture(self, number: int, state: str, status: int, raw: bytes) -> dict[str, Any]:
        if number not in self._registered or number in self._burned or state not in ("responded", "late"):
            raise ValueError("RECEIPT_STATE")
        if type(status) is not int or not 100 <= status <= 599 or type(raw) is not bytes or len(raw) > 2097152:
            raise ValueError("RECEIPT_RESPONSE")
        usage = strict_json(raw)["usage"]
        counts = (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"])
        if any(type(value) is not int or value < 0 for value in counts) or counts[2] != counts[0] + counts[1]:
            raise ValueError("RECEIPT_USAGE")
        pre = self._registered[number]
        self._burned.add(number)
        name = f"response-{number}.aesgcm"
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, raw, _canonical(pre))
        _write(self.originals, name, ciphertext)
        row = dict(pre, state=state, original=name, nonce=nonce.hex(), response_sha256=hashlib.sha256(raw).hexdigest(),
                   ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(), status=status,
                   usage={"input": counts[0], "output": counts[1]})
        row["receipt_sha256"] = hashlib.sha256(_canonical(row)).hexdigest()
        _write(self.witness, f"post-{number}.json", _canonical(row))
        self._parents[(pre["slot"], pre["arm"])] = row["receipt_sha256"]
        return dict(row)

    def audit(self, ledger: list[dict[str, Any]]) -> str:
        rows = []
        try:
            for number, pre in self._registered.items():
                if strict_json((self.witness / f"pre-{number}.json").read_bytes()) != pre:
                    return "unknown"
                row = strict_json((self.witness / f"post-{number}.json").read_bytes())
                rows.append(row)

            def original(name: str) -> bytes:
                row = next(value for value in rows if value["original"] == name)
                cipher = (self.originals / name).read_bytes()
                if hashlib.sha256(cipher).hexdigest() != row["ciphertext_sha256"]:
                    raise ValueError("CIPHERTEXT")
                return AESGCM(self._key).decrypt(bytes.fromhex(row["nonce"]), cipher, _canonical(self._registered[row["number"]]))

            return evidence.verify(rows, ledger, original, lambda name: (self.originals / name).read_bytes())
        except Exception:
            return "unknown"
