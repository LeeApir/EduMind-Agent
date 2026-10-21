"""Mechanism tests only: independent SQLite + actual adapters with MockTransport; no Provider."""

# ruff: noqa: E402
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_plan_admission as cli
from acceptance_support.five_hour_runtime import write_once
from acceptance_support.plan_admission_live import (
    execute,
    full_pipeline,
    live_gateway,
    verify_database,
    validate_database_url,
)
from acceptance_support.plan_admission_run import Ledger, RUN_ID, check_assessment
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.plan_admission import CONFIG
from acceptance_support.om_diagnostic import valid_review
from app.agents.plan_check import CHECKS
from app.core.provider_target import ApprovedTarget, ProviderTargetGuard, TargetPolicy
from prepare_five_hour_materials import draft_for, contents
from prepare_plan_admission import read

SLOTS = cli.slots()


def make_ledger(tmp_path, *, now=None):
    clock = now if now else lambda: 1000.0
    return Ledger(tmp_path / "run.sqlite", "a" * 64, SLOTS, activate=True, now=clock)


def force_prefix(ledger, slot):
    # Test fixture only. Live CLI has no mutation command and demands signed artifacts.
    with ledger.db() as db:
        pos = next(i for i, s in enumerate(SLOTS) if s["slot_id"] == slot)
        db.execute('UPDATE cases SET state="passed" WHERE position<?', (pos,))


def complete_case(ledger, spec):
    ledger.finish(spec["slot_id"], "b" * 64)
    ledger.assess(spec["slot_id"], "c" * 64, True)


def test_order_human_gate_failed_stop_and_no_replay(tmp_path):
    ledger = make_ledger(tmp_path)
    first, second = SLOTS[:2]
    with pytest.raises(ValueError, match="PRIOR"):
        ledger.start(second["slot_id"])
    ledger.start(first["slot_id"])
    n, _ = ledger.reserve(first["slot_id"], "plan_check", "d" * 64)
    ledger.complete(n, "e" * 64)
    ledger.finish(first["slot_id"], "f" * 64)
    with pytest.raises(ValueError, match="PRIOR"):
        ledger.start(second["slot_id"])
    ledger.assess(first["slot_id"], "1" * 64, False)
    assert ledger.snapshot()["run"][3] == "FIRST_FAILURE"
    with pytest.raises(ValueError, match="STOPPED"):
        ledger.start(second["slot_id"])
    reopened = Ledger(ledger.path, "a" * 64, SLOTS, now=lambda: 1001)
    assert len(reopened.snapshot()["calls"]) == 1
    with pytest.raises(FileExistsError):
        Ledger(ledger.path, "a" * 64, SLOTS, activate=True, now=lambda: 1001)


@pytest.mark.parametrize(
    "elapsed,reason", [(18000, "GLOBAL_DEADLINE"), (-1, "CLOCK_MOVED_BACKWARD")]
)
def test_absolute_clock_survives_exception_and_restart(tmp_path, elapsed, reason):
    clock = [1000.0]
    ledger = make_ledger(tmp_path, now=lambda: clock[0])
    clock[0] += elapsed
    with pytest.raises(ValueError, match=reason):
        ledger.start(SLOTS[0]["slot_id"])
    assert Ledger(ledger.path, "a" * 64, SLOTS).snapshot()["run"][3] == reason


def test_human_wait_counts_and_operation_limit(tmp_path):
    clock = [1000.0]
    ledger = make_ledger(tmp_path, now=lambda: clock[0])
    first = SLOTS[0]["slot_id"]
    ledger.start(first)
    clock[0] += 180
    with pytest.raises(ValueError, match="OPERATION_DEADLINE"):
        ledger.reserve(first, "plan_check", "d" * 64)
    assert ledger.snapshot()["run"][3] == "OPERATION_DEADLINE"


