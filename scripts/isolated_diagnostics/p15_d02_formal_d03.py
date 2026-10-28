"""Formal d03 keeps d02 strict transport/stop rules with an independent ledger history."""

import os
from pathlib import Path

from acceptance_support.p15_diagnostic_ledger import digest
from isolated_diagnostics import p15_d02_recheck_d02 as previous
from isolated_diagnostics.p15_d02_recheck_d02 import (
    ExplorationAdapter as ExplorationAdapter,
    ExplorationLimits as ExplorationLimits,
    review_pending as review_pending,
    run_experimental_slot as run_experimental_slot,
)


class ExplorationLedger(previous.ExplorationLedger):
    def usage(self, batch):
        result = super().usage(batch)
        return {
            **result,
            "prior_requests": 30,
            "workflow_requests": 30 + result["requests"],
            "workflow_reported_input": 138390 + result["reported_all_responses_input"],
            "workflow_reported_output": 31075 + result["reported_all_responses_output"],
        }


class ExplorationJournal(previous.ExplorationJournal):
    @classmethod
    def create(cls, output, batch, package, grant, *, clock=None):
        output = Path(output)
        output.mkdir(mode=0o700, exist_ok=False)
        ledger = ExplorationLedger(output / "ledger.sqlite", clock=clock)
        try:
            ledger.start(
                batch,
                package,
                ExplorationLimits(),
                grant,
                pinned_approval_sha256=digest(grant),
            )
            j = cls(ledger, batch, package, output)
            j.record(
                "new_window",
                {
                    "deadline_epoch": grant.get("window_deadline_epoch"),
                    "old_deadline_not_extended": True,
                    "prior_requests": 30,
                },
            )
            j.record(
                "explicit_exception",
                {
                    "verified_input_bound": None,
                    "verified_output_bound": None,
                    "actual_fee_cap": None,
                    "production_admission": False,
                    "review_type": "delegated_assistant",
                },
            )
            for path in output.glob("ledger.sqlite*"):
                os.chmod(path, 0o600)
            return j
        except BaseException:
            ledger.close()
            raise
