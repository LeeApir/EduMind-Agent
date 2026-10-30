"""Development-only durable reservation ledger. No network or authorization entry point."""

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Callable, cast


class ReservationError(ValueError):
    pass


class Ledger:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.db = sqlite3.connect(path, isolation_level=None, timeout=1)
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
            or path.is_symlink()
            or min(input_budget, output_budget, calls) <= 0
            or deadline <= clock()
        ):
            raise ReservationError("INIT")
        # Exclusive creation ensures a stopped or unknown batch is never replaced.
        import os

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
                state TEXT NOT NULL, response_sha TEXT, input_used INTEGER, output_used INTEGER);
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
                "INSERT INTO attempts VALUES (?,?,?,?, 'reserved',NULL,NULL,NULL)",
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
            self._active()
            row = self.db.execute(
                "SELECT * FROM attempts WHERE ticket=?", (ticket,)
            ).fetchone()
            if (
                row is None
                or row["state"] != "sent"
                or type(raw) is not bytes
                or type(input_used) is not int
                or type(output_used) is not int
                or min(input_used, output_used) < 0
                or input_used > row["input_reserved"]
                or output_used > row["output_reserved"]
            ):
                raise ReservationError("SETTLEMENT")
            self.db.execute(
                "UPDATE attempts SET state='settled', response_sha=?, input_used=?, output_used=? WHERE ticket=?",
                (hashlib.sha256(raw).hexdigest(), input_used, output_used, ticket),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def stop(self) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("UPDATE batch SET status='stopped'")
            self.db.execute(
                "UPDATE attempts SET state='unknown' WHERE state IN ('sent','reserved')"
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def summary(self) -> dict[str, object]:
        batch = self.db.execute("SELECT * FROM batch").fetchone()
        attempts = [
            dict(row)
            for row in self.db.execute("SELECT * FROM attempts ORDER BY ticket")
        ]
        return {
            "status": batch["status"],
            "attempts": attempts,
            "input_reserved": sum(int(row["input_reserved"]) for row in attempts),
            "output_reserved": sum(int(row["output_reserved"]) for row in attempts),
        }
