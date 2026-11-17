"""ADR0047: independent structural negatives, round trips and no B answer substitution."""

import json
from copy import deepcopy
import socket

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_example,
    canonical,
    digest,
)

DESIGN = json.loads((c.DESIGN / "examples.json").read_text())["cases"]
CONTEXT = json.loads((c.DESIGN / "context-example.json").read_text())
SPEC = CONTEXT["spec"]
CONTENT = next(row["payload"] for row in DESIGN if row["id"] == "positive_C_content")
BASELINE = next(row["payload"] for row in DESIGN if row["id"] == "positive_B_generate")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No network or DNS in isolated regression")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def artifact(arm="C", raw=None, revision=0, parent=None):
    catalog = c.make_catalog(SPEC)
    return c.assemble(
        deepcopy(raw or (CONTENT if arm == "C" else BASELINE)),
        c.identity("dev", "slot", arm, revision, SPEC, parent),
        catalog if arm == "C" else None,
    )


@pytest.mark.parametrize("case", DESIGN, ids=lambda x: x["id"])
def test_all_fifty_one_frozen_design_cases_retain_outcomes(case):
    value = deepcopy(case["payload"])
    catalog = c.make_catalog(SPEC)
    review_artifact = artifact()
    if case["role"] == "review_B":
        raw_b = deepcopy(BASELINE)
        raw_b["paragraphs"][0]["text"] = CONTENT["paragraphs"][0]["text"]
        review_artifact = artifact("B", raw_b)
    binding = c.make_binding(review_artifact)
    if case["role"] == "C_plan" and value["spec_id"] == CONTEXT["spec_id"]:
        value["spec_id"] = catalog["spec_id"]
    if case["role"].startswith("review_"):
        if value["candidate_id"] == CONTEXT["candidate_id"]:
            value["candidate_id"] = binding["candidate_id"]
        for issue in value["issues"]:
            if issue["target_id"] == "text_p0":
                issue["target_id"] = next(
                    k
                    for k, v in binding["targets"].items()
                    if v["path"] == "/raw_output/paragraphs/0/text"
                )
    if case["expected"] == "reject":
        with pytest.raises(c.ContractError):
            c.validate(case["role"], value, catalog=catalog, binding=binding)
    else:
        c.validate(case["role"], value, catalog=catalog, binding=binding)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"[]",
        b"null",
        b"\xff",
        b"{",
        b" " * 128001,
    ],
)
def test_strict_raw_rejects_ambiguous_nonfinite_nonobject_and_oversize(raw):
    with pytest.raises(c.ContractError):
        c.strict_json(raw)


def test_strict_raw_keeps_wrong_b_answer_and_original_bytes():
    value = deepcopy(BASELINE)
    value["answers"]["caller_head"] = "none"
    raw = canonical(value)
    assert c.strict_json(raw) == value
    assert canonical(value) == raw


@pytest.mark.parametrize("field", ["example", "facts", "spec_id", "catalog_digest"])
def test_catalog_mutation_or_rehash_cannot_forge_engine_facts(field):
    catalog = c.make_catalog(SPEC)
    if field == "example":
        catalog["example"]["observation"]["caller_head"] = None
    elif field == "facts":
        catalog["facts"]["obs_caller_head"]["value"] = None
    else:
        catalog[field] = "tampered"
    if field != "catalog_digest":
        catalog["catalog_digest"] = digest(
            {k: v for k, v in catalog.items() if k != "catalog_digest"}
        )
    with pytest.raises(c.ContractError, match="CATALOG_BINDING"):
        c.validate("C_content", CONTENT, catalog=catalog)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b["targets"].clear(),
        lambda b: b["artifact"]["raw_output"]["paragraphs"][0].update(text="other"),
        lambda b: b.update(candidate_id="foreign"),
        lambda b: b["targets"][next(iter(b["targets"]))].update(text="other"),
    ],
)
def test_binding_tamper_even_with_outer_rehash_rejected(mutate):
    binding = c.make_binding(artifact())
    mutate(binding)
    binding["binding_digest"] = digest(
        {k: v for k, v in binding.items() if k != "binding_digest"}
    )
    with pytest.raises(c.ContractError):
        c.verify_binding(binding)


def test_review_version_arm_parent_are_bound():
    a = artifact()
    bindings = [
        c.make_binding(a),
        c.make_binding(artifact("B")),
        c.make_binding(artifact(revision=1, parent=a["artifact_digest"])),
    ]
    assert len({b["candidate_id"] for b in bindings}) == 3
    opinion = dict(
        candidate_id=bindings[0]["candidate_id"],
        verdict="pass",
        uncertainty="",
        issues=[],
    )
    c.validate("review_C", opinion, binding=bindings[0])
    for other in bindings[1:]:
        with pytest.raises(c.ContractError, match="CANDIDATE_ID"):
            c.validate("review_C", opinion, binding=other)


def test_projection_covers_every_source_leaf_including_answers_and_action_states():
    a = artifact("B")
    binding = c.make_binding(a)

    def leaves(node, path=""):
        if isinstance(node, dict) and node:
            for k, v in node.items():
                yield from leaves(
                    v, path + "/" + k.replace("~", "~0").replace("/", "~1")
                )
        elif isinstance(node, list) and node:
            for i, v in enumerate(node):
                yield from leaves(v, path + "/" + str(i))
        else:
            yield path

    targets = list(binding["targets"].values())
    for leaf in leaves(a):
        assert any(
            leaf == t["path"] or leaf.startswith(t["path"] + "/") for t in targets
        )
    assert any(t["path"] == "/raw_output/answers/caller_head" for t in targets)
    assert any(t["path"].startswith("/raw_output/actions/states/") for t in targets)


