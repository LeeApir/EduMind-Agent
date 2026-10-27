"""Offline-only DeepSeek candidate packet checks; never read keys or dispatch."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-deepseek-flash-preparation"


def check_request(body, *, stream, cap):
    assert body["model"] == "deepseek-flash"
    assert body["reasoning"] == {"effort": "none"}
    assert body["stream"] is stream and body["max_output_tokens"] == cap
    assert set(body) == {
        "model",
        "instructions",
        "input",
        "reasoning",
        "stream",
        "max_output_tokens",
        "text",
    }
    assert len(json.dumps(body).encode()) < 4096
    fmt = body["text"]["format"]
    assert set(fmt) == {"type", "name", "schema"}
    assert fmt["type"] == "json_schema"
    Draft202012Validator.check_schema(fmt["schema"])


def check_package():
    manifest = json.loads((BASE / "manifest.json").read_text())
    assert manifest["state"] == "offline_preparation_not_execution_authorized"
    assert manifest["url"] == "https://api.deepseek.com/responses"
    assert manifest["model"] == "deepseek-flash"
    assert manifest["real_requests"] == 0
    required = {
        str((BASE / name).relative_to(ROOT)) for name in ("S1.json", "S2.json")
    } | {
        "scripts/check_p15_deepseek_flash_preparation.py",
        "scripts/tests/test_p15_deepseek_flash_preparation.py",
    }
    assert set(manifest["sha256"]) == required
    for name, sha in manifest["sha256"].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    for name, stream, cap in (("S1", False, 128), ("S2", True, 512)):
        check_request(
            json.loads((BASE / f"{name}.json").read_text()), stream=stream, cap=cap
        )
    estimate = (
        Decimal(8192) * Decimal("0.30") + Decimal(640) * Decimal("1.20")
    ) / 1_000_000
    assert estimate == Decimal("0.0032256") < Decimal("0.01")
    return {
        "offline_packet": "passed",
        "real_requests": 0,
        "execution_authorized": False,
    }


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(check_package()))
