"""Freeze paired v4.4 requests; no key reads, DNS, network or real approval creation."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

import httpx

from acceptance_support.om_diagnostic import Capture, inputs, stable, valid_review, wire
from acceptance_support.phase1_budget import sha
from run_review_config_comparison import BASE

from app.agents.hybrid_resource_review import review_once
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

PRIOR = "docs/acceptance/phase-1-coverage-r05"
NAMES = (
    "trace-complete",
    "trace-distributed",
    "plan-only-gap",
    "assessment-gap",
    "fact-contradiction",
    "reachable-safety",
    "gap-and-safety",
)


def read(path):
    return json.loads(path.read_text())


async def rebuild(name, old, snapshot, *, unsafe_source=None):
    material = old["material"]
    binding = deepcopy(material["binding"])

    def identity(value):
        return str(uuid5(NAMESPACE_URL, "edumind:review-config-r01:" + value))

    for key in ("owner_id", "unit_id", "operation_id", "plan_id"):
        binding[key] = identity(name + key)
    binding["input_digest"] = digest("input", "learning-input-v1", snapshot=snapshot)
    binding["policy_digest"] = active_policy_digest()
    workspace = PlannedScenes(
        material["plan"],
        binding,
        reference_context=material["reference_context"],
        input_snapshot=snapshot,
    )
    for c in material["candidates"]:
        envelope = deepcopy(c["envelope"])
        if c["role"] == "code" and unsafe_source is not None:
            envelope["content"]["source"] = unsafe_source
        with patch(
            "app.agents.planned_scene_generation.uuid4",
            return_value=identity(name + c["role"]),
        ):
            candidate = workspace.stage(c["role"], envelope)
        workspace.disposition(
            candidate.role, candidate.id, "pass"
        )  # Authored staging only.
    scenes = [
        {
            **s,
            "scene_id": identity(name + ":scene:" + c.role),
            "resource_id": c.id,
            "resource_digest": c.content_digest,
            "dependency_digest": c.dependency_digest,
        }
        for s, c in zip(material["scenes"], workspace.candidates(), strict=True)
    ]
    result = unit_material(workspace, scenes, assemble_actions(workspace.candidates()))
    capture = Capture(valid_review("unit"))
    record = await review_once(
        capture,
        CallWindow(),
        binding=binding,
        target_digest=result["unit_digest"],
        payload={"unit": result, "reference_context": workspace.reference_context},
        candidates=workspace.candidates(),
        scope="unit",
        input_snapshot=snapshot,
    )
    return {
        "material": result,
        "anchors": record["anchor_catalog"],
        "input_snapshot": snapshot,
        "wire_hex": wire(capture.requests[0]).hex(),
    }


async def materials(root=ROOT):
    frozen = read(root / PRIOR / "cases.json")
    old = read(root / "docs/acceptance/phase-1-om-admission-r03/cases.json")
    selected = {name: deepcopy(frozen[name]) for name in NAMES[:4]}
    # Recover the original bound request, never infer it from the generated plan.
    snapshot = inputs(root).snapshot()
    for name in NAMES[4:6]:
        source = old[name]
        if (
            digest("input", "learning-input-v1", snapshot=snapshot)
            != source["material"]["binding"]["input_digest"]
        ):
            raise ValueError("ORIGINAL_REQUEST_BINDING_CHANGED")
        selected[name] = await rebuild(name, source, snapshot)
        assert [c["envelope"] for c in selected[name]["material"]["candidates"]] == [
            c["envelope"] for c in source["material"]["candidates"]
        ]
    unsafe = next(
        c
        for c in old["reachable-safety"]["material"]["candidates"]
        if c["role"] == "code"
    )["envelope"]["content"]["source"]
    selected["gap-and-safety"] = await rebuild(
        "gap-and-safety",
        frozen["plan-only-gap"],
        frozen["plan-only-gap"]["input_snapshot"],
        unsafe_source=unsafe,
    )
    return selected


def review_document(data):
    lines = [
        "# v4.4 审核配置对照：实际材料与预登记判据",
        "",
        "未获真实预算/标签批准；不是正式验收或独立留出集。两臂输入/Prompt/Schema完全相同。",
        "",
    ]
    for slot, case in data.items():
        lines.extend(
            [
                f"## {slot}",
                f"类型：{case['comparison_kind']}；配置：{case['arm']}；材料：{stable(case['material'])}",
                "原始请求：" + case["input_snapshot"]["metadata"]["goal"],
                "```json",
                json.dumps(case["material"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def build(root=ROOT):
    selected = asyncio.run(materials(root))
    data, rows, slots = {}, [], []
    for name in NAMES:
        kind = (
            "positive"
            if name in NAMES[:2]
            else "pure_gap"
            if name in NAMES[2:4]
            else "fact"
            if name == "fact-contradiction"
            else "mixed"
            if name == "gap-and-safety"
            else "safety"
        )
        for arm, effort in (("candidate", "low"), ("baseline", "none")):
            case = deepcopy(selected[name])
            body = json.loads(bytes.fromhex(case["wire_hex"]))
            body["reasoning"] = {"effort": effort}
            actual = httpx.Request(
                "POST", "https://api.deepseek.com/responses", json=body
            ).content
            case.update(
                wire_hex=actual.hex(), arm=arm, comparison_kind=kind, material_id=name
            )
            slot = name + ":" + arm
            data[slot] = case
            cost = 2 * (1048576 + len(actual)) + 8 * 2048
            slots.append(
                {
                    "id": slot,
                    "wire_sha256": sha(actual),
                    "wire_bytes": len(actual),
                    "cost_micro_cny": cost,
                }
            )
            rows.append(
                {
                    "id": slot,
                    "kind": kind,
                    "expected_route": "pass"
                    if kind == "positive"
                    else "needs_human"
                    if kind == "pure_gap"
                    else "reject",
                    "human_specific_evidence_required": True,
                    "material_sha256": stable(case["material"]),
                }
            )
    labels = {
        "status": "PROPOSED_NOT_HUMAN_SIGNED",
        "rows": rows,
        "basis": "User requested five classes; original four coverage criteria retained; mixed case is new authored derivation, not a holdout.",
    }
    proof = read(root / PRIOR / "token-cost-proof.json")
    proof.update(
        scope="Independent paired review-config-r01 only; no r05 budget reuse",
        reasoning_efforts=["none", "low"],
        candidate_real_compatibility="NOT_RUN",
        source_access="2026-10-16 official CNY pricing direct read; Responses/Thinking official indexed text corroborated low and JSON Schema/total output cap; recheck before execution",
    )
    sources = deepcopy(read(root / PRIOR / "proposal.json")["sources"])
    for name, expected in sources.items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError("V44_SOURCE_BASELINE_CHANGED")
    extra = [
        "scripts/prepare_review_config_comparison.py",
        "scripts/run_review_config_comparison.py",
        "scripts/tests/test_review_config_comparison.py",
        BASE + "/README.md",
        PRIOR + "/cases.json",
        PRIOR + "/results/plan-only-gap-03.json",
        "docs/acceptance/phase-1-om-admission-r03/cases.json",
    ]
    for name in list(sources) + extra:
        sources[name] = sha((root / name).read_bytes())
    credential = (root / ".env").lstat()  # Metadata only; never read credentials here.
    if (
        not stat.S_ISREG(credential.st_mode)
        or credential.st_mode & 0o077
        or credential.st_uid != os.geteuid()
    ):
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    proposal = {
        "version": "review-config-comparison-r01",
        "execution_root": str(root.resolve()),
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "requests": 14,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "sources": sources,
        "slots": slots,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "credential_file_metadata": {
            k: getattr(credential, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "single_changed_wire_field": "reasoning.effort: none -> low",
        "real_compatibility_gate": "First candidate trace-complete, same call counts toward14; schema/anchors/check IDs then quality and human confirmation before next request",
        "semantic_success": "Requires actual evidence human review; matching route/category alone never sufficient",
    }
    return {
        "proposal.json": proposal,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = build()
    if args.write:
        directory = ROOT / BASE
        for name, value in result.items():
            content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
            path = directory / name
            if path.exists() and path.read_text() != content:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
            path.write_text(content)
        path = directory / "human-review.md"
        content = review_document(result["cases.json"])
        if path.exists() and path.read_text() != content:
            raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        path.write_text(content)
    p = result["proposal.json"]
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "requests": p["requests"],
                "cost_micro_cny": p["cost_micro_cny"],
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
