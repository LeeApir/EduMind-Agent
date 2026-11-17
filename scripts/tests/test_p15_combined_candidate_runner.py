"""Controlled two-stage tests: all HTTP is MockTransport; no real key or DNS."""

import asyncio
import json
import socket
from copy import deepcopy

import httpx
import pytest

from scripts.isolated_diagnostics import p15_combined_candidate_contract as c
from scripts.isolated_diagnostics import p15_combined_candidate_runner as p
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_combined_candidate_contract import response, value_for

PACKAGE = "a" * 64
KEYS = dict(
    generation="synthetic-generation-key-only", review="synthetic-review-key-only"
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("real DNS/network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def grant():
    return dict(
        accepted=True,
        scope=c.SCOPE,
        package_sha256=PACKAGE,
        limits=deepcopy(c.LIMITS),
        human_message="mock only",
        evidence_ref="mock only",
        window_started_epoch=999.0,
        deadline_epoch=2799.0,
        **{key: True for key in p.FLAGS},
    )


def execute(tmp_path, *, repair=False, fail_at=None, attack=None):
    seen = []
    sequence = list(c.roles.ORDER) + [
        "course_plan",
        "course_content",
        "course_review_0",
    ]
    if repair:
        sequence += ["course_repair", "course_review_1"]

    def handler(request):
        idx = len(seen)
        seen.append(request)
        name = sequence[idx]
        if idx == fail_at and attack == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if idx == fail_at and attack == "status":
            return httpx.Response(400, content=b'{"error":"synthetic"}')
        value = value_for(None, name, request.content, repair)
        raw = json.loads(response(request.content, value))
        if idx == fail_at:
            if attack == "malformed":
                raw["output"][0]["content"][0]["text"] = "{"
            elif attack == "schema":
                raw["text"]["format"]["schema"] = {}
            elif attack == "usage":
                raw["usage"]["input_tokens"] = 8193
                raw["usage"]["total_tokens"] = 8253
            elif attack in ("secret", "secret_escaped", "secret_utf16"):
                raw["extra"] = KEYS["generation"]
        encoded = canonical(raw)
        if idx == fail_at and attack == "secret_utf16":
            encoded = encoded.decode("utf-8").encode("utf-16")
        if idx == fail_at and attack == "secret_escaped":
            key = KEYS["generation"].encode()
            encoded = encoded.replace(key, b"\\u0073" + key[1:])
        return httpx.Response(200, content=encoded)

    runner = p.Runner(
        tmp_path / "out",
        PACKAGE,
        grant(),
        KEYS,
        clock=lambda: 1000.0,
        monotonic=lambda: 500.0,
    )
    result = asyncio.run(
        runner.run(
            transport_factory=lambda: httpx.MockTransport(handler),
            resolver=lambda host, port: [
                "1.1.1.1" if host == "aiapi.world" else "8.8.8.8"
            ],
        )
    )
    return runner, result, seen


@pytest.mark.parametrize("repair", [False, True])
def test_all_roles_then_one_course_with_raw_evidence_and_user_pending(tmp_path, repair):
    runner, result, seen = execute(tmp_path, repair=repair)
    assert len(seen) == (12 if repair else 10)
    assert (
        result["outcome"] == "pending_user_review"
        and result["protocol_admission_complete"]
    )
    assert (
        result["user_evaluation_pending"]
        and not result["repair_success"]
        and not result["formal_pilot_pass"]
    )
    assert result["transport_kinds"] == ["mock"] * len(seen)
    for name, request in zip(result["sent"], seen):
        assert (runner.output / f"{name}-request.json").read_bytes() == request.content
        assert (runner.output / f"{name}-response.bin").is_file()
    assert (
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False) == result
    )
    with pytest.raises(p.Refused, match="MOCK_NOT_REAL"):
        p.verify_results(runner.output, PACKAGE, grant())
    with pytest.raises(FileExistsError):
        asyncio.run(
            runner.run(
                transport_factory=lambda: httpx.MockTransport(
                    lambda req: httpx.Response(200)
                ),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize(
    "attack", ["status", "timeout", "malformed", "schema", "usage", "secret"]
)
def test_all_roles_fail_closed_and_no_course(tmp_path, index, attack):
    _, result, seen = execute(tmp_path, fail_at=index, attack=attack)
    assert len(seen) == index + 1
    assert result["outcome"] == "stopped" and not result["protocol_admission_complete"]
    assert len(result["validated"]) == index
    assert not any(name.startswith("course_") for name in result["sent"])
    assert result["unknown_sent"] == 1


@pytest.mark.parametrize("index", [7, 8, 9, 10, 11])
def test_course_failures_preserve_originals_and_do_not_continue(tmp_path, index):
    runner, result, seen = execute(
        tmp_path, repair=True, fail_at=index, attack="malformed"
    )
    assert result["protocol_admission_complete"] and result["outcome"] == "stopped"
    assert len(seen) == index + 1 and len(result["validated"]) == index
    assert (runner.output / f"{result['sent'][-1]}-response.bin").exists()
    assert (
        not result["user_evaluation_pending"] and not result["real_course_quality_pass"]
    )


def test_scope_and_window_denied_before_directory_and_keys(tmp_path):
    bad = grant()
    bad["accepted"] = False
    runner = p.Runner(
        tmp_path / "out",
        PACKAGE,
        bad,
        {},
        clock=lambda: 1000.0,
        monotonic=lambda: 500.0,
    )
    with pytest.raises(p.Refused, match="APPROVAL_REQUIRED"):
        asyncio.run(runner.run())
    assert not runner.output.exists()
    bad = grant()
    bad["deadline_epoch"] += 1
    with pytest.raises(p.Refused, match="WINDOW_INVALID"):
        p.check_grant(bad, PACKAGE, now=1000.0)


def test_raw_response_tampering_and_event_deletion_are_detected(tmp_path):
    runner, result, _ = execute(tmp_path)
    target = runner.output / f"{result['sent'][0]}-response.bin"
    original = target.read_bytes()
    target.write_bytes(original + b" ")
    with pytest.raises(p.Refused, match="RESPONSE_BINDING"):
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False)
    target.write_bytes(original)
    (runner.output / "event-001.json").unlink()
    with pytest.raises(p.Refused, match="EVENT_GAP"):
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False)


def test_json_escaped_secret_is_not_saved(tmp_path):
    runner, result, seen = execute(tmp_path, fail_at=0, attack="secret_escaped")
    assert len(seen) == 1 and result["outcome"] == "stopped"
    assert not (runner.output / "S1-response.bin").exists()
    assert not any(
        KEYS["generation"].encode() in path.read_bytes()
        for path in runner.output.iterdir()
        if path.is_file()
    )


@pytest.mark.parametrize(
    "kind, delay, expected",
    [("pinned", 10, "COMBINED_DNS_TIMEOUT"), ("observed", 61, "COMBINED_HTTP_TIMEOUT")],
)
def test_replay_rejects_per_request_timeout_even_with_rehashed_event_chain(
    tmp_path, kind, delay, expected
):
    runner, _, _ = execute(tmp_path)
    events = deepcopy(runner.events)
    first = next(i for i, event in enumerate(events) if event["kind"] == kind)
    previous = None
    for index, event in enumerate(events):
        if index >= first:
            event["epoch"] += delay
            event["elapsed"] += delay
        event["previous"] = previous
        event["digest"] = p.sha(
            canonical({k: v for k, v in event.items() if k != "digest"})
        )
        previous = event["digest"]
    with pytest.raises(p.Refused, match=expected):
        p.replay(events, runner.output, PACKAGE, grant())


def test_unreserved_request_file_rejected_for_success(tmp_path):
    runner, _, _ = execute(tmp_path)
    path = runner.output / "course_repair-request.json"
    p.private_write(path, b"{}")
    with pytest.raises(p.Refused, match="UNBOUND_FILES|SUCCESS_FILE_SET"):
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False)


