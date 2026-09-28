"""Fixed, reviewed animation template registry and data-only request validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY = _ROOT / "data" / "animation_templates"
_ALLOWED_FILES = {
    "linked-list-insertion": "linked-list-insertion.json",
    "linked-list-deletion": "linked-list-deletion.json",
}
_SOURCE_FILES = {
    "linked-list-insertion": (
        "backend/app/animation_templates/insertion_plan.py",
        "backend/app/animation_templates/linked_list_insertion.py",
    ),
}
_MAX_NODES = 8


class TemplateValidationError(ValueError):
    """A requested template or its data is outside the fixed P0 boundary."""


def source_digest(template_id: str) -> str:
    """Bind a source approval to every file that defines its teaching frames."""
    paths = _SOURCE_FILES.get(template_id)
    if paths is None:
        raise TemplateValidationError("template source is unavailable")
    digest = hashlib.sha256()
    for relative_path in paths:
        path = _ROOT / relative_path
        if not path.is_file():
            raise TemplateValidationError("template source is unavailable")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class TemplateSpec:
    template_id: str
    knowledge_point_id: str
    template_version: str
    language: str
    operation: Literal["insert", "delete"]
    parameter_schema_json: str
    teaching_steps: tuple[Mapping[str, str], ...]
    review: Mapping[str, str]

    @property
    def parameter_schema(self) -> dict[str, object]:
        schema: dict[str, object] = json.loads(self.parameter_schema_json)
        return schema

    @property
    def executable(self) -> bool:
        return self.review["source_status"] == "approved"


@dataclass(frozen=True)
class RuntimeIdentity:
    source_sha256: str
    image_digest: str
    font_digest: str
    renderer_config_sha256: str
    subtitle_version: str

    def __post_init__(self) -> None:
        for field in ("source_sha256", "font_digest", "renderer_config_sha256"):
            value = getattr(self, field)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise TemplateValidationError("invalid runtime digest")
        if (
            not self.image_digest.startswith("sha256:")
            or len(self.image_digest) != 71
            or any(char not in "0123456789abcdef" for char in self.image_digest[7:])
        ):
            raise TemplateValidationError("invalid image digest")
        if not self.subtitle_version or len(self.subtitle_version) > 40:
            raise TemplateValidationError("invalid subtitle version")


def load_template(template_id: str, *, require_executable: bool = False) -> TemplateSpec:
    """Select only repository-owned manifests; input never becomes a path."""
    filename = _ALLOWED_FILES.get(template_id)
    if filename is None:
        raise TemplateValidationError("unsupported template")
    raw: Any = json.loads((_REGISTRY / filename).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("template_id") != template_id:
        raise TemplateValidationError("invalid template manifest")
    expected = {
        "schema_version", "template_id", "knowledge_point_id", "template_version",
        "language", "operation", "parameter_schema", "teaching_steps", "review",
    }
    if set(raw) != expected or raw["schema_version"] != 1:
        raise TemplateValidationError("invalid template manifest")
    if raw["knowledge_point_id"] != template_id or raw["language"] != "zh-CN":
        raise TemplateValidationError("invalid template identity")
    operation: Literal["insert", "delete"] = (
        "insert" if template_id.endswith("insertion") else "delete"
    )
    if raw["operation"] != operation:
        raise TemplateValidationError("invalid template operation")
    schema = raw["parameter_schema"]
    Draft202012Validator.check_schema(schema)
    steps = raw["teaching_steps"]
    if not isinstance(steps, list) or not steps or any(
        not isinstance(step, dict) or set(step) != {"id", "fact"} for step in steps
    ):
        raise TemplateValidationError("invalid teaching steps")
    review = raw["review"]
    if not isinstance(review, dict) or set(review) != {
        "design_status", "source_status", "fact_source", "rule_version", "evidence",
        "source_sha256",
    } or review["design_status"] != "fact_checked" or review["source_status"] not in {
        "pending", "approved"
    }:
        raise TemplateValidationError("invalid review record")
    if review["source_status"] == "approved" and (
        review["source_sha256"] != source_digest(template_id)
    ):
        raise TemplateValidationError("template source approval digest mismatch")
    if review["source_status"] == "pending" and review["source_sha256"] != "":
        raise TemplateValidationError("pending source cannot have an approval digest")
    spec = TemplateSpec(
        template_id=raw["template_id"],
        knowledge_point_id=raw["knowledge_point_id"],
        template_version=raw["template_version"],
        language=raw["language"],
        operation=operation,
        parameter_schema_json=json.dumps(schema, sort_keys=True),
        teaching_steps=tuple(MappingProxyType(step) for step in steps),
        review=MappingProxyType(review),
    )
    if require_executable and not spec.executable:
        raise TemplateValidationError("template source is not reviewed")
    return spec


def normalize_parameters(spec: TemplateSpec, parameters: Mapping[str, object]) -> dict[str, object]:
    """Return a canonical, strictly bounded value object, never code or a path."""
    if not isinstance(parameters, dict):
        raise TemplateValidationError("parameters must be an object")
    errors = tuple(Draft202012Validator(spec.parameter_schema).iter_errors(parameters))
    if errors:
        raise TemplateValidationError("invalid animation parameters")
    values = parameters["values"]
    index = parameters["index"]
    if not isinstance(values, list) or type(index) is not int:
        raise TemplateValidationError("invalid animation parameters")
    if any(type(value) is not int for value in values):
        raise TemplateValidationError("invalid animation parameters")
    if spec.operation == "insert":
        if index > len(values) or len(values) >= _MAX_NODES:
            raise TemplateValidationError("insert index or resulting length out of range")
        value = parameters["value"]
        if type(value) is not int:
            raise TemplateValidationError("invalid animation parameters")
        return {"values": list(values), "index": index, "value": value}
    if not values or index >= len(values):
        raise TemplateValidationError("delete index out of range")
    return {"values": list(values), "index": index}


def cache_identity(
    spec: TemplateSpec,
    parameters: Mapping[str, object],
    runtime: RuntimeIdentity,
) -> str:
    """Hash only public template data and pinned runtime identity."""
    normalized = normalize_parameters(spec, parameters)
    canonical = json.dumps(
        {
            "knowledge_point_id": spec.knowledge_point_id,
            "template_id": spec.template_id,
            "template_version": spec.template_version,
            "language": spec.language,
            "parameters": normalized,
            "review_rule_version": spec.review["rule_version"],
            "source_sha256": runtime.source_sha256,
            "image_digest": runtime.image_digest,
            "font_digest": runtime.font_digest,
            "renderer_config_sha256": runtime.renderer_config_sha256,
            "subtitle_version": runtime.subtitle_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
