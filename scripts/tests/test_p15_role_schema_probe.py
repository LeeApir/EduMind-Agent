"""Three-role HTTP Mock only; no real credentials, DNS, models, or teaching claims."""

import asyncio
from copy import deepcopy
import json
import math
import sys

import httpx
import pytest

from scripts import run_p15_role_schema_probe as cli
from scripts.isolated_diagnostics import p15_role_schema_contract as c
from scripts.isolated_diagnostics import p15_role_schema_probe as p

PACKAGE = "c" * 64
KEYS = {"generation": "synthetic-generation-key-only", "review": "synthetic-review-key-only"}


def grant():
    return dict(accepted=True, scope="PHASE-1.5-T078", package_sha256=PACKAGE,
                limits=deepcopy(c.LIMITS), human_message="offline fixture approval", evidence_ref="test only",
                **{k: True for k in p.FLAGS}, window_started_epoch=999.0, deadline_epoch=1299.0)


def response(name, **updates):
    role = c.ROLES[name]
    value = dict(model=p.wire.ROUTES[role]["model"], status="completed", error=None, store=False,
                 reasoning={"effort": p.wire.ROUTES[role]["reasoning"]},
                 usage=dict(input_tokens=100, output_tokens=60, total_tokens=160,
                            output_tokens_details={"reasoning_tokens": 5 if role == "review" else 0}),
                 output=[dict(id="synthetic-message", type="message", role="assistant", status="completed",
                    phase="final_answer", content=[dict(type="output_text", text=json.dumps(c.FIXTURES[name]))])])
    value.update(updates)
    return httpx.Response(200, json=value)


def execute(tmp_path, replies, *, clock=None, resolver=None):
    seen, dns = [], []
    def handler(request):
        item = replies[len(seen)]
        seen.append(request)
        if callable(item):
            return item(request)
        if isinstance(item, Exception):
            raise item
        return item
    def default_dns(host, port):
        dns.append(host)
        return ["1.1.1.1" if host == "aiapi.world" else "8.8.8.8"]
    runner = p.Runner(tmp_path / "out", PACKAGE, grant(), KEYS,
                      clock=clock or (lambda: 1000.0), monotonic=lambda: 500.0)
    result = asyncio.run(runner.run(transport_factory=lambda: httpx.MockTransport(handler),
        resolver=resolver or default_dns))
    return runner, result, seen, dns


def events(output):
    return [json.loads(f.read_bytes()) for f in sorted(output.glob("event-*.json"))]


def rehash(rows):
    previous = None
    for i, row in enumerate(rows):
        row.update(seq=i, previous=previous)
        row.pop("digest", None)
        row["digest"] = p.sha(p.canonical(row))
        previous = row["digest"]
    return rows


def test_all_three_protocols_pass_without_authorizing_course(tmp_path):
    runner, result, seen, dns = execute(tmp_path, [response(n) for n in c.ORDER])
    assert result["outcome"] == "roles_protocol_admitted"
    assert result["admitted_roles"] == result["dispatch_markers"] == len(seen) == 3
    assert result["transport_kinds"] == {"mock": 3}
    assert dns == ["api.deepseek.com", "aiapi.world"]
    assert result["course_requests_authorized"] is result["teaching_evaluated"] is False
    assert result["actual_invoice"] is None and result["unrun_roles"] == 0
    for i, name in enumerate(c.ORDER):
        role = c.ROLES[name]
        assert seen[i].content == c.bodies()[name] == (runner.output / f"{name}-request.json").read_bytes()
        host = "aiapi.world" if role == "review" else "api.deepseek.com"
        assert seen[i].headers["Host"] == seen[i].extensions["sni_hostname"] == host
        assert seen[i].headers["Authorization"] == "Bearer " + KEYS[role]
        assert all(obs["teaching_evaluated"] is False for obs in result["observations"].values())
    assert seen[0].url == seen[1].url
    assert seen[2].url.path == "/v1/responses"
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in runner.output.iterdir())
    with pytest.raises(p.Refused, match="MOCK_NOT_REAL"):
        p.verify_results(runner.output, PACKAGE, grant())


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("failure", [httpx.Response(400, json={"error": "synthetic"}),
    httpx.Response(429), httpx.Response(302, headers={"Location": "https://example.com"}),
    httpx.ConnectError("synthetic"), httpx.ReadTimeout("synthetic")])
