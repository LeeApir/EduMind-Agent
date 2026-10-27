"""Candidate identity and schema regressions with credentials/network unavailable."""

import importlib.util
import json
import socket
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "check_p15_deepseek_flash_preparation.py"
SPEC = importlib.util.spec_from_file_location("deepseek_prep", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_package_never_reads_credentials_or_network(monkeypatch):
    original = Path.read_text

    def safe_read(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    def refuse(*args, **kwargs):
        pytest.fail("Offline preparation attempted networking")

    monkeypatch.setattr(Path, "read_text", safe_read)
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    assert m.check_package()["real_requests"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "gpt-6.1-sol"),
        ("reasoning", {"effort": "high"}),
        ("stream", True),
        ("max_output_tokens", 8000),
        ("tools", [{"type": "web_search"}]),
    ],
)
def test_changed_candidate_or_outbound_scope_rejected(field, value):
    body = json.loads((m.BASE / "S1.json").read_text())
    body[field] = value
    with pytest.raises(AssertionError):
        m.check_request(body, stream=False, cap=128)


def test_full_local_schema_rejects_wrong_enum_and_extra_fields():
    body = json.loads((m.BASE / "S2.json").read_text())
    validator = m.Draft202012Validator(body["text"]["format"]["schema"])
    valid = {
        "objective_source": "user_requirement",
        "scene_forms": ["text", "exercise"],
        "learner_level": None,
    }
    validator.validate(valid)
    assert list(validator.iter_errors({**valid, "objective_source": "user's words"}))
    assert list(validator.iter_errors({**valid, "scene_forms": ["lecture prose"]}))
    assert list(validator.iter_errors({**valid, "extra": True}))
