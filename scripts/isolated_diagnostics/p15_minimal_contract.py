"""ADR0047 isolated payload adapter. Pure data only; no provider, credentials or execution."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services.free_scene_markdown import clean_code_markdown
from scripts.isolated_diagnostics import p15_agent_pilot as legacy
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    QUESTION_KEYS as QUESTION_KEYS,
    answer,
    build_example,
    canonical,
    digest,
    validate_spec,
)

VERSION = "pilot-minimal-output-adapter-v1"
ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs/acceptance/phase-1.5-minimal-output-contract-r01"
SCHEMA_SHA = "d45e59648e5ef574674fe24ed85ac55b206eb36cbc2dc900179ad008fa52d8be"
MAX_PAYLOAD = 128000
GOALS = tuple(legacy.GOALS)
STAGES = (
    "C_plan",
    "C_content",
    "C_repair",
    "B_generate",
    "B_repair",
    "review_B",
    "review_C",
)


class ContractError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def frozen_schemas() -> dict[str, Any]:
    raw = (DESIGN / "schemas.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCHEMA_SHA, "FROZEN_SCHEMA_CHANGED")
    return dict(json.loads(raw))


def strict_json(raw: bytes) -> dict[str, Any]:
    require(type(raw) is bytes and len(raw) <= MAX_PAYLOAD, "RAW_SIZE")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def nonfinite(value: str) -> Any:
        raise ContractError("NONFINITE_JSON")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("INVALID_JSON") from exc
    require(type(value) is dict, "OBJECT_REQUIRED")
    return dict(value)


def schema_for(stage: str) -> dict[str, Any]:
    require(stage in STAGES, "STAGE")
    book = frozen_schemas()
    return deepcopy(dict(book["schemas"][book["stage_schema"][stage]]))


def bounded_text(value: Any, maximum: int = 4000, empty: bool = False) -> None:
    require(
        type(value) is str and (empty or bool(value)) and len(value) <= maximum,
        "TEXT_BOUND",
    )


def integer(value: Any, low: int, high: int) -> None:
    require(type(value) is int and low <= value <= high, "INTEGER_BOUND")


def make_catalog(spec: Any) -> dict[str, Any]:
    spec = validate_spec(spec)
    example = build_example(spec)
    facts: dict[str, Any] = {}
    for key in QUESTION_KEYS:
        facts["obs_" + key] = dict(
            path="observation." + key,
            value=answer(example, key),
            example_digest=example["payload_digest"],
            origin="deterministic",
        )
    for i, step in enumerate(example["trace"]["steps"]):
        facts[f"trace_step_{i:02d}"] = dict(
            path=f"trace.steps[{i}]",
            value=deepcopy(step),
            example_digest=example["payload_digest"],
            origin="deterministic",
        )
    result = dict(
        version=VERSION,
        spec_id="spec_" + digest(spec)[:24],
        spec_digest=digest(spec),
        example=example,
        facts=facts,
    )
    result["catalog_digest"] = digest(result)
    return result


def verify_catalog(catalog: dict[str, Any]) -> None:
    try:
        expected = make_catalog(catalog["example"]["spec"])
        require(canonical(catalog) == canonical(expected), "CATALOG_BINDING")
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("CATALOG_BINDING") from exc


def validate(
    stage: str,
    value: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
    binding: dict[str, Any] | None = None,
) -> None:
    try:
        raw = canonical(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("JSON_VALUE") from exc
    require(len(raw) <= MAX_PAYLOAD, "PAYLOAD_SIZE")
    require(Draft202012Validator(schema_for(stage)).is_valid(value), "ROLE_SCHEMA")
    if stage.startswith("review_"):
        require(binding is not None, "BINDING_REQUIRED")
        _review(value, binding, stage[-1])
        return
    if stage.startswith("C_"):
        require(catalog is not None, "CATALOG_REQUIRED")
        assert catalog is not None
        verify_catalog(catalog)
    if stage == "C_plan":
        assert catalog is not None
        require(value["spec_id"] == catalog["spec_id"], "SPEC_ID")
        require(
            len(value["objective_ids"]) == 4
            and set(value["objective_ids"]) == set(GOALS),
            "GOAL_COVERAGE",
        )
        return
    require(1 <= len(value["paragraphs"]) <= 8, "PARAGRAPH_BOUND")
    seen: set[str] = set()
    for row in value["paragraphs"]:
        key = row["key"]
        require(re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key) is not None, "KEY")
        require(
            key not in seen and key not in {"code", *("q_" + k for k in QUESTION_KEYS)},
            "DUPLICATE_KEY",
        )
        seen.add(key)
        bounded_text(row["text"])
    for q in value["questions"].values():
        bounded_text(q["stem"])
        bounded_text(q["explanation"])
    if stage.startswith("C_"):
        assert catalog is not None
        for row in [*value["paragraphs"], *value["questions"].values()]:
            refs = row["fact_ids"]
            require(1 <= len(refs) <= 12 and len(set(refs)) == len(refs), "FACT_COUNT")
            require(all(ref in catalog["facts"] for ref in refs), "FACT_ID")
        for key in QUESTION_KEYS:
            require(
                "obs_" + key in value["questions"][key]["fact_ids"], "QUESTION_FACT"
            )
        return
    bounded_text(value["code"], 20000)
    integer(value["answers"]["allocation_failures"], 0, 4)
    require(len(value["answers"]["reachable_prefix"]) <= 7, "PREFIX_BOUND")
    for number in value["answers"]["reachable_prefix"]:
        integer(number, -99, 99)
    _baseline_actions(value)


def _baseline_actions(value: dict[str, Any]) -> None:
    actions = value["actions"]
    states = actions["states"]
    events = [*states, *actions["highlights"], *actions["advances"]]
    require(1 <= len(states) <= 64 and len(events) <= 180, "ACTION_BOUND")
    orders = [event["order"] for event in events]
    require(
        all(type(n) is int for n in orders)
        and sorted(orders) == list(range(len(events))),
        "EVENT_ORDER",
    )
    steps = [state["step"] for state in states]
    require(len(set(steps)) == len(steps), "DUPLICATE_STEP")
    for state in states:
        require(len(state["nodes"]) <= 7, "NODE_BOUND")
        ids = [node["id"] for node in state["nodes"]]
        require(len(set(ids)) == len(ids), "NODE_ID")
        for node in state["nodes"]:
            if node["data_status"] == "indeterminate":
                require(
                    type(node["data"]) is int and node["data"] == 0,
                    "INACTIVE_DATA_SENTINEL",
                )
            else:
                integer(node["data"], -99, 99)
        pointers = [state["caller_head"], state["local_head"], state["p"]] + [
            node["next"] for node in state["nodes"]
        ]
        require(
            all(p in {"none", "indeterminate", *ids} for p in pointers),
            "NODE_REFERENCE",
        )
    for event in events:
        integer(event["step"], 0, 63)
        require(event["step"] in steps, "STEP_REFERENCE")
    for event in actions["highlights"]:
        integer(event["line"], 1, min(600, len(value["code"].splitlines())))


def encode_state(state: dict[str, Any]) -> dict[str, Any]:
    """Representation only. No observation or engine lookup; used in round-trip tests."""
    result = {
        key: ("none" if state[key] is None else state[key])
        for key in ("caller_head", "local_head", "p")
    }
    result["nodes"] = [
        dict(
            id=key,
            data_status="indeterminate" if node["data"] == "indeterminate" else "known",
            data=0 if node["data"] == "indeterminate" else node["data"],
            next="none" if node["next"] is None else node["next"],
        )
        for key, node in sorted(state["nodes"].items())
    ]
    return result


def decode_state(state: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: (None if state[key] == "none" else state[key])
        for key in ("caller_head", "local_head", "p")
    }
    result["nodes"] = {
        node["id"]: dict(
            data="indeterminate"
            if node["data_status"] == "indeterminate"
            else node["data"],
            next=None if node["next"] == "none" else node["next"],
        )
        for node in state["nodes"]
    }
    return result


def decode_actions(value: dict[str, Any], anchor: str) -> list[dict[str, Any]]:
    """Flatten already validated model events, without synthesizing missing states."""
    validate("B_generate", value)
    rows = []
    for state in value["actions"]["states"]:
        rows.append(
            (
                state["order"],
                dict(
                    kind="show_state",
                    anchor=anchor,
                    step=state["step"],
                    state=decode_state(state),
                ),
            )
        )
    for event in value["actions"]["highlights"]:
        rows.append(
            (
                event["order"],
                dict(
                    kind="highlight_code",
                    anchor=anchor,
                    step=event["step"],
                    line=event["line"],
                ),
            )
        )
    for event in value["actions"]["advances"]:
        rows.append(
            (
                event["order"],
                dict(kind="advance_step", anchor=anchor, step=event["step"]),
            )
        )
    return [row for _, row in sorted(rows, key=lambda pair: pair[0])]


def identity(
    run_id: str, slot_id: str, arm: str, revision: int, spec: Any, parent: str | None
) -> dict[str, Any]:
    require(
        all(
            type(v) is str and re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", v)
            for v in (run_id, slot_id)
        ),
        "IDENTITY",
    )
    require(
        arm in ("B", "C") and type(revision) is int and revision in (0, 1), "IDENTITY"
    )
    require(
        (revision == 0 and parent is None)
        or (
            revision == 1
            and type(parent) is str
            and re.fullmatch(r"[a-f0-9]{64}", parent) is not None
        ),
        "PARENT",
    )
    return dict(
        contract_version=VERSION,
        prompt_version="minimal-pilot-prompt-v1",
        run_id=run_id,
        slot_id=slot_id,
        arm=arm,
        revision=revision,
        parent_digest=parent,
        spec_digest=digest(validate_spec(spec)),
    )


def assemble(
    value: dict[str, Any], ident: dict[str, Any], catalog: dict[str, Any] | None = None
) -> dict[str, Any]:
    """B never accepts a reference; C explicitly resolves program-owned facts."""
    arm = ident["arm"]
    require(ident["contract_version"] == VERSION, "IDENTITY_VERSION")
    stage = "C_content" if arm == "C" else "B_generate"
    validate(stage, value, catalog=catalog)
    slot = ident["slot_id"]
    if arm == "C":
        assert catalog is not None
        require(ident["spec_digest"] == catalog["spec_digest"], "SPEC_BINDING")

        # Legacy assembler stays unchanged. These values are program projections, not model echoes.
        def project(row: dict[str, Any]) -> dict[str, Any]:
            return {
                **{k: deepcopy(v) for k, v in row.items() if k != "fact_ids"},
                "fact_refs": [
                    dict(
                        path=catalog["facts"][ref]["path"],
                        value=deepcopy(catalog["facts"][ref]["value"]),
                    )
                    for ref in row["fact_ids"]
                ],
            }

        old = dict(
            paragraphs=[project(p) for p in value["paragraphs"]],
            questions=[
                dict(
                    key="q_" + key,
                    observation_key=key,
                    **project(value["questions"][key]),
                )
                for key in QUESTION_KEYS
            ],
        )
        source = legacy.assemble(
            old, catalog["example"], slot, ident["revision"], ident["parent_digest"]
        )
        legacy.validate_actions(source, catalog["example"])
        source["resolved_facts"] = {
            ref: deepcopy(catalog["facts"][ref])
            for row in [*value["paragraphs"], *value["questions"].values()]
            for ref in row["fact_ids"]
        }
    else:
        require(arm == "B" and catalog is None, "BASELINE_REFERENCE_FORBIDDEN")
        blocks = [
            dict(
                kind="text",
                anchor=f"{slot}:{p['key']}",
                markdown=clean_code_markdown(p["text"]),
            )
            for p in value["paragraphs"]
        ]
        blocks.append(dict(kind="code", anchor=f"{slot}:code", text=value["code"]))
        for key in QUESTION_KEYS:
            q = value["questions"][key]
            a = deepcopy(value["answers"][key])
            if key == "caller_head" and a == "none":
                a = None
            blocks.append(
                dict(
                    kind="question",
                    anchor=f"{slot}:q_{key}",
                    stem=clean_code_markdown(q["stem"]),
                    explanation=clean_code_markdown(q["explanation"]),
                    answer_key=a,
                    observation_key=key,
                )
            )
        source = dict(
            blocks=blocks,
            actions=decode_actions(value, f"{slot}:code"),
            provenance=dict(
                code="model", answers="model", actions="model", content="model"
            ),
            degraded=False,
            production_scoring=False,
        )
    artifact: dict[str, Any] = dict(
        identity=deepcopy(ident), raw_output=deepcopy(value), source=source
    )
    artifact["artifact_digest"] = digest(artifact)
    return artifact


def verify_artifact(artifact: dict[str, Any]) -> None:
    try:
        unsigned = {k: v for k, v in artifact.items() if k != "artifact_digest"}
        require(artifact["artifact_digest"] == digest(unsigned), "ARTIFACT_BINDING")
        require(
            set(artifact) == {"identity", "raw_output", "source", "artifact_digest"},
            "ARTIFACT_SHAPE",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("ARTIFACT_BINDING") from exc


def _targets(source: Any, path: str = "", depth: int = 0) -> dict[str, dict[str, Any]]:
    """Every leaf is covered by itself or an exact projected ancestor; no fields dropped."""
    result: dict[str, dict[str, Any]] = {}

    def walk(node: Any, pointer: str, level: int) -> None:
        action_row = level == 3 and pointer.startswith("/source/actions/")
        if level >= 4 or action_row or not isinstance(node, (dict, list)) or not node:
            target = "target_" + digest(pointer)[:24]
            require(target not in result, "TARGET_COLLISION")
            result[target] = dict(
                path=pointer,
                text=node if type(node) is str else canonical(node).decode(),
                value_digest=digest(node),
                value_type=type(node).__name__,
            )
        elif isinstance(node, list):
            for i, child in enumerate(node):
                walk(child, pointer + "/" + str(i), level + 1)
        else:
            for key, child in sorted(node.items()):
                token = key.replace("~", "~0").replace("/", "~1")
                walk(child, pointer + "/" + token, level + 1)

    walk(source, path, depth)
    return result


def make_binding(artifact: dict[str, Any]) -> dict[str, Any]:
    verify_artifact(artifact)
    result = dict(
        version=VERSION,
        candidate_id="candidate_" + artifact["artifact_digest"][:24],
        candidate_digest=artifact["artifact_digest"],
        artifact=deepcopy(artifact),
        targets=_targets(artifact),
    )
    result["binding_digest"] = digest(result)
    return result


def verify_binding(binding: dict[str, Any]) -> None:
    try:
        expected = make_binding(binding["artifact"])
        require(canonical(binding) == canonical(expected), "REVIEW_BINDING")
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("REVIEW_BINDING") from exc


def _review(value: dict[str, Any], binding: dict[str, Any] | None, arm: str) -> None:
    require(binding is not None, "BINDING_REQUIRED")
    assert binding is not None
    verify_binding(binding)
    require(value["candidate_id"] == binding["candidate_id"], "CANDIDATE_ID")
    require(
        type(binding["artifact"]["identity"]) is dict
        and binding["artifact"]["identity"].get("arm") == arm,
        "REVIEW_ARM",
    )
    verdict = value["verdict"]
    bounded_text(value["uncertainty"], empty=True)
    require((verdict == "unknown") == bool(value["uncertainty"]), "REVIEW_UNCERTAINTY")
    require(len(value["issues"]) <= 20, "ISSUE_BOUND")
    require(verdict != "pass" or not value["issues"], "PASS_ISSUE")
    require(verdict != "revise" or bool(value["issues"]), "REVISE_EMPTY")
    for issue in value["issues"]:
        target = binding["targets"].get(issue["target_id"])
        require(target is not None, "TARGET_ID")
        bounded_text(issue["evidence_quote"])
        bounded_text(issue["reason"])
        require(issue["evidence_quote"] in target["text"], "QUOTE_BINDING")


def review_disposition(value: dict[str, Any]) -> str:
    """Only after validate(review,...). No model opinion is independent truth."""
    if any(
        i["severity"] == "severe" or i["area"] in ("fact", "code_safety")
        for i in value["issues"]
    ):
        return "stop_fact_or_safety"
    return {
        "pass": "advisory_pass",
        "unknown": "stop_unknown",
        "revise": "ordinary_revise",
    }[value["verdict"]]
