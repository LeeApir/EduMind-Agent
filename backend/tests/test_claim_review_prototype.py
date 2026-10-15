"""Synthetic-only pipeline tests; none of these establish model factual recall."""

import copy
import math
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support import claim_review_prototype as p  # noqa: E402


def snapshot(content=None, context=None, config=None, resource_type="explanation"):
    return p.freeze(
        resource_type,
        content or {"markdown": "甲条件。乙条件。"},
        context or {"whole_function": "helper and caller"},
        config or {"profile": "synthetic-only"},
    )


def anchored(snap, quote):
    block = next(b for b in snap.blocks if quote in b["text"])
    start = block["text"].index(quote)
    return {
        "block_id": block["block_id"],
        "start": start,
        "end": start + len(quote),
        "quote": quote,
    }


def focus(snap, quote):
    return {"text": quote, "anchors": [anchored(snap, quote)], "related_anchors": []}


def envelope(value):
    return {
        "synthetic_only": True,
        "status": "completed",
        "input_tokens": 10,
        "output_tokens": 2,
        "value": value,
    }


def finding(message="A synthetic existing defect."):
    return {"area": "fact", "severity": "major", "message": message}


def review(snap, inv, cid, verdict="pass", findings=None, incidental=None, overall=False):
    result = {
        "version": "claim-overall-v1" if overall else "claim-review-v1",
        "identity": p.binding(snap, inv, cid),
        "verdict": verdict,
        "findings": findings or [],
        "incidental_findings": incidental or [],
    }
    if overall:
        result.update(uncovered=False, uncertain=False)
    return result


def round_tape(snap, index=0, *, quotes=("甲条件", "乙条件"), missing=()):
    raw = {
        "version": "claim-inventory-v1",
        "claims": [focus(snap, q) for q in quotes],
        "exclusions": [],
    }
    coverage = {
        "version": "claim-coverage-v1",
        "missing_claims": [focus(snap, q) for q in missing],
        "uncertainties": [],
        "invalid_exclusions": [],
    }
    inv = p.inventory(snap, raw, coverage)
    prefix = str(index)
    tape = {prefix + ".inventory": envelope(raw), prefix + ".coverage": envelope(coverage)}
    for c in inv["claims"]:
        cid = c["claim_id"]
        tape[prefix + ".claim." + cid] = envelope(review(snap, inv, cid))
    tape[prefix + ".overall"] = envelope(review(snap, inv, "__overall__", overall=True))
    return tape, inv


@pytest.fixture
def replay(tmp_path):
    instances = []

    def create(tape, **kwargs):
        inst = p.Replay(tape, tmp_path / f"offline-{len(instances)}.sqlite", **kwargs)
        instances.append(inst)
        return inst

    yield create
    for inst in instances:
        inst.close()


def test_complete_round_preserves_context_and_hash_chain(replay):
    snap = snapshot()
    tape, inv = round_tape(snap)
    engine = replay(tape)
    result = engine.run(snap)
    assert result.approved and result.synthetic_only
    assert len(engine.requests) == len(inv["claims"]) + 3 == 5
    assert all(r["candidate"] == snap.data for r in engine.requests)
    rows = engine.db.execute(
        "select request_hash,parent_hash,response_hash from offline_calls"
    ).fetchall()
    for i, row in enumerate(rows):
        assert row[0] == p.digest(engine.requests[i])
        assert row[1] == (p.digest([p.VERSION, "synthetic-only"]) if i == 0 else rows[i - 1][2])
        assert row[2] is not None


def test_covering_one_block_does_not_prove_semantic_completeness(replay):
    snap = snapshot()
    tape, inv = round_tape(snap, quotes=("甲条件",), missing=("乙条件",))
    engine = replay(tape)
    assert engine.run(snap).approved
    assert len(inv["claims"]) == 2
    assert len([r for r in engine.requests if ".claim." in r["slot"]]) == 2
    # This only checks the supplied synthetic coverage result, never detects omission by itself.


