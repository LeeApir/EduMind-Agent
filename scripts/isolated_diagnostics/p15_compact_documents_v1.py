"""Offline reversible document projection. Not a model-facing contract or authorization."""

from copy import deepcopy
from typing import Any, cast

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_document_v1 as document
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest

VERSION = "isolated-compact-documents-v1"


def pack(value: dict[str, Any]) -> dict[str, Any]:
    document.verify(value)
    refs = sorted(value["references"])
    lookup = {key: i for i, key in enumerate(refs)}

    def compact_node(node: dict[str, Any]) -> dict[str, Any]:
        result = {
            k: deepcopy(v)
            for k, v in node.items()
            if k not in ("children", "reference_id")
        }
        if "children" in node:
            result["children"] = [compact_node(child) for child in node["children"]]
        if "reference_id" in node:
            result["reference_index"] = lookup[node["reference_id"]]
        return result

    docs = {}
    for key, item in value["documents"].items():
        docs[key] = dict(
            original=item["original"],
            tokens=[compact_node(node) for node in item["tokens"]],
            declared_references={
                name: dict(
                    label=row["label"], reference_index=lookup[row["reference_id"]]
                )
                for name, row in item["declared_references"].items()
            },
        )
    return dict(
        version=VERSION,
        original_digest=value["digest"],
        references=[deepcopy(value["references"][key]) for key in refs],
        documents=docs,
    )


def unpack(value: dict[str, Any]) -> dict[str, Any]:
    c.require(
        type(value) is dict
        and set(value) == {"version", "original_digest", "references", "documents"}
        and value["version"] == VERSION,
        "COMPACT_DOCUMENT_SHAPE",
    )
    c.require(
        type(value["references"]) is list and type(value["documents"]) is dict,
        "COMPACT_DOCUMENT_SHAPE",
    )
    references = {"ref_" + digest(row): deepcopy(row) for row in value["references"]}
    refs = sorted(references)
    c.require(
        len(refs) == len(value["references"])
        and [references[key] for key in refs] == value["references"],
        "COMPACT_REFERENCE_ORDER",
    )

    def ref(index: Any) -> str:
        c.require(
            type(index) is int and 0 <= index < len(refs), "COMPACT_REFERENCE_INDEX"
        )
        return cast(str, refs[index])

    docs: dict[str, Any] = {}
    for key, item in value["documents"].items():
        c.require(
            type(item) is dict
            and set(item) == {"original", "tokens", "declared_references"},
            "COMPACT_DOCUMENT_SHAPE",
        )
        occurrences: list[dict[str, Any]] = []

        def expand(
            nodes: list[dict[str, Any]], path: list[int]
        ) -> list[dict[str, Any]]:
            output = []
            for index, node in enumerate(nodes):
                c.require(type(node) is dict, "COMPACT_DOCUMENT_TOKEN")
                pos = [*path, index]
                row = {
                    k: deepcopy(v)
                    for k, v in node.items()
                    if k not in ("children", "reference_index")
                }
                if "children" in node:
                    c.require(type(node["children"]) is list, "COMPACT_DOCUMENT_TOKEN")
                    row["children"] = expand(node["children"], pos)
                if "reference_index" in node:
                    c.require(
                        row.get("type") in ("link", "image"), "COMPACT_DOCUMENT_TOKEN"
                    )
                    row["reference_id"] = ref(node["reference_index"])
                    occurrences.append(
                        dict(
                            path=pos,
                            reference_id=row["reference_id"],
                            kind=row["type"],
                            label="".join(
                                document._text(child)
                                for child in row.get("children", [])
                            ),
                        )
                    )
                output.append(row)
            return output

        tokens = expand(item["tokens"], [])
        declared = {
            name: dict(label=row["label"], reference_id=ref(row["reference_index"]))
            for name, row in item["declared_references"].items()
        }
        docs[key] = dict(
            original=item["original"],
            tokens=tokens,
            occurrences=occurrences,
            declared_references=declared,
        )
    result: dict[str, Any] = dict(
        version=document.VERSION, documents=docs, references=references
    )
    result["digest"] = digest(result)
    c.require(result["digest"] == value["original_digest"], "COMPACT_DOCUMENT_DIGEST")
    document.verify(result)
    c.require(pack(result) == value, "COMPACT_DOCUMENT_CANONICAL")
    return result
