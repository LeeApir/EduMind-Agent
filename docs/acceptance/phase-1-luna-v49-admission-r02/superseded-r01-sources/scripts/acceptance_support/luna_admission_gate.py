"""Request-count authority and irreversible stop ledger; fees explicitly uncapped by user."""

import json
import os
import sqlite3
import time
from pathlib import Path

from acceptance_support.qwen_review_budget import canonical, sha

BASE = "docs/acceptance/phase-1-luna-v49-admission-r01"
PRIVATE = "local-materials/phase-1-luna-v49-admission-r01"


def require(ok, code):
    if not ok:
        raise ValueError(code)


def read(path):
    require(path.is_file() and not path.is_symlink(), "FILE_REQUIRED")
    return json.loads(path.read_bytes())


def env_metadata(path):
    st = path.lstat()
    require(
        path.is_file() and not path.is_symlink() and st.st_mode & 0o077 == 0, "PRIVATE_ENV_REQUIRED"
    )
    return {
        k: getattr(st, k) for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    }


def verify_freeze(root):
    p = read(root / BASE / "manifest.json")
    for name, h in p["files"].items():
        path = root / name
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and sha(path.read_bytes()) == h,
            "FREEZE_CHANGED",
        )
    require(env_metadata(root / ".env") == p["env_metadata"], "ENV_CHANGED")
    return p, sha(canonical(p))


def approved(root):
    p, h = verify_freeze(root)
    a = read(root / BASE / "run-approval.json")
    require(
        a.get("manifest_sha256") == h
        and a.get("requests") == 12
        and type(a.get("requests")) is int
        and a.get("cost_policy") == "uncapped_by_explicit_user_instruction"
        and a.get("reviewer") == "Lee"
        and a.get("source_user_message")
        and a.get("decision") == "approve_exact_diagnostic",
        "NOT_AUTHORIZED",
    )
    labels = read(root / BASE / "labels-human.json")
    require(
        labels.get("manifest_sha256") == h
        and labels.get("reviewer") == "Lee"
        and labels.get("source_user_message")
        and labels.get("decision") == "accept_all_materials_and_labels"
        and labels.get("labels_sha256") == p["files"][BASE + "/proposed-labels.json"],
        "LABEL_REVIEW_REQUIRED",
    )
    require(time.time() < p["expires_at_epoch"], "APPROVAL_EXPIRED")
    return p, h


def private_write(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(canonical(value))
        f.flush()
        os.fsync(f.fileno())


class Ledger:
    def __init__(self, path, manifest_hash, now=None):
        self.path = Path(path)
        self.now = now or time.time
        require(not self.path.is_symlink(), "UNSAFE_LEDGER")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        require(self.path.stat().st_mode & 0o077 == 0, "UNSAFE_LEDGER")
        with self.db() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS run (hash TEXT PRIMARY KEY, started REAL, halted TEXT)"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS calls "
                "(n INTEGER PRIMARY KEY, slot TEXT UNIQUE, state TEXT, receipt TEXT)"
            )
            c.execute("INSERT OR IGNORE INTO run VALUES (?,?,NULL)", (manifest_hash, self.now()))
            require(
                c.execute("SELECT hash FROM run").fetchall() == [(manifest_hash,)],
                "LEDGER_REUSE_FORBIDDEN",
            )

    def db(self):
        return sqlite3.connect(self.path)

    def snapshot(self):
        with self.db() as c:
            started, halted = c.execute("SELECT started,halted FROM run").fetchone()
            rows = c.execute("SELECT n,slot,state,receipt FROM calls ORDER BY n").fetchall()
        return started, halted, rows

    def reserve(self, slots):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            start, halt = c.execute("SELECT started,halted FROM run").fetchone()
            rows = c.execute("SELECT n,slot,state FROM calls ORDER BY n").fetchall()
            if halt or self.now() - start >= 1800 or any(r[2] != "complete" for r in rows):
                c.execute("UPDATE run SET halted=COALESCE(halted,?)", ("STOPPED_OR_UNCERTAIN",))
                c.commit()
                raise ValueError("RUN_STOPPED_OR_UNCERTAIN")
            require(len(rows) < len(slots) == 12, "CALL_LIMIT")
            n = len(rows)
            slot = slots[n]
            c.execute("INSERT INTO calls VALUES (?,?,?,NULL)", (n, slot, "reserved"))
            return n, slot

    def finish(self, n, receipt_hash):
        with self.db() as c:
            require(
                c.execute("SELECT state FROM calls WHERE n=?", (n,)).fetchone() == ("reserved",),
                "STATE_CONFLICT",
            )
            c.execute("UPDATE calls SET state=?,receipt=? WHERE n=?", ("complete", receipt_hash, n))

    def stop(self, reason):
        with self.db() as c:
            c.execute("UPDATE run SET halted=COALESCE(halted,?)", (reason,))


def prior_human_checks(root, manifest_hash, ledger):
    _, halt, rows = ledger.snapshot()
    require(not halt, "RUN_STOPPED")
    for n, slot, state, receipt_hash in rows:
        if state != "complete":
            ledger.stop("SEND_STATE_UNCERTAIN")
            raise ValueError("SEND_STATE_UNCERTAIN")
        receipt = read(root / PRIVATE / (slot + ".json"))
        require(sha(canonical(receipt)) == receipt_hash, "RECEIPT_CHANGED")
        signed = read(root / BASE / "assessments" / (slot + ".json"))
        require(
            signed.get("manifest_sha256") == manifest_hash
            and signed.get("receipt_sha256") == receipt_hash
            and signed.get("reviewer") == "Lee"
            and signed.get("source_user_message"),
            "HUMAN_CHECK_REQUIRED",
        )
        if not (
            signed.get("integrity") is True
            and signed.get("all_claims") is True
            and signed.get("all_citations") is True
            and signed.get("criterion") is True
            and signed.get("issues") == []
        ):
            ledger.stop("SEMANTIC_OR_CITATION_FAILURE")
            raise ValueError("CANDIDATE_ELIMINATED")
    if len(rows) == 8:
        screen = read(root / BASE / "screen-pass.json")
        require(
            screen.get("manifest_sha256") == manifest_hash
            and screen.get("reviewer") == "Lee"
            and screen.get("source_user_message")
            and screen.get("decision") == "admit_holdout"
            and screen.get("receipts") == {r[1]: r[3] for r in rows},
            "SCREEN_PASS_REQUIRED",
        )
