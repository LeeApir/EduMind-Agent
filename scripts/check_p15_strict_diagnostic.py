"""Read-only T050 r03 preparation audit; no settings, credentials, process or network access."""

import argparse
import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-development-diagnostic-r03"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    manifest = json.loads((BASE / "manifest.json").read_text())
    assert manifest["status"] == "frozen_preparation_requires_new_exact_approval"
    assert manifest["batch_id"] == "p15-development-r03"
    assert manifest["candidate_count"] == 1 and manifest["model_attempts_max"] == 202
    assert (
        manifest["real_requests_authorized"] == manifest["new_real_provider_calls"] == 0
    )
    assert not (BASE / "execution-approval.json").exists()
    assert not Path("/tmp/edumind-p15-t038-r03").exists()
    assert manifest["limits"] == dict(
        requests=404,
        input_tokens=3440000,
        output_tokens=832000,
        fee_micros=None,
        wall_seconds=10800,
    )
    for name, expected in manifest["sha256"].items():
        assert sha(ROOT / name) == expected, name
    slots = manifest["slots"]
    assert len(slots) == len({s["slot_id"] for s in slots}) == 34
    assert [
        sum(s["kind"] == k for s in slots) for k in ["course", "negative", "probe"]
    ] == [12, 2, 20]
    previous = json.loads((ROOT / manifest["previous_result"]).read_text())
    assert (
        previous["batch_id"] == "p15-development-r02"
        and previous["verdict"] == "blocked_not_admitted"
    )
    assert (
        previous["http_attempts"] == manifest["cumulative_http_before_new_batch"] == 2
    )
    assert (
        previous["model_requests"] == manifest["cumulative_model_before_new_batch"] == 1
    )
    old_manifest = json.loads((ROOT / previous["package_manifest"]).read_text())
    assert sha(ROOT / previous["package_manifest"]) == previous["package_sha256"]
    assert slots == old_manifest["slots"], (
        "No changed, added or silently relabelled samples"
    )
    for name, expected in old_manifest["sha256"].items():
        assert sha(ROOT / name) == expected, name
    for raw in previous["raw_evidence"]:
        assert sha(Path(raw["path"])) == raw["sha256"]
        if raw["role"] == "ledger_snapshot":
            path = Path(raw["path"])
            assert not Path(str(path) + "-wal").exists()
            assert not Path(str(path) + "-journal").exists()
            with sqlite3.connect(
                "file:" + str(path) + "?mode=ro&immutable=1", uri=True
            ) as db:
                assert db.execute("SELECT state,reason FROM batches").fetchall() == [
                    ("stopped", "provider_contract_failure")
                ]
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "anyOf",
        "items",
        "$defs",
        "$ref",
        "description",
        "minItems",
        "maxItems",
    }

    def wire(node):
        assert isinstance(node, dict) and not set(node) - allowed
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node["properties"]) == set(node["required"])
        for key, value in node.items():
            if key in ["properties", "$defs"]:
                for child in value.values():
                    wire(child)
            elif key == "anyOf":
                for child in value:
                    wire(child)
            elif key == "items":
                wire(value)

    for stage in manifest["schema_stages"]:
        projected = json.loads((BASE / (stage + ".wire.json")).read_text())
        assert projected.get("type") == "object" and "anyOf" not in projected
        wire(projected)
        original = json.loads((BASE / (stage + ".local.json")).read_text())
        assert original != projected
        changes = json.loads((BASE / (stage + ".projection.json")).read_text())
        assert changes and all(
            c["action"]
            in [
                "local_validation",
                "annotation_only",
                "union_projection_local_oneOf",
                "equivalent_scalar_enum",
            ]
            for c in changes
        )
    verification = json.loads((BASE / "validation.json").read_text())
    passed = 0
    for run in verification["passing_runs"]:
        path = Path(run["xml"])
        assert sha(path) == run["sha256"]
        tree = ET.parse(path).getroot()
        counts = {
            k: sum(int(s.get(k, "0")) for s in tree)
            for k in ["tests", "failures", "errors", "skipped"]
        }
        assert counts == run["counts"] and counts["tests"] > 0
        assert counts["failures"] == counts["errors"] == counts["skipped"] == 0
        passed += counts["tests"]
    assert passed >= 27
    print(
        f"PASS r03 preparation: {passed} offline/PG-Mock tests; full local schemas preserved."
    )
    print(
        "New real authority 0; r02 stopped at 2 HTTP / 1 generation; no allowance inherited."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    check()


if __name__ == "__main__":
    main()
