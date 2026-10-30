"""Development-only B/C artifact with shared inert reference documents."""

from copy import deepcopy
from typing import Any

from scripts.isolated_diagnostics import p15_agent_pilot as legacy
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_document_v1 as document
from scripts.isolated_diagnostics import p15_review_path_v2 as path_review
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    ENGINE_VERSION,
    TEMPLATE_VERSION,
    answer,
    build_actions,
    digest,
)

VERSION = "isolated-reference-artifact-v1"


def assemble(
    value: dict[str, Any], ident: dict[str, Any], catalog: dict[str, Any] | None
) -> dict[str, Any]:
    arm = ident["arm"]
    c.require(
        ident["contract_version"] == c.VERSION and arm in ("B", "C"), "IDENTITY_VERSION"
    )
    c.validate("C_content" if arm == "C" else "B_generate", value, catalog=catalog)
    c.require(
        (catalog is not None) if arm == "C" else (catalog is None), "ARTIFACT_CATALOG"
    )
    slot = ident["slot_id"]
    docs = {f"paragraph:{p['key']}": p["text"] for p in value["paragraphs"]}
    for key in c.QUESTION_KEYS:
        docs[f"question:{key}:stem"] = value["questions"][key]["stem"]
        docs[f"question:{key}:explanation"] = value["questions"][key]["explanation"]
    representation = document.build(docs)
    blocks = [
        dict(kind="text", anchor=f"{slot}:{p['key']}", document=f"paragraph:{p['key']}")
        for p in value["paragraphs"]
    ]
    code_anchor = f"{slot}:code"
    if arm == "C":
        assert catalog is not None
        c.verify_catalog(catalog)
        c.require(ident["spec_digest"] == catalog["spec_digest"], "SPEC_BINDING")
        example = catalog["example"]

        def project(row: dict[str, Any]) -> dict[str, Any]:
            return {
                **{key: deepcopy(val) for key, val in row.items() if key != "fact_ids"},
                "fact_refs": [
                    dict(
                        path=catalog["facts"][ref]["path"],
                        value=deepcopy(catalog["facts"][ref]["value"]),
                    )
                    for ref in row["fact_ids"]
                ],
            }

        legacy.validate_content(
            dict(
                paragraphs=[project(row) for row in value["paragraphs"]],
                questions=[
                    dict(
                        key="q_" + key,
                        observation_key=key,
                        **project(value["questions"][key]),
                    )
                    for key in c.QUESTION_KEYS
                ],
            ),
            example,
        )
        code = example["code"]["source"]
        actions = build_actions(example, code_anchor)
    else:
        example = None
        code = value["code"]
        actions = c.decode_actions(value, code_anchor)
    blocks.append(dict(kind="code", anchor=code_anchor, text=code))
    for key in c.QUESTION_KEYS:
        result = (
            answer(example, key)
            if example is not None
            else deepcopy(value["answers"][key])
        )
        if key == "caller_head" and result == "none":
            result = None
        blocks.append(
            dict(
                kind="question",
                anchor=f"{slot}:q_{key}",
                stem_document=f"question:{key}:stem",
                explanation_document=f"question:{key}:explanation",
                answer_key=result,
                observation_key=key,
            )
        )
    c.require(len({b["anchor"] for b in blocks}) == len(blocks), "DUPLICATE_ANCHOR")
    source: dict[str, Any] = dict(
        version=VERSION,
        documents=representation,
        blocks=blocks,
        actions=actions,
        provenance=dict(
            code="deterministic" if arm == "C" else "model",
            answers="deterministic" if arm == "C" else "model",
            actions="deterministic" if arm == "C" else "model",
            content="model",
        ),
        degraded=False,
        production_scoring=False,
    )
    if arm == "C":
        assert catalog is not None and example is not None
        source.update(
            example_digest=example["payload_digest"],
            revision=ident["revision"],
            parent_digest=ident["parent_digest"],
            engine_version=ENGINE_VERSION,
            template_version=TEMPLATE_VERSION,
        )
        source["resolved_facts"] = {
            ref: deepcopy(catalog["facts"][ref])
            for row in [*value["paragraphs"], *value["questions"].values()]
            for ref in row["fact_ids"]
        }
        legacy.validate_actions(source, example)
    artifact: dict[str, Any] = dict(
        identity=deepcopy(ident), raw_output=deepcopy(value), source=source
    )
    artifact["artifact_digest"] = digest(artifact)
    return artifact


def verify(artifact: dict[str, Any], catalog: dict[str, Any]) -> None:
    c.verify_artifact(artifact)
    arm = artifact["identity"]["arm"]
    c.verify_catalog(catalog)
    path_review.verify_identity(artifact["identity"], catalog)
    c.require(
        artifact["identity"]["spec_digest"] == catalog["spec_digest"], "SPEC_BINDING"
    )
    c.require(
        assemble(
            artifact["raw_output"],
            artifact["identity"],
            catalog if arm == "C" else None,
        )
        == artifact,
        "ARTIFACT_RECONSTRUCTION",
    )
