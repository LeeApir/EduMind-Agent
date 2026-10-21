"""The preparation package cannot grant real calls or manufacture quality labels."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "binding_preparation", ROOT / "scripts/check_review_binding_preparation.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PACKAGE = module.PACKAGE


def test_current_zero_call_preparation_does_not_unblock_quality():
    value = module.check()
    assert value["preparation_valid"] and value["real_acceptance_ready"] is False
    assert value["real_calls_authorized"] == 0 and value["T040"] == "blocked"
    assert value["offline_fixed_cases"]["publication_qualified"] is False


@pytest.mark.parametrize(
    "mutation", ["calls", "ready", "threshold", "invented_label", "source_digest"]
)
def test_tampered_readiness_boundary_rejected(monkeypatch, tmp_path, mutation):
    manifest = copy.deepcopy(json.loads((PACKAGE / "manifest.json").read_bytes()))
    labels = copy.deepcopy(json.loads((PACKAGE / "labels.json").read_bytes()))
    if mutation == "calls":
        manifest["real_provider_calls_authorized"] = 1
    elif mutation == "ready":
        manifest["real_acceptance_ready"] = True
    elif mutation == "threshold":
        manifest["quality_thresholds"]["automatic_formal_success_percent"] = 94
    elif mutation == "invented_label":
        labels["diagnostic_design_cases"][0]["independent_semantic_label"] = "approved"
    else:
        manifest["files"]["backend/app/services/learning_policy.py"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "labels.json").write_text(json.dumps(labels))
    monkeypatch.setattr(module, "PACKAGE", tmp_path)
    with pytest.raises(ValueError):
        module.check()
