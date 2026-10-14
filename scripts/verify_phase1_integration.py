"""Read-only audit of T038 results and their immutable source; never runs a model."""

import argparse
import hashlib
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/acceptance/phase-1-integration"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(directory, name):
    return json.loads((directory / name).read_text())


def verify(directory):
    result = read(directory, "result.json")
    assert result["passed"] and result["clean_before"] and result["clean_after"]
    assert result["provider_requests"] == result["external_attempts"] == 0
    commit = result["source_commit"]

    def archived(path):
        return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)

    plan_raw = archived("docs/acceptance/phase-1-integration/protocol.json")
    assert sha(plan_raw) == result["protocol_sha256"]
    assert plan_raw == (DOCS / "protocol.json").read_bytes()
    plan = json.loads(plan_raw)
    assert plan["provider_requests_authorized"] == 0
    assert [g["file"] for g in result["backend"]] == plan["backend_files"]
    total = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for index, group in enumerate(result["backend"]):
        suites = ET.parse(directory / f"backend-{index:03}.xml").getroot()
        counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in total}
        assert (
            counts == group["counts"]
            and counts["tests"] > 0
            and group["exit_code"] == 0
        )
        for key in total:
            total[key] += counts[key]
    assert (
        total
        == result["backend_counts"]
        == {"tests": 1758, "failures": 0, "errors": 0, "skipped": 0}
    )
    assert all(command["exit_code"] == 0 for command in result["commands"])
    for path, digest in result["lock_sha256"].items():
        assert sha(archived(path)) == digest
    catalog = read(directory, "catalog-result.json")
    assert catalog["passed"] and catalog["provider_requests"] == 0
    assert catalog["external_attempts"] == []
    assert catalog["release_approval"]["state"] == "HUMAN_APPROVED"
    assert catalog["expanded_graph_nodes"] == 30
    assert catalog["journey"]["ok"] and len(catalog["journey"]["nodes"]) == 10
    assert len(catalog["journey"]["media_downloads"]) == 4
    for key in ("owner_isolation", "csrf", "dynamic_blocked", "revoked_hidden"):
        assert catalog["journey"][key]
    assert all(catalog["api_restart"].values())
    assert len(catalog["binding_probes"]) == 2
    assert all(row["ok"] for row in catalog["binding_probes"])
    screens = catalog["screen_slots"]
    assert len(screens) == 20 and all(row["ok"] for row in screens)
    assert sum(row["mode"] == "cold" for row in screens) == 10
    assert sum(row["mode"] == "warm" for row in screens) == 10
    assert len({row["node_id"] for row in screens}) == 10
    for key, limit in (("http_seconds", 2), ("dom_seconds", 10)):
        p95 = sorted(row[key] for row in screens)[18]
        assert p95 == catalog["screen_p95_seconds"][key] and p95 <= limit
    assert all(0 < row["path_load_ms"] <= 500 for row in screens)
    paths = result["path_metrics"]
    assert len(paths["slots"]) == 100 and paths["provider_requests"] == 0
    for key in ("nearest_rank_p95_ms", "nearest_rank_p99_ms"):
        assert all(0 < value <= 200 for value in paths[key].values())
    assert all(math.isfinite(row["ms"]) and row["ms"] > 0 for row in paths["slots"])
    matrix = read(directory / "queue-matrix", "matrix-result.json")
    matrix_plan_raw = archived("docs/acceptance/phase-1-integration/sse-protocol.json")
    assert sha(matrix_plan_raw) == matrix["protocol_sha256"]
    matrix_plan = json.loads(matrix_plan_raw)
    for path, digest in matrix_plan["code_sha256"].items():
        assert sha(archived(path)) == digest, path
    assert matrix["matrix_passed"] and matrix["provider_requests"] == 0
    assert len(matrix["sse_slots"]) == 100
    assert [row["id"] for row in matrix["sse_slots"]] == [
        row["id"]
        for row in matrix_plan["job_sse_slots"] + matrix_plan["classroom_sse_slots"]
    ]
    assert sum(row["ok"] for row in matrix["sse_slots"]) >= 99
    assert len(matrix["template_slots"]) == 100
    assert sum(row["ok"] for row in matrix["template_slots"]) >= 98
    assert matrix["template_render_p95_seconds"] <= 90
    audit = directory / "network-audit.txt"
    assert not audit.exists() or not audit.read_text().strip()
    return {
        "passed": True,
        "source_commit": commit,
        "backend": total,
        "screen_slots": 20,
        "path_operations": 100,
        "sse_slots": 100,
        "provider_requests": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.run_dir), indent=2))


if __name__ == "__main__":
    main()
