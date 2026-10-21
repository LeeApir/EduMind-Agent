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
from acceptance_support.v49_routing import (
    offline_router,
    GENERATION_MODEL,
    REVIEW_MODEL,
    REVIEW_ENDPOINT,
)
from app.agents.hybrid_resource_review import review_once, REVIEW_V4_PROMPT
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.agents.planned_scene_generation import PlannedScenes, SceneCandidate
from app.services.learning_contract import canonical
from app.services.learning_policy import active_policy_digest

BASE = ROOT / "docs/acceptance/phase-1-v49-admission-r01"


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
    router, gen, _ = offline_router({})
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
    assert not gen and len(router.operation.wires) == 1
    raw = router.operation.wires[0]
    body = json.loads(raw)
    assert body["model"] == REVIEW_MODEL and body["enable_thinking"] is False
    assert body["max_completion_tokens"] == 8192 and body["temperature"] == 0
    assert router.operation.targets == [REVIEW_ENDPOINT + "/chat/completions"]
    assert (
        record["request_digest"] == sha(raw)
        and record["prompt_version"] == REVIEW_V4_PROMPT
    )
    return {
        "wire_hex": raw.hex(),
        "wire_sha256": sha(raw),
        "wire_bytes": len(raw),
        "url": router.operation.targets[0],
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
        "wire_schema_sha256": sha(
            canonical(body["response_format"]["json_schema"]["schema"])
        ),
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
    router, wires, targets = offline_router(draft)
    plan = await generate_shared_plan(router, i, CallWindow())
    assert plan == p and len(wires) == 1 and not router.operation.wires
    result = {"plan": dict(wire_hex=wires[0].hex(), target=targets[0])}
    w = PlannedScenes(
        plan,
        m["binding"],
        reference_context=m["reference_context"],
        input_snapshot=snap,
    )
    for c in m["candidates"]:
        router, wires, targets = offline_router(c["envelope"])
        with patch(
            "app.agents.planned_scene_generation.uuid4", return_value=c["resource_id"]
        ):
            staged = await w.generate(router, CallWindow(), c["role"])
        assert staged.payload() == c and len(wires) == 1 and not router.operation.wires
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
    # Whole-window + exact wire-byte extra reserve follows the prior conservative envelope.
    # Wire bytes are an additional cushion, not an asserted token count or tokenizer proof.
    slots = [
        {
            "id": n,
            "phase": "holdout" if n.startswith("holdout") else "screen",
            "request_sha256": c["wire_sha256"],
            "wire_bytes": c["wire_bytes"],
            "input_reserve_tokens": 1048576 + c["wire_bytes"],
            "output_reserve_tokens": 8202,
            "cost_micro_cny": 12 * (1048576 + c["wire_bytes"]) + 36 * 8202,
        }
        for n, c in wires.items()
    ]
    budget = {
        "version": "v49-diagnostic-budget-r01",
        "candidate_limit": 1,
        "round_limit": 1,
        "requests_max": len(slots),
        "generation_real_calls": 0,
        "review_real_calls_max": len(slots),
        "slots": slots,
        "cost_micro_cny_max": sum(s["cost_micro_cny"] for s in slots),
        "input_price_cny_per_million": 12,
        "output_price_cny_per_million": 36,
        "requested_output_limit": 8192,
        "output_usage_stop_limit": 8202,
        "per_call_timeout_seconds": 60,
        "wall_deadline_seconds": 1800,
        "authorization_expiry_local": "2026-10-21T23:59:59+08:00",
        "requests_authorized": 0,
        "fees_authorized_micro_cny": 0,
        "no_retry_no_fallback_no_correction": True,
        "scope": "12 fixed whole-unit reviews, not dynamic generation or formal T040",
        "input_bound_basis": "Official qwen 1,000,000 context (nonthinking input991808); reserve1,048,576 plus wire bytes as EXTRA cushion, not byte=token; bounded text/schema only, no tools/images/history.",
        "billing_limit": "Local worst-case reservation based on documented rates/usage cap; not provider account hard cap; no free-quota/cache assumption.",
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
            (BASE / name).write_text(raw)
        elif (BASE / name).read_text() != raw:
            raise SystemExit("FREEZE_CHANGED: " + name)
    print(
        json.dumps(
            {
                "review_requests": 12,
                "offline_generation_requests": 4,
                "offline_resource_reviews": 3,
                "cost_micro_cny_max": values["budget.json"]["cost_micro_cny_max"],
                "real_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
