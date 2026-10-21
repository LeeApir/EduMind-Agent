"""Capture all four requests through the actual frozen execution path with MockTransport."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.luna_review_routing import CONFIG
from acceptance_support.om_diagnostic import valid_review
from app.core.provider_target import ApprovedTarget
from run_luna_admission import ExactTransport
import run_luna_schema_validation as engine
from run_luna_process_calibration import BASE, MATERIALS, SCHEMA_PARENT, SLOTS


async def build(root=ROOT):
    cases = json.loads((root / MATERIALS / "cases.json").read_bytes())
    previews = json.loads((root / MATERIALS / "request-previews.json").read_bytes())
    successful = json.loads((root / SCHEMA_PARENT / "request.json").read_bytes())
    successful_body = json.loads(bytes.fromhex(successful["wire_hex"]))
    requests = {}
    for slot in SLOTS:
        observed, authorities = [], []
        expected_wire = bytes.fromhex(previews[slot]["wire_hex"])

        def response(request):
            observed.append(
                dict(
                    wire_hex=request.content.hex(),
                    target_url=str(request.url),
                    host=request.headers["host"],
                    sni=request.extensions.get("sni_hostname"),
                )
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

        def transport(wire, target, auth):
            return ExactTransport(
                wire, target, auth, inner=httpx.MockTransport(response)
            )

        with (
            patch.object(
                engine, "credential", lambda *args: "OFFLINE_ONLY_NOT_A_REAL_KEY"
            ),
            patch.object(
                engine.ProviderTargetGuard,
                "approve_base",
                lambda self: ApprovedTarget(
                    CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",)
                ),
            ),
            patch.object(engine, "ExactTransport", transport),
        ):
            outcome = await engine.perform(
                root, {}, cases[slot], expected_wire, lambda: authorities.append(True)
            )
        assert len(observed) == len(authorities) == 1
        actual = bytes.fromhex(observed[0]["wire_hex"])
        assert actual == expected_wire
        body = json.loads(actual)
        for field in ("model", "reasoning", "max_output_tokens", "temperature", "text"):
            assert body[field] == successful_body[field]
        assert body["input"][0] == successful_body["input"][0]
        assert outcome["record"]["request_digest"] == sha(actual)
        requests[slot] = {
            **observed[0],
            "wire_sha256": sha(actual),
            "wire_bytes": len(actual),
            "policy_digest": cases[slot]["material"]["binding"]["policy_digest"],
            "material_sha256": sha(canonical(cases[slot])),
            "anchor_catalog": outcome["record"]["anchor_catalog"],
            "capture_kind": "actual perform -> review_once -> ExplicitRouter -> ProjectedReviewAdapter -> ExactTransport -> MockTransport; scripted pass NOT quality",
            "matches_confirmed_preview": True,
            "same_model_reasoning_limit_temperature_system_instruction_schema": True,
        }
    plan = {
        "kind": "criterion calibration ONLY; not independent/formal benchmark",
        "slots": list(SLOTS),
        "expected": {
            "cal-01": "pass",
            "cal-02": "pass",
            "cal-03": "needs_human",
            "cal-04": "needs_human",
        },
        "review_model": CONFIG.review_model,
        "generation_model_unchanged_not_called": CONFIG.generation_model,
        "review_base_url": CONFIG.review_base,
        "reasoning_effort": CONFIG.review_reasoning,
        "output_tokens_per_call_max": 8192,
        "output_tokens_total_max": 32768,
        "per_call_timeout_seconds": 60,
        "model_wait_total_seconds_max": 240,
        "transport_cleanup_timeout_seconds_max": 5,
        "wall_seconds_from_first_reservation_including_human_wait": 1800,
        "expires_at": "2026-10-22T23:59:59+08:00",
        "requests_max": 4,
        "requests_authorized_at_freeze": 0,
        "retries": 0,
        "fallback": False,
        "corrections": 0,
        "cost_cap": None,
        "cost_policy": "uncapped_by_explicit_user_instruction",
        "input_tokens": "unknown until provider reports; exact finite wire per slot, bytes are not tokens",
        "wire_bytes": {slot: req["wire_bytes"] for slot, req in requests.items()},
        "pause": "after EVERY result; integrity/all claims/all citations/criterion actual human signoff required before next slot",
        "stop": "any technical/criterion/assertion/citation failure, deadline, uncertain send, crash or 4-slot exhaustion; no reuse/retry",
        "severe_defect_and_new_material_checks": "not included; subsequent separately frozen/approved package only",
        "formal_T040": "not run; thresholds98/95/90 unchanged; human does not fill automatic numerator",
        "criteria_added_to_prompt": False,
    }
    return {"requests.json": requests, "plan.json": plan}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    for name, value in asyncio.run(build()).items():
        path = ROOT / BASE / name
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_text() != raw:
                raise ValueError("REFUSE_REWRITE")
            path.write_text(raw)
        else:
            assert path.read_text() == raw, name
    print(
        json.dumps(
            dict(
                captured=4,
                real_provider_requests=0,
                live_authorization=0,
                prior_stopped_runs_untouched=True,
            )
        )
    )


if __name__ == "__main__":
    main()