def test_concurrent_reservations_and_crash_consume_one_slot(tmp_path):
    ledger = make_ledger(tmp_path)
    name = SLOTS[0]["slot_id"]
    ledger.start(name)

    def reserve(_):
        try:
            return ledger.reserve(name, "plan_check", "d" * 64)[0]
        except ValueError:
            return None

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(reserve, range(2)), key=lambda n: n or 0) == [None, 1]
    assert ledger.snapshot()["calls"][0][3] == "reserved"
    with pytest.raises(ValueError, match="REPLAY"):
        ledger.start(name)


def test_exact_59_no_refunds_and_untransferred_closed_slot(tmp_path):
    ledger = make_ledger(tmp_path)
    for spec in SLOTS:
        ledger.start(spec["slot_id"])
        stages = (
            ["plan_check"]
            if spec["lane"] == "plan_review"
            else ["unit_review"]
            if spec["lane"] == "fixed_review"
            else ["plan_generation"] + ["resource_generation"] * 3
            if spec["lane"] == "generation_draft"
            else [
                "plan_generation",
                "plan_check",
                "resource_generation",
                "resource_review",
            ]
            + ["resource_correction", "resource_review"] * 2
            + ["resource_generation", "resource_review"]
            + ["resource_correction", "resource_review"] * 2
            + ["resource_generation", "resource_review"]
            + ["resource_correction", "resource_review", "unit_review"]
        )
        assert len(stages) == spec["cap"]
        for stage in stages:
            n, _ = ledger.reserve(spec["slot_id"], stage, "d" * 64)
            ledger.complete(n, "e" * 64)
        if spec == SLOTS[-1]:
            with pytest.raises(ValueError, match="CAP"):
                ledger.reserve(spec["slot_id"], "unit_review", "d" * 64)
        complete_case(ledger, spec)
    assert len(ledger.snapshot()["calls"]) == 59
    assert ledger.snapshot()["run"][3] == "COMPLETED_DEVELOPMENT_ONLY"


@pytest.mark.parametrize(
    "lane,stage",
    [
        ("plan_review", "resource_generation"),
        ("fixed_review", "plan_generation"),
        ("generation_draft", "unit_review"),
        ("full_pipeline", "goal_mapping"),
        ("full_pipeline", "plan_rebuild"),
    ],
)
def test_cross_lane_mapping_and_rebuild_closed(tmp_path, lane, stage):
    ledger = make_ledger(tmp_path)
    spec = next(s for s in SLOTS if s["lane"] == lane)
    force_prefix(ledger, spec["slot_id"])
    ledger.start(spec["slot_id"])
    with pytest.raises(ValueError, match="CROSS_LANE"):
        ledger.reserve(spec["slot_id"], stage, "d" * 64)
    assert not ledger.snapshot()["calls"]


def mock_guard(base):
    return SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            base, urlsplit(base).hostname, 443, ("8.8.8.8",)
        )
    )


def context(tmp_path, spec):
    ledger = make_ledger(tmp_path)
    force_prefix(ledger, spec["slot_id"])
    ledger.start(spec["slot_id"])
    directory = tmp_path / "case"
    directory.mkdir(mode=0o700)
    return dict(ledger=ledger, spec=spec, directory=directory, call_ids=[], calls=[])


def answer(value, role, **extra):
    return dict(
        model=CONFIG[role]["model"],
        status="completed",
        output=[
            dict(
                type="message",
                role="assistant",
                status="completed",
                content=[dict(type="output_text", text=json.dumps(value))],
            )
        ],
        usage=dict(input_tokens=120, output_tokens=130),
        **extra,
    )


def plan_pass():
    return dict(
        schema_version="plan-review-result-v1",
        verdict="pass",
        coverage=dict(checked=CHECKS, unchecked=[]),
        findings=[],
        unresolved=[],
    )


