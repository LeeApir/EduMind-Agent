"""Actual release preflight refuses pending, synthetic and unauthorized signatures."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from catalog_fixtures import approval_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_catalog_review import render  # noqa: E402
from verify_catalog_release import ROOT, verify  # noqa: E402

from app.services.catalog_package import load_package  # noqa: E402


def test_pending_review_is_not_publishable_and_preview_escapes_c():
    directory = ROOT / "data/course_catalog/linear-v1"
    package = load_package(directory)
    assert verify(directory, package.digest)["publishable"] is False
    preview = render()
    assert package.digest in preview
    assert "尚未作为正式课程发布" in preview
    assert "<script" not in preview and "&lt;stdio.h&gt;" in preview
    assert preview.count("<h3>固定练习及反馈</h3>") == 10
    assert preview.count("标准答案：") == 30
    with pytest.raises(ValueError, match="not authorized"):
        verify(directory, "0" * 64)


def test_test_only_approval_never_qualifies_as_actual_human_review(tmp_path):
    directory = tmp_path / "course"
    shutil.copytree(ROOT / "data/course_catalog/linear-v1", directory)
    package = load_package(directory)
    (directory / "approval.json").write_text(json.dumps(approval_fixture(package)))
    with pytest.raises(ValueError, match="Synthetic approval"):
        verify(directory, package.digest)
