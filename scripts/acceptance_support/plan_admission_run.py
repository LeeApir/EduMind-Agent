"""Independent durable admission ledger. No credentials, network or implicit run activation."""

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from acceptance_support.five_hour_runtime import require
from acceptance_support.qwen_review_budget import canonical, sha

RUN_ID = "plan-admission-execution-r02"


def schedule(index):
    rows = []
    for lane in ("plan_review", "fixed_review", "generation_draft"):
        for item in index["materials"]:
            if item["lane"] == lane:
                rows.append(
                    dict(
                        slot_id=f"{lane}:{item['id']}:1",
                        case_id=item["id"],
                        lane=lane,
                        cap=4 if lane == "generation_draft" else 1,
                        material=item["material"],
                        material_sha256=item["sha256"],
                    )
                )
        if lane == "fixed_review":
            for name in index["repeat_review_ids"]:
                item = next(x for x in index["materials"] if x["id"] == name and x["lane"] == lane)
                rows.append(
                    dict(
                        slot_id=f"{lane}:{name}:2",
                        case_id=name,
                        lane=lane,
                        cap=1,
                        material=item["material"],
                        material_sha256=item["sha256"],
                    )
                )
    item = next(x for x in index["materials"] if x["id"] == "G03")
    rows.append(
        dict(
            slot_id="full_pipeline:G03:1",
            case_id="G03",
            lane="full_pipeline",
            cap=19,
            material=item["material"],
            material_sha256=item["sha256"],
        )
    )
    require(len(rows) == 29 and sum(x["cap"] for x in rows) == 59, "SCHEDULE_CHANGED")
    return rows


