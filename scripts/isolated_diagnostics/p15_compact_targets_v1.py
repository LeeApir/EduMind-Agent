"""Offline reversible target catalog projection; no network or contract approval."""

from copy import deepcopy
import re
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_review_v1 as review
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

VERSION = "isolated-compact-targets-v1"
OCCURRENCE = re.compile(
    r"^/source/documents/documents/([^/]+)/occurrences/(0|[1-9][0-9]*)/(label|kind)$"
)


def project(binding: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assign short IDs; occurrence paths share a document prefix on the wire."""
    review.verify_binding(binding)
    targets = binding["targets"]
    by_path = {row["path"]: (key, row) for key, row in targets.items()}
    c.require(len(by_path) == len(targets), "DUPLICATE_TARGET_PATH")
    aliases = {
        "t" + str(i): key
        for i, key in enumerate(sorted(targets, key=lambda key: targets[key]["path"]))
    }
    inverse = {key: alias for alias, key in aliases.items()}
    groups: dict[str, list[list[str]]] = {}
    other: dict[str, str] = {}
    for path, (key, _) in by_path.items():
        match = OCCURRENCE.fullmatch(path)
        if match is None:
            other[inverse[key]] = path
            continue
        doc, index, field = match.groups()
        row_index = int(index)
        rows = groups.setdefault(doc, [])
        while len(rows) <= row_index:
            rows.append(["", ""])
        position = 0 if field == "label" else 1
        c.require(not rows[row_index][position], "DUPLICATE_TARGET_PATH")
        rows[row_index][position] = inverse[key]
    c.require(
        all(all(row) for rows in groups.values() for row in rows), "TARGET_COVERAGE"
    )
    wire = dict(
        version=VERSION,
        candidate_id=binding["candidate_id"],
        other=other,
        occurrences=groups,
    )
    local = dict(
        version=VERSION,
        binding_digest=binding["binding_digest"],
        aliases=aliases,
        wire_digest=digest(wire),
    )
    local["mapping_digest"] = digest(local)
    return wire, local


def verify(
    binding: dict[str, Any], wire: dict[str, Any], local: dict[str, Any]
) -> None:
    expected_wire, expected_local = project(binding)
    c.require(
        canonical(wire) == canonical(expected_wire)
        and canonical(local) == canonical(expected_local),
        "COMPACT_TARGET_BINDING",
    )


def translate(
    value: dict[str, Any],
    binding: dict[str, Any],
    wire: dict[str, Any],
    local: dict[str, Any],
) -> dict[str, Any]:
    """Validate aliases against exact binding, then apply unchanged review checks."""
    verify(binding, wire, local)
    arm = binding["artifact"]["identity"]["arm"]
    c.require(len(canonical(value)) <= c.MAX_PAYLOAD, "PAYLOAD_SIZE")
    c.require(
        Draft202012Validator(c.schema_for("review_" + arm)).is_valid(value),
        "ROLE_SCHEMA",
    )
    translated = deepcopy(value)
    for issue in translated.get("issues", []):
        alias = issue.get("target_id")
        c.require(alias in local["aliases"], "UNKNOWN_TARGET_ALIAS")
        issue["target_id"] = local["aliases"][alias]
    review.validate_review(translated, binding, arm)
    return translated
