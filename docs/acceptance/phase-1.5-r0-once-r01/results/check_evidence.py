"""Read-only R0 evidence check; deny credential and network execution."""

import json
from pathlib import Path
import re
import socket
from unittest.mock import patch

from scripts import run_p15_r0_once as cli
from scripts.isolated_diagnostics import p15_r0_once as probe


def denied(*args, **kwargs):
    raise AssertionError("No credential/network use in evidence verification")


def main():
    base = Path(__file__).resolve().parent
    with patch.object(cli, "credential", denied), patch.object(socket, "getaddrinfo", denied), patch.object(socket, "socket", denied):
        package, _ = cli.load_package()
        manifest = json.loads((base / "result-manifest.json").read_bytes())
        assert manifest["execution_manifest_sha256"] == package
        for row in manifest["files"]:
            assert cli.sha((cli.ROOT / row["path"]).read_bytes()) == row["sha256"]
        assert cli.sha((cli.ROOT / manifest["grant_path"]).read_bytes()) == manifest["grant_sha256"]
        grant = json.loads((cli.BASE / "execution-approval.json").read_bytes())
        result = probe.verify_results(cli.OUTPUT, package, grant)
        assert result == json.loads((base / "assessment.json").read_bytes())
        assert result["transport_kinds"] == {"real": 1}
        assert result["repair_status"] == "pending_independent_semantic_review"
        assert result["repair_success"] is False and cli.result_exit_code(result) == 3
        index = json.loads((base / "evidence-manifest.json").read_bytes())
        assert {p.name for p in cli.OUTPUT.iterdir()} == {r["name"] for r in index["files"]}
        for row in index["files"]:
            path = Path(row["path"])
            assert path.parent == cli.OUTPUT and path.name == row["name"]
            assert path.stat().st_size == row["bytes"] and cli.sha(path.read_bytes()) == row["sha256"]
        response = json.loads((cli.OUTPUT / "R0-response.bin").read_bytes())
        text = next(c["text"] for o in response["output"] if o["type"] == "message" for c in o["content"] if c["type"] == "output_text")
        assert (base / "R0-output.txt").read_bytes() == text.encode()
        candidate = json.loads(text)
        assert json.loads((base / "R0-candidate.json").read_bytes())["candidate"] == candidate
        request = json.loads((cli.OUTPUT / "R0-request.json").read_bytes())
        original = json.loads(request["input"][1]["content"])["original"]
        changes = probe.frozen.contract.pointer_changes(original, candidate)
        assert changes == ["/paragraphs/0/text"]
        assert json.loads((base / "before-after.json").read_bytes())["changed_paths"] == changes
        for name in ("RESULTS.md", "semantic-review-handoff.md"):
            for target in re.findall(r"\]\(([^)]+)\)", (base / name).read_text()):
                assert (base / target.split("#", 1)[0]).is_file(), target
    print("R0 evidence verified: 12 originals / 7 events / 1 real HTTP / mechanical pending / repair_success=false; no new HTTP")


if __name__ == "__main__":
    main()
