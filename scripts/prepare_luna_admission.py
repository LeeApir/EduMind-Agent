"""Zero-network freeze of exact v4.9 diagnostic wires and single-combination budget."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.qwen_review_budget import sha
from acceptance_support.luna_review_routing import offline_router, CONFIG
from acceptance_support.om_diagnostic import valid_review

GENERATION_MODEL, REVIEW_MODEL, REVIEW_ENDPOINT = (
    CONFIG.generation_model,
    CONFIG.review_model,
    CONFIG.review_base,
)
from app.agents.hybrid_resource_review import review_once, REVIEW_V4_PROMPT
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.agents.planned_scene_generation import PlannedScenes, SceneCandidate
from app.services.learning_contract import canonical
from app.services.learning_policy import active_policy_digest

BASE = ROOT / "docs/acceptance/phase-1-luna-v49-admission-r02"


def read(name):
    return json.loads((BASE / name).read_text())


def candidates(case):
    return tuple(
        SceneCandidate(
            c["resource_id"],
            c["role"],
            c["envelope"],
            c["content_digest"],
            c["dependency_digest"],
            tuple(c["upstream"]),
        )
        for c in case["material"]["candidates"]
    )


async def capture_review(case, *, resource=None):
    m = case["material"]
    router, gen, review_wires, targets = offline_router(
        valid_review("unit" if resource is None else "resource")
    )
    cs = candidates(case)
    scope = "unit" if resource is None else "resource"
    selected = cs if resource is None else (cs[resource],)
    payload = (
        {"unit": m, "reference_context": m["reference_context"]}
        if resource is None
        else {
            "plan": m["plan"],
            "candidate": selected[0].payload(),
            "reference_context": m["reference_context"],
        }
    )
    record = await review_once(
        router,
        CallWindow(),
        binding=m["binding"],
        target_digest=m["unit_digest"]
        if resource is None
        else selected[0].content_digest,
        payload=payload,
        candidates=selected,
        scope=scope,
        input_snapshot=case["input_snapshot"],
    )
    assert not gen and len(review_wires) == 1
    raw = review_wires[0]
    body = json.loads(raw)
    assert body["model"] == REVIEW_MODEL and body["reasoning"] == {
        "effort": CONFIG.review_reasoning
    }
    assert body["max_output_tokens"] == 8192 and body["temperature"] == 0
    assert (
        targets[0]["host"] == "www.cbbb.fun"
        and targets[0]["sni"] == "www.cbbb.fun"
        and targets[0]["url"] == "https://8.8.8.8/v1/responses"
    )
    assert (
        record["request_digest"] == sha(raw)
        and record["prompt_version"] == REVIEW_V4_PROMPT
    )
    return {
        "wire_hex": raw.hex(),
        "wire_sha256": sha(raw),
        "wire_bytes": len(raw),
        "target": targets[0],
        "scope": scope,
        "business_schema_sha256": sha(
            canonical(
                __import__(
                    "app.agents.hybrid_resource_review",
                    fromlist=["review_output_schema"],
                ).review_output_schema(
                    scope, anchor_ids=[a["anchor_id"] for a in record["anchor_catalog"]]
                )
            )
        ),
        "wire_schema_sha256": sha(canonical(body["text"]["format"]["schema"])),
        "anchor_catalog": record["anchor_catalog"],
        "policy_digest": active_policy_digest(),
        "evidence_type": "offline_http_capture_scripted_reply_NOT_quality_or_live_route_proof",
    }


async def capture_generation(case):
    snap = case["input_snapshot"]
    m = case["material"]
    p = m["plan"]
    i = PlanInputs(
        snap["metadata"],
        snap["references"],
        frozenset(snap["node_ids"]),
        snap["learner_evidence"],
        reference_context=m["reference_context"],
        teaching_context=snap["teaching_context"],
    )
    keys = (
        "objectives",
        "terminology",
        "conventions",
        "shared_example",
        "prerequisite_node_ids",
        "scenes",
    )
    draft = {k: p[k] for k in keys}
    draft["reference_ids"] = list(i.references)
    router, wires, review_wires, targets = offline_router(draft)
    plan = await generate_shared_plan(router, i, CallWindow())
    assert plan == p and len(wires) == 1 and not review_wires
    result = {"plan": dict(wire_hex=wires[0].hex(), target=targets[0])}
    w = PlannedScenes(
        plan,
        m["binding"],
        reference_context=m["reference_context"],
        input_snapshot=snap,
    )
    for c in m["candidates"]:
        router, wires, review_wires, targets = offline_router(c["envelope"])
        with patch(
            "app.agents.planned_scene_generation.uuid4", return_value=c["resource_id"]
        ):
            staged = await w.generate(router, CallWindow(), c["role"])
        assert staged.payload() == c and len(wires) == 1 and not review_wires
        w.disposition(c["role"], staged.id, "pass")  # fixture setup, not review quality
        result[c["role"]] = dict(wire_hex=wires[0].hex(), target=targets[0])
    for role, c in result.items():
        raw = bytes.fromhex(c["wire_hex"])
        body = json.loads(raw)
        assert body["model"] == GENERATION_MODEL and body["reasoning"] == {
            "effort": "none"
        }
        assert body["max_output_tokens"] == (2048 if role == "plan" else 4096)
        assert (
            c["target"]["host"] == "api.deepseek.com"
            and c["target"]["sni"] == "api.deepseek.com"
        )
        c.update(
            wire_sha256=sha(raw),
            wire_bytes=len(raw),
            evidence_type="offline_adapter_capture_NOT_live_generation",
        )
    return result


async def build():
    cases = read("cases.json")
    wires = {name: await capture_review(c) for name, c in cases.items()}
    generation = await capture_generation(cases["screen-complete"])
    resources = {
        role: await capture_review(cases["screen-complete"], resource=n)
        for n, role in enumerate(("explanation", "code", "exercise"))
    }
    slots = [
        {
            "id": n,
            "phase": "holdout" if n.startswith("holdout") else "screen",
            "request_sha256": c["wire_sha256"],
            "wire_bytes": c["wire_bytes"],
            "output_limit_tokens": 8192,
        }
        for n, c in wires.items()
    ]
    budget = {
        "version": "luna-v49-diagnostic-limits-r01",
        "candidate_limit": 1,
        "round_limit": 1,
        "requests_max": len(slots),
        "generation_real_calls": 0,
        "review_real_calls_max": len(slots),
        "slots": slots,
        "cost_cap": None,
        "cost_policy": "uncapped_by_explicit_user_instruction",
        "cost_authorization_quote": "不用考虑费用，无上限",
        "price_per_token": None,
        "billing_currency": None,
        "pricing_status": "third-party rates not supplied; no official-price substitution",
        "requested_output_limit": 8192,
        "output_usage_stop_limit": 8192,
        "per_call_timeout_seconds": 60,
        "execution_wall_deadline_seconds": 1800,
        "human_wait_does_not_extend_http_timeout": True,
        "authorization_expiry_local": "2026-10-21T23:59:59+08:00",
        "request_count_approval": "pending_exact_package",
        "requests_authorized": 0,
        "no_retry_no_fallback_no_correction": True,
        "scope": "12 fixed whole-unit reviews, not dynamic generation or formal T040",
        "stop_on_any_failure": True,
    }
    return {
        "requests.json": wires,
        "generation-route-capture.json": generation,
        "resource-route-capture.json": resources,
        "budget.json": budget,
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    values = asyncio.run(build())
    for name, value in values.items():
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if a.write:
            if (BASE / "manifest.json").exists() and (BASE / name).read_text() != raw:
                raise ValueError("FROZEN_PACKAGE_IMMUTABLE")
            (BASE / name).write_text(raw)
        elif (BASE / name).read_text() != raw:
            raise SystemExit("FREEZE_CHANGED: " + name)
    print(
        json.dumps(
            {
                "review_requests": 12,
                "offline_generation_requests": 4,
                "offline_resource_reviews": 3,
                "cost_cap": None,
                "request_count_authorized": 0,
                "real_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