def fixture_gateway(c, values, *, response_override=None):
    queue = list(values)
    wires = []

    def inner(role):
        def reply(request):
            body = json.loads(request.content)
            wires.append((role, body))
            value = queue.pop(0)
            return (
                response_override(request, role, value)
                if response_override
                else httpx.Response(200, json=answer(value, role))
            )

        return httpx.MockTransport(reply)

    gateway, transports = live_gateway(
        c,
        keys=("GENERATION_TEST_SECRET", "REVIEW_TEST_SECRET"),
        inner_factory=inner,
        guard_factory=mock_guard,
    )
    return gateway, transports, wires


@pytest.mark.parametrize("lane", ["plan_review", "fixed_review", "generation_draft"])
def test_actual_adapter_capture_and_stage_routes(tmp_path, lane):
    spec = next(s for s in SLOTS if s["lane"] == lane)
    case = read(ROOT / spec["material"])
    c = context(tmp_path, spec)
    if lane == "plan_review":
        values = [plan_pass()]
    elif lane == "fixed_review":
        values = [valid_review("unit")]
    else:
        from acceptance_support.plan_admission_live import inputs_for

        values = [
            draft_for(inputs_for(case), "complete"),
            *[
                dict(resource_type=k, prompt_version="learning-resources-v1", content=v)
                for k, v in contents("complete").items()
            ],
        ]
    gateway, transports, wires = fixture_gateway(c, values)
    result = asyncio.run(execute(spec, case, gateway))
    assert len(wires) == spec["cap"] == len(c["calls"])
    assert all(x[3] == "complete" for x in c["ledger"].snapshot()["calls"])
    assert all(
        (role == "review") == (body["model"] == CONFIG["review"]["model"])
        for role, body in wires
    )
    assert all("expected_verdict" not in json.dumps(body) for _, body in wires)
    assert result["production_publish_performed"] is False
    if lane == "generation_draft":
        assert result["review_calls"] == 0 and len(result["candidates"]) == 3
    for n in c["call_ids"]:
        assert (c["directory"] / f"{n:02}-logical.json").exists()
        assert (c["directory"] / f"{n:02}-response.bin").exists()
        assert "SECRET" not in (c["directory"] / f"{n:02}-request.json").read_text()
    asyncio.run(close(transports))


async def close(transports):
    for t in transports:
        await t.aclose()


@pytest.mark.parametrize(
    "bad", ["model", "schema", "usage", "http", "reflected_secret", "timeout"]
)
def test_any_adapter_or_response_failure_halts_without_refund(tmp_path, bad):
    spec = SLOTS[0]
    case = read(ROOT / spec["material"])
    c = context(tmp_path, spec)

    def response(request, role, value):
        data = answer(value, role)
        if bad == "model":
            data["model"] = "unexpected-model"
        if bad == "schema":
            data["output"][0]["content"][0]["text"] = '{"schema_version":"wrong"}'
        if bad == "usage":
            data["usage"]["output_tokens"] = 8193
        if bad == "http":
            return httpx.Response(
                400, json={"error": {"message": "unsupported uniqueItems"}}
            )
        if bad == "reflected_secret":
            return httpx.Response(500, content=b"REVIEW_TEST_SECRET")
        if bad == "timeout":
            raise httpx.ReadTimeout("private upstream text must not escape")
        return httpx.Response(200, json=data)

    gateway, ts, _ = fixture_gateway(c, [plan_pass()], response_override=response)
    with pytest.raises(Exception):
        asyncio.run(execute(spec, case, gateway))
    snap = c["ledger"].snapshot()
    assert (
        snap["run"][3] and len(snap["calls"]) == 1 and snap["calls"][0][3] == "reserved"
    )
    assert not (c["directory"] / "01-parsed.json").exists()
    assert not any(
        "REVIEW_TEST_SECRET" in p.read_text(errors="replace")
        for p in c["directory"].iterdir()
    )
    asyncio.run(close(ts))


