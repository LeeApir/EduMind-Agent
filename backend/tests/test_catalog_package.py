"""Unreviewed or tampered data never gains publication authority."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from catalog_fixtures import approval_fixture, package_fixture

from app.services.catalog_package import (
    CatalogError,
    content_digest,
    load_package,
    read_json,
    validate_approval,
    validate_package,
)


def test_complete_package_content_schema_is_separate_from_model_prompt() -> None:
    package = package_fixture()
    assert len(package.nodes) == 10 and len(approval_fixture(package)["resources"]) == 30
    assert "prompt_version" not in json.dumps(package.payload())
    assert validate_approval(package, approval_fixture(package), trusted_digest=package.digest)


@pytest.mark.parametrize("change", ["missing", "hash", "script", "code", "questions", "graph"])
def test_invalid_package_fails_closed(change: str) -> None:
    payload = deepcopy(package_fixture().payload())
    nodes, manifest = payload["nodes"], payload["manifest"]
    if change == "missing":
        del nodes["array"]
    elif change == "hash":
        manifest["nodes"]["array"] = "0" * 64
    elif change == "script":
        nodes["array"]["explanation"]["markdown"] = "<script>alert(1)</script>"
        manifest["nodes"]["array"] = content_digest(nodes["array"])
    elif change == "code":
        nodes["array"]["code"]["source"] = 'int main(void){ system("x"); }'
        manifest["nodes"]["array"] = content_digest(nodes["array"])
    elif change == "questions":
        nodes["array"]["exercise"]["items"].pop()
        manifest["nodes"]["array"] = content_digest(nodes["array"])
    else:
        manifest["graph_version"] = "unapproved"
    with pytest.raises(CatalogError):
        validate_package(payload)


@pytest.mark.parametrize("change", ["no_trust", "reviewer", "resources", "digest", "time"])
def test_approval_requires_trusted_digest_and_all_resource_records(change: str) -> None:
    package = package_fixture()
    approval = approval_fixture(package)
    trusted = package.digest
    if change == "no_trust":
        trusted = ""
    elif change == "reviewer":
        approval["reviewer"] = ""
    elif change == "resources":
        approval["resources"] = {}
    elif change == "digest":
        approval["manifest_digest"] = "0" * 64
    else:
        approval["reviewed_at"] = "2026-10-02"
    with pytest.raises(CatalogError):
        validate_approval(package, approval, trusted_digest=trusted)


def test_file_loader_rejects_duplicates_symlinks_and_path_traversal(tmp_path: Path) -> None:
    p = tmp_path / "invalid.json"
    p.write_text('{"x":1,"x":2}')
    with pytest.raises(CatalogError):
        read_json(p)
    (tmp_path / "linked.json").symlink_to(p)
    with pytest.raises(CatalogError):
        read_json(tmp_path / "linked.json")
    (tmp_path / "manifest.json").write_text(json.dumps({"nodes": {"../../.env": "ignored"}}))
    with pytest.raises(CatalogError):
        load_package(tmp_path)
