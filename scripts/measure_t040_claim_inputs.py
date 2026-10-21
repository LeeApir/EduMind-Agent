"""Read only the eight historical diagnostic payloads; no model or formal benchmark access."""

import hashlib
import json
from pathlib import Path

from acceptance_support.claim_review_prototype import Invalid, encoded, freeze

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "docs/acceptance/phase-1-dynamic-v1/history.json"


def measure():
    cases = json.loads(HISTORY.read_text())["cases"]
    rows = []
    for case in cases:
        payload = case["payload"]
        size = len(encoded(payload))
        try:
            snap = freeze(
                payload["resource_type"],
                payload["content"],
                payload["reference_context"],
            )
            rows.append(
                {
                    "case_id": case["id"],
                    "input_bytes": size,
                    "field_blocks": len(snap.blocks),
                    "input_limit_screen": "within_limits",
                }
            )
        except Invalid as exc:
            rows.append(
                {
                    "case_id": case["id"],
                    "input_bytes": size,
                    "field_blocks": None,
                    "input_limit_screen": str(exc),
                }
            )
    return {
        "version": "claim-prototype-historical-size-v1",
        "provider_requests": 0,
        "history_sha256": hashlib.sha256(HISTORY.read_bytes()).hexdigest(),
        "case_count": len(rows),
        "observations": rows,
        "claim_counts": "NOT_MEASURED: no extraction or model calls",
        "formal_benchmark_accessed": False,
        "interpretation": "Size/block screen only; not claim coverage or factual quality.",
    }


if __name__ == "__main__":
    print(json.dumps(measure(), ensure_ascii=False, indent=2))
