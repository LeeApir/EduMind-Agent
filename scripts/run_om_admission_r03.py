"""Independent fixed-check-ID calibration. Same bounded transport, separate authorization."""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from run_om_admission_r02 import runtime as scope_runtime

BASE = "docs/acceptance/phase-1-om-admission-r03"
PRIVATE = "local-materials/phase-1-om-admission-r03"


def runtime():
    module = scope_runtime()
    module.BASE, module.PRIVATE = BASE, PRIVATE
    previous_manifest = module.manifest

    def manifest(proposal, root):
        result = previous_manifest(proposal, root)
        result["run_id"] = "om-admission-r03"
        return result

    module.manifest = manifest
    return module


if __name__ == "__main__":
    runtime().main()