def test_fake_async_http_subclass_never_classified_real(tmp_path):
    class FakeReal(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            return httpx.Response(200, content=b"{}")

    runner = p.Runner(
        tmp_path / "out",
        PACKAGE,
        grant(),
        KEYS,
        clock=lambda: 1000.0,
        monotonic=lambda: 500.0,
    )
    result = asyncio.run(
        runner.run(transport_factory=FakeReal, resolver=lambda *_: ["8.8.8.8"])
    )
    assert result["outcome"] == "stopped"
    assert result["sent"] == [] and result["transport_kinds"] == []


def test_fake_resolver_is_rejected_on_real_path_before_output(tmp_path):
    runner = p.Runner(
        tmp_path / "out",
        PACKAGE,
        grant(),
        KEYS,
        clock=lambda: 1000.0,
        monotonic=lambda: 500.0,
    )
    with pytest.raises(p.Refused, match="REAL_RESOLVER_FORBIDDEN"):
        asyncio.run(runner.run(resolver=lambda *_: ["8.8.8.8"]))
    assert not runner.output.exists()


def test_non_utf8_response_never_saved(tmp_path):
    runner, result, seen = execute(tmp_path, fail_at=0, attack="secret_utf16")
    assert len(seen) == 1 and result["outcome"] == "stopped"
    assert not (runner.output / "S1-response.bin").exists()


@pytest.mark.parametrize("mode", ["--run", "--check-results"])
def test_cli_pending_grant_denies_before_credentials_dns_or_output(
    tmp_path, monkeypatch, mode
):
    import sys
    from scripts import run_p15_combined_candidate as cli

    base = tmp_path / "package"
    base.mkdir()
    (base / "execution-approval.json").write_text(json.dumps({"accepted": False}))
    monkeypatch.setattr(cli, "BASE", base)
    monkeypatch.setattr(cli, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, {}))
    monkeypatch.setattr(cli, "credential", lambda: pytest.fail("credential accessed"))
    monkeypatch.setattr(sys, "argv", ["test", mode])
    assert cli.main() == 2
    assert not cli.OUTPUT.exists()


def test_utf16_without_bom_is_rejected_before_persistence():
    raw = json.dumps({"extra": KEYS["generation"]}).encode("utf-16-le")
    assert json.loads(raw)["extra"] == KEYS["generation"]
    assert p.secret_visible(raw, KEYS) is True
