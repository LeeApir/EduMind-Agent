"""Packaged cumulative approved DTOs; runtime needs no repository docs directory."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from app.services.free_course_snapshots import SnapshotError

CONTRACT: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[1] / "contracts/free_course.openapi.json").read_text()
)
SCHEMAS: dict[str, Any] = CONTRACT["components"]["schemas"]


def validate(name: str, value: Any) -> None:
    schema = json.loads(
        json.dumps({**SCHEMAS[name], "$defs": SCHEMAS}).replace("#/components/schemas/", "#/$defs/")
    )
    if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(value):
        raise SnapshotError("INVALID_API_INPUT")


def public_openapi(base: dict[str, Any]) -> dict[str, Any]:
    extra = deepcopy(CONTRACT)
    # Namespace avoids colliding with existing catalog/legacy component names.
    extra = json.loads(
        json.dumps(extra)
        .replace("#/components/schemas/", "#/components/schemas/FreeCourse")
        .replace("#/components/parameters/", "#/components/parameters/FreeCourse")
        .replace("#/components/securitySchemes/", "#/components/securitySchemes/FreeCourse")
    )
    for kind, values in extra["components"].items():
        base.setdefault("components", {}).setdefault(kind, {}).update(
            {"FreeCourse" + k: v for k, v in values.items()}
        )
    for path, methods in extra["paths"].items():
        for method, item in methods.items():
            # Authentication is cookie-backed; security scheme name references are keys.
            for security in item.get("security", []):
                for key in list(security):
                    security["FreeCourse" + key] = security.pop(key)
        base["paths"][path] = methods
    return base
