"""Read-only two-count proposal checker. No credentials, network or start/advance command."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("docs/acceptance/phase-1.5-counter-probe-c01")


def check(root=ROOT):
    base = root / BASE
    manifest = json.loads((base / "manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
    packet = json.loads((base / "packet.json").read_text())
    assert packet["status"] == "proposal_not_authorization"
    assert packet["url"] == "https://www.cbbb.fun/v1/responses/input_tokens"
    assert packet["method"] == "POST"
    assert packet["http_requests_max"] == 2 and packet["generation_requests_max"] == 0
    assert packet["retries"] == packet["redirects"] == 0
    assert packet["seconds_max_each"] == 10 and packet["wall_seconds_max"] == 20
    assert packet["response_bytes_max_each"] == 4096
    assert packet["fee"]["waiver_approved"] is False
    assert packet["fee"]["inherits_previous_waiver"] is False
    assert packet["fee"]["currency"] is packet["fee"]["amount_cap"] is None
    assert packet["real_execution_available"] is False
    assert packet["T038_remains_blocked"] is True
    assert packet["requests"] == [
        {"id": "C01", "body": "C01-messages.json"},
        {"id": "C02", "body": "C02-instructions.json"},
    ]
    a, b = [json.loads((base / r["body"]).read_bytes()) for r in packet["requests"]]
    assert "instructions" not in a
    assert b["instructions"] == "\n\n".join(m["content"] for m in a["input"][:-1])
    assert a["input"][:-1] == [
        {"role": "system", "content": "Counter probe: no tools, files, or network."},
        {
            "role": "system",
            "content": "Only synthetic input; do not infer learner facts.",
        },
    ]
    assert (
        b["input"] == a["input"][-1:] == [{"role": "user", "content": "Reply with OK."}]
    )
    assert {k: v for k, v in a.items() if k != "input"} == {
        k: v for k, v in b.items() if k not in {"input", "instructions"}
    }
    for body in (a, b):
        assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "none"}
        assert body["store"] is body["stream"] is False
        assert body["max_output_tokens"] == 16 and body["service_tier"] == "default"
        assert body["text"]["format"]["strict"] is True
        assert set(body) <= {
            "model",
            "reasoning",
            "store",
            "stream",
            "max_output_tokens",
            "service_tier",
            "text",
            "input",
            "instructions",
        }
    print(
        "Counter-only proposal verified: <=2 HTTP / 0 generation; no execution authority"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    check()


if __name__ == "__main__":
    main()
