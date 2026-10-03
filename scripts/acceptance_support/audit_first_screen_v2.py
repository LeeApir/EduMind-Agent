"""Independent manual decision file; all planned samples retained in final gate."""

import argparse
import json
import math
from pathlib import Path

from first_screen_v2 import assessed_metrics


def summarize(rows, metric, origin):
    values = sorted(r[origin][metric] for r in rows if metric in r[origin])
    rank = math.ceil(0.95 * len(rows))
    return {
        "observed": len(values),
        "missing": len(rows) - len(values),
        "planned_p95_ms": values[rank - 1] if rank <= len(values) else None,
        "observed_conditional_p95_ms": values[math.ceil(0.95 * len(values)) - 1]
        if values
        else None,
    }


def audit(raw, decisions):
    if len(raw["samples"]) != 20 or raw["samples_planned"] != 20:
        raise ValueError("REQUIRES_ALL_20_PLANNED_SAMPLES")
    if {s["number"] for s in raw["samples"]} != set(range(1, 21)):
        raise ValueError("REQUIRES_UNIQUE_PLANNED_IDENTITIES")
    rows = [assessed_metrics(s, decisions.get(str(s["number"]), {})) for s in raw["samples"]]
    metrics = {
        origin: {
            m: summarize(rows, m, origin)
            for m in (
                "http_first_byte",
                "http_headers_complete",
                "sse_status",
                "any_nonempty_token",
                "teaching_token",
                "teaching_paragraph",
                "published",
            )
        }
        for origin in ("client_ms", "validated_ms")
    }

    def passes(origin, name, limit):
        item = metrics[origin][name]
        return item["missing"] == 0 and item["planned_p95_ms"] <= limit

    return {
        "schema": "first-screen-wire-audit-v2",
        "raw_evidence_unchanged": True,
        "metrics": metrics,
        "reviewed_samples": rows,
        "request_failures": sum(not r["outcome_success"] for r in rows),
        "stage_gate_passed": (
            all(r["outcome_success"] and r["milestone_confirmed"] for r in rows)
            and passes("client_ms", "http_first_byte", 2000)
            and passes("validated_ms", "teaching_token", 2000)
            and passes("client_ms", "teaching_paragraph", 10000)
            and passes("validated_ms", "teaching_paragraph", 10000)
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.results.read_text()), json.loads(args.decisions.read_text()))
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