@pytest.mark.parametrize("flag", ["uncertainties", "invalid_exclusions"])
def test_unresolved_coverage_halts_before_claims(replay, flag):
    snap = snapshot()
    tape, _ = round_tape(snap)
    tape["0.coverage"]["value"][flag] = ["unresolved"]
    engine = replay(tape)
    result = engine.run(snap)
    assert result.status == "unavailable" and result.error == "COVERAGE_UNRESOLVED"
    assert len(engine.requests) == 2
    assert not any(".correction" in r["slot"] for r in engine.requests)
    assert engine.run_round(snap, 1).status == "unavailable"
    assert len(engine.requests) == 2


@pytest.mark.parametrize("mutation", ["quote", "start", "bool", "unknown", "extra", "negative"])
def test_forged_anchors_stop_after_inventory(replay, mutation):
    snap = snapshot()
    tape, _ = round_tape(snap)
    a = tape["0.inventory"]["value"]["claims"][0]["anchors"][0]
    if mutation == "quote":
        a["quote"] = "forged"
    elif mutation == "start":
        a["start"] = 1000
    elif mutation == "bool":
        a["start"] = True
    elif mutation == "unknown":
        a["block_id"] = "not-a-block"
    elif mutation == "extra":
        a["trusted"] = True
    else:
        a["start"] = -1
    engine = replay(tape)
    assert engine.run(snap).status == "unavailable"
    assert len(engine.requests) == 1


def test_field_blocks_unicode_paths_scalars_and_snapshot_copy():
    content = {"z": ["中文\r\n全文", 3, True, None], "a/b~": {"c": "whole function"}}
    snap = snapshot(content, resource_type="exercise")
    content["z"][0] = "mutated"
    assert [b["path"] for b in snap.blocks] == [
        "/content/a~1b~0/c",
        "/content/z/0",
        "/content/z/1",
        "/content/z/2",
        "/content/z/3",
    ]
    assert [b["text"] for b in snap.blocks][1:] == ["中文\r\n全文", "3", "true", "null"]
    assert p.anchor(snap, anchored(snap, "文\r\n全"))["quote"] == "文\r\n全"


@pytest.mark.parametrize(
    "content,code",
    [
        ({str(i): "x" for i in range(49)}, "TOO_MANY_BLOCKS"),
        ({"markdown": "文" * 50000}, "INPUT_TOO_LARGE"),
        ({"number": math.nan}, "INVALID_JSON"),
    ],
)
def test_input_limits_reject_instead_of_truncating(content, code):
    with pytest.raises(p.Invalid, match=code):
        snapshot(content)


@pytest.mark.parametrize("kind", ["duplicate", "missing", "unknown", "overlap"])
def test_inventory_mapping_is_strict(replay, kind):
    snap = snapshot()
    tape, _ = round_tape(snap)
    raw = tape["0.inventory"]["value"]
    if kind == "duplicate":
        raw["claims"].append(copy.deepcopy(raw["claims"][0]))
    elif kind == "missing":
        raw["claims"] = []
    elif kind == "unknown":
        raw["exclusions"] = [{"block_id": "unknown", "reason": "title"}]
    else:
        raw["exclusions"] = [{"block_id": snap.blocks[0]["block_id"], "reason": "title"}]
    assert replay(tape).run(snap).status == "unavailable"


def test_claim_limit_includes_missing_claims(replay):
    snap = snapshot({"markdown": " ".join(f"claim{i}" for i in range(17))})
    raw = {
        "version": "claim-inventory-v1",
        "claims": [focus(snap, f"claim{i}") for i in range(16)],
        "exclusions": [],
    }
    coverage = {
        "version": "claim-coverage-v1",
        "missing_claims": [focus(snap, "claim16")],
        "uncertainties": [],
        "invalid_exclusions": [],
    }
    engine = replay({"0.inventory": envelope(raw), "0.coverage": envelope(coverage)})
    assert engine.run(snap).error == "TOO_MANY_CLAIMS"
    assert len(engine.requests) == 2


