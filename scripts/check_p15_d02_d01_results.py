"""Read-only D02 d01 stop audit; never sends, resumes or repairs model output."""

# ruff: noqa: E402
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_p15_d02_recheck_d01 as cli
from acceptance_support.p15_diagnostic_ledger import digest
from app.agents import free_course_planning as planner
from app.agents import free_scene_generation as generator
from isolated_diagnostics.p15_d02_review_d01 import verify_consistency
from isolated_diagnostics.p15_full_observation_r05 import checked_record
from isolated_diagnostics.p15_full_review_r05 import quote


def validate_summary(v):
    expected = dict(
        state="stopped",
        reason="UNKNOWN_SEND",
        requests=4,
        generation_requests=3,
        review_requests=1,
        http_200=4,
        complete=3,
        unknown=1,
        generated_scenes=2,
        primary_schema_valid=3,
        model_reviews_accepted=0,
        review_scenes_unrun=1,
        standard_assistant_reports=0,
        reported_input=15524,
        reported_output=4410,
        settled_input=11842,
        settled_output=4221,
        unknown_reported_input=3682,
        unknown_reported_output=189,
        workflow_requests=29,
        workflow_reported_input=136424,
        workflow_reported_output=30410,
        blind_answers_checked=4,
        blind_answers_pass=3,
        blind_answers_fail=1,
        consistency_findings=4,
        consistency_false_alarms=4,
        T038_completed=False,
        local_recheck_pass=False,
        protocol_rejection="NONEMPTY_OR_UNKNOWN_REASONING_ITEM",
    )
    if any(v.get(k) != value for k, value in expected.items()):
        raise ValueError("EXACT_STOP_FACTS_CHANGED")


