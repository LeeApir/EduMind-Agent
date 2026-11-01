"""Offline cross-check of independent synthetic receipts and response originals.

The witness must be captured separately before dispatch. This function neither
creates a receipt nor authenticates an untrusted witness; callers must keep the
witness and originals in an independently protected store.
"""

import hashlib
import json
import re
from typing import Any, Callable

from scripts.isolated_diagnostics.p15_agent_pilot import PilotError
from scripts.isolated_diagnostics.p15_pilot_wire import strict_json


def verify(
    witness: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    load_original: Callable[[str], bytes],
    load_request: Callable[[str], bytes],
) -> str:
    """Return verified only when every observed normal/late original is intact."""
    if not witness or len(witness) != len(ledger):
        return "unknown"
    seen: set[int] = set()
    originals: set[str] = set()
    request_files: set[str] = set()
    parents: dict[tuple[str, str], str] = {}
    for independent, row in zip(witness, ledger, strict=True):
        if independent != row:
            return "unknown"
        number = independent.get("number")
        digest = independent.get("request_sha256")
        if (
            type(number) is not int or number in seen or number <= 0
            or number != len(seen) + 1 or independent.get("arm") not in ("B", "C")
            or type(independent.get("slot")) is not str or not independent["slot"]
            or type(independent.get("stage")) is not str or not independent["stage"]
            or type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or any(independent.get(k) != row.get(k) for k in ("number", "slot", "arm", "stage", "request_sha256", "request_original", "parent_receipt", "receipt_sha256"))
        ):
            return "unknown"
        seen.add(number)
        pair = (independent["slot"], independent["arm"])
        if independent.get("parent_receipt") != parents.get(pair):
            return "unknown"
        request_name = independent.get("request_original")
        if type(request_name) is not str or not request_name or request_name in request_files:
            return "unknown"
        request_files.add(request_name)
        try:
            request = load_request(request_name)
        except (OSError, KeyError, ValueError):
            return "unknown"
        if type(request) is not bytes or hashlib.sha256(request).hexdigest() != digest:
            return "unknown"
        state = independent.get("state")
        if state not in ("responded", "late") or row.get("state") != state:
            return "unknown"
        if any(independent.get(k) != row.get(k) for k in ("original", "response_sha256", "status", "usage")):
            return "unknown"
        name, sha, status = independent.get("original"), independent.get("response_sha256"), independent.get("status")
        if (
            type(name) is not str or not name or type(sha) is not str
            or name in originals
            or re.fullmatch(r"[0-9a-f]{64}", sha) is None
            or type(status) is not int or not 100 <= status <= 599
        ):
            return "unknown"
        originals.add(name)
        try:
            raw = load_original(name)
        except (OSError, KeyError, ValueError):
            return "unknown"
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != sha:
            return "unknown"
        try:
            usage = strict_json(raw)["usage"]
            counts = (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"])
        except (ValueError, TypeError, KeyError, PilotError, RecursionError):
            return "unknown"
        if (
            any(type(value) is not int or value < 0 for value in counts)
            or counts[2] != counts[0] + counts[1]
            or independent.get("usage") != {"input": counts[0], "output": counts[1]}
        ):
            return "unknown"
        receipt = independent.get("receipt_sha256")
        material = {key: value for key, value in independent.items() if key != "receipt_sha256"}
        try:
            canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        except (TypeError, ValueError):
            return "unknown"
        if type(receipt) is not str or hashlib.sha256(canonical).hexdigest() != receipt:
            return "unknown"
        parents[pair] = receipt
    return "verified"
