"""Independent single-candidate screening, sharing an immutable frozen execution kernel."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.review_replacement import candidate_config  # noqa: E402

# Isolated module instance: never mutate the old run's globals, approval or ledger.
_spec = importlib.util.spec_from_file_location(
    "_review_replacement_frozen_kernel", ROOT / "scripts/run_evidence_v45.py"
)
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
core.BASE = "docs/acceptance/phase-1-review-replacement-r01"
core.PRIVATE = "local-materials/phase-1-review-replacement-r01"
core.RUN_ID = "review-replacement-r01"
core.REVIEW_DOCUMENT_MODULE = "prepare_review_replacement"
_kernel_load = core.load


def load(root=ROOT):
    p, a, data = _kernel_load(root)
    config = core.read(root / core.BASE / "candidate-config.json")
    proof = core.read(root / core.BASE / "token-cost-proof.json")
    core.require(
        config == candidate_config()
        and core.stable(config)
        == p["candidate_config_sha256"]
        == proof["candidate_config_sha256"]
        and p["policy_digest"] == config["policy_digest"]
        and p["review_prompt_version"] == config["review_prompt_version"]
        and core.stable(core.read(root / core.BASE / "offline-capture.json"))
        == p["offline_capture_sha256"],
        "CANDIDATE_BINDING_CHANGED",
    )
    old = core.read(root / "docs/acceptance/phase-1-evidence-v45-r01/cases.json")
    for slot, c in data.items():
        body = core.strict_json(bytes.fromhex(c["wire_hex"]))
        baseline = core.strict_json(bytes.fromhex(old[slot]["wire_hex"]))
        core.require(
            baseline["reasoning"] == {"effort": "low"}
            and body["reasoning"] == {"effort": "high"},
            "CANDIDATE_BINDING_CHANGED",
        )
        body["reasoning"] = baseline["reasoning"]
        core.require(body == baseline, "MULTIPLE_WIRE_VARIABLES_CHANGED")
        core.require(
            {k: v for k, v in c.items() if k != "wire_hex"}
            == {k: v for k, v in old[slot].items() if k != "wire_hex"},
            "MATERIAL_CHANGED",
        )
    return p, a, data


core.load = load

if __name__ == "__main__":
    core.main()
