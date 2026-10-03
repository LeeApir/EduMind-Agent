"""Keep raw measurements immutable; apply explicit manual paragraph decisions separately."""

import argparse
import copy
import json
from pathlib import Path

from run_first_screen import METRICS, summarize


def audit(raw, unconfirmed):
    assert len(raw["samples"]) == raw["samples_planned"] == 20
    assert {s["number"] for s in raw["samples"]} == set(range(1, 21))
    assert set(unconfirmed).issubset(range(1, 21))
    samples = copy.deepcopy(raw["samples"])
    for sample in samples:
        if sample["number"] in unconfirmed:
            sample["validated_ms"].pop("paragraph", None)
            sample["client_ms"].pop("paragraph", None)
    metrics = {m: summarize(samples, m) for m in METRICS}
    client = copy.deepcopy(samples)
    for sample in client:
        sample["validated_ms"] = sample["client_ms"]
    client_metrics = {m: summarize(client, m) for m in METRICS}

    def passes(metric, threshold):
        result = metrics[metric]
        return result["missing"] == 0 and result["planned_p95_ms"] <= threshold

    return {
        "raw_results_unchanged": True,
        "manual_semantic_review_completed": True,
        "manual_executor": "Lee",
        "unconfirmed_paragraph_samples": sorted(unconfirmed),
        "paragraph_candidate_p95_ms_not_acceptance": raw["metrics"]["paragraph"]["planned_p95_ms"],
        "validated_metrics": metrics,
        "client_end_to_end_metrics": client_metrics,
        "first_token_gate_passed": passes("token", 2000),
        "first_teachable_paragraph_gate_passed": passes("paragraph", 10000),
        "published_failures": raw["published_failures"],
        "samples_planned": 20,
        "paragraph_unconfirmed_rate": len(unconfirmed) / 20,
        "stage_gate_passed": passes("token", 2000)
        and passes("paragraph", 10000)
        and raw["published_failures"] == 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unconfirmed-paragraphs", type=int, nargs="*", required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.results.read_text()), args.unconfirmed_paragraphs)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