def test_default_target_guard_rejects_private_before_transport(tmp_path):
    c = context(tmp_path, SLOTS[0])

    def guard(base):
        return ProviderTargetGuard(
            base, TargetPolicy(), resolver=lambda *_: ("127.0.0.1",)
        )

    with pytest.raises(ValueError):
        live_gateway(c, keys=("test-gen", "test-review"), guard_factory=guard)
    assert c["ledger"].snapshot()["calls"] == []


def evaluated(evidence, spec):
    v = read(cli.PARENT / "evaluation-template.json")
    v.update(
        lane=spec["lane"],
        case_id=spec["case_id"],
        slot_id=spec["slot_id"],
        mode="real",
        status="evaluated",
        evaluator=dict(name="Lee", role="independent_human", signed=True),
        run_id=RUN_ID,
        package_manifest_sha256="a" * 64,
        inventories_complete=dict(all_assertions=True, all_citations=True),
        artifacts=dict(
            material_sha256=spec["material_sha256"],
            request_sha256=sha(
                canonical([c["logical_request_sha256"] for c in evidence["calls"]])
            ),
            response_sha256=sha(
                canonical([c["parsed_sha256"] for c in evidence["calls"]])
            ),
        ),
    )
    v["scores"] = dict(
        technical_integrity="pass",
        severe_detection="not_applicable",
        incidental_falsehoods="none",
        teaching_coverage="not_applicable",
        citation_quality="not_applicable",
        quality_success=True,
        matches_frozen_label=True,
    )
    v["claims"] = [
        dict(
            id="claim1",
            text="A statement for fixture only",
            verdict="supported",
            evidence_pointers=["/material/source"],
            reason="Test-only source binding",
        )
    ]
    return v


def test_assessment_demands_real_human_binding_and_exact_field_quote():
    spec = SLOTS[0]
    evidence = dict(
        material=dict(source="own proposition", neighbor="another proposition"),
        calls=[],
    )
    v = evaluated(evidence, spec)
    schema = read(cli.PARENT / "evaluation.schema.json")
    assert check_assessment(
        v, schema=schema, spec=spec, manifest_hash="a" * 64, evidence=evidence
    )
    for key, value in [("mode", "mock"), ("package_manifest_sha256", "b" * 64)]:
        bad = deepcopy(v)
        bad[key] = value
        with pytest.raises(Exception):
            check_assessment(
                bad, schema=schema, spec=spec, manifest_hash="a" * 64, evidence=evidence
            )
    bad = deepcopy(v)
    bad["evaluator"]["role"] = "gpt_draft"
    with pytest.raises(Exception):
        check_assessment(
            bad, schema=schema, spec=spec, manifest_hash="a" * 64, evidence=evidence
        )
    evidence["calls"] = [
        dict(n=1, logical_request_sha256="c" * 64, parsed_sha256="d" * 64)
    ]
    evidence["parsed_calls"] = [dict(value=dict(findings=[dict(anchors=["a1"])]))]
    evidence["review_sources"] = {"1:a1": dict(source_text="own proposition")}
    v = evaluated(evidence, spec)
    v["citations"] = [
        dict(
            anchor_id="1:a1",
            source_pointer="/review_sources/1:a1/source_text",
            quoted_source="another proposition",
            supports_claim_ids=["claim1"],
            verdict="supports",
            reason="Wrong adjacent field",
        )
    ]
    with pytest.raises(ValueError, match="QUOTE_NOT_IN_FIELD"):
        check_assessment(
            v, schema=schema, spec=spec, manifest_hash="a" * 64, evidence=evidence
        )


def test_incidental_falsehood_cannot_pass_even_when_core_detected():
    spec = SLOTS[0]
    evidence = dict(material=dict(source="source"), calls=[])
    v = evaluated(evidence, spec)
    v["scores"].update(severe_detection="pass", incidental_falsehoods="present")
    with pytest.raises(Exception):
        check_assessment(
            v,
            schema=read(cli.PARENT / "evaluation.schema.json"),
            spec=spec,
            manifest_hash="a" * 64,
            evidence=evidence,
        )
    v["scores"]["quality_success"] = False
    assert (
        check_assessment(
            v,
            schema=read(cli.PARENT / "evaluation.schema.json"),
            spec=spec,
            manifest_hash="a" * 64,
            evidence=evidence,
        )
        is False
    )


