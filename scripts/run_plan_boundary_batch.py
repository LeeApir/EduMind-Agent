"""One fixed development collection: eight cases, no adaptive retries, no release scoring."""

# ruff: noqa: E402
import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import httpx
from acceptance_support.five_hour_runtime import require, private_directory, write_once
from acceptance_support.luna_admission_gate import env_metadata
from acceptance_support.plan_admission import (
    CONFIG,
    CandidateReviewAdapter,
    CandidateGateway,
    LaneGateway,
)
from acceptance_support.plan_admission_live import WireTransport
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.plan_admission_run import output_fields, pointer
from app.agents.plan_check import inspect_plan
from app.agents.shared_learning_plan import CallWindow
from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.learning_policy import active_policy_digest
from app.services.provider_gateway import ProviderGateway
from prepare_plan_boundary_batch import BASE, ORDER, read, row_for, expected_binding
from run_five_hour_acceptance import load_keys

PRIVATE = ROOT / "local-materials/phase-1-plan-boundary-development-r01"
RUN_ID = "plan-boundary-development-r01"


class Ledger:
    """Collected means a technical answer exists, never that its semantics passed."""

    def __init__(self, path, digest, *, activate=False, now=time.time):
        self.path, self.now = Path(path), now
        require(not self.path.is_symlink(), "UNSAFE_LEDGER")
        if activate:
            fd = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
            os.close(fd)
            with self.db() as db:
                db.executescript(
                    "CREATE TABLE run(digest TEXT,t0 REAL,last_clock REAL,halt TEXT); CREATE TABLE cases(id TEXT PRIMARY KEY,pos INTEGER,state TEXT,started REAL,result_hash TEXT); CREATE TABLE calls(n INTEGER PRIMARY KEY,case_id TEXT UNIQUE,state TEXT,logical_hash TEXT,evidence_hash TEXT); CREATE TABLE evaluations(case_id TEXT PRIMARY KEY,digest TEXT,passed INTEGER,signed_at REAL,metrics_json TEXT);"
                )
                t = now()
                db.execute("INSERT INTO run VALUES(?,?,?,NULL)", (digest, t, t))
                db.executemany(
                    'INSERT INTO cases VALUES(?,?,"pending",NULL,NULL)',
                    [(x, i) for i, x in enumerate(ORDER)],
                )
        require(
            self.path.is_file() and self.path.stat().st_mode & 0o077 == 0,
            "PRIVATE_LEDGER_REQUIRED",
        )
        with self.db() as db:
            require(
                db.execute("SELECT digest FROM run").fetchall() == [(digest,)],
                "RUN_BINDING_CHANGED",
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
        t = self.now()
        require(halt is None, "RUN_STOPPED")
        if t < last or t >= t0 + 3600:
            reason = "CLOCK_MOVED_BACKWARD" if t < last else "BATCH_DEADLINE"
            db.execute("UPDATE run SET halt=?", (reason,))
            db.commit()
            raise ValueError(reason)
        db.execute("UPDATE run SET last_clock=?", (t,))
        return min(60, t0 + 3600 - t)

    def start(self, name):
        require(name in ORDER, "UNKNOWN_CASE")
        with self.db() as db:
            self.clock(db)
            rows = db.execute("SELECT id,state FROM cases ORDER BY pos").fetchall()
            require(
                all(state == "collected" for _, state in rows[: ORDER.index(name)]),
                "FIXED_ORDER_REQUIRED",
            )
            require(dict(rows)[name] == "pending", "CASE_REPLAY_FORBIDDEN")
            require(
                not db.execute('SELECT 1 FROM cases WHERE state="running"').fetchone(),
                "INTERRUPTED_CASE_NO_REPLAY",
            )
            db.execute(
                'UPDATE cases SET state="running",started=? WHERE id=?',
                (self.now(), name),
            )

    def reserve(self, name, logical_hash):
        with self.db() as db:
            remaining = self.clock(db)
            state, start = db.execute(
                "SELECT state,started FROM cases WHERE id=?", (name,)
            ).fetchone()
            require(state == "running", "CASE_NOT_RUNNING")
            require(
                not db.execute(
                    'SELECT 1 FROM calls WHERE case_id=? OR state!="complete"', (name,)
                ).fetchone(),
                "NO_SECOND_OR_UNCERTAIN_REQUEST",
            )
            if self.now() >= start + 180:
                db.execute('UPDATE run SET halt="CASE_DEADLINE"')
                db.commit()
                raise ValueError("CASE_DEADLINE")
            n = db.execute("SELECT count(*) FROM calls").fetchone()[0]
            require(n < 8, "BATCH_CAP")
            db.execute(
                'INSERT INTO calls VALUES(?,?,"reserved",?,NULL)',
                (n + 1, name, logical_hash),
            )
            return n + 1, min(remaining, start + 180 - self.now())

    def complete(self, n, evidence_hash):
        with self.db() as db:
            require(
                db.execute("SELECT state FROM calls WHERE n=?", (n,)).fetchone()
                == ("reserved",),
                "CALL_NOT_RESERVED",
            )
            db.execute(
                'UPDATE calls SET state="complete",evidence_hash=? WHERE n=?',
                (evidence_hash, n),
            )

    def finish(self, name, result_hash):
        with self.db() as db:
            self.clock(db)
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (name,)).fetchone()
                == ("running",),
                "CASE_NOT_RUNNING",
            )
            require(
                db.execute(
                    "SELECT state FROM calls WHERE case_id=?", (name,)
                ).fetchall()
                == [("complete",)],
                "ONE_COMPLETE_CALL_REQUIRED",
            )
            db.execute(
                'UPDATE cases SET state="collected",result_hash=? WHERE id=?',
                (result_hash, name),
            )
            if name == ORDER[-1]:
                db.execute(
                    'UPDATE run SET halt="COLLECTION_COMPLETE_QUALITY_UNASSESSED"'
                )

    def stop(self, reason):
        with self.db() as db:
            db.execute("UPDATE run SET halt=coalesce(halt,?)", (reason,))

    def record_evaluation(self, name, digest_, passed, metrics=None):
        require(type(passed) is bool, "BOOLEAN_QUALITY_REQUIRED")
        with self.db() as db:
            t0, last, halt = db.execute("SELECT t0,last_clock,halt FROM run").fetchone()
            require(
                halt in (None, "COLLECTION_COMPLETE_QUALITY_UNASSESSED"),
                "STOPPED_OR_TECHNICAL_FAILURE",
            )
            require(last <= self.now() < t0 + 3600, "EVALUATION_OUTSIDE_FROZEN_WINDOW")
            require(
                db.execute("SELECT state FROM cases WHERE id=?", (name,)).fetchone()
                == ("collected",),
                "CASE_NOT_COLLECTED",
            )
            db.execute("UPDATE run SET last_clock=?", (self.now(),))
            db.execute(
                "INSERT INTO evaluations VALUES(?,?,?,?,?)",
                (name, digest_, int(passed), self.now(), json.dumps(metrics or {})),
            )
            if db.execute("SELECT count(*) FROM evaluations").fetchone()[0] == 8:
                passed_all = (
                    db.execute("SELECT min(passed) FROM evaluations").fetchone()[0] == 1
                )
                db.execute(
                    "UPDATE run SET halt=?",
                    (
                        "DEVELOPMENT_CHECKS_PASSED_NO_H_AUTH"
                        if passed_all
                        else "DEVELOPMENT_FAILED_CONVERGE_TO_DRAFTS",
                    ),
                )

    def snapshot(self):
        with self.db() as db:
            return dict(
                run=db.execute("SELECT * FROM run").fetchone(),
                cases=db.execute("SELECT * FROM cases ORDER BY pos").fetchall(),
                calls=db.execute("SELECT * FROM calls ORDER BY n").fetchall(),
                evaluations=db.execute(
                    "SELECT * FROM evaluations ORDER BY case_id"
                ).fetchall(),
            )


