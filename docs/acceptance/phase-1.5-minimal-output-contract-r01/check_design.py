"""Offline checks for static proposal examples only; no runtime adapter or provider entry."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
KEYS = ("caller_head", "traversal_status", "reachable_prefix", "allocation_failures")
GOALS = ("trace_head", "trace_termination", "trace_values", "trace_failures")


def load(path):
    return json.loads(path.read_text())


def require(condition, code):
    if not condition:
        raise ValueError(code)


def text(value, limit=4000, empty=False):
    require(
        type(value) is str and (empty or len(value) > 0) and len(value) <= limit,
        "TEXT_BOUND",
    )


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, "INTEGER_BOUND")


def local_check(role, value, context):
    """Proposed local rules demonstrated on handwritten cases; not a production validator."""
    if role == "C_plan":
        require(value["spec_id"] == context["spec_id"], "SPEC_ID")
        require(
            len(value["objective_ids"]) == 4
            and set(value["objective_ids"]) == set(GOALS),
            "GOAL_COVERAGE",
        )
        return
    if role.startswith("review_"):
        require(value["candidate_id"] == context["candidate_id"], "CANDIDATE_BINDING")
        text(value["uncertainty"], empty=True)
        v = value["verdict"]
        require((v == "unknown") == bool(value["uncertainty"]), "UNCERTAINTY")
        require(len(value["issues"]) <= 20, "ISSUE_BOUND")
        require(v != "pass" or not value["issues"], "PASS_ISSUE")
        require(v != "revise" or bool(value["issues"]), "REVISE_EMPTY")
        for issue in value["issues"]:
            target = context["review_targets"].get(issue["target_id"])
            require(target is not None, "TARGET_ID")
            text(issue["evidence_quote"])
            text(issue["reason"])
            require(issue["evidence_quote"] in target, "QUOTE_BINDING")
        return
    require(1 <= len(value["paragraphs"]) <= 8, "PARAGRAPH_BOUND")
    seen = set()
    for row in value["paragraphs"]:
        key = row["key"]
        require(re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key) is not None, "KEY")
        require(
            key not in seen and key not in {"code", *("q_" + k for k in KEYS)},
            "DUPLICATE_KEY",
        )
        seen.add(key)
        text(row["text"])
    for q in value["questions"].values():
        text(q["stem"])
        text(q["explanation"])
    if role.startswith("C_"):
        for row in [*value["paragraphs"], *value["questions"].values()]:
            refs = row["fact_ids"]
            require(1 <= len(refs) <= 12 and len(set(refs)) == len(refs), "REF_COUNT")
            require(all(ref in context["fact_catalog"] for ref in refs), "FACT_ID")
        for key in KEYS:
            require(
                context["question_fact_ids"][key]
                in value["questions"][key]["fact_ids"],
                "QUESTION_FACT",
            )
        return
    text(value["code"], 20000)
    a = value["answers"]
    integer(a["allocation_failures"], 0, 4)
    require(len(a["reachable_prefix"]) <= 7, "PREFIX_BOUND")
    for number in a["reachable_prefix"]:
        integer(number, -99, 99)
    actions = value["actions"]
    states = actions["states"]
    events = [*states, *actions["highlights"], *actions["advances"]]
    require(1 <= len(states) <= 64 and len(events) <= 180, "ACTION_BOUND")
    orders = [e["order"] for e in events]
    require(
        all(type(v) is int for v in orders)
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
                require(node["data"] == 0, "INACTIVE_DATA_SENTINEL")
            else:
                integer(node["data"], -99, 99)
        pointers = [state["caller_head"], state["local_head"], state["p"]] + [
            node["next"] for node in state["nodes"]
        ]
        require(
            all(ptr in {"none", "indeterminate", *ids} for ptr in pointers),
            "NODE_REFERENCE",
        )
    for event in events:
        integer(event["step"], 0, 63)
        require(event["step"] in steps, "STEP_REFERENCE")
    for event in actions["highlights"]:
        integer(event["line"], 1, min(600, len(value["code"].splitlines())))


def main():
    contract = load(BASE / "schemas.json")
    schemas = contract["schemas"]
    context = load(BASE / "context-example.json")
    examples = load(BASE / "examples.json")["cases"]
    # Audit all schema positions, including nested objects/arrays, with no remote inference.
    from scripts.isolated_diagnostics import (
        p15_agent_pilot as c,
        p15_pilot_baseline as b,
    )
    from scripts.isolated_diagnostics.p15_schema_audit import audit_schema, schema_nodes

    native = {
        "B_generate": b.SCHEMA,
        "C_plan": c.PLAN_SCHEMA,
        "C_content": c.CONTENT_SCHEMA,
        "review": c.REVIEW_SCHEMA,
    }
    audit = load(BASE / "original-schema-audit.json")["roles"]
    for role, schema in native.items():
        require(audit[role]["native"] == schema, "NATIVE_SNAPSHOT_CHANGED")
        require(audit[role]["audit"] == audit_schema(schema), "AUDIT_CHANGED")
        require(
            set(audit[role]["all_keyword_locations"])
            == {
                k
                for _, node in schema_nodes(schema)
                if isinstance(node, dict)
                for k in node
            },
            "INCOMPLETE_KEYWORD_AUDIT",
        )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        for _, node in schema_nodes(schema):
            if type(node) is bool:
                require(node is False, "OPEN_BOOLEAN_SCHEMA")
                continue
            require(
                set(node) <= set(contract["wire_keyword_allowlist"]), "WIRE_KEYWORD"
            )
            require(type(node.get("type")) is str, "NON_EXPLICIT_TYPE")
            if node["type"] == "object":
                require(
                    node.get("additionalProperties") is False
                    and set(node["required"]) == set(node["properties"]),
                    "OBJECT_CLOSURE",
                )
            if node["type"] == "array":
                require(isinstance(node.get("items"), dict), "ARRAY_ITEMS")
    counts = Counter()
    for case in examples:
        schema = schemas[contract["stage_schema"][case["role"]]]
        schema_ok = Draft202012Validator(schema).is_valid(case["payload"])
        local_ok = False
        if schema_ok:
            try:
                local_check(case["role"], case["payload"], context)
                local_ok = True
            except ValueError:
                pass
        if case["expected"] == "reject":
            require(not local_ok, "UNEXPECTED_ACCEPT_" + case["id"])
            require(case["layer"] != "schema" or not schema_ok, "WRONG_FAILURE_LAYER")
        else:
            require(local_ok, "UNEXPECTED_REJECT_" + case["id"])
        counts[case["expected"]] += 1
    require(len({c["id"] for c in examples}) == len(examples), "DUPLICATE_CASE")
    require(
        set(contract["stage_schema"]) == {c["role"] for c in examples}, "STAGE_COVERAGE"
    )
    fixtures = load(BASE / "protocol-fixtures.json")["fixtures"]
    require(set(fixtures) == set(contract["stage_schema"]), "FIXTURE_COVERAGE")
    for stage, value in fixtures.items():
        Draft202012Validator(schemas[contract["stage_schema"][stage]]).validate(value)
        local_check(stage, value, context)
    plan = load(BASE / "compatibility-plan.json")
    require(
        len(plan["requests"]) == plan["limits"]["http_requests"] == 7, "REQUEST_COUNT"
    )
    require(
        sum(x["max_output_tokens"] for x in plan["requests"])
        == plan["limits"]["output_reservation"]
        == 16896,
        "OUTPUT_BUDGET",
    )
    require(plan["limits"]["input_reservation"] == 7 * 8192, "INPUT_BUDGET")
    require(
        {r["stage"] for r in plan["requests"]} == set(contract["stage_schema"]),
        "PROBE_STAGE_COVERAGE",
    )
    # Old frozen manifests are read only, including old source and result dependencies.
    old_manifests = [
        "phase-1.5-schema-compatibility/probe-p01/manifest.json",
        "phase-1.5-schema-compatibility/probe-p02/manifest.json",
        "phase-1.5-schema-compatibility/role-probe-r01/manifest.json",
        "phase-1.5-schema-compatibility/union-proposal-r01/manifest.json",
        "phase-1.5-schema-compatibility/union-probe-p01/manifest.json",
    ]
    pins = 0
    for name in old_manifests:
        manifest = load(ROOT / "docs/acceptance" / name)
        for item in manifest["files"]:
            require(
                hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
                == item["sha256"],
                "OLD_FROZEN_CHANGED_" + item["path"],
            )
            pins += 1
    manifest = load(BASE / "manifest.json")
    for item in [*manifest["files"], *manifest["source_pins"]]:
        require(
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            == item["sha256"],
            "PROPOSAL_HASH_" + item["path"],
        )
    require(
        not manifest["implementation_approved"]
        and manifest["real_http_authorized"] == 0,
        "DESIGN_ONLY",
    )
    # Documentation references and Markdown relative targets are checked without network.
    checked_links = 0
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                require(
                    (path.parent / target.split("#")[0]).exists(),
                    "MISSING_LINK_" + target,
                )
                checked_links += 1
    print(
        json.dumps(
            {
                "result": "passed_design_only",
                "distinct_native_schemas": len(native),
                "native_schema_positions": sum(
                    a["audit"]["schema_node_count"] for a in audit.values()
                ),
                "distinct_proposed_schemas": len(schemas),
                "logical_model_stages": 6,
                "protocol_contexts": len(contract["stage_schema"]),
                "examples": len(examples),
                "case_results": dict(counts),
                "old_manifest_entries_verified": pins,
                "frozen_proposal_files": len(manifest["files"]),
                "source_pins": len(manifest["source_pins"]),
                "relative_links_checked": checked_links,
                "real_provider_calls": 0,
                "semantic_correctness_proven": False,
                "independent_evaluation": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
