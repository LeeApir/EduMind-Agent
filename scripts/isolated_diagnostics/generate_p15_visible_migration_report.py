"""Generate per-target reports for two labelled synthetic development examples."""

from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_reference_review_v1 as old_review
from scripts.isolated_diagnostics import p15_visible_migration_v1 as migration
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/acceptance/phase-1.5-visible-migration-t102"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog = c.make_catalog(SPEC)
    for arm in ("B", "C"):
        value = content() if arm == "C" else b_fixture(SPEC)
        value["paragraphs"][0]["text"] += (
            "\n\n[引用][ref] 和 [相同文字][ref]。\n\n"
            "[ref]: https://example.test '示例标题'\n"
            "[unused]: https://unused.example.test"
        )
        candidate = artifact.assemble(
            value,
            c.identity("development", "slot", arm, 0, SPEC, None),
            catalog if arm == "C" else None,
        )
        report = migration.build(candidate, catalog)
        (OUTPUT / f"{arm.lower()}-target-report.json").write_bytes(
            canonical(report) + b"\n"
        )
        view, binding = visible.build(candidate, catalog)
        sources = {
            "scope": "synthetic development example, not an evaluated experimental sample",
            "old_targets": old_review.make_binding(candidate)["targets"],
            "visible_view": view,
            "visible_binding": binding,
        }
        (OUTPUT / f"{arm.lower()}-target-sources.json").write_bytes(
            canonical(sources) + b"\n"
        )
        print(f"{arm}: {len(report['targets'])} old targets; {report['report_digest']}")


if __name__ == "__main__":
    main()