def test_frozen_parent_and_all_16_signatures():
    cli.verify_authorization()
    assert not (cli.PACKAGE / "activation.json").exists()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@127.0.0.1:5432/production",
        "postgresql+asyncpg://u:p@db.example:15437/edumind_catalog_plan_admission_r02",
        "postgresql+asyncpg://u:p@127.0.0.1:15437/edumind_catalog_five_hour_r01",
    ],
)
def test_nonisolated_database_refused(url):
    with pytest.raises(ValueError, match="ISOLATED"):
        validate_database_url(url)


@pytest.mark.skipif(
    not os.getenv("EDUMIND_PLAN_ADMISSION_PG_URL"),
    reason="dedicated isolated PostgreSQL required",
)
@pytest.mark.parametrize("mode", ["complete", "needs_human", "technical_failure"])
def test_full_isolated_pipeline_records_plan_check_and_original_binding(
    tmp_path, monkeypatch, mode
):
    url = os.environ["EDUMIND_PLAN_ADMISSION_PG_URL"]
    database = os.environ["EDUMIND_PLAN_ADMISSION_PG_DATABASE"]
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    spec = SLOTS[-1]
    case = read(ROOT / spec["material"])
    c = context(tmp_path, spec)
    from acceptance_support.plan_admission_live import inputs_for

    values = [draft_for(inputs_for(case), "complete"), plan_pass()]
    for role, content in contents("complete").items():
        values += [
            dict(
                resource_type=role,
                prompt_version="learning-resources-v1",
                content=content,
            ),
            valid_review("resource"),
        ]
    values.append(valid_review("unit"))
    if mode == "needs_human":
        values[1] = {
            **plan_pass(),
            "verdict": "needs_human",
            "unresolved": ["Synthetic missing premise; not a real semantic evaluation"],
        }

    def override(request, role, value):
        if mode == "technical_failure" and role == "review":
            return httpx.Response(
                400, json={"error": {"message": "unsupported schema"}}
            )
        return httpx.Response(200, json=answer(value, role))

    gateway, ts, wires = fixture_gateway(c, values, response_override=override)

    async def run():
        await verify_database(url, empty=True, database=database)
        return await full_pipeline(case, gateway, url, database=database)

    result = asyncio.run(run())
    asyncio.run(close(ts))
    if mode != "complete":
        assert (
            result["course_state"] == "failed"
            and result["operation_calls"] == 2
            and len(wires) == 2
        )
        assert result["isolated_publication"] is None and not result["resources"]
        assert len(result["plans"]) == 1 and len(result["attempts"]) == 2
        assert len(result["plan_checks"]) == (1 if mode == "needs_human" else 0)
        assert result["original_snapshot"] == case["input_snapshot"]
        assert bool(c["ledger"].snapshot()["run"][3]) == (mode == "technical_failure")
        write_once(tmp_path / "mock-full-failed-result.json", result)
        return
    assert (
        result["course_state"] == "completed"
        and result["operation_calls"] == 9
        and len(wires) == 9
    )
    assert result["original_snapshot"] == case["input_snapshot"]
    assert result["actual_snapshots"] == [
        {**case["input_snapshot"], "reference_context": case["reference_context"]}
    ]
    assert (
        len(result["plan_checks"]) == 1
        and len(result["reviews"]) == 4
        and len(result["resources"]) == 3
    )
    assert result["isolated_publication"]["approval_source"] == "auto"
    assert result["production_publish_performed"] is False
    write_once(tmp_path / "mock-full-result.json", result)


