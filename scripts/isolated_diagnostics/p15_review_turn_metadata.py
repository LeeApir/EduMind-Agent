"""ADR0040 proposal only: quarantine one exact pair of opaque reasoning metadata maps."""

from copy import deepcopy
import re

from isolated_diagnostics import p15_review_observability as original

VERSION = "isolated-review-turn-metadata-v1"
BASE = original.BASE
SUFFIX = original.SUFFIX
schema = original.schema


def _view(response):
    if not isinstance(response, dict):
        raise ValueError("RESPONSE_SHAPE_INVALID")
    view = deepcopy(response)
    present = False
    items = view.get("output")
    if not isinstance(items, list):
        raise ValueError("OUTPUT_ITEMS_INVALID")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("UNREQUESTED_OUTPUT_TYPE")
        if item.get("type") != "reasoning":
            continue
        fields = ("metadata", "internal_chat_message_metadata_passthrough")
        if not any(k in item for k in fields):
            continue
        values = []
        for key in fields:
            value = item.get(key)
            if not isinstance(value, dict) or set(value) != {"turn_id"}:
                raise ValueError("REASONING_TURN_METADATA_SHAPE_INVALID")
            turn = value["turn_id"]
            if (
                not isinstance(turn, str)
                or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", turn)
                is None
            ):
                raise ValueError("REASONING_TURN_METADATA_ID_INVALID")
            values.append(turn)
        if values[0] != values[1]:
            raise ValueError("REASONING_TURN_METADATA_MISMATCH")
        for key in fields:
            del item[
                key
            ]  # Private validator view only; original bytes remain immutable.
        present = True
    return view, present


class ReviewObservationAdapter:
    @staticmethod
    def validate_scene(request, response, payload):
        view, present = _view(response)
        checked = original.ReviewObservationAdapter.validate_scene(
            request, view, payload
        )
        return {
            **checked,
            "compatibility_policy": VERSION,
            "reasoning_turn_metadata_quarantined": present,
            "turn_metadata_interpreted_or_forwarded": False,
            "turn_metadata_identity_verified": False,
        }


def validate_envelope(request, response, payload):
    return ReviewObservationAdapter.validate_scene(request, response, payload)
