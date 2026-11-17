"""Development-only durable reservation ledger. No network or authorization entry point."""

import hashlib
import math
import os
import sqlite3
import stat
import time
from pathlib import Path
from typing import Callable, cast


class ReservationError(ValueError):
    pass


class Ledger:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time):
        path = path.absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ReservationError("LEDGER_PATH")
        try:
            details = path.stat()
        except FileNotFoundError as exc:
            raise ReservationError("LEDGER_PATH") from exc
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise ReservationError("LEDGER_PATH")
        self.clock = clock
        self.db = sqlite3.connect(
            path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=1
        )
        self.db.row_factory = sqlite3.Row

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        input_budget: int,
        output_budget: int,
        calls: int,
        deadline: float,
        clock: Callable[[], float] = time.time,
    ) -> "Ledger":
        if (
            path.exists()
            or any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents))
            or any(type(v) is not int for v in (input_budget, output_budget, calls))
            or min(input_budget, output_budget, calls) <= 0
            or type(deadline) not in (float, int)
            or not math.isfinite(deadline)
            or deadline <= clock()
        ):
            raise ReservationError("INIT")
        # Exclusive creation ensures a stopped or unknown batch is never replaced.
        descriptor = os.open(
            path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        os.close(descriptor)
        ledger = cls(path, clock=clock)
        ledger.db.executescript("""
            CREATE TABLE batch (status TEXT, input_budget INTEGER, output_budget INTEGER,
                call_limit INTEGER, deadline REAL);
            CREATE TABLE attempts (ticket INTEGER PRIMARY KEY, request_sha TEXT NOT NULL,
                input_reserved INTEGER NOT NULL, output_reserved INTEGER NOT NULL,
                state TEXT NOT NULL, response_sha TEXT, input_used INTEGER, output_used INTEGER,
                response_raw BLOB);
        """)
        ledger.db.execute(
            "INSERT INTO batch VALUES ('active',?,?,?,?)",
            (input_budget, output_budget, calls, deadline),
        )
        return ledger

    def _active(self) -> sqlite3.Row:
        batch = self.db.execute("SELECT * FROM batch").fetchone()
        if (
            batch is None
            or batch["status"] != "active"
            or self.clock() >= batch["deadline"]
        ):
            raise ReservationError("STOPPED_OR_EXPIRED")
        return cast(sqlite3.Row, batch)

    def reserve(self, body: bytes, input_tokens: int, output_tokens: int) -> int:
        if (
            type(body) is not bytes
            or not body
            or type(input_tokens) is not int
            or type(output_tokens) is not int
            or min(input_tokens, output_tokens) <= 0
        ):
            raise ReservationError("RESERVATION")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            batch = self._active()
            rows = list(self.db.execute("SELECT * FROM attempts ORDER BY ticket"))
            if any(row["state"] != "settled" for row in rows):
                raise ReservationError("PENDING_OR_UNKNOWN")
            if any(
                row["request_sha"] == hashlib.sha256(body).hexdigest() for row in rows
            ):
                raise ReservationError("DUPLICATE_REQUEST")
            if (
                len(rows) >= batch["call_limit"]
                or sum(r["input_reserved"] for r in rows) + input_tokens
                > batch["input_budget"]
                or sum(r["output_reserved"] for r in rows) + output_tokens
                > batch["output_budget"]
            ):
                raise ReservationError("BUDGET")
            ticket = len(rows)
            self.db.execute(
                "INSERT INTO attempts VALUES (?,?,?,?, 'reserved',NULL,NULL,NULL,NULL)",
                (ticket, hashlib.sha256(body).hexdigest(), input_tokens, output_tokens),
            )
            self.db.execute("COMMIT")
            return ticket
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def sent(self, ticket: int, body: bytes) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._active()
            row = self.db.execute(
                "SELECT * FROM attempts WHERE ticket=?", (ticket,)
            ).fetchone()
            if (
                row is None
                or row["state"] != "reserved"
                or row["request_sha"] != hashlib.sha256(body).hexdigest()
            ):
                raise ReservationError("SEND_BINDING")
            self.db.execute(
                "UPDATE attempts SET state='sent' WHERE ticket=?", (ticket,)
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def settle(
        self, ticket: int, raw: bytes, input_used: int, output_used: int
    ) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            batch = self.db.execute("SELECT * FROM batch").fetchone()
            if batch is None:
                raise ReservationError("MISSING_BATCH")
            row = self.db.execute(
                "SELECT * FROM attempts WHERE ticket=?", (ticket,)
            ).fetchone()
            if (
                row is None
                or row["state"] not in ("sent", "unknown")
                or type(raw) is not bytes
                or type(input_used) is not int
                or type(output_used) is not int
                or min(input_used, output_used) < 0
            ):
                raise ReservationError("SETTLEMENT")
            late = (
                batch["status"] != "active"
                or self.clock() >= batch["deadline"]
                or row["state"] == "unknown"
            )
            over = (
                input_used > row["input_reserved"]
                or output_used > row["output_reserved"]
            )
            if late or over:
                self.db.execute("UPDATE batch SET status='stopped'")
                self.db.execute(
                    "UPDATE attempts SET state='unknown' WHERE state='sent' AND ticket!=?",
                    (ticket,),
                )
                self.db.execute(
                    "UPDATE attempts SET state='cancelled' WHERE state='reserved'"
                )
            self.db.execute(
                "UPDATE attempts SET state=?, response_sha=?, input_used=?, output_used=?, response_raw=? WHERE ticket=?",
                (
                    "late_over_budget"
                    if late and over
                    else "late_evidence"
                    if late
                    else "over_budget"
                    if over
                    else "settled",
                    hashlib.sha256(raw).hexdigest(),
                    input_used,
                    output_used,
                    raw,
                    ticket,
                ),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def stop(self) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("UPDATE batch SET status='stopped'")
            self.db.execute("UPDATE attempts SET state='unknown' WHERE state='sent'")
            self.db.execute(
                "UPDATE attempts SET state='cancelled' WHERE state='reserved'"
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def summary(self) -> dict[str, object]:
        batch = self.db.execute("SELECT * FROM batch").fetchone()
        attempts = [
            dict(row)
            for row in self.db.execute(
                "SELECT ticket,request_sha,input_reserved,output_reserved,state,response_sha,input_used,output_used FROM attempts ORDER BY ticket"
            )
        ]
        return {
            "status": batch["status"],
            "attempts": attempts,
            "input_reserved": sum(int(row["input_reserved"]) for row in attempts),
            "output_reserved": sum(int(row["output_reserved"]) for row in attempts),
        }

    def response_bytes(self, ticket: int) -> bytes | None:
        row = self.db.execute(
            "SELECT response_raw FROM attempts WHERE ticket=?", (ticket,)
        ).fetchone()
        if row is None:
            raise ReservationError("UNKNOWN_TICKET")
        return cast(bytes | None, row["response_raw"])
