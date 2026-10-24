"""Read-only document, redaction, pause and arithmetic checks; no execution interface."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("docs/acceptance/phase-1.5-provider-handoff-t055")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    base = ROOT / BASE
    manifest = json.loads((base / "manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        assert sha(ROOT / name) == expected, name
    for name, expected in manifest["preserved_sha256"].items():
        assert sha(ROOT / name) == expected, name
    vendor = base / "vendor"
    assert {p.name for p in vendor.iterdir()} == {
        "issue.md",
        "request.json",
        "observations.json",
        "manifest.json",
    }
    public = json.loads((vendor / "manifest.json").read_text())
    assert public["kind"] == "redacted_vendor_draft_not_sent"
    assert set(public["sha256"]) == {"issue.md", "request.json", "observations.json"}
    for name, expected in public["sha256"].items():
        assert sha(vendor / name) == expected
    # These are forbidden identifiers/locations, not a claim to detect every possible secret.
    for path in vendor.iterdir():
        text = path.read_text()
        for forbidden in (
            "/Users/",
            "/tmp/",
            "EDUMIND_",
            "PHASE-",
            "Bearer ",
            "sk-",
            "postgresql",
            "resp_",
            "msg_",
            "Authorization:",
        ):
            assert forbidden not in text, (path.name, forbidden)
    evidence = json.loads(
        (
            ROOT
            / "docs/acceptance/phase-1.5-compatibility-probe-p01-results/results.json"
        ).read_text()
    )
    obs = json.loads((vendor / "observations.json").read_text())
    assert obs["counter"]["input_tokens"] == evidence["preflight_input_tokens"] == 37
    assert obs["generation"]["reported_usage"] == evidence["provider_reported_usage"]
    assert (
        obs["instructions_summary"]["unrequested_suffix_sha256"]
        == evidence["suffix_sha256"]
    )
    assert obs["instructions_summary"]["full_suffix_omitted"] is True
    assert obs["generation"]["reported_max_output_tokens"] is None
    assert all(r["http_status"] == 200 for r in obs["requests"])
    assert all(
        r["body_sha256"] == sha(vendor / "request.json") for r in obs["requests"]
    )
    assert sha(vendor / "request.json") == sha(
        ROOT / "docs/acceptance/phase-1.5-compatibility-probe-p01/request.json"
    )
    pause = json.loads((base / "candidate-pause.json").read_text())
    assert (
        pause["status"] == "paused_by_user"
        and pause["new_real_requests_authorized"] == 0
    )
    plan = json.loads((base / "compatibility-plan.json").read_text())
    assert plan["status"] == "proposal_only_no_execution_authority"
    assert plan["preferred_candidate"]["base_url"] == "https://api.openai.com/v1"
    assert plan["preferred_candidate"]["selection_approved"] is False
    assert plan["paused_route_allowed"] is plan["runtime_adapter_available"] is False
    assert plan["new_real_requests_authorized"] == 0
    probes, limits = plan["probe_order"], plan["limits"]
    assert len(probes) == 2 and limits["candidates"] == limits["batches"] == 1
    assert (
        sum(p["count_http_max"] + p["generation_http_max"] for p in probes)
        == limits["http_requests_max"]
        == 4
    )
    assert (
        sum(p["generation_http_max"] for p in probes)
        == limits["model_requests_max"]
        == 2
    )
    assert (
        sum(p["input_reservation_max"] for p in probes)
        == limits["input_local_reservation_total"]
        == 8192
    )
    assert (
        sum(p["requested_output_max"] for p in probes)
        == limits["output_requested_total"]
        == 144
    )
    assert limits["wall_seconds_max"] == 90
    assert limits["retries"] == limits["redirects"] == limits["unbudgeted_probes"] == 0
    assert (
        plan["fee"]["approved"]
        is plan["fee"]["prior_unlimited_fee_waiver_inherited"]
        is False
    )
    for probe in probes:
        body = json.loads((base / probe["body"]).read_text())
        assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == probe["requested_output_max"]
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert all(
        plan[k] is False
        for k in (
            "course_prompt_change_allowed",
            "teaching_threshold_change_allowed",
            "H_access_allowed",
            "old_batches_restart_allowed",
            "live_commands_provided",
        )
    )
    task = json.loads((ROOT / "task.json").read_text())
    assert task["stage_scope"]["current_candidate_real_calls"] == "paused_by_user"
    assert (
        task["stage_scope"]["provider_requests_authorized"]
        == task["stage_scope"]["model_trials_authorized"]
        == 0
    )
    assert task["stage_scope"]["provider_requests_attempted"] == 6
    assert task["stage_scope"]["real_model_requests_attempted"] == 3
    assert (
        next(t for t in task["tasks"] if t["id"] == "PHASE-1.5-T038")["status"]
        == "blocked"
    )
    print(
        "T055 preparation verified: current candidate paused; vendor draft unsent; max4 HTTP/2 generation proposed, authorized0"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    check()