def test_wrong_b_answers_are_not_filled_and_assembly_cannot_access_engine(monkeypatch):
    wrong = deepcopy(BASELINE)
    wrong["answers"].update(
        caller_head="none", reachable_prefix=[-8], allocation_failures=4
    )
    ident = c.identity("dev", "slot", "B", 0, SPEC, None)

    def denied(*args, **kwargs):
        pytest.fail("B assembly must not access reference facts")

    monkeypatch.setattr(c, "make_catalog", denied)
    monkeypatch.setattr(c, "build_example", denied)
    monkeypatch.setattr(c, "answer", denied)
    a = c.assemble(wrong, ident)
    assert a["raw_output"] == wrong
    assert [
        b["answer_key"] for b in a["source"]["blocks"] if b["kind"] == "question"
    ] == [None, "terminated", [-8], 4]
    assert a["source"]["provenance"]["answers"] == "model"
    missing = deepcopy(wrong)
    del missing["answers"]["caller_head"]
    with pytest.raises(c.ContractError, match="ROLE_SCHEMA"):
        c.assemble(missing, ident)


def test_c_resolves_program_facts_but_preserves_wrong_prose():
    raw = deepcopy(CONTENT)
    raw["paragraphs"][0]["text"] = (
        "The caller head remains empty after the successful insertion."
    )
    a = artifact(raw=raw)
    assert a["raw_output"] == raw
    assert "remains empty" in a["source"]["blocks"][0]["markdown"]
    assert a["source"]["resolved_facts"]["obs_caller_head"]["value"] == "t0"
    assert all(
        r["origin"] == "deterministic" for r in a["source"]["resolved_facts"].values()
    )
    binding = c.make_binding(a)
    assert any("remains empty" in t["text"] for t in binding["targets"].values())


@pytest.mark.parametrize("value", [1.0, True, -1, 5])
def test_b_exact_integer_count_bounds_not_json_integer_coercion(value):
    raw = deepcopy(BASELINE)
    raw["answers"]["allocation_failures"] = value
    with pytest.raises(c.ContractError):
        c.validate("B_generate", raw)


@pytest.mark.parametrize(
    "state",
    [
        dict(caller_head=None, local_head=None, p=None, nodes={}),
        dict(
            caller_head="t0",
            local_head=None,
            p="t0",
            nodes={"t0": dict(data=0, next=None)},
        ),
        dict(
            caller_head="t0",
            local_head="t0",
            p="t0",
            nodes={"t0": dict(data="indeterminate", next="indeterminate")},
        ),
        dict(
            caller_head="i0",
            local_head="i0",
            p="t0",
            nodes={"i0": dict(data=-7, next=None), "t0": dict(data=0, next="i0")},
        ),
    ],
)
def test_handwritten_state_encoding_keeps_zero_unknown_null_and_topology(state):
    encoded = c.encode_state(state)
    assert c.decode_state(encoded) == state
    if any(n["data"] == "indeterminate" for n in state["nodes"].values()):
        assert any(
            n["data_status"] == "indeterminate" and n["data"] == 0
            for n in encoded["nodes"]
        )


@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
@pytest.mark.parametrize(
    "mask", [[True, True], [False, True], [True, False], [False, False]]
)
def test_all_template_state_round_trips_and_allocation_failure(variant, mask):
    # Codec regression only; engine correctness is checked by existing independent expected-value tests.
    spec = dict(
        SPEC,
        initial_values=[0],
        insert_values=[-4, 0],
        allocation_success=mask,
        variant=variant,
    )
    example = build_example(spec)
    for step in example["trace"]["steps"]:
        state = {
            k: deepcopy(step[k]) for k in ("caller_head", "local_head", "p", "nodes")
        }
        assert c.decode_state(c.encode_state(state)) == state


def test_no_reference_argument_accepted_in_b_assembly():
    with pytest.raises(c.ContractError, match="BASELINE_REFERENCE_FORBIDDEN"):
        c.assemble(
            BASELINE,
            c.identity("dev", "slot", "B", 0, SPEC, None),
            c.make_catalog(SPEC),
        )


def test_schema_copy_and_malformed_identity():
    schema = c.schema_for("C_plan")
    schema["properties"].clear()
    assert c.schema_for("C_plan")["properties"]
    with pytest.raises(c.ContractError):
        c.identity("../dev", "slot", "C", 0, SPEC, None)
    with pytest.raises(c.ContractError):
        c.identity("dev", "slot", "C", 1, SPEC, None)


def test_raw_markup_remains_auditable_but_rendered_prose_is_inert():
    raw = deepcopy(CONTENT)
    raw["paragraphs"][0]["text"] = '<script>fetch("https://evil.invalid")</script>'
    candidate = artifact(raw=raw)
    assert (
        candidate["raw_output"]["paragraphs"][0]["text"] == raw["paragraphs"][0]["text"]
    )
    assert "<script>" not in candidate["source"]["blocks"][0]["markdown"]
    assert "&lt;" in candidate["source"]["blocks"][0]["markdown"]


def test_review_stage_cannot_accept_other_arm_even_with_matching_candidate_id():
    binding = c.make_binding(artifact("B"))
    opinion = dict(
        candidate_id=binding["candidate_id"], verdict="pass", uncertainty="", issues=[]
    )
    with pytest.raises(c.ContractError, match="REVIEW_ARM"):
        c.validate("review_C", opinion, binding=binding)
