"""Bounded data-only animation intent shared by generation and independent review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, cast


@dataclass(frozen=True, slots=True)
class VideoIntent:
    """Built by trusted target composition; never accepts a Python/DSL/template identifier."""

    knowledge_point_id: str
    operation: Literal["insert", "delete", "compare", "swap", "traverse", "cycle"]
    parameters_json: str = field(repr=False)
    presentation: Literal["standard", "detailed_trace"] = "standard"

    def payload(self) -> dict[str, object]:
        if (
            type(self.knowledge_point_id) is not str
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.knowledge_point_id)
            or self.operation not in {"insert", "delete", "compare", "swap", "traverse", "cycle"}
            or self.presentation not in {"standard", "detailed_trace"}
            or type(self.parameters_json) is not str
            or len(self.parameters_json) > 1024
        ):
            raise ValueError("DSL_INTENT_INVALID")

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in items:
                if key in result:
                    raise ValueError("DSL_INTENT_INVALID")
                result[key] = item
            return result

        params = json.loads(self.parameters_json, object_pairs_hook=pairs)
        keys = {"insert": {"values", "index", "value"}, "delete": {"values", "index"}}
        if type(params) is not dict or set(params) != keys.get(self.operation, {"values"}):
            raise ValueError("DSL_INTENT_INVALID")
        values = params["values"]
        if (
            type(values) is not list
            or len(values) > 8
            or any(type(v) is not int or not -999 <= v <= 999 for v in values)
            or any(
                type(v) is not int or not -999 <= v <= 999
                for k, v in params.items()
                if k != "values"
            )
        ):
            raise ValueError("DSL_INTENT_INVALID")
        if self.operation in {"compare", "swap"} and len(values) < 2:
            raise ValueError("DSL_INTENT_INVALID")
        if self.operation == "insert" and (
            not 0 <= params["index"] <= len(values) or len(values) >= 8
        ):
            raise ValueError("DSL_INTENT_INVALID")
        if self.operation == "delete" and not 0 <= params["index"] < len(values):
            raise ValueError("DSL_INTENT_INVALID")
        return {
            "knowledge_point_id": self.knowledge_point_id,
            "operation": self.operation,
            "parameters": params,
            "presentation": self.presentation,
        }


def intent_from_payload(value: dict[str, object]) -> VideoIntent:
    if type(value) is not dict or set(value) != {
        "knowledge_point_id",
        "operation",
        "parameters",
        "presentation",
    }:
        raise ValueError("DSL_INTENT_INVALID")
    intent = VideoIntent(
        cast(str, value["knowledge_point_id"]),
        cast(
            Literal["insert", "delete", "compare", "swap", "traverse", "cycle"], value["operation"]
        ),
        json.dumps(value["parameters"], allow_nan=False),
        cast(Literal["standard", "detailed_trace"], value["presentation"]),
    )
    intent.payload()
    return intent
