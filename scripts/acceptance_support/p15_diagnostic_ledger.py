"""Separate diagnostic budget kernel. No transport, credentials, or authority creation.

An integrating runner must verify a human approval registry and pin its exact digest.
This kernel checks the binding, not the authenticity of a human signature. No live runner
is registered until the candidate, labels, pricing and execution package are frozen.
"""

import hashlib
import json
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


class Refused(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    requests: int
    input_tokens: int
    output_tokens: int
    fee_micros: int | None
    wall_seconds: int

    def validate(self):
        if any(
            type(v) is not int or v <= 0 for k, v in asdict(self).items() if k != "fee_micros"
        ) or (
            self.fee_micros is not None
            and (type(self.fee_micros) is not int or self.fee_micros <= 0)
        ):
            raise Refused("INVALID_LIMIT")


class Ledger:
    def __init__(self, path: Path, *, clock=None):
        self.clock = clock or (lambda: (time.time(), time.monotonic()))
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS batches(
            id TEXT PRIMARY KEY, package TEXT NOT NULL, approval TEXT NOT NULL,
            limits_json TEXT NOT NULL, state TEXT NOT NULL, reason TEXT,
            start_wall REAL NOT NULL,start_mono REAL NOT NULL,
            last_wall REAL NOT NULL,last_mono REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS attempts(
            batch TEXT NOT NULL REFERENCES batches(id),id TEXT NOT NULL,state TEXT NOT NULL,
            input_max INTEGER NOT NULL,output_max INTEGER NOT NULL,fee_max INTEGER NOT NULL,
            input_used INTEGER,output_used INTEGER,fee_used INTEGER,
            wall REAL NOT NULL,mono REAL NOT NULL,seconds INTEGER NOT NULL,
            PRIMARY KEY(batch,id));
          CREATE TABLE IF NOT EXISTS receipts(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,batch TEXT NOT NULL REFERENCES batches(id),
            attempt TEXT,kind TEXT NOT NULL,wall REAL NOT NULL,body TEXT NOT NULL);
          CREATE TRIGGER IF NOT EXISTS receipts_no_update BEFORE UPDATE ON receipts
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECEIPT'); END;
          CREATE TRIGGER IF NOT EXISTS receipts_no_delete BEFORE DELETE ON receipts
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECEIPT'); END;
          CREATE TRIGGER IF NOT EXISTS frozen_batch BEFORE
            UPDATE OF package,approval,limits_json,start_wall,start_mono ON batches
            BEGIN SELECT RAISE(ABORT,'FROZEN_BATCH'); END;
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Refused:
            # Refusals may have durably stopped the batch. Never roll that stop back.
            self.db.commit()
            raise
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def record(self, batch, kind, body, attempt=None):
        wall = self.clock()[0]
        if not math.isfinite(wall):
            wall = self.db.execute("SELECT last_wall FROM batches WHERE id=?", (batch,)).fetchone()[
                0
            ]
            body = {**body, "timestamp_source": "last_valid_wall"}
        self.db.execute(
            "INSERT INTO receipts(batch,attempt,kind,wall,body) VALUES(?,?,?,?,?)",
            (
                batch,
                attempt,
                kind,
                wall,
                json.dumps(body, sort_keys=True, allow_nan=False),
            ),
        )

    def start(self, batch, package_sha256, limits, approval, *, pinned_approval_sha256):
        limits.validate()
        if not re.fullmatch("[a-f0-9]{64}", package_sha256):
            raise Refused("PACKAGE_DIGEST_REQUIRED")
        if not approval or not pinned_approval_sha256 or digest(approval) != pinned_approval_sha256:
            raise Refused("ACCURATE_APPROVAL_REQUIRED")
        if (
            approval.get("package_sha256") != package_sha256
            or approval.get("batch_id") != batch
            or approval.get("limits") != asdict(limits)
            or approval.get("scope") != "PHASE-1.5-T038"
            or not approval.get("evidence_ref")
        ):
            raise Refused("APPROVAL_BINDING_MISMATCH")
        if limits.fee_micros is None and approval.get("fee_cap_waiver") is not True:
            raise Refused("EXPLICIT_FEE_CAP_WAIVER_REQUIRED")
        wall, mono = self.clock()
        if not all(math.isfinite(t) for t in [wall, mono]):
            raise Refused("CLOCK_ANOMALY")
        with self.transaction():
            if self.db.execute("SELECT 1 FROM batches WHERE id=?", (batch,)).fetchone():
                raise Refused("BATCH_ALREADY_STARTED")
            self.db.execute(
                "INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    batch,
                    package_sha256,
                    pinned_approval_sha256,
                    json.dumps(asdict(limits)),
                    "running",
                    None,
                    wall,
                    mono,
                    wall,
                    mono,
                ),
            )
            self.record(
                batch, "started", {"package": package_sha256, "approval": pinned_approval_sha256}
            )

    def stop(self, batch, reason):
        changed = self.db.execute(
            "UPDATE batches SET state='stopped',reason=? WHERE id=? AND state='running'",
            (reason, batch),
        ).rowcount
        if changed:
            self.record(batch, "stopped", {"reason": reason})

    def guard(self, batch, package):
        row = self.db.execute("SELECT * FROM batches WHERE id=?", (batch,)).fetchone()
        if row is None:
            raise Refused("NOT_STARTED")
        if row["package"] != package:
            self.stop(batch, "CONFIG_CHANGED")
            raise Refused("CONFIG_CHANGED")
        if row["state"] != "running":
            raise Refused("BATCH_STOPPED")
        wall, mono = self.clock()
        limits = json.loads(row["limits_json"])
        if (
            not all(math.isfinite(t) for t in [wall, mono])
            or wall < row["last_wall"]
            or mono < row["last_mono"]
            or abs((wall - row["start_wall"]) - (mono - row["start_mono"])) > 5
        ):
            self.stop(batch, "CLOCK_ANOMALY")
            raise Refused("CLOCK_ANOMALY")
        if max(wall - row["start_wall"], mono - row["start_mono"]) >= limits["wall_seconds"]:
            self.stop(batch, "WALL_LIMIT")
            raise Refused("WALL_LIMIT")
        self.db.execute(
            "UPDATE batches SET last_wall=?,last_mono=? WHERE id=?", (wall, mono, batch)
        )
        return limits

    def usage(self, batch):
        row = self.db.execute(
            """SELECT count(*) AS requests,
            coalesce(sum(coalesce(input_used,input_max)),0) AS input_tokens,
            coalesce(sum(coalesce(output_used,output_max)),0) AS output_tokens,
            coalesce(sum(coalesce(fee_used,fee_max)),0) AS fee_micros
            FROM attempts WHERE batch=?""",
            (batch,),
        ).fetchone()
        return dict(row)

    def reserve(self, batch, package, attempt, *, input_max, output_max, fee_max, seconds=120):
        if (
            any(type(v) is not int or v < 0 for v in [input_max, output_max, fee_max])
            or (
                (input_max == 0 or output_max == 0)
                and (input_max != 0 or output_max != 0 or fee_max != 0)
            )
            or type(seconds) is not int
            or not 1 <= seconds <= 120
            or input_max > 32000
            or output_max > 8000
        ):
            raise Refused("CALL_BOUND_INVALID")
        with self.transaction():
            limits = self.guard(batch, package)
            if self.db.execute(
                "SELECT 1 FROM attempts WHERE batch=? AND id=?", (batch, attempt)
            ).fetchone():
                raise Refused("ATTEMPT_ALREADY_RESERVED")
            used = self.usage(batch)
            increment = dict(
                requests=1, input_tokens=input_max, output_tokens=output_max, fee_micros=fee_max
            )
            if any(limits[k] is not None and used[k] + v > limits[k] for k, v in increment.items()):
                self.stop(batch, "BUDGET_EXHAUSTED")
                raise Refused("BUDGET_EXHAUSTED")
            wall, mono = self.clock()
            self.db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,?,NULL,NULL,NULL,?,?,?)",
                (batch, attempt, "reserved", input_max, output_max, fee_max, wall, mono, seconds),
            )
            self.record(batch, "reserved", increment, attempt)

    def mark_sent(self, batch, package, attempt):
        with self.transaction():
            self.guard(batch, package)
            row = self.db.execute(
                "SELECT * FROM attempts WHERE batch=? AND id=?", (batch, attempt)
            ).fetchone()
            if row is None or row["state"] != "reserved":
                raise Refused("NOT_NEW_RESERVED_ATTEMPT")
            if max(self.clock()[0] - row["wall"], self.clock()[1] - row["mono"]) >= row["seconds"]:
                self.stop(batch, "CALL_DEADLINE")
                raise Refused("CALL_DEADLINE")
            self.db.execute(
                "UPDATE attempts SET state='sent' WHERE batch=? AND id=?", (batch, attempt)
            )
            self.record(batch, "sent", {}, attempt)

    def settle(
        self,
        batch,
        attempt,
        *,
        outcome,
        proof_sha256=None,
        input_used=None,
        output_used=None,
        fee_used=None,
    ):
        with self.transaction():
            row = self.db.execute(
                "SELECT * FROM attempts WHERE batch=? AND id=?", (batch, attempt)
            ).fetchone()
            if row is None or row["state"] in ["complete", "not_executed"]:
                raise Refused("SETTLEMENT_CONFLICT")
            if outcome not in ["complete", "not_executed", "unknown"]:
                raise Refused("OUTCOME_INVALID")
            # Late response can settle actual costs but can never reopen the batch.
            try:
                self.guard(
                    batch,
                    self.db.execute("SELECT package FROM batches WHERE id=?", (batch,)).fetchone()[
                        0
                    ],
                )
            except Refused:
                pass
            if max(self.clock()[0] - row["wall"], self.clock()[1] - row["mono"]) >= row["seconds"]:
                self.stop(batch, "CALL_DEADLINE")
            if outcome == "unknown":
                self.db.execute(
                    "UPDATE attempts SET state='unknown' WHERE batch=? AND id=?", (batch, attempt)
                )
                self.stop(batch, "UNKNOWN_SEND")
                self.record(batch, "unknown", {}, attempt)
                return
            if not proof_sha256 or not re.fullmatch("[a-f0-9]{64}", proof_sha256):
                raise Refused("VERIFIED_EXECUTION_PROOF_REQUIRED")
            values = [input_used, output_used, fee_used]
            if any(type(v) is not int or v < 0 for v in values):
                raise Refused("USAGE_REQUIRED")
            if outcome == "complete" and row["state"] not in ["sent", "unknown"]:
                raise Refused("NOT_SENT")
            if outcome == "not_executed" and any(values):
                raise Refused("NOT_EXECUTED_USAGE_INVALID")
            if any(
                value > row[key]
                for value, key in zip(values, ["input_max", "output_max", "fee_max"])
            ):
                self.stop(batch, "USAGE_OVERFLOW")
                raise Refused("USAGE_OVERFLOW")
            self.db.execute(
                "UPDATE attempts SET state=?,input_used=?,output_used=?,fee_used=? "
                "WHERE batch=? AND id=?",
                (outcome, *values, batch, attempt),
            )
            self.record(
                batch,
                "settled",
                {
                    "outcome": outcome,
                    "proof": proof_sha256,
                    "input_tokens": input_used,
                    "output_tokens": output_used,
                    "fee_micros": fee_used,
                },
                attempt,
            )

    def halt(self, batch, reason):
        if reason not in [
            "natural_severe_error",
            "security_incident",
            "independence_contaminated",
            "threshold_unreachable",
            "human_pause",
            "provider_contract_failure",
        ]:
            raise Refused("STOP_REASON_INVALID")
        with self.transaction():
            self.stop(batch, reason)
