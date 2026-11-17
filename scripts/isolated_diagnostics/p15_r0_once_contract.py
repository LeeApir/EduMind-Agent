"""Independent R0 request; source proposal and mechanical semantics remain frozen."""

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/acceptance/phase-1.5-separated-validation-r01"
VERSION = "r0-once-diagnostic-v1"
ORDER = ("R0",)
ROLES = {"R0": "generation"}
LIMITS = dict(
    requests=1, input_reservation=8192, output_reservation=4096, fee_cap=None,
    wall_seconds=120, per_request_seconds=60, dns_seconds=9,
    request_bytes=65536, response_bytes=262144,
)


def bodies() -> dict[str, bytes]:
    return {"R0": (SOURCE / "R0.json").read_bytes()}


def policy_requests() -> list[dict[str, Any]]:
    return [dict(name="R0", task_kind="repair", url="https://api.deepseek.com/responses",
                 model="deepseek-flash", reasoning="none", input_reservation=8192,
                 max_output_tokens=4096)]