def wire_digest(name):
    # Capture before canonical artifact serialization reorders mapping keys.
    return read(BASE / f"captures/{name}.json")["exact_wire_sha256"]


class ExactWire(httpx.AsyncBaseTransport):
    def __init__(self, name, inner=None):
        self.expected, self.used = wire_digest(name), False
        self.inner = (
            inner
            if inner is not None
            else httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        )

    async def handle_async_request(self, request):
        require(
            not self.used and sha(request.content) == self.expected,
            "FROZEN_WIRE_OR_ONE_CALL_VIOLATION",
        )
        self.used = True
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


class EvidenceGateway:
    def __init__(self, gateway, c):
        self.gateway, self.c = gateway, c

    async def generate_structured(self, request, *, retry_safe=False):
        c = self.c
        require(
            not retry_safe
            and request.stage == "plan_check"
            and request.prompt.max_output_tokens == 8192,
            "STAGE_OR_OUTPUT_CHANGED",
        )
        logical = dict(
            stage=request.stage,
            prompt=asdict(request.prompt),
            schema=request.json_schema,
        )
        n, remaining = c["ledger"].reserve(c["name"], sha(canonical(logical)))
        c.update(
            active_call=n,
            stage=request.stage,
            expected_cap=8192,
            logical_request_sha256=sha(canonical(logical)),
        )
        write_once(c["directory"] / f"{n:02}-logical.json", logical)
        payload = json.loads(request.prompt.messages[-1].content)
        c["review_sources"] = {
            f"{n}:{a['anchor_id']}": dict(
                source_text=a["source_text"],
                source_kind=a["source_kind"],
                source_field=a["source_field"],
            )
            for a in payload["anchor_catalog"]
        }
        try:
            async with asyncio.timeout(remaining):
                result = await self.gateway.generate_structured(
                    request, retry_safe=False
                )
            audit = result.transport_audit
            require(
                audit.request_digest == c.get("actual_wire_sha256")
                and audit.response_digest == c.get("decoded_response_sha256")
                and audit.config_digest == c.get("expected_config_sha256"),
                "ACTUAL_AUDIT_MISMATCH",
            )
            parsed = dict(
                value=dict(result.value),
                usage=asdict(result.usage),
                model=result.model_id,
                transport_audit=asdict(audit),
            )
            require(
                not any(k.encode() in canonical(parsed) for k in c["keys"]),
                "SECRET_REFLECTED",
            )
            parsed_hash = write_once(c["directory"] / f"{n:02}-parsed.json", parsed)
            item = dict(
                n=n,
                logical_request_sha256=c["logical_request_sha256"],
                parsed_sha256=parsed_hash,
                actual_wire_sha256=c["actual_wire_sha256"],
                raw_response_sha256=c["raw_response_sha256"],
                decoded_response_sha256=c["decoded_response_sha256"],
            )
            write_once(c["directory"] / f"{n:02}-evidence.json", item)
            c["ledger"].complete(n, sha(canonical(item)))
            c["call"] = item
            return result
        except BaseException:
            c["ledger"].stop("TECHNICAL_FAILURE_NO_RETRY")
            raise


