"""Qwen diagnostic budget fork: only ceiling8202 differs from the frozen8192 kernel."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")
HASH = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}")
PHASES = {"connection", "diagnostic", "formal", "e2e"}
STAGES = {"probe", "model_refresh", "profile", "generation", "review", "correction", "warmup"}
ERRORS = {
    "AUTHENTICATION_FAILED",
    "RATE_LIMITED",
    "CAPABILITY_UNAVAILABLE",
    "TIMEOUT",
    "INVALID_OUTPUT",
    "TEMPORARILY_UNAVAILABLE",
    "TARGET_CHANGED",
    "SAFETY_FAILURE",
}


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class GateFailure(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _integer(value: object, minimum: int = 0, maximum: int = 10**12) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GateFailure("INVALID_FREEZE")
    return value


def _keys(value: object, expected: set[str]) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise GateFailure("INVALID_FREEZE")
    return value


@dataclass(frozen=True)
class Approval:
    """Resolved only from a human approval record by trusted acceptance composition code."""

    manifest_sha256: str
    phase: str
    requests: int = 0
    cost_micro: int = 0
    record_sha256: str | None = None
    authorized: bool = False


class FrozenBudget:
    """SQLite BEGIN IMMEDIATE serializes all processes for one immutable run/approval."""

    def __init__(
        self, manifest: dict, ledger: Path, *, approval: Approval | None = None, root: Path
    ):
        self.serialized = canonical(manifest)
        self.freeze = sha(self.serialized)
        self.ledger, self.root, self.approval = ledger, root.resolve(), approval
        self._validate()

    @property
    def manifest(self) -> dict:
        return json.loads(self.serialized)  # Callers cannot mutate the frozen envelope.

    def _validate(self) -> None:
        value = _keys(
            self.manifest,
            {
                "version",
                "run_id",
                "state",
                "phase",
                "files",
                "targets",
                "slots",
                "bounds",
                "required_evidence",
                "evidence",
            },
        )
        if (
            value["version"] != "phase1-run-v1"
            or value["state"] != "FROZEN_RUN_READY"
            or value["phase"] not in PHASES
            or not NAME.fullmatch(value["run_id"])
        ):
            raise GateFailure("INVALID_FREEZE")
        if type(value["files"]) is not dict or not value["files"]:
            raise GateFailure("INVALID_FREEZE")
        for name, digest in value["files"].items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not HASH.fullmatch(digest):
                raise GateFailure("INVALID_FREEZE")
        if type(value["targets"]) is not dict or not 1 <= len(value["targets"]) <= 4:
            raise GateFailure("INVALID_FREEZE")
        for target_id, target in value["targets"].items():
            if not HASH.fullmatch(target_id):
                raise GateFailure("INVALID_FREEZE")
            _keys(
                target,
                {
                    "provider_type",
                    "model_id",
                    "adapter_sha256",
                    "capability_sha256",
                    "model_revision",
                    "currency",
                    "input_price_micro_per_million",
                    "output_price_micro_per_million",
                    "input_overhead_tokens",
                    "max_wire_bytes",
                    "max_total_output_tokens",
                    "total_output_limit_verified",
                    "token_byte_bound_verified",
                    "output_limit_path",
                },
            )
            if (
                target["provider_type"]
                not in {"openai-compatible", "ollama", "anthropic", "gemini", "spark"}
                or not NAME.fullmatch(target["model_id"])
                or not NAME.fullmatch(target["model_revision"])
                or not HASH.fullmatch(target["adapter_sha256"])
                or not HASH.fullmatch(target["capability_sha256"])
                or target["currency"] not in {"USD", "CNY"}
                or target["total_output_limit_verified"] is not True
                or target["token_byte_bound_verified"] is not True
            ):
                raise GateFailure("UNKNOWN_COST_BOUND")
            if (
                type(target["output_limit_path"]) is not list
                or not 1 <= len(target["output_limit_path"]) <= 4
                or any(
                    type(k) is not str or not NAME.fullmatch(k) for k in target["output_limit_path"]
                )
            ):
                raise GateFailure("UNKNOWN_COST_BOUND")
            for field in (
                "input_price_micro_per_million",
                "output_price_micro_per_million",
                "input_overhead_tokens",
            ):
                _integer(target[field])
            _integer(target["max_wire_bytes"], 1, 2 * 1024 * 1024)
            _integer(target["max_total_output_tokens"], 1, 8202)
        if len({t["currency"] for t in value["targets"].values()}) != 1:
            raise GateFailure("UNKNOWN_COST_BOUND")  # No guessed exchange rate.
        bounds = _keys(
            value["bounds"],
            {
                "requests",
                "cost_micro",
                "max_active_attempts",
                "timeout_seconds",
                "corrections_per_resource",
            },
        )
        _integer(bounds["requests"], 0, 10000)
        _integer(bounds["cost_micro"])
        if (
            bounds["max_active_attempts"] != 1
            or type(bounds["max_active_attempts"]) is not int
            or bounds["corrections_per_resource"] != 2
            or type(bounds["corrections_per_resource"]) is not int
        ):
            raise GateFailure("INVALID_FREEZE")
        _integer(bounds["timeout_seconds"], 1, 180)
        if type(value["slots"]) is not list or not value["slots"]:
            raise GateFailure("INVALID_FREEZE")
        seen = set()
        for slot in value["slots"]:
            _keys(slot, {"id", "input_sha256", "attempts", "stages", "targets", "resources"})
            if (
                not NAME.fullmatch(slot["id"])
                or slot["id"] in seen
                or not HASH.fullmatch(slot["input_sha256"])
                or type(slot["stages"]) is not list
                or not slot["stages"]
                or not set(slot["stages"]) <= STAGES
                or type(slot["resources"]) is not list
                or not slot["resources"]
                or not set(slot["resources"]) <= {"unit", "explanation", "code", "exercise", "dsl"}
                or type(slot["targets"]) is not list
                or not slot["targets"]
                or not set(slot["targets"]) <= set(value["targets"])
            ):
                raise GateFailure("INVALID_FREEZE")
            _integer(slot["attempts"], 1, 32)
            seen.add(slot["id"])
        _keys(value["evidence"], set(value["required_evidence"]))
        needed = {
            "connection": {"adr"},
            "diagnostic": {"adr", "connection"},
            "formal": {"adr", "connection", "diagnostic"},
            "e2e": {"adr", "connection", "diagnostic", "quality", "test_opening"},
        }
        if set(value["required_evidence"]) != needed[value["phase"]]:
            raise GateFailure("PREREQUISITE_MISSING")
        if any(type(v) is not str or not HASH.fullmatch(v) for v in value["evidence"].values()):
            raise GateFailure("PREREQUISITE_MISSING")
        # Prerequisites must be exact bound file artifacts, not booleans or old scores.
        if not set(value["evidence"].values()) <= set(value["files"].values()):
            raise GateFailure("PREREQUISITE_MISSING")

    def _authorize(self) -> None:
        self._validate()
        value, approval = self.manifest, self.approval
        if (
            approval is None
            or approval.authorized is not True
            or approval.manifest_sha256 != self.freeze
            or approval.phase != value["phase"]
            or approval.record_sha256 is None
            or not HASH.fullmatch(approval.record_sha256)
        ):
            raise GateFailure("NOT_AUTHORIZED")
        _integer(approval.requests)
        _integer(approval.cost_micro)
        if (
            approval.requests != value["bounds"]["requests"]
            or approval.cost_micro != value["bounds"]["cost_micro"]
        ):
            raise GateFailure("NOT_AUTHORIZED")
        for name, expected in value["files"].items():
            path = self.root / name
            try:
                if (
                    path.is_symlink()
                    or not path.resolve().is_relative_to(self.root)
                    or sha(path.read_bytes()) != expected
                ):
                    raise GateFailure("FREEZE_CHANGED")
            except OSError:
                raise GateFailure("FREEZE_CHANGED") from None

    def _connect(self) -> sqlite3.Connection:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.ledger, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        if self.ledger.is_symlink() or self.ledger.stat().st_mode & 0o077:
            raise GateFailure("LEDGER_UNSAFE")
        db = sqlite3.connect(self.ledger, timeout=3, isolation_level=None)
        db.execute("PRAGMA busy_timeout=3000")
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS run (id INTEGER PRIMARY KEY CHECK(id=1), "
            "freeze TEXT NOT NULL, approval TEXT NOT NULL, halted TEXT)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS attempts (number INTEGER PRIMARY KEY, "
            "slot TEXT NOT NULL, stage TEXT NOT NULL, target TEXT NOT NULL, "
            "resource TEXT NOT NULL, "
            "request_sha256 TEXT NOT NULL, cost_micro INTEGER NOT NULL, state TEXT NOT NULL, "
            "input_tokens INTEGER, output_tokens INTEGER, error_code TEXT, "
            "input_bound INTEGER NOT NULL, output_bound INTEGER NOT NULL)"
        )
        db.execute(
            "INSERT OR IGNORE INTO run(id,freeze,approval) VALUES(1,?,?)",
            (self.freeze, self.approval.record_sha256 if self.approval else ""),
        )
        row = db.execute("SELECT freeze,approval FROM run WHERE id=1").fetchone()
        if row != (self.freeze, self.approval.record_sha256 if self.approval else ""):
            db.rollback()
            db.close()
            raise GateFailure("LEDGER_MISMATCH")
        return db

    def reserve(
        self, slot_id: str, stage: str, target_id: str, wire: bytes, *, resource: str = "dsl"
    ) -> int:
        self._authorize()  # Always before creating an outbound attempt or accessing a secret.
        value = self.manifest
        slot = next((s for s in value["slots"] if s["id"] == slot_id), None)
        if (
            slot is None
            or stage not in slot["stages"]
            or target_id not in slot["targets"]
            or resource not in slot["resources"]
        ):
            raise GateFailure("TARGET_NOT_APPROVED")
        target = value["targets"][target_id]
        if type(wire) is not bytes or not 1 <= len(wire) <= target["max_wire_bytes"]:
            raise GateFailure("UNKNOWN_COST_BOUND")
        try:

            def pairs(items):
                result = {}
                for k, v in items:
                    if k in result:
                        raise ValueError()
                    result[k] = v
                return result

            body = json.loads(wire, object_pairs_hook=pairs)
            limit = body
            for key in target["output_limit_path"]:
                limit = limit[key]
            if type(limit) is not int or not 1 <= limit <= target["max_total_output_tokens"]:
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            raise GateFailure("UNKNOWN_COST_BOUND") from None
        input_bound = len(wire) + target["input_overhead_tokens"]
        cost = (input_bound * target["input_price_micro_per_million"] + 999999) // 1000000 + (
            target["max_total_output_tokens"] * target["output_price_micro_per_million"] + 999999
        ) // 1000000
        db = self._connect()
        try:
            if db.execute("SELECT halted FROM run WHERE id=1").fetchone()[0] is not None:
                raise GateFailure("RUN_HALTED")
            count, total = db.execute(
                "SELECT count(*),coalesce(sum(cost_micro),0) FROM attempts"
            ).fetchone()
            if count >= value["bounds"]["requests"] or total + cost > value["bounds"]["cost_micro"]:
                raise GateFailure("BUDGET_EXHAUSTED")
            if db.execute("SELECT count(*) FROM attempts WHERE state='reserved'").fetchone()[0]:
                raise GateFailure("ATTEMPT_ACTIVE")
            used = db.execute("SELECT count(*) FROM attempts WHERE slot=?", (slot_id,)).fetchone()[
                0
            ]
            corrections = db.execute(
                "SELECT count(*) FROM attempts WHERE slot=? AND resource=? AND stage='correction'",
                (slot_id, resource),
            ).fetchone()[0]
            if used >= slot["attempts"] or stage == "correction" and corrections >= 2:
                raise GateFailure("SLOT_EXHAUSTED")
            number = count + 1
            db.execute(
                "INSERT INTO attempts(number,slot,stage,target,resource,request_sha256,"
                "cost_micro,state,input_bound,output_bound) "
                "VALUES(?,?,?,?,?,?,?,'reserved',?,?)",
                (
                    number,
                    slot_id,
                    stage,
                    target_id,
                    resource,
                    sha(wire),
                    cost,
                    input_bound,
                    target["max_total_output_tokens"],
                ),
            )
            db.commit()
            return number  # Durable reservation before sending, including failures.
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def finish(
        self,
        number: int,
        *,
        error_code: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        if error_code is not None and error_code not in ERRORS:
            raise GateFailure("INVALID_OBSERVATION")
        for value in (input_tokens, output_tokens):
            if value is not None:
                _integer(value)
        db = self._connect()
        try:
            row = db.execute(
                "SELECT state,input_bound,output_bound FROM attempts WHERE number=?", (number,)
            ).fetchone()
            if row is None or row[0] != "reserved":
                raise GateFailure("INVALID_OBSERVATION")
            if (input_tokens is not None and input_tokens > row[1]) or (
                output_tokens is not None and output_tokens > row[2]
            ):
                error_code = "USAGE_BOUND_EXCEEDED"
            db.execute(
                "UPDATE attempts SET state=?,input_tokens=?,output_tokens=?,error_code=? "
                "WHERE number=?",
                (
                    "failed" if error_code else "complete",
                    input_tokens,
                    output_tokens,
                    error_code,
                    number,
                ),
            )
            # Unknown usage remains unknown; reserved cost is NEVER refunded or estimated as zero.
            if error_code is not None or input_tokens is None or output_tokens is None:
                db.execute(
                    "UPDATE run SET halted=coalesce(halted,?) WHERE id=1",
                    (error_code or "USAGE_UNKNOWN",),
                )
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def attempt(
        self, slot_id: str, stage: str, target_id: str, wire: bytes, send: Callable[[], T]
    ) -> T:
        number = self.reserve(slot_id, stage, target_id, wire)
        try:
            result = send()
        except BaseException:
            self.finish(number, error_code="TEMPORARILY_UNAVAILABLE")
            raise
        self.finish(
            number
        )  # Usage unavailable through a generic callback => stop, not free budget.
        return result

    def halt(self, reason: str) -> None:
        if reason not in ERRORS | {
            "CONCRETE_DEFECT_MISSED",
            "CONTROL_REJECTED",
            "ADMISSION_FAILED",
        }:
            raise GateFailure("INVALID_OBSERVATION")
        self._authorize()
        db = self._connect()
        try:
            db.execute("UPDATE run SET halted=coalesce(halted,?) WHERE id=1", (reason,))
            db.commit()
        finally:
            db.close()

    def snapshot(self) -> dict:
        self._authorize()
        db = self._connect()
        try:
            halted = db.execute("SELECT halted FROM run WHERE id=1").fetchone()[0]
            rows = db.execute(
                "SELECT number,slot,stage,target,request_sha256,cost_micro,state,"
                "input_tokens,output_tokens,error_code FROM attempts ORDER BY number"
            ).fetchall()
            db.commit()
            return {
                "manifest_sha256": self.freeze,
                "halted": halted,
                "attempts": rows,
                "unattempted_slots": [
                    s["id"] for s in self.manifest["slots"] if s["id"] not in {r[1] for r in rows}
                ],
            }
        finally:
            db.close()
