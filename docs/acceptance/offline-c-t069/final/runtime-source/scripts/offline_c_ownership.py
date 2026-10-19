"""Reviewed fixed ownership drivers and three approved controlled negatives."""
import json
from pathlib import Path
from offline_c_fixtures import ROOT, FIXTURES, AdmissionError, safe_file, sha

DIRECTORY = Path("docs/acceptance/offline-c-ownership-fixtures")
MANIFEST_SHA256 = "597ce9f8a34d546f6e51b35e415f73bcbad8c829b614b9ce12f71023171a432f"


def check_ownership(root=ROOT):
    raw = safe_file(root, str(DIRECTORY / "manifest.json")).read_bytes()
    if sha(raw) != MANIFEST_SHA256:
        raise AdmissionError("ownership admission changed")
    manifest = json.loads(raw)
    review = safe_file(root, str(DIRECTORY / "review-registry.json")).read_bytes()
    if sha(review) != manifest["review_registry_sha256"]:
        raise AdmissionError("ownership review changed")
    registry = json.loads(review)
    if registry["status"] != "reviewed" or registry["artifacts"] != manifest["artifacts"]:
        raise AdmissionError("unreviewed ownership artifacts")
    for relative, binding in manifest["artifacts"].items():
        raw = safe_file(root, str(DIRECTORY / relative)).read_bytes()
        if sha(raw) != binding["sha256"] or len(raw) != binding["bytes"]:
            raise AdmissionError("ownership artifact changed")
    original = safe_file(root, str(FIXTURES / "edumind/candidate.c")).read_bytes()
    for name, edits in manifest["derivations"].items():
        derived = original
        for before, after in edits:
            if derived.count(before.encode()) != 1:
                raise AdmissionError("ambiguous negative derivation")
            derived = derived.replace(before.encode(), after.encode())
        if safe_file(root, str(DIRECTORY / name)).read_bytes() != derived:
            raise AdmissionError("negative is not the reviewed minimal derivation")
    return manifest