def gateway(c, *, keys, inner=None, guard=None):
    cfg = CONFIG["review"]
    c["keys"] = keys
    guard = (
        guard
        if guard is not None
        else ProviderTargetGuard(cfg["base_url"], TargetPolicy())
    )
    target = guard.approve_base()
    transport = WireTransport(c, "review", target, inner=ExactWire(c["name"], inner))
    adapter = CandidateReviewAdapter(
        ProviderSettings(cfg["base_url"], keys[1], cfg["model"]),
        guard,
        transport=transport,
        reasoning_effort=cfg["reasoning"],
    )
    neutral = LaneGateway(CandidateGateway(ProviderGateway(adapter)), "plan_review")
    return EvidenceGateway(neutral, c), transport


def verify_seals():
    for name, h in read(
        ROOT
        / "docs/acceptance/phase-1-plan-semantic-boundary-r01/historical-seals.json"
    ).items():
        require(sha((ROOT / name).read_bytes()) == h, "HISTORICAL_OR_H_SEAL_CHANGED")


def freeze():
    require(not (BASE / "manifest.json").exists(), "FROZEN_PACKAGE_CANNOT_REWRITE")
    verify_seals()
    from jsonschema import Draft202012Validator

    Draft202012Validator(read(BASE / "evaluation.schema.json")).validate(
        read(BASE / "evaluation-template.json")
    )
    index = read(BASE / "index.json")
    budget = read(BASE / "budget.json")
    require(
        index["order"] == ORDER
        and len(index["items"]) == 8
        and index["candidate_count"] == 1
        and budget["requests_max"] == 8
        and budget["per_case"] == 1
        and budget["output_cap_sum"] == 65536
        and budget["wall_seconds"] == 3600
        and budget["automatic_retries"] == budget["fallbacks"] == 0,
        "MATERIAL_OR_BUDGET_CHANGED",
    )
    for item in index["items"]:
        require(
            sha((ROOT / item["material"]).read_bytes()) == item["sha256"]
            and item["independent_signoff"] == "pending_Lee_for_this_batch",
            "MATERIAL_OR_PRELABEL_CHANGED",
        )
    tests = read(BASE / "offline-tests.json")
    require(
        tests["exit"] == 0 and tests["provider_calls"] == 0, "OFFLINE_TESTS_REQUIRED"
    )
    files = []
    for directory in ("backend/app", "backend/tests", "scripts"):
        files += [
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file()
            and p.suffix in (".py", ".json")
            and "__pycache__" not in p.parts
        ]
    files += [p for p in BASE.rglob("*") if p.is_file()]
    files += [
        ROOT / "backend/pyproject.toml",
        ROOT / "backend/uv.lock",
        ROOT / "docs/ADR/0021-plan-check-and-bounded-repair.md",
        ROOT / "docs/PRD.md",
        ROOT
        / "docs/acceptance/phase-1-plan-semantic-boundary-r01/historical-seals.json",
    ]
    files = [p for p in files if p.exists()]
    write_once(
        BASE / "manifest.json",
        dict(
            run_id=RUN_ID,
            kind="ONLY_ONE_DEVELOPMENT_BATCH_PREPARED_NOT_AUTHORIZED",
            source_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            branch=subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=ROOT, text=True
            ).strip(),
            order=ORDER,
            requests_max=8,
            output_cap_sum=65536,
            wall_seconds=3600,
            per_request_seconds=60,
            retries=0,
            fallbacks=0,
            candidate=CONFIG,
            policy_digest=active_policy_digest(),
            env_metadata=env_metadata(ROOT / ".env"),
            historical_seals=read(
                ROOT
                / "docs/acceptance/phase-1-plan-semantic-boundary-r01/historical-seals.json"
            ),
            files={
                str(p.relative_to(ROOT)): sha(p.read_bytes())
                for p in sorted(set(files))
            },
            independent_labels="pending_Lee",
            real_requests_authorized=0,
            T040="blocked",
            H="sealed_not_used",
        ),
    )


