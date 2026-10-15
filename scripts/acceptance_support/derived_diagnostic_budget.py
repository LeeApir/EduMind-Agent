"""ADR-0014 diagnostic reservation kernel. No credentials, HTTP or production registration.

Approval is supplied by trusted composition, not parsed from model/manifest booleans.
consume() returns frozen bytes for offline testing; it never sends them.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from jsonschema import Draft202012Validator

from . import claim_review_prototype as claims
from .phase1_budget import ERRORS, Approval, GateFailure

VERSION = "phase1-derived-diagnostic-v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
STAGES = ("inventory", "coverage", "claim", "overall", "correction")


def require(condition, code="INVALID_DERIVED_FREEZE"):
    if not condition:
        raise GateFailure(code)


def integer(value, lo=0, hi=10**12):
    require(type(value) is int and lo <= value <= hi)
    return value


def exact(value, keys):
    try:
        return claims.obj(value, keys)
    except claims.Invalid:
        raise GateFailure("INVALID_DERIVED_SCHEMA") from None


def hashed(value):
    return claims.digest(value)


def slot_id(case, round_id, stage, ordinal=0):
    return f"{case}.r{round_id}.{stage}.{ordinal}"


def price(policy, wire_bytes):
    i = wire_bytes + policy["input_overhead_tokens"]
    o = policy["max_output_tokens"]
    return (i * policy["input_price_micro_per_million"] + 999999) // 1000000 + (
        o * policy["output_price_micro_per_million"] + 999999
    ) // 1000000


class DerivedBudget:
    def __init__(self, manifest, *, root: Path, approval: Approval | None = None):
        self.serialized = claims.encoded(manifest)
        self.freeze = hashed(manifest)
        self.root = root.resolve()
        self.approval = approval
        self._lock_fd = None
        self._attempt_mono = {}
        self._validate()
        self._approve()
        self.ledger = self._path(self.manifest["ledger_path"])
        self.registry = self._path(self.manifest["registry_path"])
        require(self.ledger != self.registry, "INVALID_LEDGER_PATH")
        self._acquire()
        try:
            self._enroll()
            with self._db() as db:
                self._gate(db)
                active = db.execute(
                    "SELECT count(*) FROM children WHERE state IN ('reserved','intent')"
                ).fetchone()[0]
                if active:
                    self._halt(db, "SEND_STATE_UNCERTAIN")
                self.deadline = db.execute("SELECT deadline FROM run").fetchone()[0]
            self.mono_deadline = time.monotonic() + max(0, self.deadline - time.time())
        except BaseException:
            self.close()
            raise

    @property
    def manifest(self):
        return json.loads(self.serialized)

    def _validate(self):
        m = exact(
            self.manifest,
            "version run_id phase execution_root ledger_path registry_path files target config "
            "currency cases max_claims corrections stages bounds prerequisite_sha256",
        )
        require(m["version"] == VERSION and m["phase"] == "diagnostic")
        require(m["execution_root"] == str(self.root), "ROOT_CHANGED")
        require(type(m["run_id"]) is str and NAME.fullmatch(m["run_id"]))
        require(m["currency"] in ("CNY", "USD"))
        require(type(m["files"]) is dict and bool(m["files"]))
        for name, digest in m["files"].items():
            self._path(name)
            require(type(digest) is str and HASH.fullmatch(digest))
        require(type(m["prerequisite_sha256"]) is str and HASH.fullmatch(m["prerequisite_sha256"]))
        exact(m["target"], "model target_sha256")
        require(type(m["target"]["model"]) is str and bool(m["target"]["model"]))
        require(
            type(m["target"]["target_sha256"]) is str
            and HASH.fullmatch(m["target"]["target_sha256"])
        )
        exact(m["config"], "reasoning temperature")
        require(m["config"]["reasoning"] in ("none", "low", "high", "max"))
        require(
            type(m["config"]["temperature"]) in (int, float)
            and 0 <= m["config"]["temperature"] <= 2
        )
        k, c = integer(m["max_claims"], 1, 16), integer(m["corrections"], 0, 2)
        require(type(m["cases"]) is list and 1 <= len(m["cases"]) <= 13)
        ids = []
        for case in m["cases"]:
            exact(case, "id resource_type content reference_context label_sha256")
            require(type(case["id"]) is str and NAME.fullmatch(case["id"]))
            require(type(case["label_sha256"]) is str and HASH.fullmatch(case["label_sha256"]))
            self._snap(case)
            ids.append(case["id"])
        require(len(ids) == len(set(ids)))
        exact(m["stages"], "inventory coverage claim overall correction")
        for policy in m["stages"].values():
            exact(
                policy,
                "system schema max_wire_bytes max_result_bytes input_overhead_tokens "
                "max_output_tokens input_price_micro_per_million "
                "output_price_micro_per_million proof_sha256 timeout_seconds",
            )
            require(type(policy["system"]) is str and bool(policy["system"]))
            require(type(policy["schema"]) is dict and bool(policy["schema"]))

            def no_refs(node):
                if isinstance(node, dict):
                    require(
                        not any(k in node for k in ("$ref", "$dynamicRef", "$id")),
                        "SCHEMA_REFERENCE_FORBIDDEN",
                    )
                    for child in node.values():
                        no_refs(child)
                elif isinstance(node, list):
                    for child in node:
                        no_refs(child)

            no_refs(policy["schema"])
            Draft202012Validator.check_schema(policy["schema"])
            integer(policy["max_result_bytes"], 1, 262144)
            integer(policy["max_wire_bytes"], 1, 2 * 1024 * 1024)
            integer(policy["max_output_tokens"], 1, 384000)
            integer(policy["timeout_seconds"], 1, 3600)
            for field in (
                "input_overhead_tokens",
                "input_price_micro_per_million",
                "output_price_micro_per_million",
            ):
                integer(policy[field])
            require(policy["proof_sha256"] in m["files"].values(), "COST_PROOF_MISSING")
        b = exact(m["bounds"], "requests cost_micro expires_at overall_seconds")
        worst_calls = len(ids) * ((k + 3) * (c + 1) + c)
        integer(b["requests"], worst_calls, 10000)
        integer(b["cost_micro"])
        integer(b["expires_at"], 1)
        integer(b["overall_seconds"], 1, 86400)
        costs = {s: price(policy, policy["max_wire_bytes"]) for s, policy in m["stages"].items()}
        worst_cost = len(ids) * (
            (c + 1)
            * (costs["inventory"] + costs["coverage"] + k * costs["claim"] + costs["overall"])
            + c * costs["correction"]
        )
        require(b["cost_micro"] >= worst_cost, "INSUFFICIENT_WORST_CASE_BUDGET")

    def _path(self, name):
        require(type(name) is str and bool(name), "UNSAFE_PATH")
        rel = Path(name)
        require(not rel.is_absolute() and ".." not in rel.parts and rel != Path("."), "UNSAFE_PATH")
        path = self.root / rel
        require(
            not any(p.is_symlink() for p in [path, *path.parents] if p != self.root.parent),
            "UNSAFE_PATH",
        )
        require(path.resolve().is_relative_to(self.root), "UNSAFE_PATH")
        return path

    def _approve(self):
        a, b = self.approval, self.manifest["bounds"]
        require(
            a is not None
            and a.authorized is True
            and type(a.requests) is int
            and type(a.cost_micro) is int
            and a.phase == "diagnostic"
            and a.manifest_sha256 == self.freeze
            and a.requests == b["requests"]
            and a.cost_micro == b["cost_micro"]
            and type(a.record_sha256) is str
            and HASH.fullmatch(a.record_sha256),
            "NOT_AUTHORIZED",
        )

    def _sources(self):
        for name, digest in self.manifest["files"].items():
            p = self._path(name)
            require(
                p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == digest,
                "FREEZE_CHANGED",
            )

    def _safe_file(self, path):
        require(
            path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0,
            "LEDGER_UNSAFE",
        )

    def _create_file(self, path, data=b""):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path(str(path.relative_to(self.root)))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _acquire(self):
        lock = self._path(".derived-diagnostic-active.lock")
        if not lock.exists():
            try:
                self._create_file(lock)
            except FileExistsError:
                pass
        self._safe_file(lock)
        self._lock_fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.close()
            raise GateFailure("RUN_ACTIVE") from None

    def close(self):
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _enroll(self):
        expected = {
            "version": VERSION,
            "run_id": self.manifest["run_id"],
            "root": self.freeze,
            "approval": self.approval.record_sha256,
            "ledger_path": self.manifest["ledger_path"],
        }
        if self.registry.exists():
            self._safe_file(self.registry)
            require(json.loads(self.registry.read_bytes()) == expected, "REGISTRY_MISMATCH")
            require(self.ledger.exists(), "LEDGER_MISSING")
            self._safe_file(self.ledger)
            return
        require(not self.ledger.exists(), "REGISTRY_MISSING")
        self._sources()
        self._create_file(self.registry, claims.encoded(expected))
        self._create_file(self.ledger)
        now = time.time()
        deadline = min(
            self.manifest["bounds"]["expires_at"], now + self.manifest["bounds"]["overall_seconds"]
        )
        with sqlite3.connect(self.ledger) as db:
            db.execute(
                "CREATE TABLE run (root TEXT, approval TEXT, deadline REAL, "
                "last_clock REAL, halted TEXT)"
            )
            db.execute(
                "INSERT INTO run VALUES(?,?,?,?,NULL)",
                (self.freeze, self.approval.record_sha256, deadline, now),
            )
            db.execute(
                "CREATE TABLE children (number INTEGER PRIMARY KEY, slot TEXT UNIQUE, "
                "case_id TEXT, round_id INTEGER, stage TEXT, ordinal INTEGER, parents TEXT, "
                "wire BLOB, wire_hash TEXT, cost INTEGER, input_bound INTEGER, "
                "output_bound INTEGER, "
                "state TEXT, value TEXT, value_hash TEXT, response_hash TEXT, "
                "input_tokens INTEGER, output_tokens INTEGER, attempt_deadline REAL, "
                "reasoning_tokens INTEGER)"
            )
            db.execute(
                "CREATE TABLE decisions (case_id TEXT, round_id INTEGER, action TEXT, "
                "evidence TEXT, PRIMARY KEY(case_id,round_id))"
            )

    @contextmanager
    def _db(self):
        require(self._lock_fd is not None, "CLOSED")
        self._approve()
        self._path(self.manifest["registry_path"])
        self._path(self.manifest["ledger_path"])
        self._safe_file(self.registry)
        self._safe_file(self.ledger)
        expected = {
            "version": VERSION,
            "run_id": self.manifest["run_id"],
            "root": self.freeze,
            "approval": self.approval.record_sha256,
            "ledger_path": self.manifest["ledger_path"],
        }
        require(json.loads(self.registry.read_bytes()) == expected, "REGISTRY_MISMATCH")
        db = sqlite3.connect(self.ledger, timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException as exc:
            code = exc.code if isinstance(exc, GateFailure) else "INVALID_PERSISTED_DATA"
            transient = {
                "RUN_COMPLETE",
                "CASE_REVIEW_REQUIRED",
                "ATTEMPT_ACTIVE",
                "SEND_ALREADY_CONSUMED",
                "CORRECTION_NOT_APPROVED",
                "INVALID_ASSESSMENT",
            }
            if code not in transient:
                try:
                    db.execute("UPDATE run SET halted=coalesce(halted,?)", (code,))
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
            else:
                db.rollback()
            if isinstance(exc, (json.JSONDecodeError, sqlite3.DatabaseError, claims.Invalid)):
                raise GateFailure(code) from None
            raise
        finally:
            db.close()

    def _halt(self, db, reason):
        db.execute("UPDATE run SET halted=coalesce(halted,?)", (reason,))
        db.commit()
        raise GateFailure(reason)

    def _gate(self, db):
        row = db.execute("SELECT * FROM run").fetchone()
        require(
            row is not None
            and row["root"] == self.freeze
            and row["approval"] == self.approval.record_sha256,
            "LEDGER_MISMATCH",
        )
        if row["halted"]:
            raise GateFailure("RUN_HALTED")
        try:
            self._sources()
        except GateFailure as exc:
            self._halt(db, exc.code)
        now = time.time()
        if now < row["last_clock"]:
            self._halt(db, "CLOCK_ROLLBACK")
        if now >= row["deadline"] or (
            hasattr(self, "mono_deadline") and time.monotonic() >= self.mono_deadline
        ):
            self._halt(db, "DEADLINE")
        db.execute("UPDATE run SET last_clock=?", (now,))

    def _snap(self, case, value=None):
        content = case["content"] if value is None else value["content"]
        return claims.freeze(
            case["resource_type"],
            content,
            case["reference_context"],
            {"target": self.manifest["target"], "config": self.manifest["config"]},
        )

    def _row(self, db, case_id, r, stage, ordinal=0):
        return db.execute(
            "SELECT * FROM children WHERE slot=?", (slot_id(case_id, r, stage, ordinal),)
        ).fetchone()

    def _value(self, row):
        require(row is not None and row["state"] == "verified", "PARENT_NOT_VERIFIED")
        value = json.loads(row["value"])
        require(hashed(value) == row["value_hash"], "PARENT_HASH_MISMATCH")
        exact(value, "request_binding result")
        require(
            value["request_binding"] == self._binding(row["slot"], json.loads(row["parents"])),
            "PARENT_BINDING_MISMATCH",
        )
        return value["result"]

    def _round(self, db, case, r):
        correction = None if r == 0 else self._row(db, case["id"], r - 1, "correction")
        snap = self._snap(case, None if r == 0 else self._value(correction))
        ir = self._row(db, case["id"], r, "inventory")
        cr = self._row(db, case["id"], r, "coverage")
        inv = None
        if cr is not None and cr["state"] == "verified":
            inv = claims.inventory(snap, self._value(ir), self._value(cr))
            by_id = {b["block_id"]: b["path"] for b in snap.blocks}

            def key(c):
                a = min(c["anchors"], key=lambda a: (by_id[a["block_id"]], a["start"], a["end"]))
                return by_id[a["block_id"]], a["start"], a["end"], c["claim_id"]

            inv["claims"].sort(key=key)
        return snap, correction, ir, cr, inv

    def _next(self, db):
        for case in self.manifest["cases"]:
            for r in range(self.manifest["corrections"] + 1):
                decision = db.execute(
                    "SELECT * FROM decisions WHERE case_id=? AND round_id=?", (case["id"], r)
                ).fetchone()
                if decision and decision["action"] == "continue":
                    break
                if decision and decision["action"] == "correct":
                    row = self._row(db, case["id"], r, "correction")
                    if row is None:
                        return case, r, "correction", 0
                    self._value(row)
                    continue
                _, _, ir, cr, inv = self._round(db, case, r)
                if ir is None:
                    return case, r, "inventory", 0
                self._value(ir)
                if cr is None:
                    return case, r, "coverage", 0
                self._value(cr)
                for ordinal in range(1, len(inv["claims"]) + 1):
                    row = self._row(db, case["id"], r, "claim", ordinal)
                    if row is None:
                        return case, r, "claim", ordinal
                    self._value(row)
                overall = self._row(db, case["id"], r, "overall")
                if overall is None:
                    return case, r, "overall", 0
                self._value(overall)
                raise GateFailure("CASE_REVIEW_REQUIRED")
        raise GateFailure("RUN_COMPLETE")

    def _build(self, db, case, r, stage, ordinal):
        snap, correction, ir, cr, inv = self._round(db, case, r)
        parents = []
        if correction is not None:
            parents.append(correction)
        payload = {"candidate": snap.data, "identity": snap.identity}
        if stage != "inventory":
            parents.append(ir)
            payload["inventory"] = self._value(ir) if stage == "coverage" else inv
        if stage in ("claim", "overall", "correction"):
            parents.append(cr)
        if stage == "claim":
            payload["focus"] = inv["claims"][ordinal - 1]
        if stage in ("overall", "correction"):
            for n in range(1, len(inv["claims"]) + 1):
                parents.append(self._row(db, case["id"], r, "claim", n))
        if stage == "correction":
            parents.append(self._row(db, case["id"], r, "overall"))
            payload["issues"] = self._aggregate(db, case, r)[1]
        refs = []
        for row in parents:
            self._value(row)
            refs.append({"number": row["number"], "value_hash": row["value_hash"]})
        payload["request_binding"] = self._binding(slot_id(case["id"], r, stage, ordinal), refs)
        policy = self.manifest["stages"][stage]
        wire = claims.encoded(
            {
                "model": self.manifest["target"]["model"],
                "input": [
                    {"role": "system", "content": policy["system"]},
                    {"role": "user", "content": claims.encoded(payload).decode()},
                ],
                "reasoning": {"effort": self.manifest["config"]["reasoning"]},
                "temperature": self.manifest["config"]["temperature"],
                "max_output_tokens": policy["max_output_tokens"],
                "text": {
                    "format": {"type": "json_schema", "name": stage, "schema": policy["schema"]}
                },
            }
        )
        return snap, wire, refs

    def _binding(self, slot, parents):
        return {"root_sha256": self.freeze, "slot": slot, "parents_sha256": hashed(parents)}

    def prepare(self):
        """No reservation/send; return only the deterministic next legal request."""
        with self._db() as db:
            self._gate(db)
            if db.execute(
                "SELECT count(*) FROM children WHERE state IN ('reserved','intent')"
            ).fetchone()[0]:
                raise GateFailure("ATTEMPT_ACTIVE")
            case, r, stage, ordinal = self._next(db)
            _, wire, refs = self._build(db, case, r, stage, ordinal)
            return {"slot": slot_id(case["id"], r, stage, ordinal), "wire": wire, "parents": refs}

    def reserve(self, slot, wire, parents):
        with self._db() as db:
            self._gate(db)
            if db.execute(
                "SELECT count(*) FROM children WHERE state IN ('reserved','intent')"
            ).fetchone()[0]:
                raise GateFailure("ATTEMPT_ACTIVE")
            case, r, stage, ordinal = self._next(db)
            _, expected, refs = self._build(db, case, r, stage, ordinal)
            require(slot == slot_id(case["id"], r, stage, ordinal), "SLOT_NOT_APPROVED")
            require(
                type(wire) is bytes
                and wire == expected
                and claims.encoded(parents) == claims.encoded(refs),
                "DERIVATION_MISMATCH",
            )
            policy = self.manifest["stages"][stage]
            require(len(wire) <= policy["max_wire_bytes"], "INPUT_BOUND_EXCEEDED")
            count, cost = db.execute(
                "SELECT count(*),coalesce(sum(cost),0) FROM children"
            ).fetchone()
            reserved = price(policy, len(wire))
            require(
                count < self.manifest["bounds"]["requests"]
                and cost + reserved <= self.manifest["bounds"]["cost_micro"],
                "BUDGET_EXHAUSTED",
            )
            db.execute(
                "INSERT INTO children VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,"
                "NULL,NULL,NULL,NULL,NULL,?,NULL)",
                (
                    count + 1,
                    slot,
                    case["id"],
                    r,
                    stage,
                    ordinal,
                    claims.encoded(refs).decode(),
                    wire,
                    hashlib.sha256(wire).hexdigest(),
                    reserved,
                    len(wire) + policy["input_overhead_tokens"],
                    policy["max_output_tokens"],
                    "reserved",
                    min(self.deadline, time.time() + policy["timeout_seconds"]),
                ),
            )
            self._attempt_mono[count + 1] = min(
                self.mono_deadline, time.monotonic() + policy["timeout_seconds"]
            )
            return count + 1

    def consume(self, number):
        """One-shot transition, returning fixed bytes. Does NOT perform network I/O."""
        with self._db() as db:
            self._gate(db)
            require(type(number) is int and number > 0, "INVALID_ATTEMPT")
            row = db.execute("SELECT * FROM children WHERE number=?", (number,)).fetchone()
            require(row is not None and row["state"] == "reserved", "SEND_ALREADY_CONSUMED")
            require(
                time.time() < row["attempt_deadline"]
                and time.monotonic() < self._attempt_mono[number],
                "ATTEMPT_TIMEOUT",
            )
            require(
                hashlib.sha256(row["wire"]).hexdigest() == row["wire_hash"],
                "WIRE_HASH_MISMATCH",
            )
            case = next(c for c in self.manifest["cases"] if c["id"] == row["case_id"])
            _, wire, refs = self._build(db, case, row["round_id"], row["stage"], row["ordinal"])
            require(
                wire == row["wire"] and claims.encoded(refs).decode() == row["parents"],
                "DERIVATION_MISMATCH",
            )
            db.execute(
                "UPDATE children SET state='intent' WHERE number=? AND state='reserved'", (number,)
            )
            return bytes(wire)

    def finish(
        self,
        number,
        *,
        value,
        model,
        status,
        input_tokens,
        output_tokens,
        response_sha256,
        reasoning_tokens=None,
    ):
        with self._db() as db:
            self._gate(db)
            require(type(number) is int and number > 0, "INVALID_ATTEMPT")
            row = db.execute("SELECT * FROM children WHERE number=?", (number,)).fetchone()
            require(row is not None and row["state"] == "intent", "INVALID_FINISH_STATE")
            try:
                require(
                    time.time() < row["attempt_deadline"]
                    and time.monotonic() < self._attempt_mono[number],
                    "ATTEMPT_TIMEOUT",
                )
                require(
                    model == self.manifest["target"]["model"] and status == "completed",
                    "INVALID_OUTPUT",
                )
                require(
                    type(response_sha256) is str and HASH.fullmatch(response_sha256),
                    "INVALID_OBSERVATION",
                )
                require(
                    type(input_tokens) is int
                    and type(output_tokens) is int
                    and input_tokens >= 0
                    and output_tokens >= 0,
                    "UNKNOWN_USAGE",
                )
                require(
                    input_tokens <= row["input_bound"] and output_tokens <= row["output_bound"],
                    "USAGE_EXCEEDED",
                )
                require(
                    reasoning_tokens is None
                    or (type(reasoning_tokens) is int and 0 <= reasoning_tokens <= output_tokens),
                    "INVALID_OBSERVATION",
                )
                case = next(c for c in self.manifest["cases"] if c["id"] == row["case_id"])
                snap, _, ir, cr, inv = self._round(db, case, row["round_id"])
                stage = row["stage"]
                retained = value
                exact(retained, "request_binding result")
                require(
                    retained["request_binding"]
                    == self._binding(row["slot"], json.loads(row["parents"])),
                    "RESPONSE_BINDING_MISMATCH",
                )
                policy = self.manifest["stages"][stage]
                require(
                    len(claims.encoded(value)) <= policy["max_result_bytes"], "RESULT_TOO_LARGE"
                )
                require(
                    Draft202012Validator(policy["schema"]).is_valid(value), "INVALID_OUTPUT_SCHEMA"
                )
                value = retained["result"]
                if stage == "inventory":
                    initial = claims.inventory(
                        snap,
                        value,
                        {
                            "version": "claim-coverage-v1",
                            "missing_claims": [],
                            "uncertainties": [],
                            "invalid_exclusions": [],
                        },
                    )
                    require(len(initial["claims"]) <= self.manifest["max_claims"], "CLAIM_LIMIT")
                elif stage == "coverage":
                    result = claims.inventory(snap, self._value(ir), value)
                    require(len(result["claims"]) <= self.manifest["max_claims"], "CLAIM_LIMIT")
                elif stage in ("claim", "overall"):
                    cid = (
                        "__overall__"
                        if stage == "overall"
                        else inv["claims"][row["ordinal"] - 1]["claim_id"]
                    )
                    _, _, extra = claims.checked_review(snap, inv, value, cid, stage == "overall")
                    require(
                        all(e["claim_id"] in {c["claim_id"] for c in inv["claims"]} for e in extra),
                        "UNCOVERED_INCIDENTAL",
                    )
                    if stage == "overall":
                        require(
                            not value["uncovered"] and not value["uncertain"], "COVERAGE_UNRESOLVED"
                        )
                else:
                    exact(value, "resource_type content")
                    require(
                        value["resource_type"] == case["resource_type"],
                        "CORRECTION_RESOURCE_CHANGED",
                    )
                    self._snap(case, value)
                db.execute(
                    "UPDATE children SET state='verified',value=?,value_hash=?,response_hash=?,"
                    "input_tokens=?,output_tokens=?,reasoning_tokens=? WHERE number=?",
                    (
                        claims.encoded(retained).decode(),
                        hashed(retained),
                        response_sha256,
                        input_tokens,
                        output_tokens,
                        reasoning_tokens,
                        number,
                    ),
                )
                if stage == "overall":
                    self._aggregate(db, case, row["round_id"])
            except (GateFailure, claims.Invalid) as exc:
                code = exc.code if isinstance(exc, GateFailure) else str(exc)
                db.execute(
                    "UPDATE children SET state='failed',input_tokens=?,output_tokens=?,"
                    "response_hash=?,reasoning_tokens=? WHERE number=?",
                    (
                        input_tokens
                        if type(input_tokens) is int and 0 <= input_tokens <= 2**63 - 1
                        else None,
                        output_tokens
                        if type(output_tokens) is int and 0 <= output_tokens <= 2**63 - 1
                        else None,
                        response_sha256
                        if type(response_sha256) is str and HASH.fullmatch(response_sha256)
                        else None,
                        reasoning_tokens
                        if (
                            type(reasoning_tokens) is int
                            and type(output_tokens) is int
                            and 0 <= reasoning_tokens <= output_tokens
                            and reasoning_tokens <= 2**63 - 1
                        )
                        else None,
                        number,
                    ),
                )
                self._halt(db, code)

    def abort(self, number, *, error_code, response_sha256=None):
        """Trusted transport-failure hook; never accepts vendor exception/error text."""
        with self._db() as db:
            self._gate(db)
            require(type(number) is int and number > 0, "INVALID_ATTEMPT")
            require(type(error_code) is str and error_code in ERRORS, "INVALID_ABORT")
            require(
                response_sha256 is None
                or (type(response_sha256) is str and HASH.fullmatch(response_sha256)),
                "INVALID_OBSERVATION",
            )
            row = db.execute("SELECT * FROM children WHERE number=?", (number,)).fetchone()
            require(
                row is not None and row["state"] in ("reserved", "intent"), "INVALID_FINISH_STATE"
            )
            db.execute(
                "UPDATE children SET state='failed',response_hash=? WHERE number=?",
                (response_sha256, number),
            )
            self._halt(db, error_code)

    def _aggregate(self, db, case, r):
        snap, _, _, _, inv = self._round(db, case, r)
        results, found, incidental = {}, [], []
        for ordinal, c in enumerate(inv["claims"], 1):
            value = self._value(self._row(db, case["id"], r, "claim", ordinal))
            verdict, issues, extra = claims.checked_review(snap, inv, value, c["claim_id"])
            results[c["claim_id"]] = verdict
            found.extend(issues)
            incidental.extend(extra)
        value = self._value(self._row(db, case["id"], r, "overall"))
        overall, issues, extra = claims.checked_review(snap, inv, value, "__overall__", True)
        found.extend(issues)
        incidental.extend(extra)
        require(not value["uncovered"] and not value["uncertain"], "COVERAGE_UNRESOLVED")
        require(
            all(e["claim_id"] in results and results[e["claim_id"]] != "pass" for e in incidental),
            "CONFLICTING_VERDICTS",
        )
        found.extend(e["finding"] for e in incidental)
        verdict = (
            "reject" if "reject" in [overall, *results.values()] else "revise" if found else "pass"
        )
        return verdict, found

    def decide(self, action, *, assessment_sha256):
        """Trusted semantic gate hook, not a model field or human-signature verifier."""
        with self._db() as db:
            self._gate(db)
            require(
                action in ("continue", "correct", "halt")
                and type(assessment_sha256) is str
                and HASH.fullmatch(assessment_sha256),
                "INVALID_ASSESSMENT",
            )
            for case in self.manifest["cases"]:
                for r in range(self.manifest["corrections"] + 1):
                    decision = db.execute(
                        "SELECT action FROM decisions WHERE case_id=? AND round_id=?",
                        (case["id"], r),
                    ).fetchone()
                    if decision and decision["action"] == "continue":
                        break
                    if decision:
                        self._value(self._row(db, case["id"], r, "correction"))
                        continue
                    verdict, _ = self._aggregate(db, case, r)
                    if action == "halt":
                        self._halt(db, "ADMISSION_FAILED")
                    if action == "correct":
                        require(
                            verdict == "revise" and r < self.manifest["corrections"],
                            "CORRECTION_NOT_APPROVED",
                        )
                    db.execute(
                        "INSERT INTO decisions VALUES(?,?,?,?)",
                        (case["id"], r, action, assessment_sha256),
                    )
                    return
            raise GateFailure("RUN_COMPLETE")

    def snapshot(self):
        with self._db() as db:
            run = dict(db.execute("SELECT * FROM run").fetchone())
            rows = [
                {k: v for k, v in dict(row).items() if k not in ("wire", "value")}
                for row in db.execute("SELECT * FROM children ORDER BY number")
            ]
            return {"root_sha256": self.freeze, "run": run, "attempts": rows}
