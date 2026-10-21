"""Replay frozen budget foundation tests against the isolated8202 fork, without edits."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from acceptance_support import qwen_review_budget as budget  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "_qwen_budget_foundation", ROOT / "backend/tests/test_phase1_dynamic_gate.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.FrozenBudget = budget.FrozenBudget
module.Approval = budget.Approval
# Metrics helpers deliberately retain the historical exception type; exact code/message
# assertions still run unchanged, while all budget operations use the8202 fork.
from acceptance_support.phase1_budget import GateFailure as HistoricalGateFailure  # noqa: E402

module.GateFailure = (budget.GateFailure, HistoricalGateFailure)
for name, value in vars(module).items():
    if (
        name.startswith("test_")
        or getattr(value, "_pytestfixturefunction", None) is not None
    ):
        globals()[name] = value
