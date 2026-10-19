"""Zero-network proof of Schema normalization, full local validation and one-shot execution."""

# ruff: noqa: E402
import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_schema_projection import (
    projection,
    schema_nodes,
    ProjectedReviewAdapter,
)
from acceptance_support.om_diagnostic import valid_review
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import (
    StructuredRequest,
    StructuredResult,
    TextRequest,
    TokenUsage,
    ProviderError,
)
from prepare_luna_schema_validation import PARENT, BASE, SLOT, build
import run_luna_schema_validation as run


def parent(name):
    return json.loads((ROOT / PARENT / name).read_bytes())


def old_schema():
    return json.loads(bytes.fromhex(parent("requests.json")[SLOT]["wire_hex"]))["text"][
        "format"
    ]["schema"]


def test_precise_five_types_and_only_reachable_definition():
    original = old_schema()
    before = deepcopy(original)
    wire, info = projection(original)
    assert original == before and info["retained_definitions"] == ["finding"]
    paths = {tuple(p) for p in info["added_string_type_paths"]}
    assert paths == {
        ("properties", "schema_version"),
        ("properties", "scope"),
        ("properties", "verdict"),
        ("$defs", "finding", "properties", "category"),
        ("$defs", "finding", "properties", "severity"),
    }
    assert (
        wire["properties"]["coverage"]["properties"]["checked"]["uniqueItems"] is True
    )
    assert (
        len(
            [
                p
                for p, n in schema_nodes(wire)
                if "type" not in n and "enum" not in n and "const" not in n
            ]
        )
        == 1
    )
    assert info["removed_reachable_constraints"] == []


def test_inverse_operations_reconstruct_original_exact_contract():
    original = old_schema()
    wire, info = projection(original)
    restored = deepcopy(wire)
    for path in info["added_string_type_paths"]:
        node = restored
        for part in path:
            node = node[part]
        del node["type"]
    restored["$defs"] = deepcopy(original["$defs"])
    assert restored == original


def mutations():
    result = [valid_review("unit")]

    def add(fn):
        x = valid_review("unit")
        fn(x)
        result.append(x)

    add(lambda x: x.update(schema_version="wrong"))
    add(lambda x: x.update(scope="resource"))
    add(lambda x: x.update(verdict="revise"))
    add(lambda x: x.update(verdict=1))
    add(lambda x: x.update(extra="unexpected"))
    add(lambda x: x.update(unresolved=[1]))
    add(lambda x: x["coverage"]["checked"].append(x["coverage"]["checked"][0]))
    add(lambda x: x["coverage"].update(checked=["not-a-check"]))
    add(lambda x: x.pop("coverage"))
    finding = {
        "category": "fact",
        "severity": "major",
        "anchors": ["a1"],
        "condition_or_counterexample": "claim17 vs actual15",
        "impact": "incorrect teaching",
    }
    x = valid_review("unit")
    x.update(verdict="reject", findings=[finding])
    result.append(x)
    for field, value in [
        ("category", "invented"),
        ("severity", 2),
        ("anchors", ["not-a-server-anchor"]),
        ("condition_or_counterexample", ""),
        ("extra", "notallowed"),
    ]:
        x = deepcopy(result[-1] if result[-1]["findings"] else result[-2])
        x["findings"] = [deepcopy(finding)]
        x["findings"][0][field] = value
        result.append(x)
    return result


@pytest.mark.parametrize("value", mutations())
def test_original_and_wire_accept_same_valid_invalid_values(value):
    original = old_schema()
    wire, _ = projection(original)
    assert Draft202012Validator(original).is_valid(value) == Draft202012Validator(
        wire
    ).is_valid(value)


def test_resource_projection_keeps_its_original_verdicts_and_anchors():
    old = parent("resource-route-capture.json")
    for capture in old.values():
        schema = json.loads(bytes.fromhex(capture["wire_hex"]))["text"]["format"][
            "schema"
        ]
        wire, _ = projection(schema)
        assert wire["properties"]["scope"] == {"const": "resource", "type": "string"}
        assert (
            wire["properties"]["verdict"]["enum"]
            == schema["properties"]["verdict"]["enum"]
        )
        assert (
            wire["$defs"]["finding"]["properties"]["anchors"]
            == schema["$defs"]["finding"]["properties"]["anchors"]
        )


