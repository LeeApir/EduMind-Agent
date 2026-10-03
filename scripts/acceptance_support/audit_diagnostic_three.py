"""Non-billable independent review, no percentile or formal acceptance gate."""

import argparse
import json
from pathlib import Path

from first_screen_v2 import assessed_metrics


def audit(raw, decisions, traces):
    if len(raw["samples"]) != 3 or raw["samples_planned"] != 3:
        raise ValueError("THREE_SLOTS_REQUIRED")
    learning = [t for t in traces if t["phase"] == "learning"]
    result = {"formal_acceptance": False, "samples": []}
    for sample in raw["samples"]:
        if "candidates" not in sample:
            result["samples"].append(sample)
            continue
        measured = assessed_metrics(sample, decisions.get(str(sample["number"]), {}))
        measured["complete_user_wait_ms"] = {
            name: value + sample["anonymous_setup_ms"]
            for name, value in measured["client_ms"].items()
        }
        trace = next((t for t in learning if t["started_ns"] >= sample["started_ns"]), None)
        if trace is None:
            result["samples"].append(
                {"number": sample["number"], **measured, "stages_unconfirmed": True}
            )
            continue
        spans = {s["stage"]: s for s in trace["spans"]}
        stages = {name: s["duration_ms"] for name, s in spans.items()}
        if not all(
            name in spans
            for name in (
                "profile_extraction_merge_db",
                "profile_provider_extraction",
                "first_screen_provider_stream",
            )
        ) or "first_delta_ns" not in spans.get("first_screen_provider_stream", {}):
            result["samples"].append(
                {
                    "number": sample["number"],
                    **measured,
                    "stages_ms": stages,
                    "stages_unconfirmed": True,
                }
            )
            continue
        stages["profile_merge_db_residual"] = (
            stages["profile_extraction_merge_db"] - stages["profile_provider_extraction"]
        )
        stages["profile_pre_extraction_db"] = (
            spans["profile_provider_extraction"]["start_ns"]
            - spans["profile_extraction_merge_db"]["start_ns"]
        ) / 1e6
        stages["profile_post_extraction_merge_flush_db"] = (
            spans["profile_extraction_merge_db"]["end_ns"]
            - spans["profile_provider_extraction"]["end_ns"]
        ) / 1e6
        stream = spans["first_screen_provider_stream"]
        stages["first_screen_provider_to_first_delta"] = (
            stream["first_delta_ns"] - stream["start_ns"]
        ) / 1e6
        result["samples"].append(
            {
                "number": sample["number"],
                **measured,
                "anonymous_http_ms": sample["anonymous_http_ms"],
                "anonymous_setup_ms": sample["anonymous_setup_ms"],
                "stages_ms": stages,
                "repeated_db_spans_ms": {
                    name: [s["duration_ms"] for s in trace["spans"] if s["stage"] == name]
                    for name in ("stream_operation_read_db", "stream_operation_update_db")
                },
                "physical_connections": trace["physical_connections"],
                "checkouts": trace["checkouts"],
                "recovery_state": sample.get("recovery_state"),
                "recovery_extra_attempts": sample.get("recovery_extra_attempts"),
            }
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ("raw", "decisions", "trace", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    result = audit(*(json.loads(p.read_text()) for p in (args.raw, args.decisions, args.trace)))
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
