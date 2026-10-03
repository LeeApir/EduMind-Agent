"""Verify frozen fixed-denominator evidence offline; cannot launch any paid phase."""

import json

from catalog_acceptance_protocol import PROTOCOL, QUALITY, RESULT, ROOT, p95, sha


def verify_report(plan: dict, result: dict, quality: dict) -> dict:
    assert plan["provider_requests_authorized"] == result["provider_requests"] == 0
    assert result["external_attempts"] == []
    assert "fatal_error" not in result
    assert result["release_approval"] == "TEST_ONLY NOT HUMAN REVIEW"
    assert result["content_digest"] == plan["content_digest"]
    for name, expected, field in [
        ("first_screen_slots", "first_screen_slots", "id"),
        ("cache_slots", "cache_browser_slots", "id"),
        ("render_slots", "render_browser_slots", "id"),
    ]:
        assert [row[field] for row in result[name]] == [
            row[field] for row in plan[expected]
        ]
    assert [row["id"] for row in quality["slots"]] == [
        row["id"] for row in plan["quality_slots"]
    ]
    assert quality["summary"]["planned"] == 100 and len(quality["slots"]) == 100
    assert sum(row.get("ok") is True for row in quality["slots"]) / 100 >= 0.98
    assert quality["summary"]["fresh_rendered"] == 20  # Not 100 distinct real renders.
    assert all(row.get("ok") for row in result["first_screen_slots"])
    computed = {
        "http_p95_seconds": p95(result["first_screen_slots"], "http_seconds", 20),
        "dom_p95_seconds": p95(result["first_screen_slots"], "dom_seconds", 20),
        "cache_p95_seconds": p95(result["cache_slots"], "click_to_play_seconds", 100),
        "render_p95_seconds": p95(result["render_slots"], "click_to_play_seconds", 20),
    }
    assert result["summary"] == computed
    assert computed["http_p95_seconds"] != "+inf" and computed["http_p95_seconds"] <= 2
    assert computed["dom_p95_seconds"] != "+inf" and computed["dom_p95_seconds"] <= 10
    assert (
        computed["cache_p95_seconds"] != "+inf" and computed["cache_p95_seconds"] <= 2
    )
    assert (
        computed["render_p95_seconds"] != "+inf"
        and computed["render_p95_seconds"] <= 90
    )
    assert all(
        row.get("ok") and row["click_to_play_seconds"] <= 2
        for row in result["cache_slots"]
    )
    assert all(
        row.get("ok")
        and row["worker_job_id"] == row["job_id"]
        and row["http_status"] == 202
        for row in result["render_slots"]
    )
    journey = result["journey"]
    assert journey["ok"] and len(journey["nodes"]) == 10
    assert {row["node_id"] for row in journey["nodes"]} == {
        s["node_id"] for s in plan["first_screen_slots"]
    }
    assert sum(row["resources"] for row in journey["nodes"]) == 30
    assert sum(row["questions"] for row in journey["nodes"]) == 30
    assert all(
        row["mastery_repeat_unchanged"]
        and row["restore"]
        and row["preset_restore"]
        and row["notes"]
        and row["path"]
        for row in journey["nodes"]
    )
    assert len(journey["media_downloads"]) == 4
    assert all(
        journey[key] is True
        for key in ("owner_isolation", "csrf", "dynamic_blocked", "revoked_hidden")
    )
    return computed


def main() -> None:
    plan = json.loads(PROTOCOL.read_text())
    result = json.loads(RESULT.read_text())
    quality = json.loads(QUALITY.read_text())
    assert result["protocol_sha256"] == sha(PROTOCOL)
    component = plan["quality_component"]
    assert quality["plan_sha256"] == component["protocol_sha256"]
    assert sha(QUALITY) == component["evidence_sha256"]
    assert sha(ROOT / component["protocol"]) == component["protocol_sha256"]
    assert all(
        sha(ROOT / name) == digest
        for name, digest in component["runtime_hashes"].items()
    )
    for group in ("code_hashes", "protected_hashes"):
        for name, digest in plan[group].items():
            assert sha(ROOT / name) == digest, "Changed protected/frozen file: " + name
    print(json.dumps(verify_report(plan, result, quality), ensure_ascii=False))
    print(
        "Engineering evidence verified; human content release still pending. Provider 0."
    )


if __name__ == "__main__":
    main()