def test_output_field_inventory_and_each_actual_anchor_are_required():
    spec = SLOTS[0]
    evidence = dict(
        material=dict(source="actual source"),
        calls=[dict(n=1, logical_request_sha256="d" * 64, parsed_sha256="e" * 64)],
        parsed_calls=[
            dict(
                value=dict(
                    verdict="reject",
                    findings=[dict(anchors=["a1"], impact="a concrete defect")],
                )
            )
        ],
        review_sources={"1:a1": dict(source_text="actual source")},
    )
    v = evaluated(evidence, spec)
    schema = read(cli.PARENT / "evaluation.schema.json")

    def verify(value):
        return check_assessment(
            value, schema=schema, spec=spec, manifest_hash="a" * 64, evidence=evidence
        )

    with pytest.raises(ValueError, match="ALL_OUTPUT_FIELDS"):
        verify(v)
    v["claims"][0]["evidence_pointers"] += [
        "/parsed_calls/0/value/verdict",
        "/parsed_calls/0/value/findings/0/impact",
    ]
    with pytest.raises(ValueError, match="ALL_ACTUAL_CITATIONS"):
        verify(v)
    v["citations"] = [
        dict(
            anchor_id="1:a1",
            source_pointer="/review_sources/1:a1/source_text",
            quoted_source="actual source",
            supports_claim_ids=["claim1"],
            verdict="supports",
            reason="Exact field",
        )
    ]
    assert verify(v)
    wrong = deepcopy(v)
    wrong["citations"][0]["source_pointer"] = "/material/source"
    with pytest.raises(ValueError, match="EXACT_ANCHOR_FIELD"):
        verify(wrong)
    wrong = deepcopy(v)
    wrong["citations"][0]["supports_claim_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="UNKNOWN_CLAIM"):
        verify(wrong)


def test_generation_cannot_pass_with_unassessed_coverage():
    spec = next(s for s in SLOTS if s["lane"] == "generation_draft")
    evidence = dict(material=dict(source="source"), calls=[])
    v = evaluated(evidence, spec)
    with pytest.raises(ValueError, match="GENERATED_TEACHING_COVERAGE"):
        check_assessment(
            v,
            schema=read(cli.PARENT / "evaluation.schema.json"),
            spec=spec,
            manifest_hash="a" * 64,
            evidence=evidence,
        )


def test_no_real_activation_or_overwrite_command(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "PACKAGE", tmp_path)
    with pytest.raises(FileNotFoundError):
        cli.activated("a" * 64)
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="CANNOT_REWRITE"):
        cli.freeze()


def test_signature_change_is_rejected_without_reopening_parent(tmp_path, monkeypatch):
    for name in ("approval.json", "human-check-20261021.json"):
        (tmp_path / name).write_bytes((cli.APPROVAL / name).read_bytes())
    h = read(tmp_path / "human-check-20261021.json")
    h["materials"][0]["material_sha256"] = "0" * 64
    (tmp_path / "human-check-20261021.json").write_text(json.dumps(h))
    monkeypatch.setattr(cli, "APPROVAL", tmp_path)
    with pytest.raises(ValueError, match="LABEL_SIGNATURE_CHANGED"):
        cli.verify_authorization()


def test_result_tamper_is_rejected(tmp_path):
    path = tmp_path / "01-response.bin"
    path.write_bytes(b"original")
    result = dict(artifact_hashes={path.name: sha(path.read_bytes())})
    cli.verify_artifacts(tmp_path, result)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="ARTIFACT_CHANGED"):
        cli.verify_artifacts(tmp_path, result)


