"""Zero-execution design checks; never starts Docker or executes sample code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE / "manifest.json").read_text())
    for relative, expected in manifest["documents"].items():
        assert sha(ROOT / relative) == expected, relative
    cases = json.loads((HERE / "cases.json").read_text())
    for relative, expected in cases["sources"].items():
        original = ROOT / relative
        assert len(original.read_bytes()) == expected["bytes"], relative
        assert sha(original) == expected["sha256"], relative
    tasks = {t["id"]: t for t in json.loads((ROOT / "task.json").read_text())["tasks"]}
    keys = ["id", "depends_on", "scope", "acceptance_criteria", "verification", "execution_gate"]
    for task_id, expected in manifest["task_contracts"].items():
        assert {k: tasks[task_id][k] for k in keys} == expected, task_id
    assert len(cases["matrix"]) == 6
    assert len(cases["controlled_negatives"]) == 3
    assert len(cases["environment_probes"]) == 6
    ids = [c["id"] for c in cases["matrix"] + cases["controlled_negatives"]]
    assert len(ids) == len(set(ids))
    assert cases["budgets"]["provider_calls"] == 0
    assert cases["budgets"]["automatic_retries"] == 0
    original = ROOT / "docs/reference/head-insertion-tests-20261019/edumind-r02/candidate.c"
    assert not original.read_bytes().endswith(b"\n"), "do not repair historical original"
    prep = json.loads((HERE / "environment-preparation.json").read_text())
    assert prep["sample_compilations"] == prep["sample_executions"] == 0
    assert prep["readiness"] == "not_ready"
    assert prep["requested_toolchain"]["final_image_id"] is None
    print(f"Design only: {len(manifest['documents'])} document hashes, "
          f"{len(cases['sources'])} originals, {len(manifest['task_contracts'])} task contracts; "
          "6 matrices/3 negatives/6 probes; C compilation/execution and Provider calls 0")


if __name__ == "__main__":
    main()