@pytest.mark.parametrize(
    "key", ["candidate_sha256", "context_sha256", "config_sha256", "inventory_sha256", "claim_id"]
)
def test_mixed_results_never_pass(replay, key):
    snap = snapshot()
    tape, inv = round_tape(snap)
    cid = inv["claims"][0]["claim_id"]
    tape["0.claim." + cid]["value"]["identity"][key] = "stale"
    assert replay(tape).run(snap).error == "STALE_OR_WRONG_BINDING"


@pytest.mark.parametrize(
    "mutation", ["pass_findings", "revise_empty", "unknown_verdict", "bad_area", "extra"]
)
def test_review_schema_combinations_are_strict(replay, mutation):
    snap = snapshot()
    tape, inv = round_tape(snap)
    row = tape["0.claim." + inv["claims"][0]["claim_id"]]["value"]
    if mutation == "pass_findings":
        row["findings"] = [finding()]
    elif mutation == "revise_empty":
        row["verdict"] = "revise"
    elif mutation == "unknown_verdict":
        row["verdict"] = "unknown"
    elif mutation == "bad_area":
        row.update(verdict="revise", findings=[{**finding(), "area": "madeup"}])
    else:
        row["advice"] = "unexpected"
    assert replay(tape).run(snap).status == "unavailable"


def test_two_distinct_findings_are_not_summarized_away(replay):
    snap = snapshot()
    tape, inv = round_tape(snap)
    for c in inv["claims"]:
        cid = c["claim_id"]
        tape["0.claim." + cid]["value"].update(
            verdict="revise", findings=[finding("Same words, different location.")]
        )
    result = replay(tape).run_round(snap, 0)
    assert result.status == "revise" and len(result.issues) == 2
    assert len({r["source"] for r in result.provenance}) == 2


def test_focus_pass_incidental_findings_retained_without_majority_vote(replay):
    snap = snapshot()
    tape, inv = round_tape(snap)
    a, b = inv["claims"]
    extra = {"claim_id": b["claim_id"], "anchors": b["anchors"], "finding": finding()}
    tape["0.claim." + a["claim_id"]]["value"]["incidental_findings"] = [extra]
    engine = replay(tape)
    conflict = engine.run_round(snap, 0)
    assert conflict.status == "unavailable" and conflict.error == "CONFLICTING_VERDICTS"
    assert conflict.issues == [finding()]
    tape["0.claim." + b["claim_id"]]["value"].update(verdict="revise", findings=[finding()])
    agree = replay(tape).run_round(snap, 0)
    assert agree.status == "revise" and agree.issues == [finding()]
    assert {r["origin"] for r in agree.provenance} == {
        "0.claim." + a["claim_id"],
        "0.claim." + b["claim_id"],
    }


@pytest.mark.parametrize("flag", ["uncovered", "uncertain"])
def test_global_incomplete_preserves_known_findings(replay, flag):
    snap = snapshot()
    tape, _ = round_tape(snap)
    tape["0.overall"]["value"].update(verdict="revise", findings=[finding()], **{flag: True})
    result = replay(tape).run(snap)
    assert result.error == "OVERALL_INCOMPLETE" and result.issues == [finding()]


def test_global_new_issue_cannot_be_canceled_by_focus_pass(replay):
    snap = snapshot()
    tape, _ = round_tape(snap)
    tape["0.overall"]["value"].update(verdict="reject", findings=[finding("Cross-claim defect.")])
    result = replay(tape).run(snap)
    assert result.status == "reject" and len(result.issues) == 1


