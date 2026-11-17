"""Private AES-GCM storage for synthetic offline response evidence only.

The caller must atomically claim a previously reserved nonce in its sealed
ledger before calling seal(). Reopened vaults are read-only; this is not a
real-batch key-custody solution.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

VERSION = "synthetic-response-vault-v1"
MAX_RAW = 2 * 1024 * 1024


def _private_file(directory_fd: int, name: str, maximum: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        c.require(
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_size <= maximum,
            "VAULT_FILE",
        )
        data = stream.read(maximum + 1)
        c.require(len(data) <= maximum, "VAULT_FILE")
        return data


def _write_exclusive(directory_fd: int, name: str, data: bytes) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class SyntheticVault:
    def __init__(self, directory: Path, package_sha256: str, *, create: bool) -> None:
        c.require(re.fullmatch(r"[0-9a-f]{64}", package_sha256) is not None, "VAULT_PACKAGE")
        self.directory = directory.absolute()
        self.package_sha256 = package_sha256
        self._writable = create
        self._last_counter = 0
        if create:
            self.directory.mkdir(mode=0o700, exist_ok=False)
        self._directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(self._directory_fd)
            self._directory_identity = (opened.st_dev, opened.st_ino)
            if create:
                _write_exclusive(self._directory_fd, "synthetic-key.bin", AESGCM.generate_key(bit_length=256))
                _write_exclusive(
                    self._directory_fd, "info.json", canonical({"version": VERSION, "package_sha256": package_sha256})
                )
                self._sync_directory()
            info = os.fstat(self._directory_fd)
            c.require(
                stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700,
                "VAULT_DIRECTORY",
            )
            self._key = _private_file(self._directory_fd, "synthetic-key.bin", 32)
            c.require(len(self._key) == 32, "VAULT_KEY")
            try:
                metadata = json.loads(_private_file(self._directory_fd, "info.json", 1024))
            except (ValueError, UnicodeError) as exc:
                raise c.ContractError("VAULT_PACKAGE") from exc
            c.require(metadata == {"version": VERSION, "package_sha256": package_sha256}, "VAULT_PACKAGE")
        except BaseException:
            self.close()
            raise

    def _verify_metadata(self) -> None:
        try:
            current = os.lstat(self.directory)
            opened = os.fstat(self._directory_fd)
            key = _private_file(self._directory_fd, "synthetic-key.bin", 32)
            metadata = json.loads(_private_file(self._directory_fd, "info.json", 1024))
        except (OSError, ValueError, UnicodeError) as exc:
            raise c.ContractError("VAULT_METADATA") from exc
        c.require(
            stat.S_ISDIR(current.st_mode)
            and stat.S_IMODE(current.st_mode) == 0o700
            and (current.st_dev, current.st_ino) == self._directory_identity
            and (opened.st_dev, opened.st_ino) == self._directory_identity
            and hmac.compare_digest(key, self._key)
            and metadata == {"version": VERSION, "package_sha256": self.package_sha256},
            "VAULT_METADATA",
        )

    def _sync_directory(self) -> None:
        os.fsync(self._directory_fd)

    def close(self) -> None:
        if self._directory_fd >= 0:
            os.close(self._directory_fd)
            self._directory_fd = -1

    def seal(self, counter: int, raw: bytes, aad: dict[str, Any]) -> bytes:
        """Encrypt once after the caller durably claims counter in its ledger."""
        self._verify_metadata()
        c.require(
            self._writable
            and type(counter) is int
            and self._last_counter < counter < 2**64
            and type(raw) is bytes
            and len(raw) <= MAX_RAW
            and aad.get("package_sha256") == self.package_sha256
            and aad.get("counter") == counter,
            "VAULT_NONCE_OR_INPUT",
        )
        # Burn the in-process counter even if encryption or durable writing fails.
        self._last_counter = counter
        nonce = b"\0" * 4 + counter.to_bytes(8, "big")
        aad_bytes = canonical(aad)
        ciphertext = AESGCM(self._key).encrypt(nonce, raw, aad_bytes)
        filename = f"response-{counter:016x}.aesgcm"
        _write_exclusive(self._directory_fd, filename, ciphertext)
        self._sync_directory()
        return canonical(
            dict(
                version=VERSION,
                file=filename,
                counter=counter,
                raw_sha256=hashlib.sha256(raw).hexdigest(),
                ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
                aad_sha256=hashlib.sha256(aad_bytes).hexdigest(),
                raw_bytes=len(raw),
                transport_proof=aad.get("transport_proof"),
            )
        )

    def open_response(self, reference: bytes, aad: dict[str, Any]) -> bytes:
        self._verify_metadata()
        try:
            item = json.loads(reference)
        except (ValueError, UnicodeError) as exc:
            raise c.ContractError("VAULT_REFERENCE") from exc
        c.require(
            type(item) is dict
            and set(item)
            == {"version", "file", "counter", "raw_sha256", "ciphertext_sha256", "aad_sha256", "raw_bytes", "transport_proof"}
            and item["version"] == VERSION
            and type(item["counter"]) is int
            and 0 < item["counter"] < 2**64
            and item["file"] == f"response-{item['counter']:016x}.aesgcm"
            and aad.get("package_sha256") == self.package_sha256
            and aad.get("counter") == item["counter"]
            and aad.get("transport_proof") == item["transport_proof"],
            "VAULT_REFERENCE",
        )
        aad_bytes = canonical(aad)
        c.require(hashlib.sha256(aad_bytes).hexdigest() == item["aad_sha256"], "VAULT_AAD")
        try:
            ciphertext = _private_file(self._directory_fd, item["file"], MAX_RAW + 16)
        except OSError as exc:
            raise c.ContractError("VAULT_FILE") from exc
        c.require(hashlib.sha256(ciphertext).hexdigest() == item["ciphertext_sha256"], "VAULT_CIPHERTEXT")
        try:
            raw = AESGCM(self._key).decrypt(b"\0" * 4 + item["counter"].to_bytes(8, "big"), ciphertext, aad_bytes)
        except (InvalidTag, ValueError) as exc:
            raise c.ContractError("VAULT_CIPHERTEXT") from exc
        c.require(
            len(raw) == item["raw_bytes"] and hashlib.sha256(raw).hexdigest() == item["raw_sha256"],
            "VAULT_PLAINTEXT",
        )
        return raw

    def verify_inventory(self, references: list[tuple[bytes, dict[str, Any]]]) -> None:
        self._verify_metadata()
        expected = {"synthetic-key.bin", "info.json"}
        for reference, aad in references:
            self.open_response(reference, aad)
            item = json.loads(reference)
            c.require(item["file"] not in expected, "VAULT_DUPLICATE")
            expected.add(item["file"])
        c.require(set(os.listdir(self._directory_fd)) == expected, "VAULT_ORPHAN_OR_MISSING")