def verify():
    m = read(BASE / "manifest.json")
    require(
        m["order"] == ORDER
        and m["requests_max"] == 8
        and m["wall_seconds"] == 3600
        and m["candidate"] == CONFIG
        and m["policy_digest"] == active_policy_digest(),
        "BATCH_CONFIG_CHANGED",
    )
    require(
        m["env_metadata"] == env_metadata(ROOT / ".env"), "CREDENTIAL_METADATA_CHANGED"
    )
    require(
        m["branch"]
        == subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "BRANCH_CHANGED",
    )
    for name, h in m["files"].items():
        p = ROOT / name
        require(
            p.resolve().is_relative_to(ROOT)
            and not p.is_symlink()
            and sha(p.read_bytes()) == h,
            "FROZEN_FILE_CHANGED",
        )
    verify_seals()
    return sha((BASE / "manifest.json").read_bytes())


def authorize(h):
    a = read(BASE / "approval.json")
    require(
        a
        == dict(
            manifest_sha256=h,
            decision="approve_only_one_bounded_plan_boundary_batch",
            requests_max=8,
            wall_seconds=3600,
            labels_checked_by="Lee",
            all_eight_labels_confirmed=True,
            semantic_failure_collect_fixed_remaining=True,
            technical_failure_stop=True,
            source_user_message=a.get("source_user_message"),
        )
        and bool(a["source_user_message"]),
        "ACCURATE_BUDGET_AND_LABEL_SIGNOFF_REQUIRED",
    )


async def execute_case(name, ledger, *, keys):
    case = read(BASE / f"materials/{name}.json")
    row = row_for(case)
    directory = private_directory(PRIVATE / name)
    c = dict(name=name, ledger=ledger, directory=directory)
    transport = None
    ledger.start(name)
    try:
        g, transport = gateway(c, keys=keys)
        record = await inspect_plan(
            g,
            CallWindow(),
            row,
            row.origin_operation_id,
            expected_binding=expected_binding(case),
        )
        n = c["call"]["n"]
        result = dict(
            material=case,
            result=dict(plan_check=record),
            calls=[c["call"]],
            parsed_calls=[read(directory / f"{n:02}-parsed.json")],
            logical_requests=[read(directory / f"{n:02}-logical.json")],
            review_sources=c["review_sources"],
            quality_evaluation=None,
            independent_signoff="pending_Lee",
            artifact_hashes={
                p.name: sha(p.read_bytes()) for p in directory.iterdir() if p.is_file()
            },
        )
        digest_ = write_once(directory / "result.json", result)
        ledger.finish(name, digest_)
    except BaseException:
        ledger.stop("TECHNICAL_FAILURE_NO_ADAPTIVE_RETRY")
        write_once(
            directory / "failure-summary.json",
            dict(
                kind="technical_failure",
                artifacts={
                    p.name: sha(p.read_bytes())
                    for p in directory.iterdir()
                    if p.is_file()
                },
            ),
        )
        raise
    finally:
        if transport:
            await transport.aclose()