def test_outside_inventory_incidental_does_not_spawn_new_calls(replay):
    snap = snapshot()
    tape, inv = round_tape(snap, quotes=("甲条件",))
    tape["0.overall"]["value"]["incidental_findings"] = [
        {"claim_id": "new", "anchors": [anchored(snap, "乙条件")], "finding": finding()}
    ]
    engine = replay(tape)
    result = engine.run(snap)
    assert result.error == "UNCOVERED_INCIDENTAL" and result.issues == [finding()]
    assert len(engine.requests) == 4


@pytest.mark.parametrize(
    "change,error",
    [
        ({"status": "incomplete"}, "SYNTHETIC_COMPLETION_REQUIRED"),
        ({"synthetic_only": False}, "SYNTHETIC_COMPLETION_REQUIRED"),
        ({"input_tokens": None}, "UNKNOWN_USAGE"),
        ({"output_tokens": True}, "UNKNOWN_USAGE"),
        ({"output_tokens": 9000}, "USAGE_EXCEEDED"),
    ],
)
def test_protocol_and_usage_failure_halts_without_correction(replay, change, error):
    snap = snapshot()
    tape, _ = round_tape(snap)
    tape["0.inventory"].update(change)
    engine = replay(tape)
    result = engine.run(snap)
    assert result.error == error and len(engine.requests) == 1


def test_missing_result_call_count_and_deadline_are_fail_closed(replay, monkeypatch):
    snap = snapshot()
    tape, _ = round_tape(snap)
    engine = replay(tape, max_calls=2)
    assert engine.run(snap).error == "CALL_LIMIT" and len(engine.requests) == 2
    missing = replay({})
    assert missing.run(snap).status == "unavailable" and len(missing.requests) == 1
    expired = replay(tape)
    monkeypatch.setattr(p.time, "monotonic", lambda: expired.deadline + 1)
    assert expired.run(snap).error == "DEADLINE" and not expired.requests


def test_restart_cannot_reset_canned_attempts(tmp_path):
    snap = snapshot()
    tape, _ = round_tape(snap)
    path = tmp_path / "durable.sqlite"
    engine = p.Replay(tape, path)
    assert engine.run(snap).approved
    engine.close()
    with pytest.raises(p.Invalid, match="OFFLINE_REPLAY_FORBIDDEN"):
        p.Replay(tape, path)
    with sqlite3.connect(path) as db:
        assert db.execute("select count(*) from offline_calls").fetchone() == (5,)


def test_corrected_candidate_restarts_full_inventory_and_context(replay):
    original = snapshot()
    first, inv = round_tape(original)
    first["0.claim." + inv["claims"][0]["claim_id"]]["value"].update(
        verdict="revise", findings=[finding()]
    )
    changed = p.freeze(
        "explanation",
        {"markdown": "新甲条件。新乙条件。"},
        original.data["reference_context"],
        {"profile": "synthetic-only"},
    )
    second, _ = round_tape(changed, 1, quotes=("新甲条件", "新乙条件"))
    first["0.correction"] = envelope(
        {"resource_type": "explanation", "content": changed.data["content"]}
    )
    engine = replay({**first, **second})
    assert engine.run(original).approved
    assert len(engine.requests) == 11
    assert engine.requests[6]["slot"] == "1.inventory"
    assert engine.requests[6]["candidate"] == changed.data
    assert engine.requests[6]["identity"]["candidate_sha256"] != original.candidate_sha256
    assert all(
        r["candidate"]["reference_context"] == original.data["reference_context"]
        for r in engine.requests
    )


def test_correction_limit_does_not_allow_a_third_correction(replay):
    snap = snapshot()
    tape = {}
    for n in range(3):
        one, inv = round_tape(snap, n)
        one[str(n) + ".claim." + inv["claims"][0]["claim_id"]]["value"].update(
            verdict="revise", findings=[finding()]
        )
        tape.update(one)
        if n < 2:
            tape[str(n) + ".correction"] = envelope(
                {"resource_type": "explanation", "content": snap.data["content"]}
            )
    engine = replay(tape)
    result = engine.run(snap)
    assert result.status == "reject" and result.error == "CORRECTION_LIMIT"
    assert len(engine.requests) == 17
    assert sum(r["slot"].endswith(".correction") for r in engine.requests) == 2
    assert sum(r["slot"].endswith(".inventory") for r in engine.requests) == 3


