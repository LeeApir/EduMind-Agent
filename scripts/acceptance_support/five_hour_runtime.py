"""Durable, fail-closed controls for the single limited acceptance run."""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from acceptance_support.qwen_review_budget import canonical, sha

ORDER = [
    *(f"U{i:02}" for i in range(1, 9)),
    *(f"R{i:02}" for i in range(1, 5)),
    *(f"A{i:02}" for i in range(1, 5)),
]
BASELINE = {name: 8 if name.startswith("A") else 1 for name in ORDER}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def write_once(path, data):
    path = Path(path)
    require(not path.is_symlink() and not path.parent.is_symlink(), "UNSAFE_ARTIFACT")
    raw = data if isinstance(data, bytes) else canonical(data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha(raw)


class RunLedger:
    """A reservation consumes a slot even if transport never reaches the Provider.

    Creation never resets T0. A process crash during a case prevents replay. SQLite
    transactions protect quota; the CLI additionally holds an exclusive process lock.
    """

    def __init__(self, path, digest, *, t0=None, now=time.time):
        self.path, self.digest, self.now = Path(path), digest, now
        require(not self.path.is_symlink(), "UNSAFE_LEDGER")
        if not self.path.exists():
            require(t0 is not None and t0 <= now(), "RUN_NOT_INITIALIZED")
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            with self.db() as db:
                db.executescript("""
                    CREATE TABLE run (digest TEXT, t0 REAL, last_clock REAL, halt TEXT);
                    CREATE TABLE cases (id TEXT PRIMARY KEY, state TEXT,
                                        result TEXT, evaluation TEXT);
                    CREATE TABLE calls (n INTEGER PRIMARY KEY, case_id TEXT, state TEXT,
                                        request_hash TEXT, response_hash TEXT);
                """)
                db.execute("INSERT INTO run VALUES (?,?,?,NULL)", (digest, t0, now()))
                db.executemany(
                    "INSERT INTO cases VALUES (?,'pending',NULL,NULL)", [(x,) for x in ORDER]
                )
        require(self.path.stat().st_mode & 0o077 == 0, "PRIVATE_LEDGER_REQUIRED")
        with self.db() as db:
            require(db.execute("SELECT digest FROM run").fetchall() == [(digest,)], "RUN_REUSE")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _clock(self, db, *, sending=False):
        t0, last, halt = db.execute("SELECT t0,last_clock,halt FROM run").fetchone()
        now = self.now()
        require(halt is None, "RUN_STOPPED")
        require(now >= last, "CLOCK_MOVED_BACKWARD")
        require(now < t0 + (16200 if sending else 18000), "RUN_DEADLINE")
        db.execute("UPDATE run SET last_clock=?", (now,))

    def start_case(self, name):
        require(name in ORDER, "UNKNOWN_CASE")
        with self.db() as db:
            self._clock(db, sending=True)
            rows = db.execute("SELECT id,state FROM cases").fetchall()
            states = dict(rows)
            require(
                all(states[x] == "assessed" for x in ORDER[: ORDER.index(name)]),
                "PREVIOUS_GPT_ASSESSMENT_REQUIRED",
            )
            require(states[name] == "pending", "CASE_REPLAY_FORBIDDEN")
            require(
                not db.execute("SELECT 1 FROM calls WHERE state!='complete'").fetchone(),
                "UNKNOWN_SEND_STATE",
            )
            db.execute("UPDATE cases SET state='running' WHERE id=?", (name,))

    def reserve(self, name, request_hash):
        with self.db() as db:
            self._clock(db, sending=True)
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (name,)).fetchone()
                == ("running",),
                "CASE_NOT_RUNNING",
            )
            require(
                not db.execute("SELECT 1 FROM calls WHERE state!='complete'").fetchone(),
                "UNKNOWN_SEND_STATE",
            )
            total = db.execute("SELECT count(*) FROM calls").fetchone()[0]
            own = db.execute("SELECT count(*) FROM calls WHERE case_id=?", (name,)).fetchone()[0]
            require(total < 60 and own < (20 if name.startswith("A") else 1), "CALL_LIMIT")
            # Extras never reuse unused baseline, including already failed cases.
            extras = sum(
                max(0, count - BASELINE[case])
                for case, count in db.execute("SELECT case_id,count(*) FROM calls GROUP BY case_id")
            )
            require(own < BASELINE[name] or extras < 16, "SHARED_EXTRA_LIMIT")
            n = total + 1
            db.execute("INSERT INTO calls VALUES (?,?,'reserved',?,NULL)", (n, name, request_hash))
            return n

    def complete_call(self, n, response_hash):
        with self.db() as db:
            require(
                db.execute("SELECT state FROM calls WHERE n=?", (n,)).fetchone() == ("reserved",),
                "CALL_NOT_RESERVED",
            )
            db.execute(
                "UPDATE calls SET state='complete',response_hash=? WHERE n=?", (response_hash, n)
            )

    def finish_case(self, name, result_hash):
        with self.db() as db:
            self._clock(db)
            require(
                not db.execute("SELECT 1 FROM calls WHERE state!='complete'").fetchone(),
                "UNKNOWN_SEND_STATE",
            )
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (name,)).fetchone()
                == ("running",),
                "CASE_NOT_RUNNING",
            )
            db.execute(
                "UPDATE cases SET state='awaiting_gpt',result=? WHERE id=?", (result_hash, name)
            )

    def assess(self, name, evaluation_hash, *, red=False):
        with self.db() as db:
            self._clock(db)
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (name,)).fetchone()
                == ("awaiting_gpt",),
                "CASE_NOT_AWAITING_GPT",
            )
            db.execute(
                "UPDATE cases SET state='assessed',evaluation=? WHERE id=?", (evaluation_hash, name)
            )
            if red:
                db.execute("UPDATE run SET halt='RED_EVENT'")

    def stop(self, reason):
        with self.db() as db:
            db.execute("UPDATE run SET halt=coalesce(halt,?)", (reason,))

    def snapshot(self):
        with self.db() as db:
            return dict(
                run=db.execute("SELECT * FROM run").fetchone(),
                cases=db.execute("SELECT * FROM cases").fetchall(),
                calls=db.execute("SELECT * FROM calls ORDER BY n").fetchall(),
            )


def private_directory(path):
    path = Path(path)
    require(not path.is_symlink(), "UNSAFE_PRIVATE_DIRECTORY")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(path.stat().st_mode & 0o077 == 0, "PRIVATE_DIRECTORY_REQUIRED")
    return path


def read_json(path):
    require(not path.is_symlink(), "UNSAFE_INPUT")
    return json.loads(path.read_bytes())
