"""Read-only evidence validation for T069; evidence completeness is not quality acceptance."""

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_agent_pilot as c  # noqa: E402
from scripts.isolated_diagnostics import p15_pilot_baseline as b  # noqa: E402
from scripts.isolated_diagnostics import p15_pilot_wire as wire  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_execution import validate_assistant_report  # noqa: E402
from scripts.isolated_diagnostics.p15_pilot_replay import replay  # noqa: E402
from scripts.isolated_diagnostics.p15_head_insertion_engine import (  # noqa: E402
    canonical,
    QUESTION_KEYS,
    SpecError,
    answer,
    build_example,
    digest,
    validate_example,
)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise c.PilotError(reason)


def read(path: Path) -> bytes:
    require(
        not path.is_symlink() and path.is_file() and path.stat().st_size <= 4000000,
        "EVIDENCE_PATH_OR_SIZE",
    )
    return path.read_bytes()


def parse_file(path: Path) -> Any:
    return wire.strict_json(read(path))


def verify(
    output: Path,
    package: str,
    *,
    expected_inputs_sha256: str | None = None,
    expected_grant_digest: str | None = None,
) -> dict[str, Any]:
    output = output.absolute()
    require(
        not any(p.is_symlink() for p in (output, *output.parents)), "EVIDENCE_SYMLINK"
    )
    require(not (output / "ledger.sqlite").is_symlink(), "DATABASE_SYMLINK")
    lock = None
    if (output / "executor.lock").exists():
        require(not (output / "executor.lock").is_symlink(), "LOCK_SYMLINK")
        lock = os.open(output / "executor.lock", os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lock)
            raise c.PilotError("EXECUTION_IN_PROGRESS") from None
    db = None
    try:
        db = sqlite3.connect(
            "file:" + quote(str(output / "ledger.sqlite")) + "?mode=ro", uri=True
        )
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        require(
            db.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
            "SQLITE_INTEGRITY",
        )
        batch = wire.strict_json(
            db.execute("SELECT value FROM batch WHERE id=1").fetchone()[0]
        )
        require(batch["package_sha256"] == package, "BATCH_PACKAGE")
        grant = parse_file(output / "grant.json")
        require(digest(grant) == batch["grant_sha256"], "GRANT_DIGEST")
        if expected_grant_digest is not None:
            require(digest(grant) == expected_grant_digest, "EXTERNAL_GRANT_PIN")
        if expected_inputs_sha256 is not None:
            require(
                hashlib.sha256(read(output / "inputs.json")).hexdigest()
                == expected_inputs_sha256,
                "EXTERNAL_INPUT_PIN",
            )
        inputs = parse_file(output / "inputs.json")
        order = [
            dict(slot_id=s["slot_id"], arm=a, kind=s["kind"])
            for s in inputs["slots"]
            for a in ("B", "C")
        ]
        require(
            batch["order"] == order and 0 <= batch["position"] <= len(order),
            "ORDER_OR_POSITION",
        )
        events = db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        parent = None
        kinds: Counter[str] = Counter()
        result_rows = []
        assistant_reviews = []
        for i, row in enumerate(events):
            payload = wire.strict_json(row["payload"])
            require(
                row["seq"] == i
                and row["previous"] == parent
                and row["digest"]
                == digest(
                    dict(
                        seq=i,
                        kind=row["kind"],
                        payload=payload,
                        previous=parent,
                        epoch=row["epoch"],
                    )
                ),
                "RECEIPT_CHAIN",
            )
            parent = row["digest"]
            kinds[row["kind"]] += 1
            if row["kind"] == "slot_result":
                result_rows.append(payload)
            if row["kind"] == "assistant_review":
                assistant_reviews.append(payload)
        require(bool(events) and events[0]["kind"] == "started", "START_RECEIPT")
        calls = db.execute("SELECT * FROM calls ORDER BY rowid").fetchall()
        require(len(calls) <= 90 and kinds["reserved"] == len(calls), "CALL_COUNT")
        require(
            kinds["sent"]
            == sum(
                x["state"] in ("sent", "complete")
                or any(
                    wire.strict_json(e["payload"]).get("ticket") == x["ticket"]
                    for e in events
                    if e["kind"] == "sent"
                )
                for x in calls
            ),
            "SENT_COUNT",
        )
        totals: Counter[str] = Counter()
        per_slot: dict[tuple[str, str], list[Any]] = {}
        statuses = 0
        for row in calls:
            key = (row["slot"], row["arm"])
            per_slot.setdefault(key, []).append(row)
            expected = (
                [
                    "pilot_baseline",
                    "pilot_review",
                    "pilot_baseline_repair",
                    "pilot_review",
                ]
                if row["arm"] == "B"
                else [
                    "pilot_plan",
                    "pilot_content",
                    "pilot_review",
                    "pilot_repair",
                    "pilot_review",
                ]
            )
            require(
                [r["stage"] for r in per_slot[key]] == expected[: len(per_slot[key])],
                "STAGE_ORDER",
            )
            require(
                row["state"] in ("complete", "unknown", "sent", "reserved"),
                "CALL_STATE",
            )
            body = parse_file(output / (row["ticket"] + "-request.json"))
            require(digest(body) == row["request_sha"], "REQUEST_DIGEST")
            role = "review" if row["stage"] == "pilot_review" else "generation"
            require(
                body["model"] == wire.ROUTES[role]["model"]
                and body["max_output_tokens"] == 8000
                and body["reasoning"] == dict(effort=wire.ROUTES[role]["reasoning"])
                and body["stream"] is False
                and body["store"] is False
                and body["text"]["format"]["strict"] is True,
                "WIRE_CONFIG",
            )
            stage = row["stage"].removeprefix("pilot_")
            instruction = (
                b.INSTRUCTION
                if stage == "baseline"
                else b.REPAIR_INSTRUCTION
                if stage == "baseline_repair"
                else c.INSTRUCTIONS[stage]
            )
            schema = (
                b.SCHEMA
                if stage in ("baseline", "baseline_repair")
                else c.PLAN_SCHEMA
                if stage == "plan"
                else c.REVIEW_SCHEMA
                if stage == "review"
                else c.CONTENT_SCHEMA
            )
            require(
                body["input"][0] == dict(role="system", content=instruction)
                and body["text"]["format"]["schema"] == schema,
                "PROMPT_OR_SCHEMA_DRIFT",
            )
            status_file = output / (row["ticket"] + "-status.json")
            if status_file.exists():
                statuses += 1
            observed = [
                wire.strict_json(e["payload"])
                for e in events
                if e["kind"] == "wire_observed"
                and wire.strict_json(e["payload"]).get("ticket") == row["ticket"]
            ]
            if observed:
                require(
                    len(observed) == 1
                    and hashlib.sha256(
                        read(output / (row["ticket"] + "-response.json"))
                    ).hexdigest()
                    == observed[0]["response_sha256"]
                    and hashlib.sha256(read(status_file)).hexdigest()
                    == observed[0]["status_sha256"],
                    "OBSERVED_WIRE_DIGEST",
                )
            if row["state"] == "complete":
                require(parse_file(status_file)["http_status"] == 200, "STATUS")
                raw = read(output / (row["ticket"] + "-response.json"))
                require(
                    hashlib.sha256(raw).hexdigest() == row["response_sha"],
                    "RESPONSE_DIGEST",
                )
                _, observation = wire.validate(body, raw, role)
                require(
                    wire.strict_json(row["usage"]) == observation, "USAGE_OBSERVATION"
                )
                totals["reported_input"] += observation["reported_input_tokens"]
                totals["reported_output"] += observation["reported_total_output_tokens"]
        require(
            kinds["settled"] == sum(r["state"] == "complete" for r in calls),
            "SETTLED_COUNT",
        )
        successful = {"B": 0, "C": 0}
        first_successful = {"B": 0, "C": 0}
        refused = {"B": 0, "C": 0}
        initial_structure = {"B": 0, "C": 0}
        unverified_stop_reasons = []
        for index, row in enumerate(result_rows):
            require(
                dict(slot_id=row["slot_id"], arm=row["arm"], kind=row["kind"])
                == order[index],
                "RESULT_ORDER",
            )
            raw = read(output / row["name"])
            require(
                hashlib.sha256(raw).hexdigest() == row["result_sha256"], "RESULT_DIGEST"
            )
            result = wire.strict_json(raw)
            require(result["state"] == row["state"], "RESULT_STATE")
            key = (row["slot_id"], row["arm"])
            require(result["calls"] == len(per_slot.get(key, [])), "SLOT_CALLS")
            if row["kind"] == "refusal":
                require(
                    result["state"] == "refused" and result["calls"] == 0,
                    "REFUSAL_HTTP",
                )
                actual_slot = next(
                    s for s in inputs["slots"] if s["slot_id"] == row["slot_id"]
                )
                try:
                    reference = build_example(actual_slot["spec"])
                    if actual_slot["question"] is not None:
                        answer(reference, actual_slot["question"])
                    raise c.PilotError("REFUSAL_WAS_SUPPORTED")
                except SpecError as exc:
                    require(
                        result
                        == dict(
                            state="refused",
                            reason=str(exc),
                            calls=0,
                            versions=[],
                            events=[],
                        ),
                        "EXACT_REFUSAL_REASON",
                    )
                refused[row["arm"]] += 1
                continue
            if result["versions"] and not result["versions"][0]["payload"].get(
                "degraded"
            ):
                initial_structure[row["arm"]] += 1
            actual_slot = next(
                s for s in inputs["slots"] if s["slot_id"] == row["slot_id"]
            )
            workflow = result["events"]
            example = next(
                e["payload"]["example"] for e in workflow if e["kind"] == "example"
            )
            validate_example(example)
            require(
                canonical(example["spec"]) == canonical(actual_slot["spec"]),
                "WORKFLOW_INPUT_SPEC",
            )
            _, unverified = asyncio.run(
                replay(
                    output,
                    actual_slot,
                    row["arm"],
                    per_slot.get(key, []),
                    result,
                    batch,
                    events,
                    read,
                )
            )
            if unverified:
                unverified_stop_reasons.append(
                    dict(slot_id=row["slot_id"], arm=row["arm"])
                )
            workflow = result["events"]
            prior = None
            for i, event in enumerate(workflow):
                detached = deepcopy(event)
                sha = detached.pop("event_digest")
                require(
                    event["sequence"] == i
                    and event["previous_digest"] == prior
                    and digest(detached) == sha,
                    "WORKFLOW_CHAIN",
                )
                prior = digest(event)
            example = next(
                e["payload"]["example"] for e in workflow if e["kind"] == "example"
            )
            validate_example(example)
            actual_slot = next(
                s for s in inputs["slots"] if s["slot_id"] == row["slot_id"]
            )
            require(
                canonical(example["spec"]) == canonical(actual_slot["spec"]),
                "WORKFLOW_INPUT_SPEC",
            )
            candidate_events = [
                e["payload"]
                for e in workflow
                if e["kind"] in ("candidate", "presentation_degraded")
            ]
            require(candidate_events == result["versions"], "WORKFLOW_CANDIDATES")
            dispatches = [e["payload"] for e in workflow if e["kind"] == "dispatch"]
            responses = [e["payload"] for e in workflow if e["kind"] == "response"]
            wire_calls = per_slot.get(key, [])
            require(len(dispatches) == len(wire_calls), "WORKFLOW_DISPATCHES")
            for dispatch, call in zip(dispatches, wire_calls):
                body = parse_file(output / (call["ticket"] + "-request.json"))
                require(
                    body["input"][1]["content"]
                    == canonical(dispatch["payload"]).decode()
                    and body["text"]["format"]["schema"] == dispatch["schema"],
                    "WORKFLOW_REQUEST",
                )
            completed = [r for r in wire_calls if r["state"] == "complete"]
            require(len(responses) == len(completed), "WORKFLOW_RESPONSES")
            for response, call in zip(responses, completed):
                body = parse_file(output / (call["ticket"] + "-request.json"))
                raw = read(output / (call["ticket"] + "-response.json"))
                role = "review" if call["stage"] == "pilot_review" else "generation"
                reply, _ = wire.validate(body, raw, role)
                require(
                    response["value"] == dict(reply.value)
                    and response["model_id"] == reply.model_id
                    and response["usage"]
                    == (asdict(reply.usage) if reply.usage else None),
                    "WORKFLOW_RESPONSE",
                )
            response_by_call = {
                r["ticket"]: response for r, response in zip(completed, responses)
            }
            for dispatch, call in zip(dispatches, wire_calls):
                role = call["stage"].removeprefix("pilot_")
                require(dispatch["role"] == role, "DISPATCH_ROLE")
                payload = dispatch["payload"]
                response = response_by_call.get(call["ticket"])
                if role == "plan" and response:
                    value = response["value"]
                    if (
                        canonical(value["spec"]) != canonical(actual_slot["spec"])
                        or {
                            r["objective"]: r["observation_key"]
                            for r in value["coverage"]
                        }
                        != c.GOALS
                    ):
                        require(
                            result["state"] == "stopped"
                            and result.get("reason") == "PLAN_COVERAGE_OR_SPEC",
                            "PLAN_BINDING",
                        )
                    require(
                        payload
                        == dict(goal=list(c.GOALS), allowed_spec=actual_slot["spec"]),
                        "PLAN_INPUT",
                    )
                elif role == "content":
                    plan_response = next(
                        r["value"] for r in responses if r["role"] == "plan"
                    )
                    require(
                        payload["plan"] == plan_response
                        and payload["example"] == example,
                        "CONTENT_PLAN_OR_EXAMPLE",
                    )
                elif role == "baseline":
                    require(
                        payload
                        == dict(
                            semantics=b.SEMANTICS,
                            spec=actual_slot["spec"],
                            goals=list(c.GOALS),
                            question_keys=list(QUESTION_KEYS),
                            code_anchor=row["slot_id"] + ":code",
                        ),
                        "BASELINE_INPUT",
                    )
                elif role in ("repair", "baseline_repair"):
                    first_content = next(
                        r["value"]
                        for r in responses
                        if r["role"] in ("content", "baseline")
                    )
                    first_review = next(
                        r["value"] for r in responses if r["role"] == "review"
                    )
                    require(
                        payload["original"] == first_content
                        and payload["issues"] == first_review
                        and first_review["verdict"] == "revise"
                        and not any(
                            i["area"] in ("fact", "code_safety")
                            or i["severity"] == "severe"
                            for i in first_review["issues"]
                        ),
                        "REPAIR_CAUSALITY",
                    )
                    if role == "repair":
                        require(payload["reference"] == example, "REPAIR_REFERENCE")
                    else:
                        require(
                            payload["semantics"] == b.SEMANTICS
                            and payload["spec"] == actual_slot["spec"],
                            "BASELINE_REPAIR_SPEC",
                        )
                elif role == "review":
                    require(
                        payload["reference"] == example
                        and payload["review_context"] == c.review_context(example),
                        "REVIEW_REFERENCE",
                    )
                    revision = dispatch["identity"]["revision"]
                    require(
                        0 <= revision < len(result["versions"])
                        and payload["source"] == result["versions"][revision]["payload"]
                        and payload["source_digest"] == digest(payload["source"]),
                        "REVIEW_SOURCE",
                    )
                    if response:
                        try:
                            c.validate_review(response["value"], payload["source"])
                        except c.PilotError as exc:
                            require(
                                result["state"] == "stopped"
                                and result.get("reason") == str(exc),
                                "IGNORED_REVIEW_REJECTION",
                            )

            content_roles = (
                ("content", "repair")
                if row["arm"] == "C"
                else ("baseline", "baseline_repair")
            )
            content_responses = [
                r["value"] for r in responses if r["role"] in content_roles
            ]
            for version, artifact in enumerate(result["versions"]):
                source = artifact["payload"]
                if not source.get("degraded"):
                    parent_digest = (
                        digest(result["versions"][version - 1]) if version else None
                    )
                    expected_source = (
                        (c.assemble if row["arm"] == "C" else b.assemble)(
                            content_responses[version],
                            example,
                            row["slot_id"],
                            version,
                            parent_digest,
                        )
                        if row["arm"] == "C"
                        else b.assemble(
                            content_responses[version],
                            row["slot_id"],
                            example,
                            version,
                            parent_digest,
                        )
                    )
                    require(source == expected_source, "CANDIDATE_CONTENT")
                expected_identity = dict(
                    schema_version="pilot-artifact-v1",
                    run_id="p15_agent_pilot_p01",
                    slot_id=row["slot_id"],
                    arm=row["arm"],
                    revision=version,
                    parent_digest=digest(result["versions"][version - 1])
                    if version
                    else None,
                    spec_digest=digest(actual_slot["spec"]),
                    engine_version=example["engine_version"],
                    template_version=example["template_version"],
                    prompt_version=c.PROMPT_VERSION
                    if row["arm"] == "C"
                    else b.BASELINE_VERSION,
                )
                require(artifact["identity"] == expected_identity, "CANDIDATE_IDENTITY")
                require(
                    artifact["payload_digest"] == digest(source)
                    and source["production_scoring"] is False,
                    "CANDIDATE_AUTHORITY",
                )
            reports = [a for a in assistant_reviews if (a["slot_id"], a["arm"]) == key]
            if reports:
                require(
                    len(reports) == 1
                    and reports[0]["result_sha256"] == row["result_sha256"],
                    "ASSISTANT_RESULT",
                )
                report_file = output / f"assistant-{index:02d}.json"
                require(parse_file(report_file) == reports[0], "ASSISTANT_REPORT_FILE")
                validate_assistant_report(
                    reports[0],
                    package,
                    dict(
                        slot_id=row["slot_id"],
                        arm=row["arm"],
                        result_sha256=row["result_sha256"],
                    ),
                    result,
                )
                if reports[0]["decision"] == "accept":
                    require(
                        all(reports[0]["checks"].values()) and not reports[0]["issues"],
                        "ASSISTANT_ACCEPT",
                    )
                    successful[row["arm"]] += 1
                    if len(result["versions"]) == 1:
                        first_successful[row["arm"]] += 1
        if batch["status"] == "collected":
            require(
                batch["position"] == len(order) == len(result_rows),
                "COLLECTED_DENOMINATOR",
            )
        if batch["status"] == "awaiting_assistant":
            require(
                batch["position"] + 1 == len(result_rows)
                and batch["pending"]["result_sha256"]
                == result_rows[-1]["result_sha256"],
                "PENDING_RESULT_STATE",
            )
        return dict(
            evidence_verified=True,
            authority_pins_verified=expected_grant_digest is not None
            and expected_inputs_sha256 is not None,
            batch_state=batch["status"],
            requests_reserved=len(calls),
            http_responses_recorded=statuses,
            transport_kinds=dict(
                Counter(
                    wire.strict_json(e["payload"])["kind"]
                    for e in events
                    if e["kind"] == "transport_kind"
                )
            ),
            unknown=sum(r["state"] == "unknown" for r in calls),
            pending=sum(r["state"] in ("reserved", "sent") for r in calls),
            planned_arm_slots=len(order),
            slot_results=len(result_rows),
            unrun_arm_slots=len(order) - len(result_rows),
            initial_structure=dict(
                numerators=initial_structure, denominator_each_arm=10
            ),
            first_e2e=dict(numerators=first_successful, denominator_each_arm=10),
            final_e2e=dict(numerators=successful, denominator_each_arm=10),
            local_refusals=dict(numerators=refused, denominator_each_arm=4),
            **dict(totals),
            unverified_transport_stop_reasons=unverified_stop_reasons,
            actual_invoice=None,
            actual_currency=None,
            independent_overall_quality_evaluated=False,
            T070_completed=False,
            production_admission=False,
        )
    finally:
        if db is not None:
            db.close()
        if lock is not None:
            os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--package-sha256", required=True)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                verify(args.directory, args.package_sha256),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        print("Evidence refused; no files modified or requests sent.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
