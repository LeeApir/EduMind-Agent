"""Exact seven synthetic bodies from the completed ADR0047 adaptation; no I/O to providers."""

import json
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as local
from scripts.isolated_diagnostics import p15_minimal_pilot as adapter

VERSION = "minimal-seven-protocol-v1"
ORDER = tuple(f"S{i}" for i in range(1, 8))
PLAN = json.loads((local.DESIGN / "compatibility-plan.json").read_text())
STAGES = {row["slot"]: row["stage"] for row in PLAN["requests"]}
ROLES = {
    name: "review" if STAGES[name].startswith("review_") else "generation"
    for name in ORDER
}
CAPS = {row["slot"]: (8192, row["max_output_tokens"]) for row in PLAN["requests"]}
LIMITS = dict(
    requests=7,
    input_reservation=57344,
    output_reservation=16896,
    fee_cap=None,
    wall_seconds=900,
    per_request_seconds=60,
    dns_seconds=9,
    request_bytes=65536,
    response_bytes=262144,
)


def bodies() -> dict[str, bytes]:
    return adapter.protocol_bodies()


def fixtures() -> dict[str, dict[str, Any]]:
    return {
        name: json.loads(json.loads(raw)["input"][1]["content"])["expected_output"]
        for name, raw in bodies().items()
    }


FIXTURES = fixtures()
INSTRUCTION = json.loads(bodies()["S1"])["input"][0]["content"]


def original_schemas() -> dict[str, dict[str, Any]]:
    return {name: local.schema_for(STAGES[name]) for name in ORDER}


def validate_local(name: str, value: dict[str, Any], body: dict[str, Any]) -> None:
    stage = STAGES[name]
    payload = json.loads(body["input"][1]["content"])
    given = payload["role_input"]
    if stage.startswith("review_"):
        binding = local.make_binding(given["artifact"])
        local.require(
            binding["targets"] == given["target_catalog"], "PROTOCOL_TARGET_BINDING"
        )
        local.validate(stage, value, binding=binding)
    elif stage.startswith("C_"):
        context = json.loads((local.DESIGN / "context-example.json").read_text())
        local.validate(stage, value, catalog=local.make_catalog(context["spec"]))
    else:
        local.validate(stage, value)
