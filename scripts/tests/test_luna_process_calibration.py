"""Offline invariants for four calibration drafts; no semantic quality claims."""

import asyncio
import json
from pathlib import Path
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_luna_process_calibration as prep
from acceptance_support.qwen_review_budget import canonical, sha


@pytest.fixture(scope="module")
def built():
    # Any accidental DNS use, including normal HTTP transport, must fail.
    original = socket.getaddrinfo
    try:
        def denied(*args, **kwargs):
            raise AssertionError("NETWORK_FORBIDDEN")
        socket.getaddrinfo = denied
        return asyncio.run(prep.build())
    finally:
        socket.getaddrinfo = original


def visible(case):
    return {c["role"]: c["envelope"]["content"] for c in case["material"]["candidates"]}


def test_exact_reproduction_and_no_presigned_results(built):
    cases, requests, labels = built
    assert cases == json.loads((prep.BASE / "cases.json").read_text())
    assert requests == json.loads((prep.BASE / "request-previews.json").read_text())
    assert labels == json.loads((prep.BASE / "proposed-labels.json").read_text())["labels"]
    assert [label["proposed_verdict"] for label in labels] == ["pass", "pass", "needs_human", "needs_human"]
    for label in labels:
        assert label["independent_human_status"] == "pending"
        assert label["actual_model_result"] is None
        assert label["material_sha256"] == sha(canonical(cases[label["id"]]))


def test_minimal_contrasts_and_process_questions(built):
    cases, _, _ = built
    a, b, c, d = (visible(cases[f"cal-0{n}"]) for n in range(1, 5))
    assert len({v["code"]["source"] for v in [a, b, c, d]}) == 1
    assert a["exercise"] == b["exercise"]
    for i in range(3):
        for field in ("id", "question", "answer"):
            assert a["exercise"]["items"][i][field] == c["exercise"]["items"][i][field]
    assert a["code"] == d["code"] and a["explanation"] == d["explanation"]
    assert "逐轮推演" in a["exercise"]["items"][0]["question"]
    assert "第一次条件检查失败" in a["exercise"]["items"][1]["question"]
    # Missing teaching must not accidentally be supplied in worked answers.
    ctext = json.dumps(c, ensure_ascii=False)
    for trace in ("s=3", "s=11", "s=15", "i=3", "3<3为假"):
        assert trace not in ctext
    assert "开始s=0" in a["explanation"]["markdown"]
    assert "s=11" in b["code"]["key_steps"][0]
    assert "不执行a[3]" in b["exercise"]["items"][1]["explanation"]


def test_configuration_instruction_schema_unchanged(built):
    _, requests, _ = built
    parent = json.loads((prep.PARENT / "request.json").read_text())
    original = json.loads(bytes.fromhex(parent["wire_hex"]))
    for preview in requests.values():
        wire = bytes.fromhex(preview["wire_hex"])
        assert sha(wire) == preview["wire_sha256"]
        body = json.loads(wire)
        for field in ("model", "reasoning", "max_output_tokens", "temperature", "text"):
            assert body[field] == original[field]
        assert body["input"][0] == original["input"][0]
        assert preview["target"]["host"] == "www.cbbb.fun"
        assert preview["target"]["sni"] == "www.cbbb.fun"
        assert "derived preview" in preview["evidence_type"]


def test_old_freezes_and_stopped_results_unchanged():
    root = prep.ROOT
    for dirname in ("phase-1-luna-v49-admission-r02", "phase-1-luna-schema-validation-r01"):
        base = root / "docs/acceptance" / dirname
        manifest = json.loads((base / "manifest.json").read_text())
        for name, expected in manifest["files"].items():
            assert sha((root / name).read_bytes()) == expected, name
        summary = json.loads((base / "results/run-summary.json").read_text())
        if dirname.endswith("admission-r02"):
            assert summary["actual_http_requests"] == 1
            assert summary["run_halted"] is True
            assert summary["remaining_unsent"] == 11
        else:
            assert summary["actual_requests_this_run"] == 1
            assert summary["run_stopped"] is True
    result = json.loads((prep.PARENT / "results/run-summary.json").read_text())
    assert result["returned_verdict"] == "needs_human"
    assert result["frozen_clean_pass_criterion"] is False
