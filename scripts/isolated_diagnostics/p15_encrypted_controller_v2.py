"""Synthetic-only supervised controller with encrypted response evidence.

This is an offline development implementation, not a live execution grant.
Reopening a batch is read-only and never authorizes another dispatch/encryption.
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, cast
from urllib.parse import urlsplit

from scripts.isolated_diagnostics import p15_controlled_mock_v2 as base
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_supervised_mock_v2 as supervised
from scripts.isolated_diagnostics import p15_synthetic_vault_v1 as vault_module
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

VERSION = "supervised-encrypted-controller-v2-offline"
CLAIM_VERSION = "synthetic-vault-nonce-claimed-v1"


class EncryptedController(base.Controller):
    _encrypted_supervisor = True

    def __init__(
        self,
        path: Path,
        grant: dict[str, Any],
        transport: supervised.SupervisedMockTransport,
        *,
        selected: tuple[str, str] | None = None,
    ) -> None:
        c.require(type(transport) is supervised.SupervisedMockTransport, "ENCRYPTED_OFFLINE_ONLY")
        existed = os.path.lexists(path)
        vault_path = Path(str(path.absolute()) + ".vault")
        super().__init__(path, grant, transport, selected=selected)
        try:
            self.vault = vault_module.SyntheticVault(
                vault_path, hashlib.sha256(self._grant_bytes).hexdigest(), create=not existed
            )
            if existed and self.batch_status() == "active":
                # Even a clean close of a partial batch is not authority to
                # reopen its key for encryption or dispatch.
                self.db.execute("UPDATE batch SET status='stopped' WHERE status='active'")
                self._seal()
            self._verify_vault_inventory()
        except BaseException:
            try:
                self._stop_after_vault_failure()
            finally:
                if hasattr(self, "vault"):
                    self.vault.close()
                super().close()
            raise

    def close(self) -> None:
        super().close()
        self.vault.close()

    def abandon_pending(self) -> None:
        super().abandon_pending()
        self.vault.close()

    def _stop_after_vault_failure(self) -> None:
        self._verify_seal()
        self.db.execute("UPDATE batch SET status='stopped' WHERE status NOT IN ('stopped','stop_unconfirmed')")
        self.db.execute("UPDATE attempts SET state='unknown' WHERE state IN ('reserved','sent')")
        self._seal()

    def _aad(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            proof = json.loads(bytes(row["response"]))["transport_proof"]
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise c.ContractError("VAULT_PROOF") from exc
        role = "review" if row["stage"].startswith("review_") else "generation"
        route = self.package["runtime_contract"]["routes"][role]
        c.require(
            type(proof) is dict
            and set(proof) == {"pid", "role", "stage", "ordinal", "target", "ip", "host", "sni", "request_sha256", "credential_roles", "provider_env_present", "transport_kind", "tls_verification_configured", "retries"}
            and proof.get("role") == role
            and proof.get("stage") == row["stage"]
            and proof.get("ordinal") == row["ordinal"]
            and proof.get("target") == route["url"]
            and proof.get("host") == proof.get("sni") == urlsplit(route["url"]).hostname
            and proof.get("ip") == "1.1.1.1"
            and proof.get("request_sha256") == row["request_sha"]
            and proof.get("credential_roles") == [role]
            and proof.get("provider_env_present") is False
            and proof.get("transport_kind") == "httpx-async-http-transport-core-intercepted"
            and proof.get("tls_verification_configured") is True
            and proof.get("retries") == 0
            and type(proof.get("pid")) is int
            and proof["pid"] > 0,
            "VAULT_PROOF",
        )
        return dict(
            version=VERSION,
            package_sha256=hashlib.sha256(self._grant_bytes).hexdigest(),
            batch=self.package["batch"],
            slot=row["slot"],
            arm=row["arm"],
            ordinal=row["ordinal"],
            stage=row["stage"],
            http_status=row["http_status"],
            request_sha256=row["request_sha"],
            previous_receipt_digest=row["previous_receipt"],
            counter=row["rowid"],
            transport_proof=proof,
        )

    def _row(self, scope: tuple[str, str, int]) -> sqlite3.Row:
        row = self.db.execute(
            "SELECT rowid,* FROM attempts WHERE slot=? AND arm=? AND ordinal=?", scope
        ).fetchone()
        c.require(row is not None, "VAULT_ATTEMPT")
        assert row is not None
        return cast(sqlite3.Row, row)

    def _protect_response(self, scope: tuple[str, str, int], raw: bytes, http_status: int) -> bytes:
        row = self._row(scope)
        c.require(row["response"] is None, "VAULT_NONCE_ALREADY_CLAIMED")
        self._verify_vault_inventory()
        c.require(type(http_status) is int and 100 <= http_status <= 599, "VAULT_HTTP_STATUS")
        assert type(self.transport) is supervised.SupervisedMockTransport
        c.require(bool(self.transport.audit), "VAULT_PROOF")
        proof = self.transport.audit[-1]
        claim = canonical({
            "version": CLAIM_VERSION, "counter": row["rowid"],
            "http_status": http_status, "transport_proof": proof,
        })
        self.db.execute("BEGIN IMMEDIATE")
        try:
            updated = self.db.execute(
                "UPDATE attempts SET response=?,http_status=? WHERE slot=? AND arm=? AND ordinal=? AND response IS NULL",
                (claim, http_status, *scope),
            )
            c.require(updated.rowcount == 1, "VAULT_NONCE_ALREADY_CLAIMED")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        # The rowid was allocated in the already-committed reservation, and
        # this one-way claim is sealed before AES-GCM ever sees the nonce.
        self._seal()
        claimed = self._row(scope)
        return self.vault.seal(row["rowid"], raw, self._aad(claimed))

    def _restore_response(self, row: sqlite3.Row) -> bytes:
        actual = self._row((row["slot"], row["arm"], row["ordinal"]))
        return self.vault.open_response(bytes(actual["response"]), self._aad(actual))

    def _check_response_material(self, raw: bytes) -> None:
        assert type(self.transport) is supervised.SupervisedMockTransport
        self.transport.check_response_safe(raw)

    def _verify_vault_inventory(self) -> None:
        references = []
        rows = list(self.db.execute("SELECT rowid,* FROM attempts ORDER BY rowid"))
        for row in rows:
            state = row["state"]
            c.require(state in {"reserved", "sent", "responded", "unknown", "cancelled", "late"}, "VAULT_STATE")
            if state == "responded":
                c.require(
                    type(row["response"]) is bytes
                    and type(row["response_sha"]) is str
                    and type(row["http_status"]) is int and 100 <= row["http_status"] <= 599
                    and (
                        (row["input_used"] is None and row["output_used"] is None)
                        or (type(row["input_used"]) is int and row["input_used"] >= 0
                            and type(row["output_used"]) is int and row["output_used"] >= 0)
                    ),
                    "VAULT_RESPONDED_INCOMPLETE",
                )
            if row["response"] is None:
                c.require(
                    row["response_sha"] is None and row["http_status"] is None
                    and row["input_used"] is None and row["output_used"] is None,
                    "VAULT_RESPONSE_CONTRADICTION",
                )
                continue
            c.require(type(row["response"]) is bytes, "VAULT_REFERENCE")
            raw_reference = bytes(row["response"])
            try:
                value = json.loads(raw_reference)
            except (ValueError, UnicodeError) as exc:
                raise c.ContractError("VAULT_REFERENCE") from exc
            c.require(type(value) is dict and value.get("version") != CLAIM_VERSION, "VAULT_INCOMPLETE")
            c.require(
                state in {"responded", "unknown", "late"}
                and type(row["response_sha"]) is str
                and type(row["http_status"]) is int and 100 <= row["http_status"] <= 599,
                "VAULT_RESPONSE_CONTRADICTION",
            )
            aad = self._aad(row)
            raw = self.vault.open_response(raw_reference, aad)
            c.require(hashlib.sha256(raw).hexdigest() == row["response_sha"], "VAULT_RESPONSE_DIGEST")
            if state == "responded" and row["input_used"] is not None:
                try:
                    response = json.loads(raw)
                    usage = response["usage"]
                    counts = (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"])
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
                    raise c.ContractError("VAULT_USAGE") from exc
                c.require(
                    all(type(value) is int and value >= 0 for value in counts)
                    and counts[0] == row["input_used"] and counts[1] == row["output_used"]
                    and counts[2] == counts[0] + counts[1],
                    "VAULT_USAGE",
                )
            references.append((raw_reference, aad))
        self.vault.verify_inventory(references)
        for slot in self.package["slots"]:
            pair = (slot["slot"], slot["arm"])
            status = self.db.execute("SELECT status FROM slots WHERE slot=? AND arm=?", pair).fetchone()[0]
            if status != "complete":
                continue
            attempts = [row for row in rows if (row["slot"], row["arm"]) == pair]
            if slot["kind"] == "refusal":
                c.require(not attempts and self.db.execute(
                    "SELECT 1 FROM local_refusals WHERE slot=? AND arm=?", pair
                ).fetchone() is not None, "VAULT_COMPLETE_REFUSAL")
                continue
            stages = [row["stage"] for row in attempts]
            first = ["B_generate", "review_B"] if pair[1] == "B" else ["C_plan", "C_content", "review_C"]
            with_repair = first + [pair[1] + "_repair", "review_" + pair[1]]
            c.require(
                stages in (first, with_repair)
                and all(row["ordinal"] == i and row["state"] == "responded"
                        and row["http_status"] == 200
                        and type(row["input_used"]) is int and type(row["output_used"]) is int
                        and row["input_used"] <= row["input_reserved"]
                        and row["output_used"] <= row["output_reserved"]
                        for i, row in enumerate(attempts)),
                "VAULT_COMPLETE_ATTEMPTS",
            )
        if self.batch_status() == "complete":
            c.require(
                self.db.execute("SELECT COUNT(*) FROM slots WHERE status!='complete'").fetchone()[0] == 0,
                "VAULT_COMPLETE_BATCH",
            )

    async def _exchange(
        self, stage: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._verify_seal()
        self._verify_vault_inventory()
        return await super()._exchange(stage, payload)

    def fixed_denominator_summary(self) -> dict[str, Any]:
        try:
            self._verify_vault_inventory()
        except (c.ContractError, OSError):
            self._stop_after_vault_failure()
            summary = super().fixed_denominator_summary()
            for item in summary["slots"]:
                if item["outcome"] == "mechanical_complete":
                    item["outcome"] = "evidence_unknown"
            summary["evidence_integrity"] = "unknown"
            return summary
        summary = super().fixed_denominator_summary()
        summary["evidence_integrity"] = "verified"
        return summary