def test_each_role_failure_stops_and_preserves_remaining_roles(tmp_path, index, failure):
    replies = [response(n) for n in c.ORDER[:index]] + [failure]
    _, result, seen, _ = execute(tmp_path, replies)
    assert len(seen) == index + 1
    assert result["admitted_roles"] == index
    assert result["outcome"] == "inconclusive_stopped"
    assert result["unrun_roles"] == 2 - index
    assert result["unknown_protocol_or_usage"] == 1


@pytest.mark.parametrize("name", ["S1", "S2", "S3"])
@pytest.mark.parametrize("attack", ["wrong_fixture", "model", "phase", "extra_field", "usage"])
def test_schema_echo_identity_phase_fields_and_usage_remain_strict(tmp_path, name, attack):
    index = c.ORDER.index(name)
    value = response(name).json()
    if attack == "wrong_fixture":
        fixture = deepcopy(c.FIXTURES[name])
        if name == "S1":
            fixture["spec"]["insert_values"] = [1]
        elif name == "S2":
            fixture["paragraphs"][0]["text"] = "Different but schema-valid."
        else:
            fixture["uncertain_reason"] = "Different but schema-valid."
        value["output"][0]["content"][0]["text"] = json.dumps(fixture)
    elif attack == "model":
        value["model"] = "other"
    elif attack == "phase":
        value["output"][0]["phase"] = "commentary"
    elif attack == "extra_field":
        value["output"][0]["unrecognized"] = True
    else:
        value["usage"] = None
    _, result, seen, _ = execute(tmp_path, [response(n) for n in c.ORDER[:index]] + [httpx.Response(200, json=value)])
    assert len(seen) == index + 1 and result["admitted_roles"] == index
    assert result["outcome"] == "inconclusive_stopped"


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("dimension", ["input", "output"])
def test_each_role_reported_token_budget_enforced(tmp_path, index, dimension):
    name = c.ORDER[index]
    value = response(name).json()
    cap = c.CAPS[name][0 if dimension == "input" else 1]
    value["usage"][dimension + "_tokens"] = cap + 1
    value["usage"]["total_tokens"] = value["usage"]["input_tokens"] + value["usage"]["output_tokens"]
    _, result, seen, _ = execute(tmp_path, [response(n) for n in c.ORDER[:index]] + [httpx.Response(200, json=value)])
    assert len(seen) == index + 1 and result["admitted_roles"] == index
    assert result["outcome"] == "inconclusive_stopped"


def test_review_known_suffix_and_bounded_reasoning_are_quarantined(tmp_path):
    value = response("S3").json()
    value["instructions"] = c.INSTRUCTION + p.wire.SUFFIX
    turn = "11111111-2222-3333-4444-555555555555"
    value["output"].insert(0, dict(type="reasoning", summary=[{"type": "summary_text", "text": "synthetic"}],
        metadata={"turn_id": turn}, internal_chat_message_metadata_passthrough={"turn_id": turn}))
    _, result, _, _ = execute(tmp_path, [response("S1"), response("S2"), httpx.Response(200, json=value)])
    obs = result["observations"]["S3"]
    assert obs["known_suffix_observed"] and obs["summary_quarantined"]
    assert obs["opaque_turn_metadata_quarantined"] and not obs["opaque_identity_verified"]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_nonpublic_target_stops_before_http(tmp_path, address):
    _, result, seen, _ = execute(tmp_path, [], resolver=lambda *a: [address])
    assert seen == [] and result["dispatch_markers"] == 0
    assert result["unrun_roles"] == 3 and result["unattempted_roles"] == 2