def test_no_transport_or_credentials_interface(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "MUST_NOT_BE_READ")
    with pytest.raises(p.Invalid, match="INVALID_JSON"):
        p.Replay(lambda: pytest.fail("callback invoked"), tmp_path / "reject.sqlite")
    snap = snapshot()
    tape, _ = round_tape(snap)
    with pytest.raises(TypeError):
        p.Replay(tape, tmp_path / "transport.sqlite", transport=lambda: None)
    assert b"MUST_NOT_BE_READ" not in p.encoded(tape)


def test_zero_claims_still_requires_coverage_and_overall(replay):
    snap = snapshot({"markdown": "# Title"})
    raw = {
        "version": "claim-inventory-v1",
        "claims": [],
        "exclusions": [{"block_id": snap.blocks[0]["block_id"], "reason": "Title only"}],
    }
    coverage = {
        "version": "claim-coverage-v1",
        "missing_claims": [],
        "uncertainties": [],
        "invalid_exclusions": [],
    }
    inv = p.inventory(snap, raw, coverage)
    tape = {
        "0.inventory": envelope(raw),
        "0.coverage": envelope(coverage),
        "0.overall": envelope(review(snap, inv, "__overall__", overall=True)),
    }
    engine = replay(tape)
    assert engine.run(snap).approved and len(engine.requests) == 3
    tape["0.overall"]["value"]["uncovered"] = True
    assert replay(tape).run(snap).status == "unavailable"


def test_coverage_added_claim_replaces_exclusion_but_not_other_blocks(replay):
    snap = snapshot()
    raw = {
        "version": "claim-inventory-v1",
        "claims": [],
        "exclusions": [
            {"block_id": snap.blocks[0]["block_id"], "reason": "Synthetic mistaken exclusion"}
        ],
    }
    coverage = {
        "version": "claim-coverage-v1",
        "missing_claims": [focus(snap, "甲条件"), focus(snap, "乙条件")],
        "uncertainties": [],
        "invalid_exclusions": [],
    }
    inv = p.inventory(snap, raw, coverage)
    assert inv["exclusions"] == [] and len(inv["claims"]) == 2
    tape = {
        "0.inventory": envelope(raw),
        "0.coverage": envelope(coverage),
        "0.overall": envelope(review(snap, inv, "__overall__", overall=True)),
    }
    for c in inv["claims"]:
        tape["0.claim." + c["claim_id"]] = envelope(review(snap, inv, c["claim_id"]))
    assert replay(tape).run(snap).approved


def test_worst_case_request_ceiling_is_59_not_reset_per_correction(replay):
    quotes = tuple(f"claim{i};" for i in range(16))
    snap = snapshot({"markdown": " ".join(quotes)})
    tape = {}
    for n in range(3):
        one, inv = round_tape(snap, n, quotes=quotes)
        cid = inv["claims"][0]["claim_id"]
        one[f"{n}.claim." + cid]["value"].update(verdict="revise", findings=[finding()])
        tape.update(one)
        if n < 2:
            tape[f"{n}.correction"] = envelope(
                {"resource_type": "explanation", "content": snap.data["content"]}
            )
    engine = replay(tape)
    assert engine.run(snap).error == "CORRECTION_LIMIT"
    assert len(engine.requests) == p.MAX_CALLS == 59
    limited = replay(tape, max_calls=58)
    assert limited.run(snap).error == "CALL_LIMIT" and len(limited.requests) == 58


