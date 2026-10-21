"""One exact r04 request; separate label, budget and per-receipt human gates."""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.phase1_budget import GateFailure
from run_om_admission_r03 import runtime as prior_runtime

from app.agents.hybrid_resource_review import route_review

BASE = "docs/acceptance/phase-1-coverage-r04-admission"
PRIVATE = "local-materials/phase-1-coverage-r04-real"
SLOTS = ("trace-complete", "trace-distributed", "plan-only-gap", "assessment-gap")


def runtime():
    module = prior_runtime()
    module.BASE, module.PRIVATE = BASE, PRIVATE
    original_load, original_manifest = module.load, module.manifest
    original_classify = module.classify_failure

    def load(root=ROOT):
        p, a, data = original_load(root)
        proof = module.read(root / BASE / "token-cost-proof.json")
        module.require(
            proof.get("checked_on") == module.time.strftime("%Y-%m-%d"),
            "TERMS_RECHECK_REQUIRED",
        )
        # The readable review must match the exact data whose digests are being signed.
        from prepare_coverage_admission import review_document

        module.require(
            (root / BASE / "human-review.md").read_text()
            == review_document(
                {
                    "proposal.json": p,
                    "cases.json": data,
                }
            ),
            "HUMAN_REVIEW_CHANGED",
        )
        path = root / BASE / "labels-human.json"
        module.require(path.is_file(), "LABEL_REVIEW_REQUIRED")
        review = module.read(path)
        module.require(
            set(review)
            == {
                "proposal_sha256",
                "labels_sha256",
                "case_digests",
                "decision",
                "reviewer",
                "source_message_id",
                "user_confirmation",
            }
            and review["proposal_sha256"] == module.stable(p)
            and review["labels_sha256"] == p["labels_sha256"]
            and review["case_digests"]
            == {name: module.stable(data[name]["material"]) for name in SLOTS}
            and review["decision"] == "accept_calibration_labels"
            and review["reviewer"] == "Lee"
            and all(
                isinstance(review[k], str) and review[k].strip()
                for k in ("source_message_id", "user_confirmation")
            ),
            "LABEL_REVIEW_REQUIRED",
        )
        module.require(tuple(data) == SLOTS, "FREEZE_CHANGED")
        return p, a, data

    def manifest(p, root):
        value = original_manifest(p, root)
        value["run_id"] = "coverage-r04"
        # Bind the separate human label record into the durable run identity too.
        name = str(Path(BASE) / "labels-human.json")
        value["files"][name] = module.sha((root / name).read_bytes())
        return value

    async def assess(case, value, slot, root=ROOT):
        module.require(slot in SLOTS, "FREEZE_CHANGED")
        route = route_review(value, scope="unit", catalog=case["anchors"])
        positive = slot in SLOTS[:2]
        module.require(
            route["verdict"] == ("pass" if positive else "needs_human"),
            "COVERAGE_ROUTE_MISMATCH",
        )
        if not positive:
            module.require(
                not value["findings"] and bool(value["unresolved"]),
                "PURE_COVERAGE_FINDING_INVALID",
            )
        return {
            "route": route,
            "scope": "coverage calibration only",
            "human_concrete_detection_check_required": True,
            "semantic_detection_confirmed": False,
            "note": "Expected route alone is insufficient. Independently inspect actual "
            "states/exit or process-assessment reasoning and locations; generic "
            "uncertainty does not establish detection.",
        }

    def classify(error):
        if isinstance(error, GateFailure) and error.code in {
            "COVERAGE_ROUTE_MISMATCH",
            "PURE_COVERAGE_FINDING_INVALID",
        }:
            return "INVALID_OUTPUT", "coverage_admission"
        return original_classify(error)

    module.load, module.manifest = load, manifest
    module.assess, module.classify_failure = assess, classify
    return module


if __name__ == "__main__":
    runtime().main()
