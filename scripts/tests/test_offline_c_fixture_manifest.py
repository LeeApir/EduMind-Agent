"""Fixed input admission, no compiler, container, model or database used."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from offline_c_fixtures import (  # noqa: E402
    AdmissionError, BASE, DESIGN, FIXTURES, check_manifest, extract_originals, safe_file,
)


@pytest.fixture
def tree(tmp_path):
    shutil.copytree(ROOT / FIXTURES, tmp_path / FIXTURES)
    design = json.loads((ROOT / DESIGN).read_text())
    for relative in [str(DESIGN), "docs/acceptance/phase-1-fixed-c-design-r01/manifest.json",
                     "docs/ADR/0019-approval-20261019.json", *design["sources"]]:
        dest = tmp_path / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, dest)
    # main-function.c is an extraction artifact, already present in the fixed package.
    return tmp_path


def test_reviewed_package_reproduces_original_bytes_and_retains_failures():
    result = check_manifest()
    assert result["sources"] == ["edumind-r02-original", "om-original"]
    assert result["provider_calls"] == 0
    extracted = extract_originals(ROOT)
    assert extracted["edumind/candidate.c"] == (ROOT / BASE / "edumind-r02/candidate.c").read_bytes()
    assert not extracted["edumind/candidate.c"].endswith(b"\n")
    om = extracted["om/original-program.c"]
    assert b"head = insertHead(head, 1)" in om and b"typedef struct Node Node;" not in om
    driver = (ROOT / FIXTURES / "om/function-harness.c").read_bytes()
    assert b"typedef struct Node Node;" in driver
    assert b"insertHead(&head, i)" in driver


@pytest.mark.parametrize("relative", [
    "edumind/candidate.c", "om/original-program.c", "edumind/checks/fault-injection.c",
    "om/function-harness.c", "spec/independent.json", "spec/extraction.json",
])
def test_source_driver_or_spec_tampering_is_rejected(tree, relative):
    path = tree / FIXTURES / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(AdmissionError):
        check_manifest(root=tree)


def test_unreviewed_or_rewritten_registry_is_rejected(tree):
    path = tree / FIXTURES / "review-registry.json"
    value = json.loads(path.read_text())
    value["status"] = "pending"
    path.write_text(json.dumps(value))
    with pytest.raises(AdmissionError, match="registry"):
        check_manifest(root=tree)


def test_rewritten_manifest_cannot_admit_new_source(tree):
    path = tree / FIXTURES / "manifest.json"
    value = json.loads(path.read_text())
    value["sources"]["new-generated-code"] = {}
    path.write_text(json.dumps(value))
    with pytest.raises(AdmissionError, match="frozen admission"):
        check_manifest(root=tree)


def test_undeclared_extra_file_is_rejected(tree):
    (tree / FIXTURES / "edumind/unreviewed.c").write_text("int main(void){return 0;}\n")
    with pytest.raises(AdmissionError, match="unlisted package file"):
        check_manifest(root=tree)


@pytest.mark.parametrize("relative", ["../escape.c", "/tmp/escape.c", "spec/../../escape.c"])
def test_outside_paths_are_rejected(tmp_path, relative):
    with pytest.raises(AdmissionError):
        safe_file(tmp_path, relative)


def test_symlink_and_parent_symlink_and_hardlink_are_rejected(tmp_path):
    original = tmp_path / "real.c"
    original.write_text("original")
    (tmp_path / "link.c").symlink_to(original)
    with pytest.raises(AdmissionError, match="symlink"):
        safe_file(tmp_path, "link.c")
    (tmp_path / "link-dir").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(AdmissionError, match="symlink"):
        safe_file(tmp_path, "link-dir/real.c")
    (tmp_path / "hard.c").hardlink_to(original)
    with pytest.raises(AdmissionError, match="single-link"):
        safe_file(tmp_path, "hard.c")


def test_arbitrary_manifest_and_changed_sealed_source_rejected(tree):
    with pytest.raises(AdmissionError, match="fixed manifest"):
        check_manifest(tree / "other.json", root=tree)
    source = tree / BASE / "edumind-r02/candidate.c"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(AdmissionError, match="sealed source changed"):
        check_manifest(root=tree)


def test_design_approval_cannot_be_assumed(tree):
    approval = tree / "docs/ADR/0019-approval-20261019.json"
    value = json.loads(approval.read_text())
    value["approved"] = False
    approval.write_text(json.dumps(value))
    with pytest.raises(AdmissionError, match="specific design approval"):
        check_manifest(root=tree)