@pytest.mark.parametrize("resource_type", ["code", "exercise"])
def test_all_resource_fields_are_visible_to_each_stage(replay, resource_type):
    snap = snapshot(
        {"source": "whole helper and caller", "answers": ["甲条件", "乙条件"]},
        resource_type=resource_type,
    )
    quotes = ("whole helper and caller", "甲条件", "乙条件")
    tape, _ = round_tape(snap, quotes=quotes)
    engine = replay(tape)
    assert engine.run(snap).approved
    assert len(engine.requests) == 6
    assert all(r["candidate"] == snap.data for r in engine.requests)


@pytest.mark.parametrize("value", [None, [], "invalid", 1])
def test_nonobject_tape_is_rejected_before_any_ledger(replay, value):
    with pytest.raises(p.Invalid, match="INVALID_TAPE"):
        replay(value)


def test_same_anchor_can_host_distinct_assertions_and_related_code_keeps_identity():
    snap = snapshot()
    base = focus(snap, "甲条件")
    second = copy.deepcopy(base)
    second["text"] = "Another interpretation of the same quoted sentence"
    assert p.claim(snap, base)["claim_id"] != p.claim(snap, second)["claim_id"]
    second["related_anchors"] = [anchored(snap, "乙条件")]
    assert p.claim(snap, second)["related_anchors"] == [anchored(snap, "乙条件")]


def test_dependency_allowlist_cannot_gain_provider_or_credentials_imports():
    import ast

    module = ast.parse(Path(p.__file__).read_text())
    allowed = {"__future__", "hashlib", "json", "math", "sqlite3", "time", "dataclasses", "pathlib"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "eval", "exec", "open"}
        for node in ast.walk(module)
    )


def test_persistent_call_count_cannot_be_reset_by_clearing_debug_records(replay):
    snap = snapshot()
    tape, _ = round_tape(snap)
    engine = replay(tape, max_calls=1)
    engine.take("0.inventory", snap, {})
    engine.requests.clear()
    with pytest.raises(p.Invalid, match="CALL_LIMIT"):
        engine.take("0.coverage", snap, {})
    assert engine.db.execute("select count(*) from offline_calls").fetchone() == (1,)


def test_corrected_resource_cannot_reuse_prior_candidate_pass_identity(replay):
    original = snapshot()
    first, old_inv = round_tape(original)
    old_cid = old_inv["claims"][0]["claim_id"]
    first["0.claim." + old_cid]["value"].update(verdict="revise", findings=[finding()])
    changed = p.freeze(
        "explanation",
        {"markdown": "新甲条件。新乙条件。"},
        original.data["reference_context"],
        {"profile": "synthetic-only"},
    )
    second, inv = round_tape(changed, 1, quotes=("新甲条件", "新乙条件"))
    new_cid = inv["claims"][0]["claim_id"]
    second["1.claim." + new_cid]["value"]["identity"] = p.binding(original, old_inv, old_cid)
    first["0.correction"] = envelope(
        {"resource_type": "explanation", "content": changed.data["content"]}
    )
    engine = replay({**first, **second})
    assert engine.run(original).error == "STALE_OR_WRONG_BINDING"
    assert engine.requests[-1]["slot"] == "1.claim." + new_cid
    assert not any(r["slot"] == "1.overall" for r in engine.requests)


@pytest.mark.parametrize("bad", [{1: "not-a-string-key"}, ("tuple",)])
def test_canonicalization_does_not_silently_coerce_non_json_types(bad):
    with pytest.raises(p.Invalid, match="INVALID_JSON"):
        p.encoded(bad)


def test_completed_response_after_whole_deadline_cannot_pass(replay, monkeypatch):
    snap = snapshot()
    tape, _ = round_tape(snap)
    clock = iter([0, 1, 31])
    monkeypatch.setattr(p.time, "monotonic", lambda: next(clock))
    engine = replay(tape, deadline_seconds=30)
    result = engine.run(snap)
    assert result.error == "DEADLINE" and len(engine.requests) == 1
