"""Fixed four-slot focus budget adapter. No HTTP or credential reading in this module."""

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager

from . import claim_review_prototype as p
from . import span_review_offline as span
from .derived_diagnostic_budget import DerivedBudget, require
from .phase1_budget import FrozenBudget, GateFailure

STRATEGY = "span-selection-redesign-v1"


class FixedFocusGate:
    """Adapt one immutable legacy static budget to the already tested raw-byte sender.

    Each of two fixed round registry names can bind only one approved root. At most
    four single-attempt slots per round; no alternate paths or arbitrary round IDs.
    """

    def __init__(self, root, manifest, plan, requests, approval):
        self.root = root.resolve()
        self.plan, self.requests = json.loads(p.encoded(plan)), json.loads(p.encoded(requests))
        plan = self.plan
        require(plan["execution_root"] == str(self.root), "ROOT_CHANGED")
        self.freeze = p.digest(manifest)
        self._attempt_mono = {}
        number = plan["round"]
        require(type(number) is int and number in (1, 2), "INVALID_ROUND")
        require(plan["strategy_id"] == STRATEGY, "INVALID_ROUND")
        require(manifest["run_id"] == f"span-focus-r{number + 9:02d}", "INVALID_ROUND")
        require(
            manifest["bounds"]["requests"] == 4
            and len(manifest["slots"]) == 4
            and all(s["attempts"] == 1 and s["stages"] == ["review"] for s in manifest["slots"]),
            "INVALID_ROUND",
        )
        self.guard = object.__new__(DerivedBudget)
        self.guard.root, self.guard._lock_fd = self.root, None
        self.ledger = self.guard._path(
            f"local-materials/phase-1-t040-focus-r{number + 9:02d}/budget.sqlite"
        )
        self.registry = self.guard._path(f"local-materials/{STRATEGY}/round-{number}.json")
        self.budget = FrozenBudget(manifest, self.ledger, approval=approval, root=self.root)
        self.budget._authorize()  # Before creating any runtime state.
        self.manifest = {
            "target": {"model": "deepseek-flash", "target_sha256": p.digest(plan["target"])},
            "stages": {"focus": {"max_result_bytes": 65536}},
        }
        self.guard._acquire()
        try:
            expected = {
                "strategy": STRATEGY,
                "round": number,
                "root": self.freeze,
                "approval": approval.record_sha256,
                "ledger": str(self.ledger.relative_to(self.root)),
            }
            if self.registry.exists():
                self.guard._safe_file(self.registry)
                registry = json.loads(self.registry.read_bytes())
                require({k: registry[k] for k in expected} == expected, "REGISTRY_MISMATCH")
                require(self.ledger.exists(), "LEDGER_MISSING")
                self.guard._safe_file(self.ledger)
                self.deadline = registry["deadline"]
            else:
                require(not self.ledger.exists(), "REGISTRY_MISSING")
                if number == 2:
                    prior = self.guard._path(f"local-materials/{STRATEGY}/round-1.json")
                    require(prior.is_file(), "PREREQUISITE_MISSING")
                    self.guard._safe_file(prior)
                    prior_record = json.loads(prior.read_bytes())
                    prior_ledger = self.guard._path(
                        "local-materials/phase-1-t040-focus-r10/budget.sqlite"
                    )
                    self.guard._safe_file(prior_ledger)
                    with sqlite3.connect(f"file:{prior_ledger}?mode=ro", uri=True) as db:
                        prior_run = db.execute("SELECT freeze,halted FROM run").fetchone()
                        assessed = db.execute(
                            "SELECT count(*) FROM receipts WHERE assessment_hash IS NOT NULL"
                        ).fetchone()[0]
                    require(prior_run[0] == prior_record["root"], "LEDGER_MISMATCH")
                    require(prior_run[1] is not None or assessed == 4, "PREREQUISITE_MISSING")
                self.deadline = min(plan["expires_at"], time.time() + plan["overall_seconds"])
                self.guard._create_file(
                    self.registry, p.encoded({**expected, "deadline": self.deadline})
                )
                self.budget.snapshot()
                with self._db() as db:
                    db.execute("CREATE TABLE control (deadline REAL, last_clock REAL)")
                    db.execute("INSERT INTO control VALUES(?,?)", (self.deadline, time.time()))
                    db.execute(
                        "CREATE TABLE receipts (number INTEGER PRIMARY KEY, slot TEXT UNIQUE, "
                        "consumed INTEGER, attempt_deadline REAL, value TEXT, value_hash TEXT, "
                        "response_hash TEXT, reasoning_tokens INTEGER, assessment_hash TEXT)"
                    )
                    db.execute(
                        "CREATE VIEW children AS SELECT number,attempt_deadline FROM receipts"
                    )
            self.mono_deadline = time.monotonic() + max(0, self.deadline - time.time())
            with self._db() as db:
                self._gate(db)
                reserved = db.execute(
                    "SELECT count(*) FROM attempts WHERE state='reserved'"
                ).fetchone()[0]
                missing = db.execute(
                    "SELECT count(*) FROM attempts a LEFT JOIN receipts r "
                    "ON a.number=r.number WHERE a.state='complete' AND r.value IS NULL"
                ).fetchone()[0]
                if reserved or missing:
                    self._halt(db, "SAFETY_FAILURE")
        except BaseException:
            self.close()
            raise

    def close(self):
        self.guard.close()

    @contextmanager
    def _db(self):
        require(self.guard._lock_fd is not None, "CLOSED")
        db = self.budget._connect()
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _halt(self, db, reason):
        db.execute("UPDATE run SET halted=coalesce(halted,?)", (reason,))
        db.commit()
        raise GateFailure(reason)

    def _gate(self, db):
        self.budget._authorize()
        require(db.execute("SELECT halted FROM run").fetchone()[0] is None, "RUN_HALTED")
        control = db.execute("SELECT * FROM control").fetchone()
        require(control is not None and control["deadline"] == self.deadline, "LEDGER_MISMATCH")
        now = time.time()
        if (
            now < control["last_clock"]
            or now >= self.deadline
            or time.monotonic() >= self.mono_deadline
        ):
            self._halt(db, "TIMEOUT")
        db.execute("UPDATE control SET last_clock=?", (now,))

    def reserve_next(self):
        with self._db() as db:
            self._gate(db)
            rows = db.execute(
                "SELECT a.number,r.assessment_hash FROM attempts a "
                "LEFT JOIN receipts r ON a.number=r.number ORDER BY a.number"
            ).fetchall()
            if rows and not rows[-1]["assessment_hash"]:
                raise GateFailure("HUMAN_REVIEW_REQUIRED")
            require(len(rows) < 4, "RUN_COMPLETE")
            slot = self.budget.manifest["slots"][len(rows)]
            wire = p.encoded(self.requests[slot["id"]])
            require(hashlib.sha256(wire).hexdigest() == slot["input_sha256"], "FREEZE_CHANGED")
        n = self.budget.reserve(
            slot["id"], "review", slot["targets"][0], wire, resource="explanation"
        )
        limit = min(self.deadline, time.time() + 60)
        with self._db() as db:
            db.execute(
                "INSERT INTO receipts VALUES(?,?,0,?,NULL,NULL,NULL,NULL,NULL)",
                (n, slot["id"], limit),
            )
        self._attempt_mono[n] = min(self.mono_deadline, time.monotonic() + 60)
        return n

    def consume(self, number):
        with self._db() as db:
            self._gate(db)
            require(type(number) is int and number > 0, "INVALID_ATTEMPT")
            row = db.execute("SELECT * FROM receipts WHERE number=?", (number,)).fetchone()
            require(row is not None and row["consumed"] == 0, "SEND_ALREADY_CONSUMED")
            require(
                time.time() < row["attempt_deadline"]
                and time.monotonic() < self._attempt_mono[number],
                "TIMEOUT",
            )
            wire = p.encoded(self.requests[row["slot"]])
            attempt = db.execute("SELECT * FROM attempts WHERE number=?", (number,)).fetchone()
            slot = next(s for s in self.budget.manifest["slots"] if s["id"] == row["slot"])
            require(
                attempt["state"] == "reserved"
                and attempt["request_sha256"]
                == slot["input_sha256"]
                == hashlib.sha256(wire).hexdigest(),
                "FREEZE_CHANGED",
            )
            db.execute("UPDATE receipts SET consumed=1 WHERE number=?", (number,))
            return wire

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
            row = db.execute("SELECT * FROM receipts WHERE number=?", (number,)).fetchone()
            require(row is not None and row["consumed"] == 1, "INVALID_OUTPUT")
            require(
                time.time() < row["attempt_deadline"]
                and time.monotonic() < self._attempt_mono[number],
                "TIMEOUT",
            )
            require(model == "deepseek-flash" and status == "completed", "INVALID_OUTPUT")
            require(type(input_tokens) is int and type(output_tokens) is int, "INVALID_OUTPUT")
            require(
                reasoning_tokens is None or type(reasoning_tokens) is int and reasoning_tokens == 0,
                "INVALID_OUTPUT",
            )
            item = next(x for x in self.plan["focus_items"] if x["probe_id"] == row["slot"])
            snapshot = p.freeze(
                item["payload"]["resource_type"],
                item["payload"]["content"],
                item["payload"]["reference_context"],
                {"experiment": "span-offline-v1"},
            )
            try:
                span.focus_result(snapshot, row["slot"], item["claim"], value)
            except p.Invalid:
                raise GateFailure("INVALID_OUTPUT") from None
        self.budget.finish(number, input_tokens=input_tokens, output_tokens=output_tokens)
        with self._db() as db:
            require(db.execute("SELECT halted FROM run").fetchone()[0] is None, "RUN_HALTED")
            db.execute(
                "UPDATE receipts SET value=?,value_hash=?,response_hash=?,reasoning_tokens=? "
                "WHERE number=?",
                (
                    p.encoded(value).decode(),
                    p.digest(value),
                    response_sha256,
                    reasoning_tokens,
                    number,
                ),
            )

    def abort(
        self,
        number,
        *,
        error_code,
        response_sha256=None,
        input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
    ):
        def safe(x):
            return x if type(x) is int and 0 <= x <= 10**12 else None

        reasoning = safe(reasoning_tokens)
        if reasoning is not None and (safe(output_tokens) is None or reasoning > output_tokens):
            reasoning = None
        with self._db() as db:
            state = db.execute("SELECT state FROM attempts WHERE number=?", (number,)).fetchone()
        if state is not None and state[0] == "reserved":
            self.budget.finish(
                number,
                error_code=error_code,
                input_tokens=safe(input_tokens),
                output_tokens=safe(output_tokens),
            )
        with self._db() as db:
            db.execute(
                "UPDATE receipts SET response_hash=?,reasoning_tokens=? WHERE number=?",
                (response_sha256, reasoning, number),
            )
            self._halt(db, error_code)

    def coarse_gate(self, number):
        with self._db() as db:
            self._gate(db)
            row = db.execute("SELECT * FROM receipts WHERE number=?", (number,)).fetchone()
            self._coarse_row(db, row)

    def _coarse_row(self, db, row):
        value = json.loads(row["value"])
        expected = self.plan["expected_by_probe"][row["slot"]]
        if expected == "pass" and (value["verdict"] != "pass" or value["other_findings"]):
            self._halt(db, "CONTROL_REJECTED")
        if expected != "pass" and value["verdict"] == "pass":
            self._halt(db, "CONCRETE_DEFECT_MISSED")
        if expected != "pass" and not any(f["area"] == "fact" for f in value["findings"]):
            self._halt(db, "ADMISSION_FAILED")

    def assess(self, evidence):
        p.obj(
            evidence,
            "root_sha256 number value_hash passed confirmed_by user_confirmation "
            "source_message_id observation",
        )
        require(
            evidence["root_sha256"] == self.freeze
            and type(evidence["number"]) is int
            and type(evidence["passed"]) is bool
            and evidence["confirmed_by"] == "Lee"
            and all(
                type(evidence[k]) is str and bool(evidence[k].strip())
                for k in ("user_confirmation", "source_message_id", "observation")
            ),
            "INVALID_ASSESSMENT",
        )
        with self._db() as db:
            self._gate(db)
            row = db.execute("SELECT * FROM receipts ORDER BY number DESC LIMIT 1").fetchone()
            require(
                row is not None
                and row["number"] == evidence["number"]
                and row["value_hash"] == evidence["value_hash"]
                and row["value"] is not None
                and row["assessment_hash"] is None,
                "INVALID_ASSESSMENT",
            )
            require(p.digest(json.loads(row["value"])) == row["value_hash"], "INVALID_ASSESSMENT")
            # Receipt may survive a crash before the post-send quality gate.
            self._coarse_row(db, row)
            db.execute(
                "UPDATE receipts SET assessment_hash=? WHERE number=?",
                (p.digest(evidence), row["number"]),
            )
            if not evidence["passed"]:
                self._halt(db, "ADMISSION_FAILED")
