"""No network: high-reasoning full diagnosis uses fixed historical slots and independent caps."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import t040_high_diagnostics as high  # noqa: E402
from acceptance_support.phase1_budget import canonical, sha  # noqa: E402


def test_full_high_plan_keeps_original_inputs_and_separates_all_four_budgets():
    bodies, plan = asyncio.run(high.proposed())
    previous = json.loads((high.prior.BASE / "requests.json").read_text())
    assert [g["requests"] for g in plan["groups"]] == [5, 5, 1, 2]
    assert plan["requested_total_calls"] == 13
    assert plan["provider_requests_authorized"] == 0 and plan["old_budget_transferred"] is False
    for slot, body in bodies.items():
        assert body["input"] == previous[slot]["input"]
        assert body["text"] == previous[slot]["text"]
        assert body["reasoning"] == {"effort": "high"} and body["max_output_tokens"] == 8192
    for group in plan["groups"]:
        assert group["timeout_seconds_per_request"] == 120
        assert group["cost_cap_micro_cny"] >= group["computed_reservation_micro_cny"]
        for slot in group["slots"]:
            assert slot["request_sha256"] == sha(canonical(bodies[slot["slot"]]))
            assert slot["output_token_upper_bound"] == 8192
    assert plan["requested_total_cost_micro_cny"] == sum(
        g["cost_cap_micro_cny"] for g in plan["groups"]
    )
    assert not plan["formal_quality_authorized"] and not plan["dsl_quality_authorized"]
    assert not plan["t041_authorized"]
