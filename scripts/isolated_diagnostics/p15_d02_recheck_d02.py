"""Narrow D02 recheck: existing strict wire protocol, independent smaller ledger."""

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from acceptance_support.p15_diagnostic_ledger import Refused, digest
from app.services.free_course_scheduler import SendPolicy
from isolated_diagnostics import p15_d02_wire_d02 as old
from isolated_diagnostics import p15_split_provider as source
from isolated_diagnostics.p15_d02_slot_d02 import run_slot


@dataclass(frozen=True)
class ExplorationLimits:
    requests: int = 5
    input_tokens: None = None
    output_tokens: None = None
    fee_micros: None = None
    wall_seconds: int = 1800

    def validate(self):
        if self != ExplorationLimits():
            raise Refused("D02_LIMITS_CHANGED")


class ExplorationLedger(old.ExplorationLedger):
    def usage(self, batch):
        result = super().usage(batch)
        return {
            **result,
            "prior_requests": 29,
            "workflow_requests": 29 + result["requests"],
            "workflow_reported_input": 136424 + result["reported_all_responses_input"],
            "workflow_reported_output": 30410 + result["reported_all_responses_output"],
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
            j = cls(ledger, batch, package, output)
            j.record(
                "new_window",
                {
                    "deadline_epoch": grant.get("window_deadline_epoch"),
                    "old_deadline_not_extended": True,
                    "prior_requests": 29,
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

    def record(self, kind, body):
        # Called inside the inherited dispatch reservation lock, before mark_sent/HTTP.
        if kind == "live_dispatch_reserved":
            role = body.get("provider")
            identity = body.get("identity", {})
            count = sum(v["provider"] == role for v in self.events(kind))
            if (
                role not in ("generation", "review")
                or identity.get("slot_id")
                != ("D02-known" if role == "generation" else "D02-known:scene-review")
                or count >= (3 if role == "generation" else 2)
                or body.get("stage")
                not in (
                    "free_course_plan_generation",
                    "free_scene_generation",
                    "development_scene_review",
                )
            ):
                raise Refused("D02_ROLE_SCOPE_OR_LIMIT")
        return super().record(kind, body)


class ExplorationAdapter(old.ExplorationAdapter):
    def bound(self, identity):
        self.journal.bind(identity)
        outer = self

        class Bound(ExplorationAdapter):
            policy = SendPolicy(
                package_id=outer.journal.batch,
                requests=5,
                bounded_output_verified=False,
            )

            async def send(self, request, *, retry_safe):
                return await outer.send(identity, request, retry_safe=retry_safe)

            def input_upper_bound(self, request):
                raise Refused("NO_VERIFIED_INPUT_BOUND")

        return Bound.__new__(Bound)

    async def send(self, identity, request, *, retry_safe):
        if request.stage not in (
            "free_course_plan_generation",
            "free_scene_generation",
            "development_scene_review",
        ):
            raise Refused("D02_STAGE_ONLY")
        return await super().send(identity, request, retry_safe=retry_safe)


review_pending = old.review_pending


async def run_experimental_slot(slot, sessions, adapter):
    if slot["slot_id"] != "D02-known" or slot["kind"] != "course":
        raise Refused("D02_KNOWN_ONLY")
    j = adapter.journal
    identity = source.Identity(
        slot["slot_id"],
        str(uuid5(NAMESPACE_URL, j.batch + "/" + slot["slot_id"])),
        "EXPERIMENT_PENDING_COURSE",
    )
    j.bind(identity)
    result = await run_slot(
        slot, sessions, adapter.bound(identity), j.ledger, j.batch, j.package
    )
    plans = result["tables"].get("free_course_plans", [])
    if not result["engineering_pass"] or not plans:
        return result
    actual = source.Identity(
        identity.slot_id + ":scene-review",
        identity.owner_id,
        str(plans[0]["course_id"]),
    )
    j.bind(actual)
    targets = await source.load_targets(sessions, actual)
    if len(targets) != 2:
        raise Refused("EXACT_TWO_SCENES_REQUIRED")
    j.freeze(actual, targets)
    # Export persisted reports as separate local evidence; do not prime the reviewer.
    validations = result["tables"].get("free_course_scene_validations", [])
    if len(validations) != 2 or any(
        v["rule_version"] != "free-scene-hard-gate-v4" or len(v["findings"]) != 1
        for v in validations
    ):
        raise Refused("EXACT_TWO_V4_CONSISTENCY_AUDITS_REQUIRED")
    for v in validations:
        report = v["findings"][0]["report"]
        j.record(
            "consistency_observation",
            {
                "validation_id": str(v["id"]),
                "raw_digest": v["raw_digest"],
                "generation_result_id": str(v["generation_result_id"]),
                "report_sha256": digest(report),
                "report": report,
            },
        )

    async def current(target):
        return target in await source.load_targets(sessions, actual)

    state = await review_pending(adapter, actual, verify_current=current)
    return {
        **result,
        "scene_review_identity": actual.packed(),
        "scene_source_hashes": [v["payload"]["source_sha256"] for v in targets],
        "scene_review_state_at_first_observation": state,
        "experimental_unbounded_admission": True,
        "production_bound_evidence": False,
    }
