"""Offline verification of separately frozen quality, metrics and core components."""

import json

from catalog_acceptance_protocol import ROOT, p95, sha
from catalog_component_checks import verify_report

PROTOCOL = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v5-protocol.json"
RESULT = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v5-core.json"


def verify_components(plan, metrics, quality, core):
    assert core["provider_requests"] == 0 and core["external_attempts"] == []
    assert "fatal_error" not in core
    assert core["release_approval"] == "TEST_ONLY NOT HUMAN REVIEW"
    assert core["content_digest"] == plan["content_digest"]
    assert all(
        r["ok"] and r["worker_job_id"] == r["job_id"] for r in core["binding_probes"]
    )
    assert {r["template_id"] for r in core["binding_probes"]} == {
        "linked-list-insertion",
        "linked-list-deletion",
    }
    # Independent metrics and independent core. No modification of either raw report.
    component = {
        k: metrics[k]
        for k in (
            "provider_requests",
            "external_attempts",
            "release_approval",
            "content_digest",
            "first_screen_slots",
            "cache_slots",
            "render_slots",
        )
    }
    component["journey"] = core["journey"]
    component["summary"] = {
        "http_p95_seconds": p95(metrics["first_screen_slots"], "http_seconds", 20),
        "dom_p95_seconds": p95(metrics["first_screen_slots"], "dom_seconds", 20),
        "cache_p95_seconds": p95(metrics["cache_slots"], "click_to_play_seconds", 100),
        "render_p95_seconds": p95(metrics["render_slots"], "click_to_play_seconds", 20),
    }
    return verify_report(plan, component, quality)


def main():
    plan = json.loads(PROTOCOL.read_text())
    core = json.loads(RESULT.read_text())
    assert core["protocol_sha256"] == sha(PROTOCOL)
    for group in ("code_hashes", "protected_hashes"):
        for name, digest in plan[group].items():
            assert sha(ROOT / name) == digest, "Changed frozen/protected file: " + name
    metric = plan["metric_component"]
    quality_component = plan["quality_component"]
    for component in (metric, quality_component):
        assert sha(ROOT / component["evidence"]) == component["evidence_sha256"]
        assert sha(ROOT / component["protocol"]) == component["protocol_sha256"]
        assert all(
            sha(ROOT / name) == digest
            for name, digest in component["runtime_hashes"].items()
        )
    metrics = json.loads((ROOT / metric["evidence"]).read_text())
    quality = json.loads((ROOT / quality_component["evidence"]).read_text())
    assert metrics["protocol_sha256"] == metric["protocol_sha256"]
    assert quality["plan_sha256"] == quality_component["protocol_sha256"]
    snapshot = metric["executor_snapshot"]
    assert sha(ROOT / snapshot["path"]) == snapshot["sha256"]
    print(
        json.dumps(verify_components(plan, metrics, quality, core), ensure_ascii=False)
    )
    print("Independent catalog components verified; human release pending; Provider 0.")


if __name__ == "__main__":
    main()
