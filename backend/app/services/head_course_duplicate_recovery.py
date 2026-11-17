"""Explicit, finite format derivation; the strict wire parser remains unchanged."""

import hashlib
import json
from typing import Any

from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, canonical

VERSION = "head-questions-identical-duplicate-v1"


class Pairs(list):
    """An object is distinct from an array, even before duplicate validation."""


def recover(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Remove only a second type-identical member at /questions/<fixed key>."""

    def invalid_constant(value):
        raise SnapshotError("HEAD_RECOVERY_JSON_CONSTANT")

    try:
        tree = json.loads(text, object_pairs_hook=Pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as error:
        raise SnapshotError("HEAD_RECOVERY_JSON_SYNTAX") from error
    duplicates: list[dict[str, Any]] = []

    def typed_equal(a, b):
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(typed_equal(a[k], b[k]) for k in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(typed_equal(x, y) for x, y in zip(a, b, strict=True))
        return a == b

    def walk(node, path):
        if isinstance(node, Pairs):
            result = {}
            counts = {}
            for index, (key, value) in enumerate(node):
                value = walk(value, [*path, key])
                counts[key] = counts.get(key, 0) + 1
                if counts[key] > 1:
                    if path != ["questions"] or key not in m.QKEYS or counts[key] != 2:
                        raise SnapshotError("HEAD_RECOVERY_DUPLICATE_SCOPE")
                    if not typed_equal(result[key], value):
                        raise SnapshotError("HEAD_RECOVERY_DUPLICATE_CONFLICT")
                    duplicates.append(
                        dict(
                            path=[*path, key],
                            removed_member_index=index,
                            occurrence=2,
                            value_sha256=hashlib.sha256(canonical(value)).hexdigest(),
                        )
                    )
                else:
                    result[key] = value
            return result
        if isinstance(node, list):
            return [walk(value, [*path, i]) for i, value in enumerate(node)]
        return node

    value = walk(tree, [])
    if not isinstance(value, dict) or not isinstance(value.get("questions"), dict):
        raise SnapshotError("HEAD_RECOVERY_QUESTIONS_REQUIRED")
    if set(value["questions"]) != set(m.QKEYS):
        raise SnapshotError("HEAD_RECOVERY_QUESTIONS_REQUIRED")
    # Includes missing fields, exact stem/explanation shape and primitive types.
    # Full fact/scenario/frame checks require the original payload at the call site.
    m.Draft202012Validator(m.SCHEMA).validate(value)
    canonical(value)  # Reject non-finite numbers / unsupported local values too.
    return value, duplicates