@pytest.mark.parametrize("flag", ["accepted", *p.FLAGS])
def test_every_new_grant_flag_required(flag):
    g = grant()
    g[flag] = False
    with pytest.raises(p.Refused, match="EXACT_NEW_ROLE_APPROVAL_REQUIRED"):
        p.check_grant(g, PACKAGE, now=1000)


@pytest.mark.parametrize("field,value", [("scope", "PHASE-1.5-T076"), ("package_sha256", "b" * 64),
    ("limits", {}), ("human_message", ""), ("evidence_ref", None)])
def test_old_scope_modified_budget_and_missing_authority_refused(field, value):
    g = grant()
    g[field] = value
    with pytest.raises(p.Refused):
        p.check_grant(g, PACKAGE, now=1000)


@pytest.mark.parametrize("field,value", [("deadline_epoch", math.nan), ("deadline_epoch", 1300),
    ("window_started_epoch", True)])
def test_invalid_new_window_refused(field, value):
    g = grant()
    g[field] = value
    with pytest.raises(p.Refused, match="WINDOW"):
        p.check_grant(g, PACKAGE, now=1000)


@pytest.mark.parametrize("late", [1299.0, 998.0, math.nan])
def test_late_or_rollback_response_cannot_advance(tmp_path, late):
    wall = [1000.0]
    def delayed(request):
        wall[0] = late
        return response("S1")
    _, result, seen, _ = execute(tmp_path, [delayed], clock=lambda: wall[0])
    assert len(seen) == 1 and result["admitted_roles"] == 0
    assert result["outcome"] == "inconclusive_stopped"


@pytest.mark.parametrize("attack", ["remove_validate", "late_validate", "post_stop", "duplicate_sent", "change_gen_ip"])
def test_rehashed_traces_still_require_checks_window_stop_unique_send_and_same_gen_ip(tmp_path, attack):
    runner, _, _, _ = execute(tmp_path, [response(n) for n in c.ORDER])
    rows = events(runner.output)
    if attack == "remove_validate":
        rows = [r for r in rows if not (r["kind"] == "validated" and r["data"]["name"] == "S1")]
    elif attack == "late_validate":
        next(r for r in rows if r["kind"] == "validated")["epoch"] = 1299
    elif attack == "post_stop":
        rows.insert(5, deepcopy(rows[-1]))
    elif attack == "duplicate_sent":
        i = next(i for i, r in enumerate(rows) if r["kind"] == "sent")
        rows.insert(i + 1, deepcopy(rows[i]))
    else:
        pins = [r for r in rows if r["kind"] == "target_pinned"]
        pins[1]["data"]["addresses"] = ["1.1.1.1"]
    with pytest.raises(p.Refused):
        p.replay(rehash(rows), PACKAGE, grant(), c.bodies())


@pytest.mark.parametrize("attack", ["raw", "summary", "permissions", "symlink"])
def test_readonly_result_tampering_refused(tmp_path, attack):
    runner, _, _, _ = execute(tmp_path, [response(n) for n in c.ORDER])
    if attack == "raw":
        (runner.output / "S2-response.bin").write_text("{}")
    elif attack == "summary":
        (runner.output / "summary.json").write_text("{}")
    elif attack == "permissions":
        (runner.output / "S1-response.bin").chmod(0o644)
    else:
        (runner.output / "S1-response.bin").unlink()
        (runner.output / "S1-response.bin").symlink_to(runner.output / "S2-response.bin")
    with pytest.raises(p.Refused):
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False)


def test_no_restart_or_post_terminal_advance(tmp_path):
    runner, _, _, _ = execute(tmp_path, [response(n) for n in c.ORDER])
    with pytest.raises(FileExistsError):
        execute(tmp_path, [])
    with pytest.raises(p.Refused, match="POST_STOP"):
        runner.record("reserved", dict(name="S1", request_sha256=p.sha(c.bodies()["S1"])))


