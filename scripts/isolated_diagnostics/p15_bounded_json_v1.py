"""Bounded incremental canonical JSON, for offline pre-dispatch accounting."""

import json
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c


def encode(value: Any, maximum: int, code: str) -> bytes:
    c.require(type(maximum) is int and maximum > 0, "ENCODE_BOUND")
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    output = bytearray()
    try:
        for fragment in encoder.iterencode(value):
            encoded = fragment.encode("utf-8")
            c.require(len(output) + len(encoded) <= maximum, code)
            output.extend(encoded)
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, c.ContractError):
            raise
        raise c.ContractError("ENCODE_UNKNOWN") from exc
    return bytes(output)
