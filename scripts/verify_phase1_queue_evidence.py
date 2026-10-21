"""Verify complete T036 evidence without modifying original results or sample denominators."""

import hashlib
import json
import math
import platform
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "local-materials/phase-1-t036"


def read(relative):
    path = EVIDENCE / relative
    return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    fault, fault_hash = read("r01/fault-result.json")
    matrix, matrix_hash = read("matrix-r02/matrix-result.json")
    extra, extra_hash = read("fault-matrix-r01/matrix-result.json")
    publisher, publisher_hash = read("publish-fault-r01/matrix-result.json")
    assert fault["passed"] and fault["counts"] == {
        "tests": 55,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert matrix["matrix_passed"] and extra["passed"] and publisher["passed"]
    assert all(
        row["provider_requests"] == 0 for row in (fault, matrix, extra, publisher)
    )
    slots = matrix["template_slots"]
    assert len(slots) == 100 and len({row["id"] for row in slots}) == 100
    assert Counter(row["template_id"] for row in slots) == {
        "linked-list-insertion": 50,
        "linked-list-deletion": 50,
    }
    assert sum(row["ok"] for row in slots) >= 98
    cold = [row for row in slots if row["cold"]]
    assert len(cold) == 20
    values = sorted(row["ready_seconds"] if row["ok"] else math.inf for row in cold)
    assert values[18] == matrix["template_render_p95_seconds"] and values[18] <= 90
    sse = matrix["sse_slots"]
    assert len(sse) == 100 and len({row["id"] for row in sse}) == 100
    assert sum(row["id"].startswith("T036-job-sse-") for row in sse) == 50
    assert sum(row["id"].startswith("T036-classroom-sse-") for row in sse) == 50
    assert sum(row["ok"] for row in sse) >= 99
    assert len(extra["faults"]) == 7 and all(row["ok"] for row in extra["faults"])
    assert len(publisher["faults"]) == 1 and publisher["faults"][0]["ok"]
    assert publisher["faults"][0]["actual_redis_deliveries"] >= 2
    for report, relative, name in (
        (fault, "r01/protocol.json", "protocol"),
        (matrix, "matrix-r02/matrix-protocol.json", "matrix-protocol"),
        (extra, "fault-matrix-r01/fault-matrix-protocol.json", "fault-matrix-protocol"),
        (
            publisher,
            "publish-fault-r01/publish-fault-protocol.json",
            "publish-fault-protocol",
        ),
    ):
        plan, digest = read(relative)
        assert digest == report["protocol_sha256"]
        assert (
            ROOT / f"docs/acceptance/phase-1-queue-v1/{name}.json"
        ).read_bytes() == (EVIDENCE / relative).read_bytes()
        for path, expected in plan["code_sha256"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, (
                path
            )
    initial, initial_hash = read("matrix-r01/matrix-result.json")
    assert (
        not initial["passed"]
        and not initial["template_slots"]
        and not initial["sse_slots"]
    )
    hardware = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "logical_cpu": int(
            subprocess.check_output(["sysctl", "-n", "hw.ncpu"], text=True)
        ),
        "memory_bytes": int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        ),
        "concurrency": 1,
    }
    summary = {
        "task_id": "PHASE-1-T036",
        "passed": True,
        "provider_requests": 0,
        "hardware": hardware,
        "fault_tests": fault["counts"],
        "templates": {
            "denominator": 100,
            "passed": sum(row["ok"] for row in slots),
            "uncached": 20,
            "uncached_p95_seconds": values[18],
        },
        "sse": {
            "denominator": 100,
            "passed": sum(row["ok"] for row in sse),
            "job": 50,
            "classroom": 50,
            "classroom_provider": "explicit MockProvider",
        },
        "additional_actual_fault_windows": 8,
        "evidence_sha256": {
            "r01/fault-result.json": fault_hash,
            "matrix-r02/matrix-result.json": matrix_hash,
            "fault-matrix-r01/matrix-result.json": extra_hash,
            "publish-fault-r01/matrix-result.json": publisher_hash,
        },
        "prior_environment_failure": {
            "path": "matrix-r01/matrix-result.json",
            "sha256": initial_hash,
            "reason": initial["matrix_error"],
            "templates_unrun": 100,
            "sse_unrun": 100,
            "p95": "+inf",
            "qualification": "not a passed run",
        },
        "limitations": [
            "classroom speech is MockProvider; no real model quality claim",
            "supplementary media frames are not new human course signoff",
            "catalog_only stays default; no deployment or dynamic opening",
        ],
    }
    destination = EVIDENCE / "complete-evidence.json"
    assert not destination.exists(), "Never overwrite completed evidence"
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