class Ledger:
    def __init__(self, path, manifest_hash, slots, *, activate=False, now=time.time):
        self.path, self.now, self.slots = Path(path), now, slots
        require(not self.path.is_symlink(), "UNSAFE_LEDGER")
        if activate:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with self.db() as db:
                db.executescript("""
                    CREATE TABLE run (manifest TEXT, t0 REAL, last_clock REAL, halt TEXT);
                    CREATE TABLE cases (id TEXT PRIMARY KEY, position INTEGER, state TEXT,
                                        started REAL, result_hash TEXT, evaluation_hash TEXT);
                    CREATE TABLE calls (n INTEGER PRIMARY KEY, slot TEXT, stage TEXT,
                                        state TEXT, logical_hash TEXT, evidence_hash TEXT);
                """)
                t = now()
                db.execute("INSERT INTO run VALUES (?,?,?,NULL)", (manifest_hash, t, t))
                db.executemany(
                    'INSERT INTO cases VALUES (?, ?, "pending",NULL,NULL,NULL)',
                    [(r["slot_id"], i) for i, r in enumerate(slots)],
                )
        require(
            self.path.is_file() and self.path.stat().st_mode & 0o077 == 0,
            "PRIVATE_ACTIVE_LEDGER_REQUIRED",
        )
        with self.db() as db:
            require(
                db.execute("SELECT manifest FROM run").fetchall() == [(manifest_hash,)],
                "RUN_BINDING_CHANGED",
            )
            require(
                db.execute("SELECT id FROM cases ORDER BY position").fetchall()
                == [(s["slot_id"],) for s in slots],
                "ORDER_CHANGED",
            )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def clock(self, db):
        t0, last, halt = db.execute("SELECT t0,last_clock,halt FROM run").fetchone()
        require(halt is None, "RUN_STOPPED")
        t = self.now()
        if t < last or t >= t0 + 18000:
            reason = "CLOCK_MOVED_BACKWARD" if t < last else "GLOBAL_DEADLINE"
            db.execute("UPDATE run SET halt=?", (reason,))
            db.commit()  # Halt survives the exception; waiting never restarts T0.
            raise ValueError(reason)
        db.execute("UPDATE run SET last_clock=?", (t,))
        return min(60, t0 + 18000 - t)

    def start(self, slot):
        require(slot in [x["slot_id"] for x in self.slots], "UNKNOWN_SLOT")
        with self.db() as db:
            self.clock(db)
            rows = db.execute("SELECT id,state FROM cases ORDER BY position").fetchall()
            prior = [state for name, state in rows[: [name for name, _ in rows].index(slot)]]
            require(all(x == "passed" for x in prior), "INDEPENDENT_PRIOR_ASSESSMENT_REQUIRED")
            require(dict(rows)[slot] == "pending", "CASE_REPLAY_FORBIDDEN")
            require(
                not db.execute('SELECT 1 FROM cases WHERE state="running"').fetchone(),
                "INTERRUPTED_CASE_NO_REPLAY",
            )
            require(
                not db.execute('SELECT 1 FROM calls WHERE state!="complete"').fetchone(),
                "UNCERTAIN_ATTEMPT_NO_REPLAY",
            )
            db.execute('UPDATE cases SET state="running",started=? WHERE id=?', (self.now(), slot))

    def reserve(self, slot, stage, logical_hash):
        spec = next(x for x in self.slots if x["slot_id"] == slot)
        allowed = {
            "plan_review": {"plan_check"},
            "fixed_review": {"unit_review"},
            "generation_draft": {"plan_generation", "resource_generation"},
            "full_pipeline": {
                "plan_generation",
                "plan_check",
                "resource_generation",
                "resource_correction",
                "resource_review",
                "unit_review",
            },
        }[spec["lane"]]
        require(stage in allowed, "CROSS_LANE_OR_UNPLANNED_STAGE")
        with self.db() as db:
            remaining = self.clock(db)
            state, start = db.execute(
                "SELECT state,started FROM cases WHERE id=?", (slot,)
            ).fetchone()
            require(state == "running", "CASE_NOT_RUNNING")
            if self.now() >= start + 180:
                db.execute('UPDATE run SET halt="OPERATION_DEADLINE"')
                db.commit()
                raise ValueError("OPERATION_DEADLINE")
            remaining = min(remaining, start + 180 - self.now())
            require(
                not db.execute('SELECT 1 FROM calls WHERE state!="complete"').fetchone(),
                "UNCERTAIN_ATTEMPT_NO_REPLAY",
            )
            n = db.execute("SELECT count(*) FROM calls").fetchone()[0]
            own = db.execute("SELECT stage FROM calls WHERE slot=? ORDER BY n", (slot,)).fetchall()
            require(n < 59 and len(own) < spec["cap"], "REQUEST_CAP")
            stages = [x[0] for x in own]
            if spec["lane"] == "generation_draft":
                require(
                    stage == ("plan_generation" if not stages else "resource_generation"),
                    "DRAFT_SEQUENCE_CHANGED",
                )
            if spec["lane"] == "full_pipeline":
                require(stage != "plan_generation" or not stages, "SECOND_PLAN_FORBIDDEN")
                require(stage != "plan_check" or stages == ["plan_generation"], "PLAN_CHECK_ORDER")
                if len(stages) < 2:
                    require(
                        stage == ("plan_generation" if not stages else "plan_check"),
                        "PLAN_BEFORE_CONTENT",
                    )
                require("unit_review" not in stages, "AFTER_FINAL_REVIEW")
                if stage == "resource_generation":
                    require(
                        stages[-1] in ("plan_check", "resource_review"), "RESOURCE_SEQUENCE_CHANGED"
                    )
                if stage == "resource_review":
                    require(
                        stages[-1] in ("resource_generation", "resource_correction"),
                        "REVIEW_WITHOUT_NEW_CONTENT",
                    )
                if stage == "resource_correction":
                    require(stages[-1] == "resource_review", "CORRECTION_WITHOUT_REVIEW")
                    last_gen = max(
                        i for i, value in enumerate(stages) if value == "resource_generation"
                    )
                    require(
                        stages[last_gen:].count("resource_correction") < 2,
                        "PER_RESOURCE_CORRECTION_CAP",
                    )
                if stage == "unit_review":
                    require(stages[-1] == "resource_review", "FINAL_REVIEW_SEQUENCE_CHANGED")
                require(
                    stages.count("resource_generation") + (stage == "resource_generation") <= 3,
                    "RESOURCE_CAP",
                )
                require(
                    stages.count("resource_correction") + (stage == "resource_correction") <= 5,
                    "CORRECTION_CAP",
                )
                if stage == "unit_review":
                    require(stages.count("resource_generation") == 3, "INCOMPLETE_RESOURCES")
            db.execute(
                'INSERT INTO calls VALUES (?,?,?,"reserved",?,NULL)',
                (n + 1, slot, stage, logical_hash),
            )
            return n + 1, remaining

    def complete(self, n, evidence_hash):
        with self.db() as db:
            require(
                db.execute("SELECT state FROM calls WHERE n=?", (n,)).fetchone() == ("reserved",),
                "ATTEMPT_NOT_RESERVED",
            )
            db.execute(
                'UPDATE calls SET state="complete",evidence_hash=? WHERE n=?', (evidence_hash, n)
            )

    def finish(self, slot, result_hash):
        with self.db() as db:
            self.clock(db)
            require(
                not db.execute('SELECT 1 FROM calls WHERE state!="complete"').fetchone(),
                "UNCERTAIN_ATTEMPT",
            )
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (slot,)).fetchone()
                == ("running",),
                "CASE_NOT_RUNNING",
            )
            spec = next(s for s in self.slots if s["slot_id"] == slot)
            count = db.execute("SELECT count(*) FROM calls WHERE slot=?", (slot,)).fetchone()[0]
            require(
                count > 0 and (spec["lane"] == "full_pipeline" or count == spec["cap"]),
                "INCOMPLETE_CASE_CALLS",
            )
            db.execute(
                'UPDATE cases SET state="awaiting_human",result_hash=? WHERE id=?',
                (result_hash, slot),
            )

    def assess(self, slot, evaluation_hash, passed):
        require(type(passed) is bool, "QUALITY_DECISION_REQUIRED")
        with self.db() as db:
            self.clock(db)
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (slot,)).fetchone()
                == ("awaiting_human",),
                "HUMAN_ASSESSMENT_NOT_EXPECTED",
            )
            db.execute(
                "UPDATE cases SET state=?,evaluation_hash=? WHERE id=?",
                ("passed" if passed else "failed", evaluation_hash, slot),
            )
            if not passed:
                db.execute('UPDATE run SET halt="FIRST_FAILURE"')
            elif not db.execute('SELECT 1 FROM cases WHERE state!="passed"').fetchone():
                db.execute('UPDATE run SET halt="COMPLETED_DEVELOPMENT_ONLY"')

    def stop(self, reason):
        with self.db() as db:
            db.execute("UPDATE run SET halt=coalesce(halt,?)", (reason,))

    def snapshot(self):
        with self.db() as db:
            return dict(
                run=db.execute("SELECT * FROM run").fetchone(),
                cases=db.execute("SELECT * FROM cases ORDER BY position").fetchall(),
                calls=db.execute("SELECT * FROM calls ORDER BY n").fetchall(),
            )


