"""Versioned scene repair and delegated assistant review, without human provenance claims."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from acceptance_support.p15_diagnostic_ledger import Refused, digest
from isolated_diagnostics import p15_exploration as old
from isolated_diagnostics import p15_split_provider as prior

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(
    (ROOT / "docs/acceptance/phase-1.5-split-exploration-r02/plan.json").read_bytes()
)


@dataclass(frozen=True)
class ExplorationLimits:
    requests: int = 247
    input_tokens: None = None
    output_tokens: None = None
    fee_micros: None = None
    wall_seconds: int = PLAN["limits"]["wall_seconds"]

    def validate(self):
        if self != ExplorationLimits() or not 1 <= self.wall_seconds <= 10800:
            raise Refused("REMAINING_WORKFLOW_LIMITS_CHANGED")


class ExplorationLedger(old.ExplorationLedger):
    def record(self, batch, kind, body, attempt=None):
        if kind == "human_review":
            if (
                body.get("review_type") != "delegated_assistant"
                or body.get("independent_human_truth") is not False
            ):
                raise Refused("DELEGATED_ASSISTANT_PROVENANCE_REQUIRED")
            kind = "assistant_review"
        return super().record(batch, kind, body, attempt)

    def guard(self, batch, package):
        if self.clock()[0] >= PLAN["workflow_deadline_epoch"]:
            self.stop(batch, "SHARED_WORKFLOW_WALL_LIMIT")
            raise Refused("SHARED_WORKFLOW_WALL_LIMIT")
        return super().guard(batch, package)

    def usage(self, batch):
        result = super().usage(batch)
        return {
            **result,
            "prior_requests": 3,
            "workflow_requests": 3 + result["requests"],
            "workflow_reported_input_tokens": 10455 + result["input_tokens"],
            "workflow_reported_output_tokens": 5465 + result["output_tokens"],
        }


class ExplorationJournal(old.ExplorationJournal):
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
            journal = cls(ledger, batch, package, output)
            journal.record(
                "workflow_continuation",
                {
                    "prior_batch": "p15-split-experiment-r01",
                    "prior_requests": 3,
                    "new_requests_max": 247,
                    "workflow_requests_max": 250,
                    "workflow_deadline_epoch": PLAN["workflow_deadline_epoch"],
                    "prior_failure_preserved": True,
                    "new_configuration": "free-scene-generation-v2",
                    "review_type": "delegated_assistant",
                    "independent_human_truth": False,
                },
            )
            for path in output.glob("ledger.sqlite*"):
                os.chmod(path, 0o600)
            return journal
        except BaseException:
            ledger.close()
            raise


class ExplorationAdapter(old.ExplorationAdapter):
    async def send(self, identity, request, *, retry_safe):
        if request.stage in self.policy_data["stages"]:
            role = self.policy_data["stages"][request.stage]["provider"]
            sent = sum(
                v["provider"] == role
                for v in self.journal.events("live_dispatch_reserved")
            )
            if sent >= (179 if role == "generation" else 68):
                raise Refused("SHARED_ROLE_REQUEST_LIMIT")
        return await super().send(identity, request, retry_safe=retry_safe)


class SplitExecution(prior.SplitExecution):
    def events(self, kind):
        return super().events("assistant_review" if kind == "human_review" else kind)

    def review(self, report):
        if (
            report.get("review_type") != "delegated_assistant"
            or report.get("independent_human_truth") is not False
            or report.get("reviewer") != "Codex assistant"
        ):
            raise Refused("DELEGATED_ASSISTANT_PROVENANCE_REQUIRED")
        outputs = self.events("slot_output")
        if outputs:
            value = json.loads(
                (self.output / (outputs[-1]["slot_id"] + ".json")).read_bytes()
            )
            if value.get("engineering_pass") is not True:
                raise Refused("ENGINEERING_FAILURE_CANNOT_BE_REVIEWED_AS_SUCCESS")
        return super().review(report)


run_experimental_slot = old.run_experimental_slot
