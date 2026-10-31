"""Offline sample inventory of old targets; not a complete-domain proof or wire implementation."""

import json
import re
from collections import Counter
from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_reference_review_v1 as review
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC

OUT = Path(__file__).with_name("sample-old-target-inventory.json")


def classify(path: str) -> str:
    if path == "/artifact_digest" or re.fullmatch(
        r"/identity/(arm|contract_version|parent_digest|prompt_version|revision|run_id|slot_id|spec_digest|binding_version|stage|instruction_digest|request_digest|response_digest|receipt_digest|plan_receipt_digest|parent_review_receipt_digest)",
        path,
    ):
        return "identity_and_receipts_program_check"
    if re.fullmatch(r"/raw_output/paragraphs/[0-9]+/(text|key|fact_ids)", path):
        return "paragraph_and_fact_references"
    if re.fullmatch(
        r"/raw_output/questions/(caller_head|traversal_status|reachable_prefix|allocation_failures)/(stem|explanation|fact_ids)",
        path,
    ):
        return "question_and_fact_references"
    if path == "/raw_output/code":
        return "baseline_code"
    if re.fullmatch(
        r"/raw_output/answers/(caller_head|traversal_status|reachable_prefix|allocation_failures)(/[0-9]+)?",
        path,
    ):
        return "baseline_answers"
    if re.fullmatch(
        r"/raw_output/actions(?:/(?:states|highlights|advances)(?:/[0-9]+)?)?", path
    ):
        return "baseline_states_and_actions"
    if re.fullmatch(r"/source/actions(?:/[0-9]+)?", path):
        return "player_actions"
    if re.fullmatch(
        r"/source/blocks/[0-9]+/(kind|anchor|document|text|stem_document|explanation_document|answer_key|observation_key)",
        path,
    ):
        return "block_content_and_bindings"
    if re.fullmatch(
        r"/source/documents/documents(?:/[^/]+(?:/occurrences/[0-9]+/(?:label|kind))?)?",
        path,
    ):
        if "/occurrences/" in path:
            return "occurrence_label_and_kind"
        return "document_ancestor_split"
    if re.fullmatch(r"/source/documents/references(?:/ref_[0-9a-f]{64})?", path):
        return "reference_definition_split"
    if path in ("/source/documents/version", "/source/documents/digest"):
        return "document_version_and_digest_program_check"
    if re.fullmatch(
        r"/source/resolved_facts(?:/[^/]+/(?:path|value|origin|example_digest))?", path
    ):
        return "resolved_fact_and_provenance"
    if re.fullmatch(
        r"/source/provenance/(actions|answers|code|content)", path
    ) or path in (
        "/source/version",
        "/source/engine_version",
        "/source/template_version",
        "/source/example_digest",
        "/source/revision",
        "/source/parent_digest",
        "/source/degraded",
        "/source/production_scoring",
    ):
        return "source_identity_and_provenance"
    raise ValueError(f"unclassified old target: {path}")


def main() -> None:
    for bad in (
        "",
        "/source/not_registered",
        "/unregistered/x",
        "/identity/unregistered",
        "/raw_output/questions/unknown/hidden",
        "/raw_output/paragraphs/0/forged_new_field",
        "/source/actions/invalid/a/b",
        "/source/blocks/0/unknown",
    ):
        try:
            classify(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unregistered path accepted: {bad}")
    catalog = c.make_catalog(SPEC)
    report = {
        "scope": "development examples only; not all legal candidates",
        "arms": {},
    }
    for arm in ("B", "C"):
        for variant in ("without_references", "with_references"):
            value = content() if arm == "C" else b_fixture(SPEC)
            if variant == "with_references":
                value["paragraphs"][0]["text"] = (
                    '`c` [甲"乙][a] [](x)\n\n[a]: https://example.test'
                )
            candidate = artifact.assemble(
                value,
                c.identity("dev", "slot", arm, 0, SPEC, None),
                catalog if arm == "C" else None,
            )
            binding = review.make_binding(candidate)
            rows = [
                {"path": target["path"], "category": classify(target["path"])}
                for target in binding["targets"].values()
            ]
            assert len(rows) == len(binding["targets"]) and len(
                {row["path"] for row in rows}
            ) == len(rows)
            report["arms"][f"{arm}_{variant}"] = {
                "count": len(rows),
                "categories": dict(
                    sorted(Counter(row["category"] for row in rows).items())
                ),
                "targets": rows,
            }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        "B/C development inventory:",
        {arm: data["count"] for arm, data in report["arms"].items()},
    )


if __name__ == "__main__":
    main()
