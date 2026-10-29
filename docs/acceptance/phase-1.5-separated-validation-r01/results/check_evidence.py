"""Read-only T088 evidence verification; never invokes credentials or HTTP execution."""

import json
from pathlib import Path
import re
import socket
from unittest.mock import patch

from scripts import run_p15_separated_probe as cli
from scripts.isolated_diagnostics import p15_separated_probe as probe


def denied(*args, **kwargs):
    raise AssertionError("Evidence check must not read credentials or use network")


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
        assert result["transport_kinds"] == {"real": 6}
        assert result["repair_status"] == "not_run" and result["repair_success"] is False
        index = json.loads((base / "evidence-manifest.json").read_bytes())
        assert {p.name for p in cli.OUTPUT.iterdir()} == {r["name"] for r in index["files"]}
        for row in index["files"]:
            path = Path(row["path"])
            assert path.parent == cli.OUTPUT and path.name == row["name"]
            assert path.stat().st_size == row["bytes"] and cli.sha(path.read_bytes()) == row["sha256"]
        for row in json.loads((base / "response-observations.json").read_bytes())["rows"]:
            if row["name"] == "R0":
                assert row["status"] == "not_run"
                continue
            raw = (cli.OUTPUT / (row["name"] + "-response.bin")).read_bytes()
            response = json.loads(raw)
            text = next(c["text"] for o in response["output"] if o["type"] == "message" for c in o["content"] if c["type"] == "output_text")
            assert (base / row["output_text_file"]).read_bytes() == text.encode()
            assert row["reported_usage"] == response["usage"]
        for target in re.findall(r"\]\(([^)]+)\)", (base / "RESULTS.md").read_text()):
            assert (base / target.split("#", 1)[0]).is_file(), target
    print("T088 evidence verified: 51 originals / 31 events / 6 real HTTP / 5 validated / R0 not run; no new HTTP, no repair success")


if __name__ == "__main__":
    main()
