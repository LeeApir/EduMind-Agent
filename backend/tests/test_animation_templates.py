"""Boundary and fact checks for the fixed animation template registry."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.services.animation_templates import (
    RuntimeIdentity,
    TemplateValidationError,
    cache_identity,
    load_template,
    normalize_parameters,
)

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = RuntimeIdentity(
    source_sha256="a" * 64,
    image_digest="sha256:" + "b" * 64,
    font_digest="c" * 64,
    renderer_config_sha256="d" * 64,
    subtitle_version="srt-v1",
)


def test_registry_matches_reviewed_graph_nodes_and_step_order() -> None:
    graph = json.loads((ROOT / "data/knowledge_graph.yaml").read_text())
    nodes = {node["id"] for node in graph["nodes"]}
    for template_id, steps in {
        "linked-list-insertion": ["before", "save_successor", "link_predecessor", "after"],
        "linked-list-deletion": ["before", "save_successor", "relink", "release", "after"],
    }.items():
        spec = load_template(template_id)
        assert spec.knowledge_point_id in nodes
        assert spec.template_version == "1.0.0"
        assert spec.language == "zh-CN"
        assert [step["id"] for step in spec.teaching_steps] == steps
        assert spec.review["design_status"] == "fact_checked"
        assert spec.review["source_status"] == "pending"
        with pytest.raises(TemplateValidationError, match="not reviewed"):
            load_template(template_id, require_executable=True)


@pytest.mark.parametrize("template_id", ["../secrets", "linked-list-insertion.py", "array", ""])
def test_registry_rejects_unlisted_template_ids(template_id: str) -> None:
    with pytest.raises(TemplateValidationError, match="unsupported"):
        load_template(template_id)


@pytest.mark.parametrize("values,index,value", [
    ([], 0, 5), ([1, 2], 0, -4), ([1, 2], 1, 5), ([1, 2], 2, 5),
])
def test_insert_boundaries(values: list[int], index: int, value: int) -> None:
    spec = load_template("linked-list-insertion")
    assert normalize_parameters(spec, {"values": values, "index": index, "value": value}) == {
        "values": values, "index": index, "value": value,
    }


@pytest.mark.parametrize("values,index", [([3], 0), ([1, 2, 3], 0), ([1, 2, 3], 1), ([1, 2, 3], 2)])
def test_delete_boundaries(values: list[int], index: int) -> None:
    spec = load_template("linked-list-deletion")
    assert normalize_parameters(spec, {"values": values, "index": index}) == {
        "values": values, "index": index,
    }


@pytest.mark.parametrize("template_id,parameters", [
    ("linked-list-insertion", {"values": [], "index": 1, "value": 1}),
    ("linked-list-insertion", {"values": list(range(8)), "index": 0, "value": 1}),
    ("linked-list-insertion", {"values": [1], "index": -1, "value": 2}),
    ("linked-list-insertion", {"values": [1], "index": True, "value": 2}),
    ("linked-list-insertion", {"values": [1], "index": 1, "value": "2"}),
    ("linked-list-insertion", {"values": [1], "index": 1, "value": 2, "code": "exec(1)"}),
    ("linked-list-insertion", {"values": ["__import__('os')"], "index": 0, "value": 2}),
    ("linked-list-insertion", {"values": [100], "index": 0, "value": 2}),
    ("linked-list-deletion", {"values": [], "index": 0}),
    ("linked-list-deletion", {"values": [1], "index": 1}),
    ("linked-list-deletion", {"values": [1], "index": 0, "path": "/tmp/x"}),
    ("linked-list-deletion", {"values": [1], "index": 0, "value": 2}),
])
def test_invalid_parameters_are_rejected(template_id: str, parameters: dict[str, object]) -> None:
    with pytest.raises(TemplateValidationError):
        normalize_parameters(load_template(template_id), parameters)


def test_cache_key_is_stable_and_versions_and_runtime_change_it() -> None:
    spec = load_template("linked-list-insertion")
    params = {"values": [1, 2], "index": 1, "value": 7}
    key = cache_identity(spec, params, RUNTIME)
    assert len(key) == 64
    assert key == cache_identity(spec, dict(reversed(list(params.items()))), RUNTIME)
    assert key != cache_identity(replace(spec, template_version="1.0.1"), params, RUNTIME)
    assert key != cache_identity(spec, {**params, "value": 8}, RUNTIME)
    assert key != cache_identity(spec, params, replace(RUNTIME, source_sha256="e" * 64))
    assert key != cache_identity(spec, params, replace(RUNTIME, image_digest="sha256:" + "f" * 64))
    assert key != cache_identity(spec, params, replace(RUNTIME, subtitle_version="srt-v2"))
    assert key != cache_identity(spec, params, replace(RUNTIME, font_digest="1" * 64))
    assert key != cache_identity(spec, params, replace(RUNTIME, renderer_config_sha256="2" * 64))


def test_cache_key_has_no_owner_or_untrusted_text() -> None:
    spec = load_template("linked-list-deletion")
    with pytest.raises(TemplateValidationError):
        cache_identity(spec, {"values": [1], "index": 0, "owner_id": "other"}, RUNTIME)
    with pytest.raises(TemplateValidationError):
        RuntimeIdentity("bad", RUNTIME.image_digest, RUNTIME.font_digest,
                        RUNTIME.renderer_config_sha256, "srt-v1")


def test_loaded_manifest_cannot_be_mutated_to_bypass_review_or_schema() -> None:
    spec = load_template("linked-list-insertion")
    with pytest.raises(TypeError):
        spec.review["source_status"] = "approved"  # type: ignore[index]
    with pytest.raises(TypeError):
        spec.teaching_steps[0]["id"] = "unsafe"  # type: ignore[index]
    editable_schema = spec.parameter_schema
    editable_schema["additionalProperties"] = True
    with pytest.raises(TemplateValidationError):
        normalize_parameters(spec, {"values": [], "index": 0, "value": 1, "path": "/tmp"})


def test_cache_key_includes_knowledge_language_and_review_rule() -> None:
    from types import MappingProxyType

    spec = load_template("linked-list-insertion")
    parameters = {"values": [], "index": 0, "value": 1}
    key = cache_identity(spec, parameters, RUNTIME)
    assert key != cache_identity(replace(spec, knowledge_point_id="other"), parameters, RUNTIME)
    assert key != cache_identity(replace(spec, language="en-US"), parameters, RUNTIME)
    changed_review = dict(spec.review, rule_version="animation-template-review-v2")
    assert key != cache_identity(
        replace(spec, review=MappingProxyType(changed_review)), parameters, RUNTIME
    )


def test_openapi_template_variants_match_registry_static_bounds() -> None:
    spec = json.loads((ROOT / "docs/api/openapi.yaml").read_text())
    schemas = spec["components"]["schemas"]
    variants = schemas["AnimationRequest"]["oneOf"]
    assert {item["$ref"].split("/")[-1] for item in variants} == {
        "AnimationInsertRequest", "AnimationDeleteRequest"
    }
    cases = (
        ("linked-list-insertion", {"values": [], "index": 0, "value": -3}),
        ("linked-list-deletion", {"values": [2], "index": 0}),
    )
    for template_id, parameters in cases:
        variant = schemas["AnimationInsertRequest" if template_id.endswith("insertion")
                          else "AnimationDeleteRequest"]
        request = {"template_id": template_id, "template_version": "1.0.0",
                   "scene_version": 1, "parameters": parameters}
        assert Draft202012Validator(variant).is_valid(request)
        assert normalize_parameters(load_template(template_id), parameters)
        assert not Draft202012Validator(variant).is_valid(
            {**request, "parameters": {**parameters, "code": "eval(1)"}}
        )
