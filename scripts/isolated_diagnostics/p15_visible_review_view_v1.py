"""ADR-0049 isolated visible-view prototype. No HTTP, credentials or scoring."""

import re
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from scripts.isolated_diagnostics import p15_agent_pilot as legacy
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as pilot
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact_module
from scripts.isolated_diagnostics import p15_review_path_v2 as path_review
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

VERSION = "visible-review-view-v1"


def build(
    artifact: dict[str, Any], catalog: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build visible cells from a reconstructed candidate; only C states use engine trace."""
    artifact_module.verify(artifact, catalog)
    source, raw = artifact["source"], artifact["raw_output"]
    arm = artifact["identity"]["arm"]
    docs = source["documents"]
    cells: list[dict[str, str]] = []
    paths: dict[str, Any] = {}
    context = legacy.review_context(catalog["example"])
    config = {
        "goals": list(c.GOALS),
        "question_definitions": pilot.QUESTION_DEFINITIONS,
    }
    roots = {
        "artifact": artifact,
        "catalog": catalog,
        "context": context,
        "config": config,
    }
    reference_ids = {
        ref: f"r{index}" for index, ref in enumerate(sorted(docs["references"]))
    }
    split_cache: dict[tuple[str, str], list[str]] = {}

    def add(
        kind: str,
        value: Any,
        path: str,
        origin: str,
        *,
        plain: bool = False,
        root: str = "artifact",
        projection: dict[str, Any] | None = None,
    ) -> None:
        c.require(root in roots, "VISIBLE_SOURCE_ROOT")
        original = path_review.pointer_value(roots[root], path)
        rule = projection or {"type": "identity"}
        operation = rule["type"]
        if operation == "identity":
            reconstructed = original
        elif operation == "block_metadata":
            reconstructed = {
                key: item for key, item in original.items() if key != "text"
            }
        elif operation == "splitline_text_v1":
            cache_key = (root, path)
            if cache_key not in split_cache:
                split_cache[cache_key] = original.splitlines()
            reconstructed = split_cache[cache_key][rule["index"]]
        elif operation == "reference_declarations":
            reconstructed = {
                "document": rule["document"],
                "declarations": {
                    name: {
                        "label": row["label"],
                        "reference_id": reference_ids[row["reference_id"]],
                    }
                    for name, row in original.items()
                },
            }
        elif operation == "reference_occurrence":
            reconstructed = {
                "document": rule["document"],
                "ordinal": rule["index"],
                "reference_id": reference_ids[original["reference_id"]],
                "kind": original["kind"],
                "label": original["label"],
            }
        elif operation == "reference_definition":
            reconstructed = {
                "reference_id": reference_ids[rule["reference_id"]],
                **original,
            }
        else:
            raise c.ContractError("VISIBLE_PROJECTION")
        c.require(reconstructed == value, "VISIBLE_SOURCE_VALUE")
        text = value if plain else canonical(value).decode()
        c.require(type(text) is str, "VISIBLE_TEXT")
        short = f"t{len(cells)}"
        cells.append(dict(id=short, kind=kind, text=text, origin=origin))
        paths[short] = {"root": root, "pointer": path, "projection": rule}

    add(
        "original_goal",
        context["original_goal"],
        "/original_goal",
        "context",
        plain=True,
        root="context",
    )
    add(
        "plan_constraints",
        context["plan_constraints"],
        "/plan_constraints",
        "context",
        root="context",
    )
    add("upstream", context["upstream"], "/upstream", "context", root="context")
    add("goals", list(c.GOALS), "/goals", "context", root="config")
    add(
        "question_definitions",
        pilot.QUESTION_DEFINITIONS,
        "/question_definitions",
        "context",
        root="config",
    )
    add(
        "source_provenance",
        source["provenance"],
        "/source/provenance",
        "representation",
    )
    add("degraded", source["degraded"], "/source/degraded", "representation")
    for field, value in sorted(source["provenance"].items()):
        add(
            "provenance_field",
            value,
            f"/source/provenance/{field}",
            "representation",
            plain=True,
        )
    for index, block in enumerate(source["blocks"]):
        metadata = {key: value for key, value in block.items() if key != "text"}
        add(
            "block_binding",
            metadata,
            f"/source/blocks/{index}",
            "representation",
            projection={"type": "block_metadata"},
        )
        for field, value in sorted(block.items()):
            if field not in ("text", "answer_key"):
                add(
                    "block_field",
                    value,
                    f"/source/blocks/{index}/{field}",
                    "representation",
                    plain=type(value) is str,
                )

    for index, paragraph in enumerate(raw["paragraphs"]):
        add(
            "paragraph",
            paragraph["text"],
            f"/raw_output/paragraphs/{index}/text",
            "model",
            plain=True,
        )
        add(
            "paragraph_key",
            paragraph["key"],
            f"/raw_output/paragraphs/{index}/key",
            "model",
            plain=True,
        )
        if arm == "C":
            add(
                "paragraph_fact_ids",
                paragraph["fact_ids"],
                f"/raw_output/paragraphs/{index}/fact_ids",
                "model",
            )
    code_index = next(
        i for i, block in enumerate(source["blocks"]) if block["kind"] == "code"
    )
    code = source["blocks"][code_index]["text"]
    # Match the existing action validator's splitlines() semantics without losing terminators.
    lines = code.splitlines(keepends=True)
    line_texts = code.splitlines()
    c.require("".join(lines) == code, "CODE_ROUNDTRIP")
    c.require(len(lines) == len(line_texts), "CODE_ROUNDTRIP")
    for index, (line, line_text) in enumerate(zip(lines, line_texts)):
        c.require(line.startswith(line_text), "CODE_ROUNDTRIP")
        add(
            "code_line",
            line_text,
            f"/source/blocks/{code_index}/text",
            source["provenance"]["code"],
            plain=True,
            projection={"type": "splitline_text_v1", "index": index},
        )
        cells[-1]["line_ending"] = line[len(line_text) :]

    for key in c.QUESTION_KEYS:
        question = raw["questions"][key]
        block_index = next(
            i
            for i, block in enumerate(source["blocks"])
            if block.get("observation_key") == key
        )
        block = source["blocks"][block_index]
        add(
            "question_stem",
            question["stem"],
            f"/raw_output/questions/{key}/stem",
            "model",
            plain=True,
        )
        answer = block["answer_key"] if arm == "C" else raw["answers"][key]
        add(
            "question_answer",
            answer,
            f"/source/blocks/{block_index}/answer_key"
            if arm == "C"
            else f"/raw_output/answers/{key}",
            source["provenance"]["answers"],
        )
        if arm == "B":
            add(
                "display_answer",
                block["answer_key"],
                f"/source/blocks/{block_index}/answer_key",
                "representation",
            )
            if key == "reachable_prefix":
                for item_index, item in enumerate(answer):
                    add(
                        "answer_item",
                        item,
                        f"/raw_output/answers/{key}/{item_index}",
                        "model",
                    )
        add(
            "question_explanation",
            question["explanation"],
            f"/raw_output/questions/{key}/explanation",
            "model",
            plain=True,
        )
        if arm == "C":
            add(
                "question_fact_ids",
                question["fact_ids"],
                f"/raw_output/questions/{key}/fact_ids",
                "model",
            )

    if arm == "C":
        for index, state in enumerate(catalog["example"]["trace"]["steps"]):
            add(
                "state",
                state,
                f"/example/trace/steps/{index}",
                "deterministic",
                root="catalog",
            )
    else:
        for index, action in enumerate(source["actions"]):
            if action["kind"] == "show_state":
                add(
                    "state",
                    action["state"],
                    f"/source/actions/{index}/state",
                    "model_projection",
                )
    for index, action in enumerate(source["actions"]):
        add(
            "action",
            action,
            f"/source/actions/{index}",
            "model_projection" if arm == "B" else source["provenance"]["actions"],
        )
    if arm == "B":
        for group in ("states", "highlights", "advances"):
            if not raw["actions"][group]:
                add(
                    "model_raw_" + group + "_empty",
                    [],
                    f"/raw_output/actions/{group}",
                    "model",
                )
            for index, action in enumerate(raw["actions"][group]):
                add(
                    "model_raw_" + group,
                    action,
                    f"/raw_output/actions/{group}/{index}",
                    "model",
                )
    else:
        add(
            "resolved_facts",
            source["resolved_facts"],
            "/source/resolved_facts",
            "deterministic",
        )
        for ref, fact in sorted(source["resolved_facts"].items()):
            token = ref.replace("~", "~0").replace("/", "~1")
            add(
                "resolved_fact_value",
                fact["value"],
                f"/source/resolved_facts/{token}/value",
                "deterministic",
            )
            for field in ("path", "origin"):
                add(
                    "resolved_fact_provenance",
                    fact[field],
                    f"/source/resolved_facts/{token}/{field}",
                    "deterministic",
                    plain=True,
                )

    for key in sorted(docs["documents"]):
        doc = docs["documents"][key]
        token = key.replace("~", "~0").replace("/", "~1")
        declarations = {
            name: {
                "label": row["label"],
                "reference_id": reference_ids[row["reference_id"]],
            }
            for name, row in doc["declared_references"].items()
        }
        add(
            "reference_declarations",
            {"document": key, "declarations": declarations},
            f"/source/documents/documents/{token}/declared_references",
            "parser",
            projection={"type": "reference_declarations", "document": key},
        )
        for index, occurrence in enumerate(doc["occurrences"]):
            # Local ordinal identifies the parser occurrence; never a raw byte offset.
            target_field = "label" if occurrence["label"] else "kind"
            add(
                "reference_occurrence",
                occurrence[target_field],
                f"/source/documents/documents/{token}/occurrences/{index}/{target_field}",
                "parser",
                plain=True,
            )
            cells[-1].update(
                document=key,
                ordinal=str(index),
                reference_id=reference_ids[occurrence["reference_id"]],
                reference_kind=occurrence["kind"],
                label=occurrence["label"],
            )
    for ref in sorted(docs["references"]):
        definition = docs["references"][ref]
        add(
            "reference_definition",
            {"reference_id": reference_ids[ref], **definition},
            f"/source/documents/references/{ref}",
            "parser",
            projection={"type": "reference_definition", "reference_id": ref},
        )
        add(
            "reference_url",
            definition["url"],
            f"/source/documents/references/{ref}/url",
            "parser",
            plain=True,
        )
        add(
            "reference_title",
            definition["title"],
            f"/source/documents/references/{ref}/title",
            "parser",
            plain=type(definition["title"]) is str,
        )

    # The original reference is sent in full and independently addressable.
    add(
        "reference_example",
        catalog["example"],
        "/example",
        "deterministic",
        root="catalog",
    )
    for index, state in enumerate(catalog["example"]["trace"]["steps"]):
        add(
            "reference_state",
            state,
            f"/example/trace/steps/{index}",
            "deterministic",
            root="catalog",
        )
    for key in c.QUESTION_KEYS:
        add(
            "reference_observation",
            catalog["example"]["observation"][key],
            f"/example/observation/{key}",
            "deterministic",
            root="catalog",
        )
    candidate_id = "candidate_" + artifact["artifact_digest"][:24]
    view = dict(
        version=VERSION,
        candidate_id=candidate_id,
        arm=arm,
        slot_id=artifact["identity"]["slot_id"],
        revision=artifact["identity"]["revision"],
        cells=cells,
    )
    binding = dict(
        version=VERSION,
        candidate_digest=artifact["artifact_digest"],
        view_digest=digest(view),
        paths=paths,
    )
    binding["binding_digest"] = digest(binding)
    return view, binding


def validate_review(
    value: dict[str, Any],
    sent_view: bytes,
    artifact: dict[str, Any],
    catalog: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    """Reject any quote not in the exact parsed view; this does not authenticate HTTP."""
    c.require(type(sent_view) is bytes, "VISIBLE_REQUEST")
    view = wire.strict_json(sent_view)
    c.require(type(view) is dict, "VISIBLE_REQUEST")
    expected, expected_binding = build(artifact, catalog)
    c.require(
        canonical(view) == sent_view
        and view == expected
        and binding == expected_binding,
        "VISIBLE_BINDING",
    )
    arm = artifact["identity"]["arm"]
    c.require(
        len(canonical(value)) <= c.MAX_PAYLOAD
        and Draft202012Validator(c.schema_for("review_" + arm)).is_valid(value),
        "ROLE_SCHEMA",
    )
    c.require(value["candidate_id"] == view["candidate_id"], "CANDIDATE_ID")
    verdict = value["verdict"]
    c.bounded_text(value["uncertainty"], empty=True)
    c.require(
        (verdict == "unknown") == bool(value["uncertainty"]), "REVIEW_UNCERTAINTY"
    )
    c.require(
        len(value["issues"]) <= 20
        and (verdict != "pass" or not value["issues"])
        and (verdict != "revise" or bool(value["issues"])),
        "REVIEW_ISSUES",
    )
    for issue in value["issues"]:
        identifier = issue["target_id"]
        c.require(
            type(identifier) is str
            and re.fullmatch(r"t(?:0|[1-9][0-9]*)", identifier) is not None,
            "TARGET_ID",
        )
        index = int(identifier[1:])
        c.require(
            index < len(view["cells"]) and view["cells"][index]["id"] == identifier,
            "TARGET_ID",
        )
        c.bounded_text(issue["evidence_quote"])
        c.bounded_text(issue["reason"])
        c.require(
            issue["evidence_quote"] in view["cells"][index]["text"], "QUOTE_BINDING"
        )