def test_pending_cli_never_loads_credentials_or_creates_output(tmp_path, monkeypatch):
    g = grant()
    g["accepted"] = False
    (tmp_path / "execution-approval.json").write_text(json.dumps(g))
    def forbidden(*a, **kw):
        raise AssertionError("credential reached")
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", tmp_path / "no-output")
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, c.bodies()))
    monkeypatch.setattr(cli, "credential", forbidden)
    monkeypatch.setattr(sys, "argv", ["roles", "--run"])
    assert cli.main() == 2 and not cli.OUTPUT.exists()


@pytest.mark.parametrize("base", ["https://cbbb.fun/v1", "https://openrouter.ai/api/v1", "http://127.0.0.1"])
def test_generic_key_never_falls_back_to_foreign_provider(monkeypatch, base):
    import dotenv
    for name in ("EDUMIND_DEEPSEEK_COMPAT_API_KEY", "EDUMIND_AIAPI_REVIEW_API_KEY",
                 "EDUMIND_PROVIDER_BASE_URL", "EDUMIND_PROVIDER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dotenv, "dotenv_values", lambda *a, **k: {
        "EDUMIND_DEEPSEEK_COMPAT_API_KEY": KEYS["generation"],
        "EDUMIND_PROVIDER_BASE_URL": base, "EDUMIND_PROVIDER_API_KEY": KEYS["review"]})
    with pytest.raises(p.Refused, match="EXACT_CREDENTIALS_REQUIRED"):
        cli.credential()


def test_same_aiapi_generic_key_binding_only(monkeypatch):
    import dotenv
    for name in ("EDUMIND_DEEPSEEK_COMPAT_API_KEY", "EDUMIND_AIAPI_REVIEW_API_KEY",
                 "EDUMIND_PROVIDER_BASE_URL", "EDUMIND_PROVIDER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dotenv, "dotenv_values", lambda *a, **k: {
        "EDUMIND_DEEPSEEK_COMPAT_API_KEY": KEYS["generation"],
        "EDUMIND_PROVIDER_BASE_URL": "https://aiapi.world/v1", "EDUMIND_PROVIDER_API_KEY": KEYS["review"]})
    assert cli.credential() == KEYS


def test_valid_negative_stop_cannot_be_followed_by_rehashed_valid_roles(tmp_path):
    runner, _, _, _ = execute(tmp_path, [response(n) for n in c.ORDER])
    rows = events(runner.output)
    index = next(i for i, row in enumerate(rows)
                 if row["kind"] == "reserved" and row["data"]["name"] == "S2")
    stop = deepcopy(rows[-1])
    stop["data"] = {"outcome": "inconclusive_stopped", "reason": "synthetic_stop"}
    rows.insert(index, stop)
    with pytest.raises(p.Refused, match="POST_STOP"):
        p.replay(rehash(rows), PACKAGE, grant(), c.bodies())


def test_rehashed_non200_control_cannot_advance(tmp_path):
    runner, _, _, _ = execute(tmp_path, [response(n) for n in c.ORDER])
    rows = events(runner.output)
    next(row for row in rows if row["kind"] == "observed")["data"]["status"] = 400
    with pytest.raises(p.Refused, match="VALIDATE_ORDER"):
        p.replay(rehash(rows), PACKAGE, grant(), c.bodies())


def test_late_terminal_does_not_admit_whole_batch_even_with_three_recorded_roles(tmp_path, monkeypatch):
    wall = [1000.0]
    original = p.Runner.record
    def record(runner, kind, data):
        if kind == "terminal" and data.get("outcome") == "roles_protocol_admitted":
            wall[0] = 1299.0
        return original(runner, kind, data)
    monkeypatch.setattr(p.Runner, "record", record)
    _, result, seen, _ = execute(tmp_path, [response(n) for n in c.ORDER], clock=lambda: wall[0])
    assert len(seen) == result["admitted_roles"] == 3
    assert result["outcome"] == "inconclusive_stopped"
    assert result["protocol_admission_complete"] is False
    assert result["course_requests_authorized"] is False


