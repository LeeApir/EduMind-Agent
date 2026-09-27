"""Three opt-in profile contract probes; never a stage gate or retry loop."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.agents.profile_agent import (
    PROFILE_BEHAVIOR_INSTRUCTION_VERSION,
    PROFILE_INSTRUCTION_VERSION,
    ProfileAgent,
)
from app.core.config import get_provider_settings
from app.core.provider_factory import build_default_provider_gateway
from tests.resource_quality import BoundedGateway


async def run():
    gateway = BoundedGateway(build_default_provider_gateway(), limit=3, progress=True)
    agent = ProfileAgent(gateway)
    extraction = await agent.extract("我想学习单链表，请从必要的前置知识开始。")
    probes = [{"kind": "extraction", "degraded": extraction.degraded}]
    for _ in range(2):
        proposal = await agent.update_from_behavior(
            {"event_type": "quiz_attempt", "knowledge_node_id": "c-pointer",
             "score": 1.0, "correct_count": 3, "question_count": 3},
            allowed_fields=("error_preferences",),
        )
        probes.append({"kind": "behavior", "degraded": proposal.degraded,
                       "no_change": not proposal.updates})
    return {
        "model": get_provider_settings().model,
        "profile_instruction_version": PROFILE_INSTRUCTION_VERSION,
        "behavior_instruction_version": PROFILE_BEHAVIOR_INSTRUCTION_VERSION,
        "provider_calls": gateway.calls, "call_limit": 3, "retries": 0,
        "provider_attempts": gateway.attempts, "probes": probes,
        "passed": all(not item["degraded"] for item in probes),
        "stage_gate_passed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable or args.output.exists():
        parser.error("Requires billing confirmation and a new report path")
    report = asyncio.run(run())
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