@pytest.mark.parametrize(
    "item",
    [
        x
        for x in read(cli.PARENT / "index.json")["materials"]
        if x["lane"] in ("plan_review", "fixed_review")
    ],
    ids=lambda x: x["id"] + "-" + x["lane"],
)
def test_review_wire_matches_parent_frozen_capture(tmp_path, item):
    spec = next(
        s for s in SLOTS if s["case_id"] == item["id"] and s["lane"] == item["lane"]
    )
    case = read(ROOT / spec["material"])
    c = context(tmp_path, spec)
    gateway, ts, wires = fixture_gateway(
        c, [plan_pass() if spec["lane"] == "plan_review" else valid_review("unit")]
    )
    asyncio.run(execute(spec, case, gateway))
    asyncio.run(close(ts))
    kind = "plan" if spec["lane"] == "plan_review" else "review"
    expected = read(cli.PARENT / f"captures/{kind}/{spec['case_id']}.json")["wires"][0][
        "body"
    ]
    assert wires[0][1] == expected
    assert len(c["review_sources"]) == len(
        json.loads(wires[0][1]["input"][-1]["content"])["anchor_catalog"]
    )


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_bounded_error_decoder_preserves_safe_error_and_never_retries(
    tmp_path, encoding
):
    import gzip

    spec = SLOTS[0]
    case = read(ROOT / spec["material"])
    c = context(tmp_path, spec)

    def response(request, role, value):
        raw = json.dumps({"error": {"message": "unsupported uniqueItems"}}).encode()
        if encoding == "gzip":
            raw = gzip.compress(raw)
        return httpx.Response(
            400,
            headers={"content-type": "application/json", "content-encoding": encoding},
            stream=httpx.ByteStream(raw),
        )

    gateway, ts, wires = fixture_gateway(c, [plan_pass()], response_override=response)
    with pytest.raises(Exception):
        asyncio.run(execute(spec, case, gateway))
    asyncio.run(close(ts))
    receipt = read(c["directory"] / "01-receipt.json")
    assert len(wires) == 1 and receipt["status"] == 400 and receipt["provider_error"]
    assert "uniqueItems" in json.dumps(receipt["provider_error"])
    assert c["ledger"].snapshot()["run"][3]


