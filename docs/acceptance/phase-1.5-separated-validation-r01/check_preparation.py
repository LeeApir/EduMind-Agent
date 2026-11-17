"""Read-only preparation check; deny credentials and network even for pending CLI modes."""

import builtins
import json
import os
from pathlib import Path
import re
import runpy
import socket
import sys
from unittest.mock import patch

from scripts import run_p15_separated_probe as cli
from scripts.isolated_diagnostics import p15_separated_probe as probe


def denied(*args, **kwargs):
    raise AssertionError("FORBIDDEN_CREDENTIAL_OR_NETWORK")


def main():
    read = Path.read_bytes
    original_open = builtins.open
    getenv = os.getenv
    getitem = os._Environ.__getitem__

    def guarded_read(path, *args, **kwargs):
        if path.name == ".env":
            denied()
        return read(path, *args, **kwargs)

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) and Path(file).name == ".env":
            denied()
        return original_open(file, *args, **kwargs)

    def guarded_getenv(key, *args):
        if "API_KEY" in key:
            denied()
        return getenv(key, *args)

    def guarded_getitem(env, key):
        if "API_KEY" in key:
            denied()
        return getitem(env, key)

    with (
        patch.object(cli, "credential", denied),
        patch.object(socket, "getaddrinfo", denied),
        patch.object(socket, "socket", denied),
        patch.object(Path, "read_bytes", guarded_read),
        patch.object(builtins, "open", guarded_open),
        patch.object(os, "getenv", guarded_getenv),
        patch.object(os._Environ, "__getitem__", guarded_getitem),
    ):
        package, bodies = cli.load_package()
        for mode, expected in [("--check", 0), ("--run", 2), ("--check-results", 2)]:
            with patch.object(sys, "argv", ["run_p15_separated_probe.py", mode]):
                assert cli.main() == expected
        runpy.run_path(str(cli.contract.DESIGN / "check_design.py"), run_name="__main__")
        requests = json.loads((cli.BASE / "requests.json").read_bytes())
        assert requests["order"] == list(cli.contract.ORDER)
        assert requests["preparation_only"] is True
        assert [r["name"] for r in requests["requests"]] == list(cli.contract.ORDER)
        for row in requests["requests"]:
            raw = bodies[row["name"]]
            assert row["sha256"] == cli.sha(raw) and row["bytes"] == len(raw)
            assert row["input_reservation"] == 8192
            assert row["max_output_tokens"] == json.loads(raw)["max_output_tokens"] == 4096
        data = json.loads((cli.BASE / "mock-evidence.json").read_bytes())
        assert data["real_provider_calls"] == 0
        total = 0
        for case in data["cases"]:
            directory = Path(case["directory"])
            assert set(p.name for p in directory.iterdir()) == {
                r["name"] for r in case["files"]
            }
            for row in case["files"]:
                raw = (directory / row["name"]).read_bytes()
                assert len(raw) == row["bytes"] and cli.sha(raw) == row["sha256"]
            grant = json.loads((directory / "grant.json").read_bytes())
            result = probe.verify_results(
                directory, grant["package_sha256"], grant, require_real=False
            )
            assert result["repair_success"] is False
            assert result["diagnostic_success"] is False
            assert result["repair_status"] == case["repair_status"]
            assert result["outcome"] == case["outcome"]
            assert result["transport_kinds"] == {"mock": case["mock_requests"]}
            total += result["dispatch_markers"]
        assert len(data["cases"]) == 8 and total == 48
        links = 0
        for target in re.findall(r"\]\(([^)]+)\)", (cli.BASE / "README.md").read_text()):
            if not target.startswith(("https://", "#")):
                assert (cli.BASE / target.split("#", 1)[0]).is_file(), target
                links += 1
    assert not cli.OUTPUT.exists()
    print(json.dumps(dict(
        package_sha256=package, requests=7, mock_cases=8, mock_http=48,
        relative_links=links, pending_cli_exits=[0, 2, 2],
        credentials_read=False, real_provider_calls=0, live_window_started=False,
        repair_success=False, R0_mechanical_pass_never_semantic_success=True,
    )))


if __name__ == "__main__":
    main()