def test_unknown_reference_and_untyped_nonstring_enum_fail_closed():
    x = old_schema()
    x["properties"]["findings"]["items"]["$ref"] = "https://example.invalid/schema"
    with pytest.raises(ValueError, match="REFERENCE"):
        projection(x)
    x = old_schema()
    x["properties"]["verdict"] = {"enum": [0, 1]}
    with pytest.raises(ValueError, match="UNTYPED_ENUM"):
        projection(x)


def test_new_capture_is_only_schema_transport_difference():
    actual = asyncio.run(build())
    assert actual == {
        name: json.loads((ROOT / BASE / name).read_text()) for name in actual
    }
    before = json.loads(bytes.fromhex(parent("requests.json")[SLOT]["wire_hex"]))
    after = json.loads(bytes.fromhex(actual["request.json"]["wire_hex"]))
    assert before["input"] == after["input"]
    before["text"]["format"]["schema"] = after["text"]["format"]["schema"]
    assert before == after and "strict" not in after["text"]["format"]
    assert (
        actual["plan.json"]["requests_max"] == 1
        and actual["plan.json"]["stop_after_call_regardless_of_outcome"] is True
    )


def test_full_original_validator_still_rejects_even_if_wire_adapter_accepts(
    monkeypatch,
):
    value = valid_review("unit")
    value["coverage"]["checked"][-1] = value["coverage"]["checked"][0]

    async def bypass_wire(self, request):
        return StructuredResult(value, "gpt-6-luna", TokenUsage(10, 10))

    monkeypatch.setattr(DeepSeekResponsesAdapter, "generate_structured", bypass_wire)
    adapter = object.__new__(ProjectedReviewAdapter)
    with pytest.raises(ProviderError) as e:
        asyncio.run(
            adapter.generate_structured(
                StructuredRequest(TextRequest(()), old_schema())
            )
        )
    assert e.value.schema_keyword == "uniqueItems" and e.value.usage.output_tokens == 10


@pytest.mark.parametrize("failure", [False, True])
def test_one_shot_stops_and_reentry_never_calls_again(tmp_path, monkeypatch, failure):
    h = "a" * 64
    monkeypatch.setattr(
        run,
        "authorize",
        lambda root: (
            {
                "request_sha256": json.loads(
                    (ROOT / BASE / "request.json").read_text()
                )["wire_sha256"]
            },
            h,
        ),
    )
    monkeypatch.setattr(run, "assert_parent_stopped", lambda root: None)
    p = tmp_path / PARENT
    p.mkdir(parents=True)
    (p / "cases.json").write_text(json.dumps({SLOT: parent("cases.json")[SLOT]}))
    p = tmp_path / BASE
    p.mkdir(parents=True)
    (p / "request.json").write_bytes((ROOT / BASE / "request.json").read_bytes())
    sends = []

    async def attempt(root, m, case, wire, auth):
        auth()
        sends.append(1)
        if failure:
            raise TimeoutError()
        return {"record": {"local_routing": {"verdict": "pass"}}}

    result = asyncio.run(run.step(tmp_path, attempt))
    assert result["state"] == "STOPPED"
    with pytest.raises(FileExistsError):
        asyncio.run(run.step(tmp_path, attempt))
    assert sends == [1] and (tmp_path / run.PRIVATE / "receipt.json").is_file()


def test_missing_approval_denies_before_private_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run,
        "authorize",
        lambda root: (_ for _ in ()).throw(ValueError("NOT_AUTHORIZED")),
    )
    monkeypatch.setattr(run, "credential", lambda *a: pytest.fail("no key access"))
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        asyncio.run(run.step(tmp_path))
    assert not (tmp_path / run.PRIVATE).exists()