@pytest.mark.parametrize("raw", [b"x" * 65537, KEYS["review"].encode()])
def test_oversize_or_either_provider_secret_response_never_saved_or_advanced(tmp_path, raw):
    runner, result, seen, _ = execute(tmp_path, [httpx.Response(200, content=raw)])
    assert len(seen) == 1 and result["admitted_roles"] == 0
    assert not (runner.output / "S1-response.bin").exists()


@pytest.mark.parametrize("keys", [{"generation": KEYS["generation"]},
    {"generation": KEYS["generation"], "review": ""}])
def test_direct_runner_missing_credentials_refused_before_output(tmp_path, keys):
    runner = p.Runner(tmp_path / "none", PACKAGE, grant(), keys,
                      clock=lambda: 1000.0, monotonic=lambda: 500.0)
    with pytest.raises(p.Refused, match="EXACT_KEYS_REQUIRED"):
        asyncio.run(runner.run())
    assert not runner.output.exists()


@pytest.mark.parametrize("role", ["generation", "review"])
@pytest.mark.parametrize("timeout", [False, True])
def test_dns_child_only_receives_allowed_hostname_and_is_reaped(monkeypatch, role, timeout):
    class Process:
        returncode = None
        killed = False
        done = False
        def __init__(self):
            self.stdout = self
        async def read(self, maximum):
            if timeout:
                raise TimeoutError("synthetic")
            if self.done:
                return b""
            self.done = True
            return b'["8.8.8.8"]'
        async def wait(self):
            self.returncode = -9 if self.killed else 0
            return self.returncode
        def kill(self):
            self.killed = True
    process = Process()
    async def spawn(*args, **kwargs):
        expected = "api.deepseek.com" if role == "generation" else "aiapi.world"
        assert args[-1] == expected and kwargs["env"] == {}
        assert not any(key in repr((args, kwargs)) for key in KEYS.values())
        return process
    monkeypatch.setattr(p.asyncio, "create_subprocess_exec", spawn)
    if timeout:
        with pytest.raises(TimeoutError):
            asyncio.run(p.bounded_target(p.wire.ROUTES[role]["url"], 9.0, None))
        assert process.killed
    else:
        target = asyncio.run(p.bounded_target(p.wire.ROUTES[role]["url"], 9.0, None))
        assert target.url == p.wire.ROUTES[role]["url"]
    assert process.returncode is not None


@pytest.mark.parametrize("url", ["https://cbbb.fun/v1/responses", "http://127.0.0.1/responses"])
def test_foreign_target_never_reaches_dns(url, monkeypatch):
    async def forbidden(*a, **kw):
        raise AssertionError("DNS reached")
    monkeypatch.setattr(p.asyncio, "create_subprocess_exec", forbidden)
    with pytest.raises(p.Refused, match="TARGET_CHANGED"):
        asyncio.run(p.bounded_target(url, 9.0, None))


def test_exact_schema_echo_recognized_without_claiming_enforcement(tmp_path):
    replies = []
    for name in c.ORDER:
        value = response(name).json()
        value["text"] = json.loads(c.bodies()[name])["text"]
        replies.append(httpx.Response(200, json=value))
    _, result, _, _ = execute(tmp_path, replies)
    assert result["protocol_admission_complete"] is True
    assert all(obs["schema_echo"] == "recognized" for obs in result["observations"].values())
    assert all(obs["provider_schema_enforcement_verified"] is False for obs in result["observations"].values())


@pytest.mark.parametrize("name", c.ORDER)
@pytest.mark.parametrize("attack", ["type", "strict", "schema"])
def test_contradictory_format_or_schema_echo_stops(name, attack, tmp_path):
    value = response(name).json()
    echo = deepcopy(json.loads(c.bodies()[name])["text"])
    echo["format"][attack] = {"type": "object"} if attack == "schema" else (False if attack == "strict" else "text")
    value["text"] = echo
    index = c.ORDER.index(name)
    _, result, seen, _ = execute(tmp_path, [response(n) for n in c.ORDER[:index]] + [httpx.Response(200, json=value)])
    assert len(seen) == index + 1 and result["admitted_roles"] == index
    assert result["outcome"] == "inconclusive_stopped"