def verify_prior(ledger):
    for name, _, state, _, h in ledger.snapshot()["cases"]:
        if state == "collected":
            directory = PRIVATE / name
            result = read(directory / "result.json")
            require(
                sha((directory / "result.json").read_bytes()) == h,
                "PRIOR_RESULT_CHANGED",
            )
            for filename, digest_ in result["artifact_hashes"].items():
                require(
                    sha((directory / filename).read_bytes()) == digest_,
                    "PRIOR_ARTIFACT_CHANGED",
                )


def evaluate(name, ledger, value, manifest_hash):
    from jsonschema import Draft202012Validator

    Draft202012Validator(read(BASE / "evaluation.schema.json")).validate(value)
    require(
        value["status"] == "evaluated"
        and value["mode"] == "real"
        and value["evaluator"]
        == dict(name="Lee", role="independent_human", signed=True),
        "INDEPENDENT_HUMAN_REQUIRED",
    )
    require(
        value["run_id"] == RUN_ID
        and value["package_manifest_sha256"] == manifest_hash
        and value["case_id"] == name
        and value["slot_id"] == name
        and value["lane"] == "plan_review",
        "EVALUATION_BINDING_CHANGED",
    )
    directory = PRIVATE / name
    result = read(directory / "result.json")
    row = next(x for x in ledger.snapshot()["cases"] if x[0] == name)
    require(
        row[2] == "collected"
        and row[4] == sha((directory / "result.json").read_bytes()),
        "RESULT_CHANGED",
    )
    item = next(x for x in read(BASE / "index.json")["items"] if x["id"] == name)
    require(
        value["artifacts"]
        == dict(
            material_sha256=item["sha256"],
            request_sha256=sha(
                canonical([c["logical_request_sha256"] for c in result["calls"]])
            ),
            response_sha256=sha(
                canonical([c["parsed_sha256"] for c in result["calls"]])
            ),
        ),
        "RESULT_ARTIFACT_BINDING_CHANGED",
    )
    scores = value["scores"]
    require(
        all(v is not None for v in scores.values())
        and type(scores["quality_success"]) is bool,
        "ALL_SCORES_REQUIRED",
    )
    claims = {c["id"]: c for c in value["claims"]}
    require(
        len(claims) == len(value["claims"]) and bool(claims), "ALL_ASSERTIONS_REQUIRED"
    )
    required = set()
    anchors = set()
    for i, parsed in enumerate(result["parsed_calls"]):
        required |= output_fields(parsed["value"], f"/parsed_calls/{i}/value")
        for f in parsed["value"]["findings"]:
            anchors |= {
                f"{result['calls'][i]['n']}:{a}"
                for a in [f["target_anchor"], *f["evidence_anchors"]]
            }
    require(
        required <= {p for c in claims.values() for p in c["evidence_pointers"]},
        "ALL_TEXT_FIELDS_REQUIRED",
    )
    require(
        anchors == {c["anchor_id"] for c in value["citations"]},
        "ALL_CITATIONS_REQUIRED",
    )
    for c in claims.values():
        for p in c["evidence_pointers"]:
            pointer(result, p)
    for c in value["citations"]:
        require(
            set(c["supports_claim_ids"]) <= claims.keys()
            and c["source_pointer"]
            == "/review_sources/" + c["anchor_id"] + "/source_text"
            and c["quoted_source"] in pointer(result, c["source_pointer"]),
            "EXACT_CITATION_SOURCE_REQUIRED",
        )
    observed = result["result"]["plan_check"]
    label = item["prelabel"]
    categorical_match = (
        observed["model_result"]["verdict"] in label["model_verdicts"]
        and observed["server_assessment"]["route"] in label["routes"]
    )
    dimensions = value["dimensions"]
    is_correct = label["model_verdicts"] == ["pass"]
    if is_correct:
        require(
            dimensions["core_detection"] == "not_applicable"
            and dimensions["false_block"] is (not categorical_match),
            "FALSE_BLOCK_MUST_MATCH_OBSERVED_ROUTE",
        )
    else:
        require(
            dimensions["core_detection"] in ("detected", "missed")
            and dimensions["false_block"] is None,
            "DEFECT_DETECTION_ASSESSMENT_REQUIRED",
        )
    if scores["quality_success"]:
        require(categorical_match, "CANNOT_PASS_FROZEN_LABEL_MISMATCH")
        require(
            dimensions["core_detection"] in ("detected", "not_applicable")
            and dimensions["false_block"] is not True,
            "CANNOT_PASS_MISS_OR_FALSE_BLOCK",
        )
        if label.get("severe_control", False):
            require(scores["severe_detection"] == "pass", "SEVERE_DETECTION_REQUIRED")
    verify_prior(ledger)
    # Semantic assertions need Lee's actual checking; structure is not independent truth.
    h = write_once(directory / "evaluation.json", value)
    ledger.record_evaluation(
        name, h, scores["quality_success"], {"dimensions": dimensions, "scores": scores}
    )


