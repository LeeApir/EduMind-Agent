"""Admit only the fixed, reviewed C artifacts. This module never executes code."""
from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path("docs/acceptance/offline-c-fixtures")
DESIGN = Path("docs/acceptance/phase-1-fixed-c-design-r01/cases.json")
DESIGN_SHA256 = "21d3c72ffc830824734ad34fc39b2b3543bd489006eec7a6c7a2d19d1cc40aa9"
# Filled when the reviewed package is frozen; a rewritten manifest is not a new admission.
MANIFEST_SHA256 = "59020455441fb55d1231c1f6ef0ff75403ce633895d6c600c38119cd0f6a106b"
SOURCE_IDS = {"edumind-r02-original", "om-original"}
BASE = Path("docs/reference/head-insertion-tests-20261019")
OM_BLOCKS = [(3, "text_PC4lH1c-", "head-functions.c"),
             (4, "text_xl2jWB1X", "print-function.c"),
             (4, "text_lQ4hkvgP", "free-function.c"),
             (4, "text_H9ykoDg9", "main-function.c")]


class AdmissionError(ValueError):
    pass


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts or not part.parts:
        raise AdmissionError("outside fixed package")
    current = root
    for component in part.parts:
        current = current / component
        if current.is_symlink():
            raise AdmissionError("symlink forbidden")
    if not current.is_file() or current.stat().st_nlink != 1:
        raise AdmissionError("ordinary single-link file required")
    if not current.resolve().is_relative_to(root.resolve()):
        raise AdmissionError("outside fixed package")
    return current


def extract_originals(root: Path) -> dict[str, bytes]:
    case = json.loads(safe_file(root, str(BASE / "edumind-r02/complete-review-case.json")).read_bytes())
    candidates = [c for c in case["material"]["candidates"] if c["role"] == "code"]
    if len(candidates) != 1:
        raise AdmissionError("one exact code candidate required")
    source = candidates[0]["envelope"]["content"]["source"].encode("utf-8")
    course = json.loads(safe_file(root, str(BASE / "openmaic/original-manifest.json")).read_bytes())
    with zipfile.ZipFile(safe_file(root, str(BASE / "openmaic/original-course.maic.zip"))) as archive:
        if archive.namelist() != ["manifest.json"] or archive.getinfo("manifest.json").file_size > 1048576:
            raise AdmissionError("unexpected original archive")
        original_manifest = safe_file(root, str(BASE / "openmaic/original-manifest.json")).read_bytes()
        if archive.read("manifest.json") != original_manifest:
            raise AdmissionError("course archive and manifest mismatch")
    blocks = {}
    for scene, element_id, filename in OM_BLOCKS:
        elements = course["scenes"][scene]["content"]["canvas"]["elements"]
        elements = [e for e in elements if e["id"] == element_id and e["type"] == "text"]
        if len(elements) != 1:
            raise AdmissionError("one exact source element required")
        raw = elements[0]["content"]
        # Display normalization only: no C token, alias, signature or newline repair.
        text = html.unescape(re.sub(r"<[^>]+>", "", raw.replace("</p>", "\n")))
        blocks[filename] = text.replace("\xa0", " ").encode("utf-8")
    return {"edumind/candidate.c": source,
            "om/original-program.c": b"\n".join(blocks.values()),
            **{f"om/{name}": value for name, value in blocks.items()}}


def check_manifest(path: Path | None = None, *, root: Path = ROOT) -> dict[str, Any]:
    expected = root / FIXTURES / "manifest.json"
    if path is not None and path.absolute() != expected.absolute():
        raise AdmissionError("only the fixed manifest path is admitted")
    manifest_bytes = safe_file(root, str(FIXTURES / "manifest.json")).read_bytes()
    if sha(manifest_bytes) != MANIFEST_SHA256:
        raise AdmissionError("manifest not the frozen admission")
    manifest = json.loads(manifest_bytes)
    design_manifest = safe_file(root, manifest["design_manifest"]).read_bytes()
    if sha(design_manifest) != manifest["design_manifest_sha256"]:
        raise AdmissionError("approved design manifest changed")
    approval = json.loads(safe_file(root, manifest["approval"]).read_bytes())
    if approval.get("approved") is not True or approval.get("manifest_sha256") != sha(design_manifest):
        raise AdmissionError("specific design approval required")
    design_bytes = safe_file(root, str(DESIGN)).read_bytes()
    if sha(design_bytes) != DESIGN_SHA256:
        raise AdmissionError("approved independent specification changed")
    design = json.loads(design_bytes)
    for relative, evidence in design["sources"].items():
        raw = safe_file(root, relative).read_bytes()
        if sha(raw) != evidence["sha256"] or len(raw) != evidence["bytes"]:
            raise AdmissionError("sealed source changed")
    if set(manifest["sources"]) != SOURCE_IDS:
        raise AdmissionError("unlisted source")
    registry_bytes = safe_file(root, str(FIXTURES / "review-registry.json")).read_bytes()
    if sha(registry_bytes) != manifest["review_registry_sha256"]:
        raise AdmissionError("review registry changed")
    registry = json.loads(registry_bytes)
    if registry["status"] != "reviewed" or not registry["reviewer"] or not registry["reviewed_at"]:
        raise AdmissionError("maintainer review required")
    artifacts = manifest["artifacts"]
    if artifacts != registry["reviewed_artifacts"] or len(artifacts) > 32:
        raise AdmissionError("unreviewed artifact")
    total = 0
    for relative, evidence in artifacts.items():
        if not relative.startswith(("edumind/", "om/", "spec/")):
            raise AdmissionError("unlisted artifact directory")
        raw = safe_file(root, str(FIXTURES / relative)).read_bytes()
        total += len(raw)
        if len(raw) > 1048576 or len(raw) != evidence["bytes"] or sha(raw) != evidence["sha256"]:
            raise AdmissionError("artifact mismatch or size limit")
    if total > 2097152:
        raise AdmissionError("package size limit")
    found = {str(f.relative_to(root / FIXTURES)) for d in ("edumind", "om", "spec")
             for f in (root / FIXTURES / d).rglob("*") if f.is_file() or f.is_symlink()}
    if found != set(artifacts):
        raise AdmissionError("unlisted package file")
    for name, data in extract_originals(root).items():
        if safe_file(root, str(FIXTURES / name)).read_bytes() != data:
            raise AdmissionError("extraction changed original bytes")
    if safe_file(root, str(FIXTURES / "edumind/candidate.c")).read_bytes().endswith(b"\n"):
        raise AdmissionError("historical newline failure was repaired")
    return {"sources": sorted(SOURCE_IDS), "artifacts": len(artifacts), "bytes": total,
            "registry_sha256": sha(registry_bytes), "provider_calls": 0,
            "qualification": "reviewed fixed input only; execution needs separate toolchain/isolation lock"}