def test_empty_completed_case_refused(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.start(SLOTS[0]["slot_id"])
    with pytest.raises(ValueError, match="INCOMPLETE_CASE_CALLS"):
        ledger.finish(SLOTS[0]["slot_id"], "f" * 64)


def test_waiting_for_human_does_not_extend_five_hours(tmp_path):
    clock = [1000.0]
    ledger = make_ledger(tmp_path, now=lambda: clock[0])
    name = SLOTS[0]["slot_id"]
    ledger.start(name)
    n, _ = ledger.reserve(name, "plan_check", "d" * 64)
    ledger.complete(n, "e" * 64)
    ledger.finish(name, "f" * 64)
    clock[0] = 19000.0
    with pytest.raises(ValueError, match="GLOBAL_DEADLINE"):
        ledger.assess(name, "a" * 64, True)
    assert ledger.snapshot()["cases"][0][2] == "awaiting_human"
    assert ledger.snapshot()["run"][3] == "GLOBAL_DEADLINE"


@pytest.mark.parametrize("response_kind", ["correct", "label_mismatch"])
def test_run_slot_persists_evidence_and_never_advances_without_human(
    tmp_path, monkeypatch, response_kind
):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(cli, "PRIVATE", private)
    ledger = Ledger(private / "run.sqlite", "a" * 64, SLOTS, activate=True)

    def factory(c, *, keys):
        result = plan_pass()
        if response_kind == "label_mismatch":
            result.update(verdict="needs_human", unresolved=["Synthetic uncertainty"])
        gateway, ts, _ = fixture_gateway(c, [result])
        return gateway, ts

    monkeypatch.setattr(cli, "live_gateway", factory)
    asyncio.run(
        cli.run_slot(
            ledger, SLOTS[0], "a" * 64, ("GENERATION_TEST_SECRET", "REVIEW_TEST_SECRET")
        )
    )
    snapshot = ledger.snapshot()
    assert (
        snapshot["cases"][0][2] == "awaiting_human"
        and snapshot["cases"][1][2] == "pending"
    )
    assert len(snapshot["calls"]) == 1
    assert snapshot["run"][3] == (
        None if response_kind == "correct" else "FROZEN_LABEL_OR_ROUTE_MISMATCH"
    )
    directory = cli.case_directory(SLOTS[0])
    evidence = read(directory / "result.json")
    cli.verify_artifacts(directory, evidence)
    assert (
        evidence["review_sources"]
        and evidence["logical_requests"]
        and evidence["parsed_calls"]
    )
    with pytest.raises(ValueError):
        ledger.start(SLOTS[1]["slot_id"])


def test_only_complete_correction_pairs_can_spend_extra_slots(tmp_path):
    ledger = make_ledger(tmp_path)
    slot = SLOTS[-1]["slot_id"]
    force_prefix(ledger, slot)
    ledger.start(slot)
    for stage in [
        "plan_generation",
        "plan_check",
        "resource_generation",
        "resource_review",
    ]:
        n, _ = ledger.reserve(slot, stage, "d" * 64)
        ledger.complete(n, "e" * 64)
    with pytest.raises(ValueError, match="WITHOUT_NEW_CONTENT"):
        ledger.reserve(slot, "resource_review", "d" * 64)
    for _ in range(2):
        for stage in ["resource_correction", "resource_review"]:
            n, _ = ledger.reserve(slot, stage, "d" * 64)
            ledger.complete(n, "e" * 64)
    with pytest.raises(ValueError, match="PER_RESOURCE_CORRECTION_CAP"):
        ledger.reserve(slot, "resource_correction", "d" * 64)


def test_exact_frozen_executor_and_activation_hash_are_required(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    source = tmp_path / "runtime.py"
    source.write_text("bound runtime")
    env = tmp_path / ".env"
    env.write_text("not a real credential")
    env.chmod(0o600)
    from acceptance_support.luna_admission_gate import env_metadata

    manifest = dict(
        kind="PLAN_ADMISSION_EXECUTION_FROZEN_NOT_ACTIVATED",
        slots=SLOTS,
        requests_max=59,
        wall_seconds=18000,
        first_failure_stop=True,
        automatic_retries=0,
        fallbacks=0,
        database=cli.DATABASE,
        branch="codex/test",
        env_metadata=env_metadata(env),
        files={"runtime.py": sha(source.read_bytes())},
    )
    (package / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "PACKAGE", package)
    monkeypatch.setattr(cli, "verify_authorization", lambda: None)
    monkeypatch.setattr(cli.subprocess, "check_output", lambda *a, **kw: "codex/test\n")
    h = cli.verify()
    (package / "activation.json").write_text(
        json.dumps(
            dict(
                manifest_sha256="0" * 64,
                decision="activate_plan_admission_execution_r02",
                reviewer="Lee",
                source_user_message="fixture only",
            )
        )
    )
    with pytest.raises(ValueError, match="ACTIVATION"):
        cli.activated(h)
    source.write_text("changed runtime")
    with pytest.raises(ValueError, match="FROZEN_FILE_CHANGED"):
        cli.verify()


def test_compressed_success_has_matching_decoded_transport_digest(tmp_path):
    import gzip

    spec = SLOTS[0]
    case = read(ROOT / spec["material"])
    c = context(tmp_path, spec)

    def response(request, role, value):
        raw = json.dumps(answer(value, role)).encode()
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
            stream=httpx.ByteStream(gzip.compress(raw)),
        )

    gateway, ts, wires = fixture_gateway(c, [plan_pass()], response_override=response)
    result = asyncio.run(execute(spec, case, gateway))
    asyncio.run(close(ts))
    assert result["plan_check"]["model_result"]["verdict"] == "pass" and len(wires) == 1
    parsed = read(c["directory"] / "01-parsed.json")
    assert (
        parsed["transport_audit"]["response_digest"]
        == c["calls"][0]["decoded_response_sha256"]
    )
