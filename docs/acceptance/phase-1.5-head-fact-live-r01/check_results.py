"""Read-only one-call/raw/four-field replay. No Provider or publication."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from cryptography.fernet import Fernet  # noqa: E402
from scripts import head_course_fact_revision as e  # noqa: E402

HERE = Path(__file__).resolve().parent
PREP = ROOT / "docs/acceptance/phase-1.5-head-fact-revision-r01"
SHA = "a96bab6b252feea6e4541d1c869a9643dabbc12164dc35bfb5dee17f51c5e4b3"


def main():
    data = (PREP / "manifest.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA
    # Approved execution tree remains inspectable after authorized post-call publication edits.
    for name, sha in json.loads(data)["files"].items():
        assert (
            hashlib.sha256(
                subprocess.check_output(["git", "show", "7429407:" + name], cwd=ROOT)
            ).hexdigest()
            == sha
        ), name
    v = e.VAULT
    manifest = json.loads((HERE / "originals-manifest.json").read_text())
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((v / name).read_bytes()).hexdigest() == sha, name
    assert (
        (v / "STOP").exists()
        and not (v / "ACTIVE").exists()
        and len(list(v.glob("*.attempt.json"))) == 1
    )
    approval = e.old.read(v / "approval.json")
    window = e.old.read(HERE / "execution-window.json")
    assert (
        approval["explicit_user_authorization"]
        and approval["accept_fact_revision_and_batch_C2"]
    )
    assert approval["manifest_sha256"] == SHA and approval["max_http_requests"] == 1
    assert (
        approval["starts_epoch"] == window["starts_epoch"]
        and approval["expires_epoch"] == window["expires_epoch"]
    )
    assert approval["expires_epoch"] - approval["starts_epoch"] == 600
    raw = e.old.raw_io.decrypt(
        v / "revision.raw.enc", Fernet((v / "raw.key").read_bytes())
    )
    receipt = e.old.read(v / "revision.body.json")
    req = e.old.read(v / "revision.request.json")
    attempt = e.old.read(v / "revision.attempt.json")
    assert receipt == dict(
        http_status=200,
        raw_bytes=len(raw),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        body_complete=True,
    )
    assert len(raw) == 4022 and req == e.f.body() == e.old.read(PREP / "request.json")
    assert (
        attempt["manifest_sha256"] == SHA
        and attempt["evidence_kind"] == "actual_provider_response"
    )
    assert attempt["request_sha256"] == hashlib.sha256(e.canonical(req)).hexdigest()
    result, obs = e.old.raw_io.observe_generation(req, raw)
    output = dict(result.value)
    assert output == e.old.read(v / "revision.output.json")
    parent = e.f.inputs()["parent_candidate"]
    candidate = e.f.merge(parent, output)
    assert candidate == e.old.read(v / "revision.candidate.json")
    assert e.f.assemble(candidate) == e.old.read(v / "revision.assembled.private.json")
    restored = json.loads(json.dumps(candidate["raw_output"]))
    for path in e.f.PATHS.values():
        obj = restored
        original = parent["raw_output"]
        for part in path[:-1]:
            obj = obj[part]
            original = original[part]
        obj[path[-1]] = original[path[-1]]
    assert (
        restored == parent["raw_output"] and candidate["payload"] == parent["payload"]
    )
    for p in v.glob("revision.*.json"):
        assert p.read_bytes() == (HERE / p.name).read_bytes(), p.name
    assert not (v / "revision.failure.json").exists()
    print(
        "PASS: 1 HTTP200, complete encrypted original replay, exact parent/request, only four texts replaced, full assembly, STOP; this audit calls Provider 0 times."
    )


if __name__ == "__main__":
    main()
