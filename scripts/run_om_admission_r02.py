"""Independent r02 composition of the frozen one-step transport; no old ledger reuse."""

# ruff: noqa: E402
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.om_admission_r02 import BASE, PRIVATE
from acceptance_support.phase1_budget import GateFailure
from app.agents.hybrid_resource_review import route_review
from app.services.learning_contract import LearningContractError


def runtime():
    # A separate module namespace: importing r02 never retargets the original r01 CLI.
    spec = importlib.util.spec_from_file_location(
        "om_admission_r02_transport", ROOT / "scripts/run_om_admission.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE, module.PRIVATE = BASE, PRIVATE
    original_manifest = module.manifest
    original_assess = module.assess
    original_classify = module.classify_failure

    def manifest(proposal, root):
        result = original_manifest(proposal, root)
        result["run_id"] = "om-admission-r02"
        return result

    async def assess(case, value, slot, root=ROOT):
        if slot != "missing-unit-objective":
            return await original_assess(case, value, slot, root)
        route = route_review(value, scope=case["scope"], catalog=case["anchors"])
        module.require(
            route["verdict"] in ("reject", "needs_human"), "CONCRETE_DEFECT_MISSED"
        )
        return {
            "route": route,
            "human_objective_coverage_check_required": True,
            "note": "No fact/difficulty category demanded for an omission; actual evidence still needs human adjudication.",
        }

    def classify(error):
        if isinstance(error, LearningContractError):
            return "INVALID_OUTPUT", "review_contract"
        if isinstance(error, GateFailure) and error.code in {
            "CONTROL_NOT_AUTO_PASS",
            "CONCRETE_DEFECT_MISSED",
            "USAGE_UNKNOWN",
            "USAGE_BOUND_EXCEEDED",
        }:
            return "INVALID_OUTPUT", "admission_or_usage"
        return original_classify(error)

    module.manifest, module.assess, module.classify_failure = manifest, assess, classify
    return module


if __name__ == "__main__":
    runtime().main()
