"""Exactly one original distributed-low wire with the observed isolated executor."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "docs/acceptance/phase-1-distributed-diagnostic-r01"
PRIVATE = "local-materials/phase-1-distributed-diagnostic-r01"
SLOT = "trace-distributed:candidate"


def runtime():
    # Separate module globals: do not retarget either old comparison entry point.
    spec = importlib.util.spec_from_file_location(
        "distributed_single_transport", ROOT / "scripts/run_review_config_observed.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE, module.PRIVATE = BASE, PRIVATE
    module.REQUESTS, module.SLOT_IDS = 1, (SLOT,)
    module.RUN_ID = "distributed-single-r01"
    module.REVIEW_DOCUMENT_MODULE = "prepare_distributed_diagnostic"
    return module


if __name__ == "__main__":
    runtime().main()
