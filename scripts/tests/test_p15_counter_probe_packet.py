"""Proposal boundaries, not real counter behavior."""

import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_p15_counter_probe_packet import BASE, check  # noqa: E402


@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network or credentials allowed")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


def test_frozen_counter_only_proposal():
    check()


@pytest.mark.parametrize(
    "field,value",
    [
        ("url", "https://www.cbbb.fun/v1/responses"),
        ("generation_requests_max", 1),
        ("http_requests_max", 3),
        ("retries", 1),
        ("real_execution_available", True),
        ("T038_remains_blocked", False),
    ],
)
def test_tampered_authority_or_scope_rejected(tmp_path, field, value):
    base = tmp_path / BASE
    shutil.copytree(ROOT / BASE, base)
    path = base / "packet.json"
    packet = json.loads(path.read_text())
    packet[field] = value
    path.write_text(json.dumps(packet))
    # Even if a caller recomputes hashes, semantic scope changes remain refused.
    import hashlib

    manifest_path = base / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = {
        str(BASE / "packet.json"): hashlib.sha256(path.read_bytes()).hexdigest()
    }
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(AssertionError):
        check(tmp_path)
