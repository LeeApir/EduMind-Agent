"""Full new high attempt-path captures; no live key, DNS, HTTP or authorization."""

# ruff: noqa: E402
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.qwen_review_budget import sha
from acceptance_support.om_diagnostic import valid_review
from app.core.provider_target import ApprovedTarget
from run_luna_admission import ExactTransport
import run_final_review_attempt as engine
from run_final_review_candidate import BASE, MATERIALS, SLOTS


async def build(root=ROOT):
    cases = json.loads((root / MATERIALS / "cases.json").read_bytes())
    requests = json.loads((root / MATERIALS / "requests.json").read_bytes())
    observed = {}
    for slot in SLOTS:
        captures = []
        authorizations = []
        wire = bytes.fromhex(requests[slot]["wire_hex"])

        def reply(request):
            captures.append(request)
            value = valid_review("unit")
            return httpx.Response(
                200,
                stream=httpx.ByteStream(
                    json.dumps(
                        dict(
                            model="gpt-6-luna",
                            status="completed",
                            output=[
                                dict(
                                    type="message",
                                    role="assistant",
                                    status="completed",
                                    content=[
                                        dict(type="output_text", text=json.dumps(value))
                                    ],
                                )
                            ],
                            usage=dict(input_tokens=100, output_tokens=100),
                        )
                    ).encode()
                ),
            )

        def transport(raw, target, auth):
            return ExactTransport(raw, target, auth, inner=httpx.MockTransport(reply))

        with (
            patch.object(engine, "credential", lambda *a: "OFFLINE_NOT_A_KEY"),
            patch.object(
                engine.ProviderTargetGuard,
                "approve_base",
                lambda self: ApprovedTarget(
                    engine.CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",)
                ),
            ),
            patch.object(engine, "ExactTransport", transport),
        ):
            outcome = await engine.perform(
                root, {}, cases[slot], wire, lambda: authorizations.append(True)
            )
        assert len(captures) == len(authorizations) == 1 and captures[0].content == wire
        assert outcome["record"]["request_digest"] == sha(wire)
        assert outcome["requested_reasoning"] == "high"
        observed[slot] = dict(
            wire_sha256=sha(wire),
            wire_bytes=len(wire),
            host=captures[0].headers["host"],
            sni=captures[0].extensions["sni_hostname"],
            url=str(captures[0].url),
            requested_effort=json.loads(wire)["reasoning"]["effort"],
            full_original_schema_validation=True,
            scripted_pass_NOT_quality=True,
        )
    plan = deepcopy(json.loads((root / MATERIALS / "plan.json").read_bytes()))
    plan.update(
        execution="new durable12-slot runner,distinct private ledger,per-result actual human gate and terminal research-batch halt",
        expires_at="2026-10-23T23:59:59+08:00",
        wall_seconds_including_human_wait=86400,
    )
    return {
        "requests.json": requests,
        "plan.json": plan,
        "execution-capture.json": observed,
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    for name, value in asyncio.run(build()).items():
        path = ROOT / BASE / name
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if a.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_text() != raw:
                raise ValueError("REFUSE_REWRITE")
            path.write_text(raw)
        else:
            assert path.read_text() == raw, name
    print(json.dumps(dict(captured=12, live_requests=0, request_authority=0)))


if __name__ == "__main__":
    main()
