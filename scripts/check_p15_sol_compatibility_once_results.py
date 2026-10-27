"""Read-only exact one-shot evidence verification; never issues another request."""

# ruff: noqa: E402
import argparse
import hashlib
import json
from pathlib import Path
from run_p15_sol_compatibility_once import BASE, OUTPUT, evaluate


def inspect(output=OUTPUT):
    index = json.loads((BASE / "evidence-index.json").read_bytes())
    for name, sha in index["sha256"].items():
        p = Path(name)
        if p.parent != output or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            raise ValueError("PRIVATE_EVIDENCE_CHANGED")
    manifest_raw = (BASE / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    for name, sha in manifest["sha256"].items():
        p = (Path(__file__).resolve().parents[1] / name).resolve()
        if (
            not p.is_relative_to(Path(__file__).resolve().parents[1])
            or hashlib.sha256(p.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("FROZEN_PACKAGE_CHANGED")
    package = hashlib.sha256(manifest_raw).hexdigest()
    summary = json.loads((output / "summary.json").read_bytes())
    dispatch = json.loads((output / "dispatch.json").read_bytes())
    raw = (output / "request.json").read_bytes()
    request = json.loads(raw)
    if (
        request != json.loads((BASE / "request.json").read_bytes())
        or hashlib.sha256(raw).hexdigest() != dispatch["request_sha256"]
    ):
        raise ValueError("REQUEST_CHANGED")
    if (
        dispatch.get("url") != "https://aiapi.world/v1/responses"
        or dispatch.get("attempt") != 1
    ):
        raise ValueError("DISPATCH_CHANGED")
    if json.loads((output / "status.json").read_bytes()) != {"http_status": 200}:
        raise ValueError("HTTP_STATUS_CHANGED")
    reservation = json.loads((output / "reservation.json").read_bytes())
    auth = json.loads((BASE / "execution-authorization.json").read_bytes())
    if any(v.get("package_sha256") != package for v in [reservation, auth, summary]):
        raise ValueError("AUTHORITY_PACKAGE_CHANGED")
    response = json.loads((output / "response.json").read_bytes())
    result = evaluate(
        request, response, json.loads((BASE / "expected.json").read_bytes())
    )
    if (
        summary["outcome"] != result
        or summary["state"] != "one_synthetic_observation_only"
        or summary["dispatch_markers"] != 1
        or summary["safe_failure_code"] is not None
        or not result["synthetic_only_pass"]
        or summary["reported_usage"]
        != {
            k: response["usage"][k]
            for k in ("input_tokens", "output_tokens", "total_tokens")
        }
    ):
        raise ValueError("SYNTHETIC_RESULT_CHANGED")
    return {
        "package_sha256": package,
        "verified_single_synthetic_case": True,
        "http_requests": 1,
        "reported_usage": summary["reported_usage"],
        "reasoning_effort": response["reasoning"]["effort"],
        "reported_reasoning_tokens": result["reported_reasoning_tokens"],
        "known_suffix_observed": result["observed_known_suffix"],
        "correct_control_flagged": result["correct_control_flagged"],
        "incorrect_pointer": result["opinion"]["issues"][0]["source_pointer"],
        "workflow_requests": 7,
        "workflow_reported_input_tokens": 18521
        + summary["reported_usage"]["input_tokens"],
        "workflow_reported_output_tokens": 8103
        + summary["reported_usage"]["output_tokens"],
        "actual_fee_usd": None,
        "course_admission": False,
        "T038_completed": False,
        "nonzero_reasoning_item_seen_this_call": result["reported_reasoning_tokens"]
        > 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    result = inspect()
    if result != json.loads((BASE / "results.json").read_bytes()):
        raise ValueError("RESULT_REPORT_CHANGED")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
