"""Approved immutable graph releases; configuration never grants course authority."""

import hashlib
import json
from functools import lru_cache
from os import getenv
from pathlib import Path

from app.services.knowledge_graph import (
    KnowledgeGraphRepository,
    KnowledgeGraphValidationError,
)

_DATA = Path(__file__).resolve().parents[3] / "data"
_LEGACY_DIGEST = "84ac4c08297623a3a6e167ef9775b67ab195c43048e23be1e2874b26a6f63dc7"
_RELEASE_DIGEST = "6b3063fa05a0cdd34007b09a96618fb318e9a099c376853db13ce0649aa7a264"


def _verified_bytes(path: Path, digest: str) -> bytes:
    try:
        if path.is_symlink():
            raise KnowledgeGraphValidationError("Graph release is unavailable.")
        raw = path.read_bytes()
    except OSError as error:
        raise KnowledgeGraphValidationError("Graph release is unavailable.") from error
    if hashlib.sha256(raw).hexdigest() != digest:
        raise KnowledgeGraphValidationError("Graph release digest mismatch.")
    return raw


@lru_cache(maxsize=8)
def graph_repository_for_version(
    version: str, legacy_path: str | None = None
) -> KnowledgeGraphRepository:
    """Read an approved release once; retain historical versions until process restart."""
    if version == "mvp-0.2.0":
        path = Path(legacy_path) if legacy_path else _DATA / "knowledge_graph.yaml"
        raw = _verified_bytes(path, _LEGACY_DIGEST)
        references = None
    elif version == "phase-1.1.0" and legacy_path is None:
        directory = _DATA / "knowledge"
        manifest = json.loads(
            _verified_bytes(directory / "phase-1.1.0.manifest.json", _RELEASE_DIGEST)
        )
        artifacts = {
            name: _verified_bytes(directory / name, digest)
            for name, digest in manifest["artifacts"].items()
        }
        raw = artifacts["phase-1.1.0.json"]
        references = json.loads(artifacts["phase-1.1.0.sources.json"])
    else:
        raise KnowledgeGraphValidationError("Unknown or conflicting graph configuration.")
    graph = KnowledgeGraphRepository.from_payload(json.loads(raw), reference_payload=references)
    if graph.graph_version != version:
        raise KnowledgeGraphValidationError("Graph release version mismatch.")
    return graph


def configured_graph_repository() -> KnowledgeGraphRepository:
    """Resolve configuration on each request, with no silent fallback on invalid settings."""
    version = getenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "mvp-0.2.0")
    override = getenv("EDUMIND_KNOWLEDGE_GRAPH_PATH") or None
    # Existing container mount may coexist with explicit expansion selection.
    if override and Path(override) == _DATA / "knowledge_graph.yaml":
        override = None
    return graph_repository_for_version(version, override)


def catalog_knowledge_graph_repository() -> KnowledgeGraphRepository:
    """Keep signed catalog validation/enrollment bound to its historical release."""
    return graph_repository_for_version("mvp-0.2.0", None)
