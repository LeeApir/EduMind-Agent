"""Audit original failed wire and capture a one-call normalized Schema candidate offline."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_schema_projection import (
    projection,
    schema_nodes,
    ProjectedReviewAdapter,
)
from acceptance_support.luna_review_routing import CONFIG, ExplicitRouter
from acceptance_support.luna_admission_gate import env_metadata
from acceptance_support.om_diagnostic import valid_review
from acceptance_support.qwen_review_budget import canonical, sha
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow
from app.core.provider_target import ApprovedTarget
from app.core.config import ProviderSettings
from prepare_luna_admission import candidates

PARENT = "docs/acceptance/phase-1-luna-v49-admission-r02"
BASE = "docs/acceptance/phase-1-luna-schema-validation-r01"
SLOT = "screen-complete"


def read(path):
    return json.loads(path.read_bytes())


async def build(root=ROOT):
    parent = root / PARENT
    original = read(parent / "requests.json")[SLOT]
    wire = bytes.fromhex(original["wire_hex"])
    body = json.loads(wire)
    schema = body["text"]["format"]["schema"]
    projected, changes = projection(schema)
    untyped = [
        {
            "path": list(p),
            "keywords": list(n),
            "classification": "implicit scalar type via const/enum"
            if ("const" in n or "enum" in n)
            else "reference node; no standalone type required by ordinary JSON Schema"
            if "$ref" in n
            else "union schema; no standalone type required by ordinary JSON Schema",
        }
        for p, n in schema_nodes(schema)
        if "type" not in n
    ]
    missing_after = [
        list(p)
        for p, n in schema_nodes(projected)
        if "type" not in n and ("enum" in n or "const" in n)
    ]
    case = read(parent / "cases.json")[SLOT]
    captured = []
    target = []

    def reply(request):
        captured.append(request.content)
        target.append(
            {
                "url": str(request.url),
                "host": request.headers["host"],
                "sni": request.extensions.get("sni_hostname"),
            }
        )
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                json.dumps(
                    {
                        "model": CONFIG.review_model,
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "status": "completed",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": json.dumps(valid_review("unit")),
                                    }
                                ],
                            }
                        ],
                        "usage": {"input_tokens": 100, "output_tokens": 100},
                    }
                ).encode()
            ),
        )

    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",)
        )
    )
    adapter = ProjectedReviewAdapter(
        ProviderSettings(CONFIG.review_base, "OFFLINE_ONLY", CONFIG.review_model),
        guard,
        transport=httpx.MockTransport(reply),
        reasoning_effort=CONFIG.review_reasoning,
    )

    class NoGeneration:
        async def generate_structured(self, request):
            raise ValueError("GENERATION_FORBIDDEN")

    router = ExplicitRouter(NoGeneration(), adapter)
    m = case["material"]
    record = await review_once(
        router,
        CallWindow(),
        binding=m["binding"],
        target_digest=m["unit_digest"],
        payload={"unit": m, "reference_context": m["reference_context"]},
        candidates=candidates(case),
        scope="unit",
        input_snapshot=case["input_snapshot"],
    )
    assert len(captured) == 1
    actual = captured[0]
    newbody = json.loads(actual)
    expected = deepcopy(body)
    expected["text"]["format"]["schema"] = projected
    assert (
        newbody == expected
        and record["request_digest"] == sha(actual)
        and missing_after == []
    )
    audit = {
        "version": "luna-schema-zero-call-audit-v1",
        "parent_manifest_sha256": "2cb7190424d4b6d47e9d77be4b02f2548bf913b39fc046c793c73d51be73d130",
        "original_wire_sha256": sha(wire),
        "original_full_schema_sha256": sha(canonical(schema)),
        "provider_failure": read(parent / "results/screen-complete-01.json")["details"][
            "provider_error"
        ],
        "causality": "Exact first-rejected field cannot be uniquely reconstructed from redacted error; audit proves multiple concrete untyped enum/const nodes. $ref/anyOf are not all invalid.",
        "original_untyped_nodes": untyped,
        "projection": changes,
        "remaining_untyped_scalar_enum_nodes": missing_after,
        "all_other_request_fields_unchanged": True,
        "original_business_schema_kept_for_local_validation": True,
        "production_app_source_changes": False,
        "official_reference": "https://developers.openai.com/api/docs/guides/structured-outputs",
        "provider_documentation_limit": "OpenAI official schema subset is reference only, not proof of third-party support; uniqueItems retained pending evidence, strict mode unchanged.",
        "real_calls": 0,
    }
    request = {
        "wire_hex": actual.hex(),
        "wire_sha256": sha(actual),
        "wire_bytes": len(actual),
        "target": target[0],
        "business_schema_sha256": sha(canonical(schema)),
        "wire_schema_sha256": sha(canonical(projected)),
        "profile": changes["profile"],
        "mock_result_not_quality_score": True,
        "unchanged_model": "gpt-6-luna",
        "reasoning": "low",
        "output_tokens_max": 8192,
        "timeout_seconds": 60,
    }
    plan = {
        "scope": "same failed screen-complete only; compatibility and clean-pass signal, not T040",
        "requests_max": 1,
        "retries": 0,
        "fallback": False,
        "corrections": 0,
        "per_call_timeout_seconds": 60,
        "output_limit_tokens": 8192,
        "cost_cap": None,
        "fee_policy": "user explicitly uncapped; no third-party price inferred",
        "request_authorized": False,
        "stop_after_call_regardless_of_outcome": True,
        "parent_r02": "persistently stopped; remaining11 not reused",
        "labels": "exact unchanged case/criteria reuse prior actual human confirmation; real output not presigned",
        "env_metadata": env_metadata(root / ".env"),
    }
    return {"audit.json": audit, "request.json": request, "plan.json": plan}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    values = asyncio.run(build())
    for name, value in values.items():
        path = ROOT / BASE / name
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if a.write:
            if (ROOT / BASE / "manifest.json").exists() and path.read_text() != raw:
                raise ValueError("FROZEN_PACKAGE_IMMUTABLE")
            path.write_text(raw)
        elif path.read_text() != raw:
            raise ValueError("FREEZE_CHANGED")
    print(
        json.dumps(
            {
                "untyped_nodes_before": len(
                    values["audit.json"]["original_untyped_nodes"]
                ),
                "added_explicit_string_types": len(
                    values["audit.json"]["projection"]["added_string_type_paths"]
                ),
                "retained_defs": values["audit.json"]["projection"][
                    "retained_definitions"
                ],
                "real_calls": 0,
                "new_requests_max": 1,
            }
        )
    )


if __name__ == "__main__":
    main()