def check():
    package, grant, _, slots = cli.gate()
    output = cli.OUTPUT
    db = sqlite3.connect((output / "ledger.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")

        def events(kind):
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                    (cli.BATCH, kind),
                )
            ]

        batch = db.execute(
            "SELECT package,approval,state,reason FROM batches WHERE id=?", (cli.BATCH,)
        ).fetchone()
        assert (batch["package"], batch["approval"]) == (package, digest(grant))
        assert grant["approved"] is True and events("planned_slots") == [
            dict(slots=slots)
        ]
        attempts = db.execute(
            "SELECT * FROM attempts WHERE batch=?", (cli.BATCH,)
        ).fetchall()
        calls = events("live_dispatch_reserved")
        assert len(calls) == len(attempts) == 4
        sources = events("scene_source_frozen")
        assert len(sources) == 2
        for s in sources:
            assert digest(s["payload"]["source"]) == s["payload"]["source_sha256"]
        statuses, reported = [], []
        protocol = None
        for c in calls:
            ticket = c["ticket"]
            request_raw = (output / (ticket + "-request.json")).read_bytes()
            response_raw = (output / (ticket + "-response.json")).read_bytes()
            assert hashlib.sha256(request_raw).hexdigest() == c["request_sha256"]
            assert (
                digest(
                    dict(
                        identity=c["identity"],
                        stage=c["stage"],
                        request_sha256=c["request_sha256"],
                    )
                )
                == ticket
            )
            status = json.loads((output / (ticket + "-status.json")).read_bytes())[
                "http_status"
            ]
            statuses.append(status)
            response = json.loads(response_raw)
            usage = response["usage"]
            assert (
                usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
            )
            reported.append((usage["input_tokens"], usage["output_tokens"]))
            matching = [a for a in attempts if a["id"] == ticket]
            assert len(matching) == 1
            settlement = [
                r
                for r in events("settled_observation")
                if r["proof_sha256"] == hashlib.sha256(response_raw).hexdigest()
            ]
            if c["provider"] == "review":
                assert matching[0]["state"] == "unknown" and not settlement
                try:
                    checked_record(
                        request_raw,
                        response_raw,
                        stage=c["stage"],
                        identity=c["identity"],
                        ticket=ticket,
                        slots=slots,
                    )
                except ValueError as exc:
                    protocol = str(exc)
                else:
                    raise ValueError("ORIGINAL_PROTOCOL_FAILURE_DISAPPEARED")
                # Never strip/repair fields or settle the rejected response here.
                reason = next(i for i in response["output"] if i["type"] == "reasoning")
                assert reason["content"] == [] and reason["summary"] == []
                assert {
                    "metadata",
                    "internal_chat_message_metadata_passthrough",
                } <= reason.keys()
            else:
                assert matching[0]["state"] == "complete" and len(settlement) == 1
        assert not events("scene_review_finished") and not events(
            "review_protocol_observation"
        )
        assert not events("slot_output") and not events("assistant_review")
        pg = json.loads((output / "pg-export.json").read_bytes())
        tables = pg["tables"]
        for a in tables["free_course_attempts"]:
            stage = a["request_json"]["request"]["stage"]
            settlement = next(
                s
                for s in tables["free_course_settlements"]
                if s["attempt_id"] == a["id"]
            )
            (
                planner if stage == "free_course_plan_generation" else generator
            ).validate_response(
                settlement["outcome_json"]["value"], a["input_snapshot"]
            )
        verify_consistency([dict(tables=tables)], events("consistency_observation"))
        assert len(tables["free_course_scene_versions"]) == 2
        assert [o["state"] for o in tables["free_course_operations"]] == ["succeeded"]
        blind = json.loads((output / "D02-known-blind-review.json").read_bytes())
        assert blind["prior_model_opinions_consulted"] is False
        assert (
            blind["independent_human_truth"] is False
            and blind["review_type"] == "delegated_assistant"
        )
        by_sha = {
            s["payload"]["source_sha256"]: s["payload"]["source"] for s in sources
        }
        assert set(blind["source_sha256s"]) == by_sha.keys()
        for b in blind["block_checks"]:
            quote(by_sha[b["source_sha256"]], b["source_pointer"], b["evidence_quote"])
        questions = {
            q["question_id"]: q
            for s in sources
            for b in s["payload"]["source"]["scene"]["content"]["blocks"]
            if b["kind"] == "exercise"
            for q in b["items"]
        }
        assert {a["question_id"] for a in blind["answer_checks"]} == questions.keys()
        for a in blind["answer_checks"]:
            assert (
                a["question"] == questions[a["question_id"]]["question"]
                and a["answer_key"] == questions[a["question_id"]]["answer_key"]
            )
        assert [
            a["question_id"] for a in blind["answer_checks"] if a["verdict"] == "fail"
        ] == ["q3_swap_order"]
        advisory = json.loads(
            (output / "D02-known-consistency-adjudication.json").read_bytes()
        )
        findings = [
            f
            for o in events("consistency_observation")
            for f in o["report"]["findings"]
        ]
        assert [r["finding_sha256"] for r in advisory["findings"]] == [
            digest(f) for f in findings
        ]
        assert all(
            r["decision"] == "false_alarm" and r["reason"] for r in advisory["findings"]
        )
        result = dict(
            state=batch["state"],
            reason=batch["reason"],
            requests=len(calls),
            generation_requests=sum(c["provider"] == "generation" for c in calls),
            review_requests=sum(c["provider"] == "review" for c in calls),
            http_200=statuses.count(200),
            complete=sum(a["state"] == "complete" for a in attempts),
            unknown=sum(a["state"] == "unknown" for a in attempts),
            generated_scenes=len(sources),
            primary_schema_valid=sum(r["valid"] for r in events("primary_schema")),
            model_reviews_accepted=0,
            review_scenes_unrun=1,
            standard_assistant_reports=0,
            reported_input=sum(v[0] for v in reported),
            reported_output=sum(v[1] for v in reported),
            settled_input=sum(a["input_used"] or 0 for a in attempts),
            settled_output=sum(a["output_used"] or 0 for a in attempts),
            unknown_reported_input=reported[-1][0],
            unknown_reported_output=reported[-1][1],
            workflow_requests=25 + len(calls),
            workflow_reported_input=120900 + sum(v[0] for v in reported),
            workflow_reported_output=26000 + sum(v[1] for v in reported),
            blind_answers_checked=len(blind["answer_checks"]),
            blind_answers_pass=sum(
                a["verdict"] == "pass" for a in blind["answer_checks"]
            ),
            blind_answers_fail=sum(
                a["verdict"] == "fail" for a in blind["answer_checks"]
            ),
            consistency_findings=len(findings),
            consistency_false_alarms=len(advisory["findings"]),
            protocol_rejection=protocol,
            T038_completed=False,
            local_recheck_pass=False,
            actual_fee=None,
            independent_human_truth=False,
        )
        validate_summary(result)
        return result
    finally:
        db.close()


if __name__ == "__main__":
    result = check()
    expected = json.loads((cli.BASE / "results.json").read_bytes())
    if result != expected:
        raise ValueError("SAVED_RESULT_CHANGED")
    manifest = json.loads((cli.BASE / "results-manifest.json").read_bytes())
    for name, sha in manifest["private_sha256"].items():
        if hashlib.sha256((cli.OUTPUT / name).read_bytes()).hexdigest() != sha:
            raise ValueError("PRIVATE_EVIDENCE_CHANGED")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2)  # Accurately stopped, not a passed course or full diagnostic.
