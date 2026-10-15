"""Local contract checks for immutable planned learning; never grants publication."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROLES = ("explanation", "code", "exercise")
SCHEMA = json.loads(Path(__file__).with_suffix(".schema.json").read_text())


class LearningContractError(ValueError):
    def __init__(self, code: str = "LEARNING_CONTRACT_INVALID") -> None:
        self.code = code
        super().__init__(code)


def canonical(value: object) -> bytes:
    def check(item: object) -> None:
        if isinstance(item, float):
            raise LearningContractError
        if isinstance(item, dict):
            if not all(isinstance(k, str) for k in item):
                raise LearningContractError
            for v in item.values():
                check(v)
        elif isinstance(item, (list, tuple)):
            for v in item:
                check(v)

    try:
        check(value)
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LearningContractError from None


def digest(kind: str, version: str, **fields: object) -> str:
    return hashlib.sha256(
        canonical({"kind": kind, "schema_version": version, **fields})
    ).hexdigest()


def validate_contract(value: object, name: str) -> dict[str, Any]:
    schema = {"$ref": "#/$defs/" + name, "$defs": SCHEMA["$defs"]}
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
        canonical(value)
    except Exception:
        raise LearningContractError from None
    return deepcopy(cast(dict[str, Any], value))


def validate_plan(
    value: object, *, node_ids: set[str], references: dict[str, object]
) -> dict[str, Any]:
    plan = validate_contract(value, "plan")
    if len(canonical(plan)) > 8192 or plan["node_id"] not in node_ids:
        raise LearningContractError
    for key, field in [
        ("objectives", "id"),
        ("terminology", "term"),
        ("references", "reference_id"),
    ]:
        ids = [v[field] for v in plan[key]]
        if len(ids) != len(set(ids)):
            raise LearningContractError
    goals = {o["id"] for o in plan["objectives"]}
    if any(not set(s["objective_ids"]) <= goals for s in plan["scenes"]):
        raise LearningContractError
    if not set(plan["prerequisite_node_ids"]) <= node_ids:
        raise LearningContractError
    if any(references.get(r["reference_id"]) != r for r in plan["references"]):
        raise LearningContractError
    conventions = plan["conventions"]
    if (conventions["index_base"] is None or conventions["capacity"] is None) and not conventions[
        "not_applicable_reasons"
    ]:
        raise LearningContractError
    return plan
