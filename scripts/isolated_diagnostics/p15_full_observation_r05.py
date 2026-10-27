"""Source/wire-bound safe observation receipts. No transport, raw rewriting or summary export."""

import hashlib

from acceptance_support.p15_candidate_compatibility import parse
from acceptance_support.p15_diagnostic_execution import PROBE_PROMPT
from acceptance_support.p15_diagnostic_ledger import Refused
from isolated_diagnostics import p15_review_observability as compat


def checked_record(raw, response_raw, *, stage, identity, ticket, slots):
    body, payload = parse(raw), parse(response_raw)
    if stage == "development_scene_review":
        submitted = parse(body["input"][-1]["content"])
        checked = compat.ReviewObservationAdapter.validate_scene(
            body, payload, submitted
        )
        source = submitted["source_sha256"]
    elif stage == "development_review_probe":
        selected = [s for s in slots if s["slot_id"] == identity["slot_id"]]
        if (
            len(selected) != 1
            or selected[0]["kind"] != "probe"
            or body["input"]
            != [
                {"role": "system", "content": PROBE_PROMPT},
                {"role": "user", "content": selected[0]["content"]},
            ]
        ):
            raise Refused("EXACT_PROBE_CONTENT_WITHOUT_GOLD_REQUIRED")
        checked = compat.validate_probe_envelope(body, payload)
        source = None
    else:
        raise Refused("UNKNOWN_REVIEW_STAGE")
    return checked["opinion"], {
        "ticket": ticket,
        "identity": identity,
        "stage": stage,
        "request_sha256": hashlib.sha256(raw).hexdigest(),
        "response_sha256": hashlib.sha256(response_raw).hexdigest(),
        "source_sha256": source,
        **{
            key: checked[key]
            for key in (
                "compatibility_policy",
                "instruction_echo_status",
                "instruction_delivery_verified",
                "upstream_context_verified",
                "summary_interpreted_or_forwarded",
                "production_admission",
                "observed_known_suffix",
                "reported_reasoning_tokens",
                "reported_output_tokens_including_reasoning",
            )
        },
    }


def audit_records(*, output, calls, settlements, observations, slots):
    """Read-only audit; no receipt can replace missing raw evidence or count as quality truth."""
    review_calls = {c["ticket"]: c for c in calls if c["provider"] == "review"}
    if len(review_calls) != sum(c["provider"] == "review" for c in calls):
        raise Refused("DUPLICATE_REVIEW_CALL")
    seen = set()
    for record in observations:
        ticket = record.get("ticket")
        if ticket not in review_calls or ticket in seen:
            raise Refused("REVIEW_OBSERVATION_BINDING_INVALID")
        seen.add(ticket)
        call = review_calls[ticket]
        # Tickets derive from SHA256, never arbitrary paths from a report.
        if (
            not isinstance(ticket, str)
            or len(ticket) != 64
            or any(c not in "0123456789abcdef" for c in ticket)
        ):
            raise Refused("INVALID_REVIEW_TICKET")
        raw = (output / (ticket + "-request.json")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != call["request_sha256"]:
            raise Refused("REQUEST_EVIDENCE_CHANGED")
        response_raw = (output / (ticket + "-response.json")).read_bytes()
        _, expected = checked_record(
            raw,
            response_raw,
            stage=call["stage"],
            identity=call["identity"],
            ticket=ticket,
            slots=slots,
        )
        if record != expected:
            raise Refused("REVIEW_OBSERVATION_CHANGED")
    for ticket, settlement in settlements:
        if ticket in review_calls:
            if ticket not in seen or settlement["proof_sha256"] != next(
                r["response_sha256"] for r in observations if r["ticket"] == ticket
            ):
                raise Refused("SETTLED_REVIEW_OBSERVATION_REQUIRED")
    return len(seen)
