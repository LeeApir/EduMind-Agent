"""Versioned, inert Markdown document projection for isolated experiments.

Original text remains available for evidence. Link/image destinations are stored once
per distinct destination/title; occurrences keep token-tree paths and labels. No HTML,
network access, navigation, or code execution is performed here.
"""

from copy import deepcopy
from typing import Any, cast

import mistune

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest

VERSION = "isolated-reference-document-v1"
ALLOWED = {
    "blank_line",
    "paragraph",
    "heading",
    "thematic_break",
    "block_quote",
    "list",
    "list_item",
    "block_text",
    "text",
    "emphasis",
    "strong",
    "codespan",
    "block_code",
    "softbreak",
    "linebreak",
    "link",
    "image",
    "inline_html",
    "block_html",
}


def _text(node: dict[str, Any]) -> str:
    return (
        str(node.get("raw", ""))
        + ("\n" if node.get("type") in ("linebreak", "softbreak") else "")
        + "".join(_text(child) for child in node.get("children", []))
    )


def build(documents: dict[str, str]) -> dict[str, Any]:
    c.require(type(documents) is dict and 1 <= len(documents) <= 16, "DOCUMENT_COUNT")
    definitions: dict[str, Any] = {}
    result: dict[str, Any] = {}
    parser = mistune.create_markdown(renderer=None, plugins=[])
    for key, raw in sorted(documents.items()):
        c.require(type(key) is str and 1 <= len(key) <= 128, "DOCUMENT_KEY")
        c.bounded_text(raw)
        tokens, state = parser.parse(raw)
        c.require(type(tokens) is list, "DOCUMENT_AST")
        occurrences: list[dict[str, Any]] = []

        def project(
            nodes: list[dict[str, Any]], path: list[int]
        ) -> list[dict[str, Any]]:
            projected = []
            for index, node in enumerate(nodes):
                c.require(
                    type(node) is dict and node.get("type") in ALLOWED, "DOCUMENT_TOKEN"
                )
                position = [*path, index]
                item = {k: deepcopy(v) for k, v in node.items() if k != "children"}
                if "children" in node:
                    c.require(type(node["children"]) is list, "DOCUMENT_CHILDREN")
                    item["children"] = project(node["children"], position)
                if item["type"] in ("link", "image"):
                    attrs = item.get("attrs")
                    c.require(
                        type(attrs) is dict and type(attrs.get("url")) is str,
                        "DOCUMENT_REFERENCE",
                    )
                    attrs = cast(dict[str, Any], attrs)
                    definition = {"url": attrs["url"], "title": attrs.get("title")}
                    c.require(
                        definition["title"] is None or type(definition["title"]) is str,
                        "DOCUMENT_REFERENCE",
                    )
                    ref = "ref_" + digest(definition)
                    c.require(
                        ref not in definitions or definitions[ref] == definition,
                        "DOCUMENT_COLLISION",
                    )
                    definitions[ref] = definition
                    item["attrs"] = {
                        k: v for k, v in attrs.items() if k not in ("url", "title")
                    }
                    item["reference_id"] = ref
                    occurrences.append(
                        {
                            "path": position,
                            "reference_id": ref,
                            "kind": item["type"],
                            "label": "".join(
                                _text(child) for child in item.get("children", [])
                            ),
                        }
                    )
                projected.append(item)
            return projected

        declared: dict[str, Any] = {}
        for name, entry in state.env.get("ref_links", {}).items():
            definition = {"url": entry["url"], "title": entry.get("title")}
            ref = "ref_" + digest(definition)
            c.require(
                ref not in definitions or definitions[ref] == definition,
                "DOCUMENT_COLLISION",
            )
            definitions[ref] = definition
            declared[name] = {"label": entry.get("label"), "reference_id": ref}
        result[key] = {
            "original": raw,
            "tokens": project(cast(list[dict[str, Any]], tokens), []),
            "occurrences": occurrences,
            "declared_references": declared,
        }
    output: dict[str, Any] = {
        "version": VERSION,
        "documents": result,
        "references": definitions,
    }
    output["digest"] = digest(output)
    return output


def verify(value: dict[str, Any]) -> None:
    try:
        documents = {key: item["original"] for key, item in value["documents"].items()}
        c.require(build(documents) == value, "DOCUMENT_BINDING")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise c.ContractError("DOCUMENT_BINDING") from exc


def occurrence_label(
    value: dict[str, Any], key: str, occurrence: dict[str, Any]
) -> str:
    """Resolve a tree path to inert label text; this is not a raw-source offset."""
    docs = value["documents"]
    c.require(
        key in docs and occurrence in docs[key]["occurrences"], "DOCUMENT_OCCURRENCE"
    )
    nodes = docs[key]["tokens"]
    path = occurrence["path"]
    c.require(type(path) is list and bool(path), "DOCUMENT_PATH")
    node: dict[str, Any] = {}
    for depth, index in enumerate(path):
        c.require(
            type(nodes) is list and type(index) is int and 0 <= index < len(nodes),
            "DOCUMENT_PATH",
        )
        node = nodes[index]
        if depth + 1 < len(path):
            nodes = node.get("children")
    c.require(
        node.get("reference_id") == occurrence["reference_id"]
        and node.get("type") == occurrence["kind"],
        "DOCUMENT_OCCURRENCE",
    )

    label = "".join(_text(child) for child in node.get("children", []))
    c.require(label == occurrence["label"], "DOCUMENT_LABEL")
    return label
