"""Data-only course package validation; hashes are integrity, not review authority."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from app.agents.learning_resource_schema import ResourceSchemaError, validate_resource_content
from app.services.knowledge_graph import default_knowledge_graph_repository

CATALOG_SCHEMA_VERSION = "catalog-content-v1"
KINDS = ("explanation", "code", "exercise")
MAX_FILE_BYTES = 256 * 1024


class CatalogError(ValueError):
    def __init__(self, code: str = "CATALOG_INVALID") -> None:
        self.code = code
        super().__init__(code)


def content_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CatalogError()
    return cast(dict[str, object], value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise CatalogError()
    return dict(pairs)


def read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise CatalogError()
    try:
        return json.loads(path.read_text(), object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(CatalogError()))
    except (ValueError, UnicodeError, RecursionError, OSError):
        raise CatalogError() from None


@dataclass(frozen=True)
class CatalogPackage:
    manifest: dict[str, object]
    nodes: dict[str, dict[str, object]]
    demo: dict[str, object]

    @property
    def digest(self) -> str:
        return content_digest(self.manifest)

    def payload(self) -> dict[str, object]:
        return {"manifest": self.manifest, "nodes": self.nodes, "demo": self.demo}


def validate_package(payload: object) -> CatalogPackage:
    outer = _object(payload, {"manifest", "nodes", "demo"})
    manifest = _object(outer["manifest"], {"schema_version", "package_id", "version",
        "graph_version", "nodes", "demo_digest", "templates"})
    graph = default_knowledge_graph_repository()
    expected_ids = {node.id for node in graph.all_nodes()}
    if (manifest["schema_version"] != CATALOG_SCHEMA_VERSION
            or manifest["graph_version"] != graph.graph_version
            or not all(isinstance(manifest[k], str) and re.fullmatch(r"[a-z0-9.-]{1,40}",
                cast(str, manifest[k])) for k in ("package_id", "version"))):
        raise CatalogError()
    entries = manifest["nodes"]
    if not isinstance(entries, dict) or set(entries) != expected_ids:
        raise CatalogError()
    nodes = _object(outer["nodes"], expected_ids)
    validated: dict[str, dict[str, object]] = {}
    for node_id, value in nodes.items():
        content = _object(value, set(KINDS))
        try:
            checked = {kind: validate_resource_content(kind, content[kind]) for kind in KINDS}
        except ResourceSchemaError:
            raise CatalogError() from None
        exercise = checked["exercise"]
        code = checked["code"]
        if (code["language"] != "C" or len(cast(list[object], exercise["items"])) != 3
                or content_digest(value) != entries[node_id]):
            raise CatalogError()
        if re.search(r"<\s*(script|iframe)|javascript\s*:", json.dumps(value), re.I):
            raise CatalogError()
        source = cast(str, code["source"])
        if re.search(r"\b(system|exec[lvpe]*|popen|fopen|socket|connect)\s*\(", source):
            raise CatalogError()
        validated[node_id] = cast(dict[str, object], checked)
    demo = _object(outer["demo"], {"title", "perspectives", "summary"})
    if (content_digest(demo) != manifest["demo_digest"]
            or not isinstance(demo["title"], str) or not isinstance(demo["summary"], str)
            or not isinstance(demo["perspectives"], list) or len(demo["perspectives"]) != 3):
        raise CatalogError()
    for item in demo["perspectives"]:
        p = _object(item, {"title", "text"})
        if not all(isinstance(v, str) and v.strip() for v in p.values()):
            raise CatalogError()
    if re.search(r"<\s*(script|iframe)|javascript\s*:", json.dumps(demo), re.I):
        raise CatalogError()
    from app.services.animation_templates import load_template
    templates = manifest["templates"]
    if not isinstance(templates, dict) or set(templates) != {"linked-list-insertion",
                                                           "linked-list-deletion"}:
        raise CatalogError()
    for key, version in templates.items():
        spec = load_template(key, require_executable=True)
        if spec.template_version != version:
            raise CatalogError()
    return CatalogPackage(manifest, validated, demo)


def load_package(directory: Path) -> CatalogPackage:
    manifest = read_json(directory / "manifest.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("nodes"), dict):
        raise CatalogError()
    ids = manifest["nodes"]
    if any(not re.fullmatch(r"[a-z0-9-]{1,64}", str(n)) for n in ids):
        raise CatalogError()
    return validate_package({"manifest": manifest,
        "nodes": {node_id: read_json(directory / f"{node_id}.json") for node_id in ids},
        "demo": read_json(directory / "demo.json")})


def validate_approval(
    package: CatalogPackage, value: object, *, trusted_digest: str
) -> dict[str, object]:
    approval = _object(value, {"manifest_digest", "reviewer", "reviewed_at", "resources",
                              "demo_digest", "basis"})
    expected = {f"{node}:{kind}": content_digest(payload[kind])
                for node, payload in package.nodes.items() for kind in KINDS}
    try:
        reviewed_at = datetime.fromisoformat(cast(str, approval["reviewed_at"]))
    except (ValueError, TypeError):
        raise CatalogError("CATALOG_APPROVAL_INVALID") from None
    if (not trusted_digest or trusted_digest != package.digest
            or approval["manifest_digest"] != trusted_digest or approval["resources"] != expected
            or approval["demo_digest"] != package.manifest["demo_digest"]
            or reviewed_at.tzinfo is None
            or not all(isinstance(approval[k], str) and cast(str, approval[k]).strip()
                       for k in ("reviewer", "basis"))):
        raise CatalogError("CATALOG_APPROVAL_INVALID")
    return approval
