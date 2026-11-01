"""Per-target old-to-visible migration report; offline and not an HTTP receipt proof."""

import re
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_review_v1 as old_review
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest

VERSION = "visible-migration-report-v1"


def build(artifact: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    view, binding = visible.build(artifact, catalog)
    old = old_review.make_binding(artifact)
    by_path: dict[str, list[str]] = {}
    for short, loc in binding["paths"].items():
        if loc["root"] == "artifact":
            by_path.setdefault(loc["pointer"], []).append(short)
    cells = {row["id"]: row for row in view["cells"]}
    source, raw = artifact["source"], artifact["raw_output"]
    code_idx = next(
        i for i, block in enumerate(source["blocks"]) if block["kind"] == "code"
    )
    code_path = f"/source/blocks/{code_idx}/text"
    checks = {
        "ARTIFACT_RECONSTRUCTION": "executed_by_visible_build",
        "CATALOG_BINDING": "executed_by_visible_build",
        "DOCUMENT_RECONSTRUCTION": "executed_by_visible_build",
        "IDENTITY_SHAPE": "executed_by_visible_build",
        "RECEIPT_AND_PARENT_CHAIN": "pending_controlled_http",
    }

    def document_text_path(doc: str) -> str:
        if doc.startswith("paragraph:"):
            key = doc.removeprefix("paragraph:")
            index = next(
                i for i, row in enumerate(raw["paragraphs"]) if row["key"] == key
            )
            return f"/raw_output/paragraphs/{index}/text"
        match = re.fullmatch(
            r"question:(caller_head|traversal_status|reachable_prefix|allocation_failures):(stem|explanation)",
            doc,
        )
        c.require(match is not None, "MIGRATION_DOCUMENT")
        assert match is not None
        return f"/raw_output/questions/{match.group(1)}/{match.group(2)}"

    rows = []
    for old_id, target in old["targets"].items():
        path = target["path"]
        ids = list(by_path.get(path, []))
        check_ids: list[str] = []
        relation = "direct" if ids else "program"
        if path == "/artifact_digest":
            check_ids = ["ARTIFACT_RECONSTRUCTION", "RECEIPT_AND_PARENT_CHAIN"]
        elif re.fullmatch(
            r"/identity/(arm|contract_version|parent_digest|prompt_version|revision|run_id|slot_id|spec_digest|binding_version|stage|instruction_digest|request_digest|response_digest|receipt_digest|plan_receipt_digest|parent_review_receipt_digest)",
            path,
        ):
            check_ids = ["IDENTITY_SHAPE", "RECEIPT_AND_PARENT_CHAIN"]
        elif path == "/raw_output/code":
            ids, check_ids, relation = (
                list(by_path.get(code_path, [])),
                ["ARTIFACT_RECONSTRUCTION"],
                "split",
            )
        elif re.fullmatch(r"/raw_output/paragraphs/[0-9]+/key", path):
            index = int(path.split("/")[3])
            ids = ids or list(by_path.get(f"/source/blocks/{index}", []))
            check_ids = ["ARTIFACT_RECONSTRUCTION"]
            relation = "direct" if by_path.get(path) else "split"
        elif re.fullmatch(r"/raw_output/answers/reachable_prefix/[0-9]+", path):
            ids = ids or list(by_path.get("/raw_output/answers/reachable_prefix", []))
            check_ids = ["ARTIFACT_RECONSTRUCTION"]
            relation = "direct" if by_path.get(path) else "split"
        elif re.fullmatch(
            r"/source/blocks/[0-9]+/(kind|anchor|document|text|stem_document|explanation_document|answer_key|observation_key)",
            path,
        ):
            block = int(path.split("/")[3])
            if path.endswith("/text"):
                ids = list(by_path.get(code_path, []))
            elif not ids:
                ids = list(by_path.get(f"/source/blocks/{block}", []))
            check_ids = ["ARTIFACT_RECONSTRUCTION"]
            relation = (
                "direct"
                if by_path.get(path) and not path.endswith("/text")
                else "split"
            )
        elif re.fullmatch(r"/source/documents/documents/[^/]+", path):
            doc = path.split("/")[-1].replace("~1", "/").replace("~0", "~")
            ids = list(by_path.get(document_text_path(doc), []))
            prefix = path + "/"
            ids += [
                short
                for pointer, found in by_path.items()
                if pointer.startswith(prefix)
                for short in found
            ]
            doc_value = source["documents"]["documents"][doc]
            refs = {row["reference_id"] for row in doc_value["occurrences"]}
            refs.update(
                row["reference_id"] for row in doc_value["declared_references"].values()
            )
            for ref in sorted(refs):
                ref_path = "/source/documents/references/" + ref
                for suffix in ("", "/url", "/title"):
                    ids.extend(by_path.get(ref_path + suffix, []))
            ids = list(dict.fromkeys(ids))
            check_ids, relation = ["DOCUMENT_RECONSTRUCTION"], "split"
        elif re.fullmatch(
            r"/source/documents/documents/[^/]+/occurrences/[0-9]+/(label|kind)", path
        ):
            # A label and its parser-derived kind are different source fields,
            # even when both contain the same text. Never alias one to the other.
            check_ids = ["DOCUMENT_RECONSTRUCTION"]
            relation = "direct" if ids else "program"
        elif re.fullmatch(r"/source/documents/references/ref_[0-9a-f]{64}", path):
            ids = (
                list(by_path.get(path, []))
                + list(by_path.get(path + "/url", []))
                + list(by_path.get(path + "/title", []))
            )
            check_ids, relation = ["DOCUMENT_RECONSTRUCTION"], "split"
        elif re.fullmatch(
            r"/source/resolved_facts/[^/]+/(path|origin|example_digest)", path
        ):
            check_ids = ["CATALOG_BINDING"]
            # A shared digest inside the parent object cannot identify which
            # fact supplied it; retain it as a program check instead.
            relation = "direct" if ids else "program"
        elif path in (
            "/source/documents/digest",
            "/source/documents/version",
            "/source/documents/references",
            "/source/resolved_facts",
            "/source/documents/documents",
        ):
            check_ids = [
                "DOCUMENT_RECONSTRUCTION"
                if "/documents/" in path
                else "CATALOG_BINDING"
            ]
        elif re.fullmatch(
            r"/source/(version|engine_version|template_version|example_digest|revision|parent_digest|degraded|production_scoring|provenance/(actions|answers|code|content))",
            path,
        ):
            check_ids = ["ARTIFACT_RECONSTRUCTION", "RECEIPT_AND_PARENT_CHAIN"]
            if path.startswith("/source/provenance/"):
                ids = ids or list(by_path.get("/source/provenance", []))
                relation = (
                    "direct" if by_path.get(path) else "split" if ids else "program"
                )
        elif ids:
            check_ids = ["ARTIFACT_RECONSTRUCTION"]
        else:
            raise c.ContractError("MIGRATION_UNCLASSIFIED:" + path)
        c.require(bool(ids) or bool(check_ids), "MIGRATION_EMPTY")
        c.require(all(short in cells for short in ids), "MIGRATION_TARGET")
        rows.append(
            dict(
                old_id=old_id,
                old_path=path,
                relation=relation,
                visible_ids=ids,
                program_checks=check_ids,
                old_quote_rule="exact_only_if_actual_visible_target_contains_quote",
            )
        )
    report = dict(
        version=VERSION,
        candidate_digest=artifact["artifact_digest"],
        old_binding_digest=old["binding_digest"],
        view_digest=binding["view_digest"],
        checks=checks,
        targets=rows,
    )
    report["report_digest"] = digest(report)
    return report


def classify_quote(
    artifact: dict[str, Any], catalog: dict[str, Any], old_id: str, quote: str
) -> dict[str, Any]:
    """Recompute the migration; do not infer that an unquoted old substring survives."""
    c.bounded_text(quote)
    report = build(artifact, catalog)
    old = old_review.make_binding(artifact)
    c.require(old_id in old["targets"], "MIGRATION_OLD_TARGET")
    c.require(quote in old["targets"][old_id]["text"], "MIGRATION_OLD_QUOTE")
    row = next(item for item in report["targets"] if item["old_id"] == old_id)
    view, _ = visible.build(artifact, catalog)
    cells = {cell["id"]: cell for cell in view["cells"]}
    matches = [short for short in row["visible_ids"] if quote in cells[short]["text"]]
    # A substring in a split child can also occur elsewhere inside the old
    # ancestor.  Do not assert an exact old-field migration from value alone.
    status = (
        "visible"
        if matches and row["relation"] == "direct"
        else "split_requires_source_review"
        if matches
        else "program_only"
        if row["relation"] == "program"
        else "split_not_quotable"
    )
    return dict(
        status=status,
        visible_ids=matches,
        report_digest=report["report_digest"],
        note="offline view only; actual HTTP visibility and provenance pending",
    )
