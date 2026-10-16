"""Capture v4.4 requests from unchanged r04 student envelopes and original goal snapshots."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from acceptance_support.om_diagnostic import Capture, stable, valid_review, wire

from app.agents.hybrid_resource_review import review_once
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

ROOT = Path(__file__).resolve().parents[2]
PRIOR = "docs/acceptance/phase-1-coverage-r04-admission"
PRIOR_SHA = "91c9d5f818d1f675f22691f9e318aec89fc6f0828bb070f245c86cc1b07ea1db"
SLOTS = ("trace-complete", "trace-distributed", "plan-only-gap", "assessment-gap")


def identity(name):
    return str(uuid5(NAMESPACE_URL, "edumind:coverage-r05-v44:" + name))


def original(root=ROOT):
    base = root / PRIOR
    p = json.loads((base / "proposal.json").read_text())
    data = json.loads((base / "cases.json").read_text())
    if stable(p) != PRIOR_SHA or stable(data) != p["cases_sha256"]:
        raise ValueError("HISTORICAL_MATERIAL_CHANGED")
    for name, key in (
        ("proposed-labels.json", "labels_sha256"),
        ("token-cost-proof.json", "proof_sha256"),
    ):
        if stable(json.loads((base / name).read_text())) != p[key]:
            raise ValueError("HISTORICAL_MATERIAL_CHANGED")
    return p, data


async def build_cases(root=ROOT):
    _, seeds = original(root)
    result = {}
    for name in SLOTS:
        old = seeds[name]
        m, raw = deepcopy(old["material"]), deepcopy(old["input_snapshot"])
        if set(raw) != {"goal", "node_id", "code_language", "reference_context"}:
            raise ValueError("HISTORICAL_INPUT_SHAPE_CHANGED")
        # Explicit transport-only adapter. The original goal comes from the frozen
        # request snapshot, NEVER by reconstructing it from model plan.goal.
        snapshot = {
            "metadata": {k: raw[k] for k in ("goal", "node_id", "code_language")},
            "reference_context": raw["reference_context"],
        }
        if digest("input", "learning-input-v1", snapshot=raw) != m["binding"]["input_digest"]:
            raise ValueError("HISTORICAL_INPUT_BINDING_MISMATCH")
        binding = m["binding"]
        for k in ("owner_id", "unit_id", "operation_id", "plan_id"):
            binding[k] = identity(name + ":" + k)
        binding["input_digest"] = digest("input", "learning-input-v1", snapshot=snapshot)
        binding["policy_digest"] = active_policy_digest()
        w = PlannedScenes(
            m["plan"], binding, reference_context=m["reference_context"], input_snapshot=snapshot
        )
        for c in m["candidates"]:
            with patch(
                "app.agents.planned_scene_generation.uuid4",
                return_value=identity(name + ":" + c["role"]),
            ):
                new = w.stage(c["role"], c["envelope"])
            w.disposition(new.role, new.id, "pass")  # Authored staging, never model evidence.
        scenes = [
            {
                **s,
                "scene_id": identity(name + ":scene:" + c.role),
                "resource_id": c.id,
                "resource_digest": c.content_digest,
                "dependency_digest": c.dependency_digest,
            }
            for s, c in zip(m["scenes"], w.candidates(), strict=True)
        ]
        material = unit_material(w, scenes, assemble_actions(w.candidates()))
        capture = Capture(valid_review("unit"))
        record = await review_once(
            capture,
            CallWindow(),
            binding=binding,
            target_digest=material["unit_digest"],
            payload={"unit": material, "reference_context": w.reference_context},
            candidates=w.candidates(),
            scope="unit",
            input_snapshot=snapshot,
        )
        comparison = []
        for before, after in zip(
            old["material"]["candidates"], material["candidates"], strict=True
        ):
            if (
                before["envelope"] != after["envelope"]
                or before["content_digest"] != after["content_digest"]
            ):
                raise ValueError("STUDENT_CONTENT_CHANGED")
            comparison.append(
                {
                    "role": before["role"],
                    "envelope_sha256": stable(before["envelope"]),
                    "content_digest": before["content_digest"],
                    "unchanged": True,
                }
            )
        result[name] = {
            "wire_hex": wire(capture.requests[0]).hex(),
            "scope": "unit",
            "kind": "review",
            "material": material,
            "input_snapshot": snapshot,
            "original_input_snapshot": raw,
            "original_input_digest": old["material"]["binding"]["input_digest"],
            "anchors": record["anchor_catalog"],
            "student_content_comparison": comparison,
            "original_material_sha256": stable(old["material"]),
            "plan_unchanged": material["plan"] == old["material"]["plan"],
            "fixture_status": "SAME_AUTHORED_R04_CONTENT_NEW_INPUT_CONTRACT_NOT_HOLDOUT",
        }
    return result


def cases(root=ROOT):
    return asyncio.run(build_cases(root))