def pointer(root, path):
    require(path.startswith("/"), "ABSOLUTE_POINTER_REQUIRED")
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        root = root[int(part)] if isinstance(root, list) else root[part]
    return root


def output_fields(value, path):
    """Enumerate model text fields; humans may split one field into several assertions."""
    if isinstance(value, str) and value:
        return {path}
    result = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k not in {
                "schema_version",
                "prompt_version",
                "resource_type",
                "reference_ids",
                "anchors",
                "target_anchor",
                "evidence_anchors",
                "finding_id",
            }:
                result |= output_fields(v, path + "/" + k.replace("~", "~0").replace("/", "~1"))
    if isinstance(value, list):
        for i, v in enumerate(value):
            result |= output_fields(v, path + f"/{i}")
    return result


def check_assessment(value, *, schema, spec, manifest_hash, evidence):
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(value)
    require(
        value["status"] == "evaluated" and value["mode"] == "real", "REAL_HUMAN_ASSESSMENT_REQUIRED"
    )
    require(
        value["evaluator"] == dict(name="Lee", role="independent_human", signed=True),
        "LEE_SIGNATURE_REQUIRED",
    )
    require(
        value["run_id"] == RUN_ID
        and value["slot_id"] == spec["slot_id"]
        and value["case_id"] == spec["case_id"]
        and value["lane"] == spec["lane"]
        and value["package_manifest_sha256"] == manifest_hash,
        "ASSESSMENT_BINDING_CHANGED",
    )
    calls = evidence["calls"]
    require(
        value["artifacts"]
        == dict(
            material_sha256=spec["material_sha256"],
            request_sha256=sha(canonical([c["logical_request_sha256"] for c in calls])),
            response_sha256=sha(canonical([c["parsed_sha256"] for c in calls])),
        ),
        "EVIDENCE_CHANGED",
    )
    require(all(x is not None for x in value["scores"].values()), "SCORES_INCOMPLETE")
    claims = {c["id"]: c for c in value["claims"]}
    require(len(claims) == len(value["claims"]) and bool(claims), "ASSERTION_INVENTORY_REQUIRED")
    for claim in claims.values():
        for p in claim["evidence_pointers"]:
            pointer(evidence, p)
    required_fields = set()
    required_citations = set()
    for i, item in enumerate(evidence.get("parsed_calls", [])):
        body = item["value"]
        required_fields |= output_fields(body, f"/parsed_calls/{i}/value")
        n = calls[i]["n"]
        for finding in body.get("findings", []):
            anchors = finding.get("anchors", finding.get("evidence_anchors", []))
            if "target_anchor" in finding:
                anchors = [*anchors, finding["target_anchor"]]
            required_citations |= {f"{n}:{a}" for a in anchors}
    covered = {p for c in claims.values() for p in c["evidence_pointers"]}
    require(required_fields <= covered, "ALL_OUTPUT_FIELDS_MUST_BE_REVIEWED")
    ids = {c["anchor_id"] for c in value["citations"]}
    require(required_citations == ids, "ALL_ACTUAL_CITATIONS_REQUIRED")
    for citation in value["citations"]:
        require(set(citation["supports_claim_ids"]) <= claims.keys(), "UNKNOWN_CLAIM_REFERENCE")
        source = pointer(evidence, citation["source_pointer"])
        require(
            isinstance(source, str) and citation["quoted_source"] in source,
            "CITATION_QUOTE_NOT_IN_FIELD",
        )
        require(
            citation["source_pointer"]
            == "/review_sources/" + citation["anchor_id"] + "/source_text",
            "EXACT_ANCHOR_FIELD_REQUIRED",
        )
    if value["scores"]["quality_success"] and spec["lane"] in ("generation_draft", "full_pipeline"):
        require(
            value["scores"]["teaching_coverage"] == "pass", "GENERATED_TEACHING_COVERAGE_REQUIRED"
        )
        if spec["lane"] == "full_pipeline":
            require(
                evidence["result"]["course_state"] == "completed"
                and value["automatic_publication_completed"] is True,
                "AUTOMATIC_FULL_COMPLETION_REQUIRED",
            )
    # Completeness and semantic support are human attestations, not machine-proven truth.
    require(value["scores"]["quality_success"] is not None, "QUALITY_DECISION_REQUIRED")
    return value["scores"]["quality_success"]
