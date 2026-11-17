"""Pure batch protocol reducer. No IO, model, credentials or synthetic execution clock."""

from copy import deepcopy
from dataclasses import dataclass, field
import math
import re
from typing import Any

from scripts.isolated_diagnostics.p15_head_insertion_engine import digest

VERSION = "pilot-batch-protocol-v1"
STAGES = {
    "B": ["pilot_baseline", "pilot_review", "pilot_baseline_repair", "pilot_review"],
    "C": [
        "pilot_plan",
        "pilot_content",
        "pilot_review",
        "pilot_repair",
        "pilot_review",
    ],
}


class BatchError(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise BatchError("BATCH_" + reason)


def initial_batch(
    grant: dict[str, Any], inputs: dict[str, Any], package: str
) -> dict[str, Any]:
    return dict(
        package_sha256=package,
        grant_sha256=digest(grant),
        status="active",
        position=0,
        deadline_epoch=grant["deadline_epoch"],
        started_epoch=grant["window_started_epoch"],
        order=[
            dict(slot_id=s["slot_id"], arm=a, kind=s["kind"])
            for s in inputs["slots"]
            for a in ("B", "C")
        ],
        pending=None,
    )


@dataclass
class BatchState:
    batch: dict[str, Any]
    calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    observed: dict[str, dict[str, Any]] = field(default_factory=dict)
    sent: set[str] = field(default_factory=set)
    metadata: set[tuple[str, str]] = field(default_factory=set)
    results: set[int] = field(default_factory=set)
    last_epoch: float = -math.inf
    initialized: bool = False
    independent_accepts: int = 0
    late_slot_observations: int = 0

    def terminal(self) -> None:
        self.batch["status"] = "stopped"
        for call in self.calls.values():
            if call["state"] in ("reserved", "sent"):
                call["state"] = "unknown"

    def advance(self) -> None:
        self.batch["position"] += 1
        self.batch["pending"] = None
        self.batch["status"] = (
            "collected"
            if self.batch["position"] == len(self.batch["order"])
            else "active"
        )

    def apply(self, event: dict[str, Any]) -> None:
        kind, p, epoch = event["kind"], event["payload"], event["epoch"]
        need(type(epoch) in (int, float) and math.isfinite(epoch), "EPOCH")
        need(type(p) is dict, "PAYLOAD")
        timely = (
            self.batch["started_epoch"] <= epoch < self.batch["deadline_epoch"]
            and epoch >= self.last_epoch
        )
        if kind == "started":
            need(not self.initialized and p == self.batch and timely, "START")
            self.initialized = True
        else:
            need(self.initialized, "MISSING_START")
            if kind == "stopped":
                need(
                    set(p) == {"reason"}
                    and type(p["reason"]) is str
                    and bool(p["reason"]),
                    "STOP",
                )
                self.terminal()
            elif kind == "reserved":
                need(
                    self.batch["status"] == "active" and timely, "RESERVE_STATE_OR_TIME"
                )
                current = self.current()
                need(
                    current["kind"] == "supported"
                    and (p["slot_id"], p["arm"])
                    == (current["slot_id"], current["arm"]),
                    "SLOT_ORDER",
                )
                need(
                    not any(c["state"] != "complete" for c in self.calls.values()),
                    "INFLIGHT",
                )
                own = [
                    c
                    for c in self.calls.values()
                    if (c["slot"], c["arm"]) == (current["slot_id"], current["arm"])
                ]
                need(
                    len(self.calls) < 90
                    and len(own) < len(STAGES[p["arm"]])
                    and p["stage"] == STAGES[p["arm"]][len(own)],
                    "STAGE_OR_LIMIT",
                )
                need(p["ticket"] == f"call-{len(self.calls):03d}", "TICKET")
                self.sha(p["request_sha256"])
                self.calls[p["ticket"]] = dict(
                    ticket=p["ticket"],
                    slot=p["slot_id"],
                    arm=p["arm"],
                    stage=p["stage"],
                    state="reserved",
                    request_sha=p["request_sha256"],
                    response_sha=None,
                    usage=None,
                )
            elif kind in (
                "target_pinned",
                "transport_kind",
                "wire_observed",
                "sent",
                "settled",
            ):
                ticket = p["ticket"]
                need(ticket in self.calls, "UNKNOWN_TICKET")
                call = self.calls[ticket]
                if kind == "sent":
                    need(
                        self.batch["status"] == "active"
                        and timely
                        and call["state"] == "reserved",
                        "SEND_STATE_OR_TIME",
                    )
                    call["state"] = "sent"
                    self.sent.add(ticket)
                elif kind == "settled":
                    need(
                        self.batch["status"] == "active"
                        and timely
                        and call["state"] == "sent",
                        "SETTLE_STATE_OR_TIME",
                    )
                    need(
                        ticket in self.observed
                        and self.observed[ticket]["response_sha256"]
                        == p["response_sha256"],
                        "SETTLE_WIRE",
                    )
                    need(
                        (ticket, "target_pinned") in self.metadata
                        and (ticket, "transport_kind") in self.metadata,
                        "SETTLE_TRANSPORT",
                    )
                    # Store JSON objects here; the SQLite adapter owns serialization.
                    call.update(
                        state="complete",
                        response_sha=p["response_sha256"],
                        usage=deepcopy(p["observation"]),
                    )
                elif kind == "wire_observed":
                    need(
                        ticket in self.sent and ticket not in self.observed,
                        "WIRE_ORDER",
                    )
                    self.sha(p["response_sha256"])
                    self.sha(p["status_sha256"])
                    self.observed[ticket] = deepcopy(p)
                else:
                    need(
                        (ticket, kind) not in self.metadata and ticket not in self.sent,
                        "TRANSPORT_METADATA_ORDER",
                    )
                    need(
                        call["state"] in ("reserved", "unknown"),
                        "TRANSPORT_METADATA_STATE",
                    )
                    if kind == "transport_kind":
                        need(p["kind"] in ("mock", "real"), "TRANSPORT_KIND")
                    else:
                        need(
                            p["hostname"]
                            == (
                                "aiapi.world"
                                if call["stage"] == "pilot_review"
                                else "api.deepseek.com"
                            ),
                            "TRANSPORT_HOST",
                        )
                    self.metadata.add((ticket, kind))
            elif kind in ("slot_result", "late_slot_result"):
                current = self.current()
                pos = self.batch["position"]
                need(
                    pos not in self.results
                    and all(p[k] == current[k] for k in ("slot_id", "arm", "kind")),
                    "RESULT_SLOT",
                )
                need(
                    p["name"] == f"slot-{pos:02d}-{current['arm']}-result.json",
                    "RESULT_NAME",
                )
                self.sha(p["result_sha256"])
                own = [
                    c
                    for c in self.calls.values()
                    if (c["slot"], c["arm"]) == (current["slot_id"], current["arm"])
                ]
                if kind == "late_slot_result":
                    need(
                        self.batch["status"] == "stopped" and not timely,
                        "LATE_RESULT_STATE",
                    )
                    self.late_slot_observations += 1
                elif p["state"] == "model_advisory_pending_assistant":
                    need(
                        self.batch["status"] == "active"
                        and timely
                        and all(c["state"] == "complete" for c in own)
                        and len(own) in ((2, 4) if current["arm"] == "B" else (3, 5))
                        and own[-1]["stage"] == "pilot_review",
                        "RESULT_CHECKPOINT",
                    )
                    self.batch.update(
                        status="awaiting_assistant",
                        pending={
                            k: deepcopy(p[k])
                            for k in ("slot_id", "arm", "kind", "name", "result_sha256")
                        },
                    )
                elif p["state"] == "refused" and current["kind"] == "refusal":
                    need(
                        self.batch["status"] == "active" and timely and not own,
                        "REFUSAL_STATE",
                    )
                    self.advance()
                else:
                    # A failed outcome is evidence, never a way to advance a stopped batch.
                    need(p["state"] in ("stopped", "refused"), "RESULT_OUTCOME")
                    self.terminal()
                self.results.add(pos)
            elif kind == "assistant_review":
                pending = self.batch["pending"]
                need(
                    self.batch["status"] == "awaiting_assistant"
                    and pending is not None,
                    "ASSISTANT_STATE",
                )
                need(
                    all(p[k] == pending[k] for k in ("slot_id", "arm", "result_sha256"))
                    and p["package_sha256"] == self.batch["package_sha256"]
                    and p["reviewer"] == "pilot_independent_evaluator"
                    and p["reviewer_type"] == "assistant",
                    "ASSISTANT_BINDING",
                )
                if p["decision"] == "accept":
                    need(timely, "ASSISTANT_TIME")
                    need(
                        set(p["checks"])
                        == {"facts", "answers", "code", "actions", "teaching"}
                        and all(v is True for v in p["checks"].values())
                        and not p["issues"],
                        "ASSISTANT_ACCEPT",
                    )
                    self.independent_accepts += 1
                    self.advance()
                else:
                    need(p["decision"] == "stop", "ASSISTANT_DECISION")
                    self.terminal()
            else:
                raise BatchError("BATCH_EVENT_KIND")
        self.last_epoch = max(self.last_epoch, float(epoch))

    def current(self) -> dict[str, Any]:
        need(0 <= self.batch["position"] < len(self.batch["order"]), "NO_CURRENT_SLOT")
        return self.batch["order"][self.batch["position"]]  # type: ignore[no-any-return]

    @staticmethod
    def sha(value: Any) -> None:
        need(
            type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "DIGEST",
        )


def reduce_batch(initial: dict[str, Any], events: list[dict[str, Any]]) -> BatchState:
    initial = deepcopy(initial)
    start, end = initial["started_epoch"], initial["deadline_epoch"]
    need(
        type(start) in (int, float)
        and type(end) in (int, float)
        and math.isfinite(start)
        and math.isfinite(end)
        and 0 < end - start <= 10800,
        "WINDOW",
    )
    need(
        initial["status"] == "active"
        and initial["position"] == 0
        and initial["pending"] is None,
        "INITIAL_STATE",
    )
    need(
        bool(initial["order"])
        and all(
            r["arm"] in STAGES and r["kind"] in ("supported", "refusal")
            for r in initial["order"]
        ),
        "ORDER",
    )
    need(
        len({(r["slot_id"], r["arm"]) for r in initial["order"]})
        == len(initial["order"]),
        "DUPLICATE_SLOT",
    )
    state = BatchState(initial)
    for event in events:
        state.apply(event)
    return state
