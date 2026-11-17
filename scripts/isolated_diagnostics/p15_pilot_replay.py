"""Replay frozen B/C control flow against recorded bytes only. No transport or keys."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast

from app.services.provider_gateway import StructuredRequest, StructuredResult
from scripts.isolated_diagnostics import p15_agent_pilot as c
from scripts.isolated_diagnostics import p15_pilot_execution as e
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical


async def replay(
    output: Path,
    slot: dict[str, Any],
    arm: str,
    calls: list[Any],
    result: dict[str, Any],
    batch: dict[str, Any],
    events: list[Any],
    read: Callable[[Path], bytes],
) -> tuple[dict[str, Any], bool]:
    state: dict[str, Any] = dict(
        position=0, expired=False, postcheck_then_expire=False, unverified_reason=False
    )
    deadline = 1000000.0
    # The durable slot_result event carries the time of the recorded outcome.
    result_time = next(
        (
            row["epoch"]
            for row in events
            if row["kind"] in ("slot_result", "late_slot_result")
            and wire.strict_json(row["payload"])["slot_id"] == slot["slot_id"]
            and wire.strict_json(row["payload"])["arm"] == arm
        ),
        None,
    )
    late_outcome = result_time is not None and result_time >= batch["deadline_epoch"]
    if result.get("reason") == "BUDGET_OR_DEADLINE" and not calls:
        if not late_outcome:
            raise c.PilotError("UNSUPPORTED_REPLAY_TIME_STOP")
        state["expired"] = True

    def clock() -> float:
        if state["postcheck_then_expire"]:
            state["postcheck_then_expire"] = False
            state["expired"] = True
            return 0.0
        return deadline if state["expired"] else 0.0

    class ReplyAdapter:
        def __init__(self, role: str):
            self.role = role

        async def generate_structured(
            self, request: StructuredRequest
        ) -> StructuredResult:
            index = state["position"]
            if index >= len(calls):
                raise c.PilotError("UNRECORDED_REPLAY_DISPATCH")
            row = calls[index]
            body = wire.strict_json(read(output / (row["ticket"] + "-request.json")))
            expected = wire.request_body(request, self.role)
            if row["stage"] != request.stage or canonical(body) != canonical(expected):
                state["request_mismatch"] = True
                raise c.PilotError("COMPLETE_REQUEST_REPLAY_MISMATCH")
            state["position"] += 1
            status_path = output / (row["ticket"] + "-status.json")
            response_path = output / (row["ticket"] + "-response.json")
            if row["state"] == "complete":
                reply, _ = wire.validate(body, read(response_path), self.role)
                if index + 1 == len(calls) and result.get("reason") in (
                    "DEADLINE_AFTER_RESPONSE",
                    "BUDGET_OR_DEADLINE",
                ):
                    if not late_outcome:
                        raise c.PilotError("UNSUPPORTED_REPLAY_TIME_STOP")
                    if result["reason"] == "DEADLINE_AFTER_RESPONSE":
                        state["expired"] = True
                    else:
                        state["postcheck_then_expire"] = True
                return reply
            # Unknown calls can never produce a model reply, success or another dispatch.
            if result["state"] != "stopped" or index + 1 != len(calls):
                raise c.PilotError("UNKNOWN_CANNOT_ADVANCE")
            if (
                status_path.exists()
                and wire.strict_json(read(status_path))["http_status"] != 200
            ):
                raise c.PilotError("HTTP_STATUS")
            if response_path.exists():
                # Reproduce the exact schema/protocol rejection when bytes are available.
                wire.validate(body, read(response_path), self.role)
                late = [
                    row
                    for row in events
                    if row["kind"] == "stopped"
                    and wire.strict_json(row["payload"]).get("reason") == "LATE_REPLY"
                ]
                if late and any(
                    row["epoch"] >= batch["deadline_epoch"] for row in late
                ):
                    raise c.PilotError("LATE_REPLY")
            state["unverified_reason"] = True
            reason = result.get("reason")
            if reason in (
                "SECRET_ECHO_REFUSED",
                "RESPONSE_TOO_LARGE",
                "BATCH_WINDOW",
                "DISPATCH_WINDOW_OR_STATE",
            ):
                raise c.PilotError(reason)
            raise TimeoutError(
                "Unknown transport outcome, not independently reconstructible"
            )

    journal = SimpleNamespace(
        guard=lambda: {}, clock=clock, batch=lambda: dict(deadline_epoch=deadline)
    )
    generation = e.ExecutionGateway(ReplyAdapter("generation"))  # type: ignore[arg-type]
    review = e.ExecutionGateway(ReplyAdapter("review"))  # type: ignore[arg-type]
    workflow = (e.ExecutionB if arm == "B" else e.ExecutionC)(
        generation, review, cast(e.Journal, journal)
    )
    reconstructed = await workflow.run(
        run_id="p15_agent_pilot_p01",
        slot_id=slot["slot_id"],
        spec=slot["spec"],
        question=slot["question"],
    )
    if state.get("request_mismatch"):
        raise c.PilotError("COMPLETE_REQUEST_REPLAY_MISMATCH")
    if state["position"] != len(calls):
        raise c.PilotError("UNCONSUMED_DISPATCH_AFTER_POLICY_STOP")
    if canonical(reconstructed) != canonical(result):
        raise c.PilotError("WORKFLOW_STATE_REPLAY_MISMATCH")
    return reconstructed, bool(state["unverified_reason"])