def quality_summary(ledger):
    snapshot = ledger.snapshot()
    with ledger.db() as db:
        rows = db.execute(
            "SELECT case_id,passed,metrics_json FROM evaluations ORDER BY case_id"
        ).fetchall()
    passed = {name: passed for name, passed, _ in rows}
    metrics = [json.loads(m) for _, _, m in rows]
    dimensions = [m.get("dimensions", {}) for m in metrics]
    score_views = [m.get("scores", {}) for m in metrics]
    return dict(
        reserved_requests=len(snapshot["calls"]),
        completed_valid_responses=sum(c[2] == "complete" for c in snapshot["calls"]),
        physical_send_note="Reservations consume budget; uncertain sends are not guessed. Check private raw-response receipts for confirmed HTTP results.",
        collected=sum(x[2] == "collected" for x in snapshot["cases"]),
        signed_evaluations=len(rows),
        development_admission_pass=(
            False
            if any(not v for v in passed.values())
            else (True if len(rows) == 8 else None)
        ),
        correct_controls={k: passed.get(k) for k in ORDER[:4]},
        negative_controls={k: passed.get(k) for k in ORDER[4:]},
        judged_false_blocks=sum(d.get("false_block") is True for d in dimensions),
        judged_core_misses=sum(d.get("core_detection") == "missed" for d in dimensions),
        incidental_error_records=sum(
            d.get("incidental_falsehoods") == "present" for d in score_views
        ),
        citation_failure_records=sum(
            d.get("citation_quality") == "fail" for d in score_views
        ),
        counts_only_signed_records=True,
        limitations="Only developer admission, never formal98/95/90, representative error rates, or authorization to use H.",
        H="sealed_not_used",
        T040="blocked",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=["freeze", "check", "activate", "run", "report", "assess", "stop"],
    )
    p.add_argument("--case", choices=ORDER)
    p.add_argument("--evaluation", type=Path)
    args = p.parse_args()
    if args.action == "freeze":
        freeze()
    h = verify()
    if args.action in ("freeze", "check"):
        print(
            json.dumps(
                dict(
                    manifest_sha256=h,
                    requests_max=8,
                    labels="see separate human approval",
                    activated=(PRIVATE / "run.sqlite").exists(),
                )
            )
        )
        return
    authorize(h)
    private_directory(PRIVATE)
    with (PRIVATE / "process.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "activate":
            require(not (PRIVATE / "run.sqlite").exists(), "NO_REACTIVATION")
            load_keys(read(BASE / "manifest.json")["env_metadata"])
            ledger = Ledger(PRIVATE / "run.sqlite", h, activate=True)
        else:
            ledger = Ledger(PRIVATE / "run.sqlite", h)
        if args.action == "run":
            require(args.case is not None, "CASE_REQUIRED")
            verify_prior(ledger)
            keys = load_keys(read(BASE / "manifest.json")["env_metadata"])
            asyncio.run(execute_case(args.case, ledger, keys=keys))
        elif args.action == "assess":
            require(
                args.case is not None and args.evaluation is not None,
                "SIGNED_EVALUATION_REQUIRED",
            )
            evaluate(args.case, ledger, read(args.evaluation), h)
        elif args.action == "stop":
            ledger.stop("EXPLICIT_STOP")
        print(
            json.dumps(dict(ledger=ledger.snapshot(), summary=quality_summary(ledger)))
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Bounded development batch failed closed; no automatic retry or release claim.",
            file=sys.stderr,
        )
        sys.exit(1)
