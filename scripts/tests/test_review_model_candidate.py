"""Offline-only routing/material/budget validation; no independent model quality claim."""

# ruff: noqa: E402
import json
import socket
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import prepare_review_model_candidate as p
from app.services.learning_policy import active_policy_digest


@pytest.fixture(scope="module")
def prepared():
    return p.build()


def test_screen_inputs_prompt_schema_and_materials_unchanged(prepared):
    old = p.read(ROOT / p.PRIOR / "cases.json")
    for slot in p.SCREEN:
        c = deepcopy(prepared["cases.json"][slot])
        raw = bytes.fromhex(c.pop("candidate_wire_hex"))
        assert c == old[slot]
        body = json.loads(raw)
        before = json.loads(bytes.fromhex(c["wire_hex"]))
        assert body["messages"] == before["input"]
        assert (
            body["response_format"]["json_schema"]["schema"]
            == before["text"]["format"]["schema"]
        )
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["model"] == "qwen3.8-max-0902" and not body["enable_thinking"]
        assert body["max_completion_tokens"] == 8192 and "max_tokens" not in body


def test_router_captures_both_review_and_generation_models(prepared):
    captures = prepared["offline-capture.json"]
    assert captures["generation-control"]["actual_model"] == "deepseek-flash"
    assert captures["generation-control"]["candidate_review_sends"] == 0
    for slot in prepared["cases.json"]:
        assert captures[slot]["actual_model"] == "qwen3.8-max-0902"
        assert captures[slot]["generation_sends"] == 0
        assert captures[slot]["policy_digest"] == active_policy_digest()
        assert captures[slot]["wire_sha256"] == p.sha(
            bytes.fromhex(prepared["cases.json"][slot]["candidate_wire_hex"])
        )


def test_no_env_dns_or_nonmock_http(monkeypatch, prepared):
    reader = Path.read_text
    bytes_reader = Path.read_bytes

    def safe_text(path, *a, **k):
        assert path.name != ".env"
        return reader(path, *a, **k)

    def safe_bytes(path, *a, **k):
        assert path.name != ".env"
        return bytes_reader(path, *a, **k)

    monkeypatch.setattr(Path, "read_text", safe_text)
    monkeypatch.setattr(Path, "read_bytes", safe_bytes)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS"))
    import httpx

    async def reject_network(*a, **k):
        pytest.fail("real HTTP")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", reject_network
    )
    assert p.build() == prepared


def test_budget_one_candidate_two_gated_phases_and_overrun(prepared):
    proposal = prepared["proposal.json"]
    config = proposal["config"]
    assert config["candidate_count_max"] == 1 and config["requests_max"] == 12
    assert (
        config["output_request_limit"] == 8192
        and config["output_reserve_limit"] == 8202
    )
    assert config["input_price_micro_cny_per_million"] == 12000000
    assert config["output_price_micro_cny_per_million"] == 36000000
    assert (
        config["output_reserve_limit"]
        == config["output_request_limit"] + config["documented_output_overrun"]
    )
    assert config["documented_output_overrun"] == 10 and config["timeout_seconds"] == 60
    rows = proposal["slots"]
    assert len(rows) == 12
    assert sum(s["phase"] == "screen" for s in rows) == 4
    assert sum(s["phase"] == "generalization" for s in rows) == 8
    for s in rows:
        assert s["cost_micro_cny"] == 12 * (1048576 + s["wire_bytes"]) + 36 * 8202
        assert s["wire_bytes"] <= 65536
    assert proposal["exact_slot_reserve_micro_cny"] == sum(
        s["cost_micro_cny"] for s in rows
    )
    assert proposal["absolute_request_budget_micro_cny"] == 163975392
    assert proposal["exact_slot_reserve_micro_cny"] <= 163975392 < 164000000
    assert proposal["requests_authorized"] == proposal["fees_authorized"] == 0
    assert proposal["execution_status"] == "PROPOSAL_ONLY_NO_LIVE_RUNNER"


def test_new_cases_not_used_in_existing_repairs_and_schema_unchanged(prepared):
    old = p.read(ROOT / p.PRIOR / "cases.json")
    old_digests = {p.stable(c["material"]) for c in old.values()}
    new = [c for slot, c in prepared["cases.json"].items() if slot not in p.SCREEN]
    assert len(new) == 8 and len({p.stable(c["material"]) for c in new}) == 8
    assert all(p.stable(c["material"]) not in old_digests for c in new)
    schema = json.loads(bytes.fromhex(old["trace-complete:candidate"]["wire_hex"]))[
        "text"
    ]["format"]["schema"]
    for c in new:
        assert c["input_snapshot"]["metadata"]["goal"] == c["material"]["plan"]["goal"]
        assert c["material"]["binding"]["policy_digest"] == active_policy_digest()
        actual = json.loads(bytes.fromhex(c["candidate_wire_hex"]))
        assert actual["response_format"]["json_schema"]["schema"] == schema
        user = json.loads(actual["messages"][1]["content"])
        assert not {"comparison_kind", "expected_route", "criterion"} & user.keys()

    assert {c["comparison_kind"] for c in new} == {
        "positive",
        "fact",
        "safety",
        "mixed",
    }


@pytest.mark.parametrize(
    "family,expected_main",
    [
        ("search", "int main(void){return (find(9)==2 && find(8)==-1)?0:1;}"),
        ("stack", "int main(void){return demo()==9?0:1;}"),
    ],
)
def test_defined_c_controls_execute_with_expected_results(
    tmp_path, prepared, family, expected_main
):
    # Execute only authored correct/fact code, never unsafe or mixed variants.
    source = next(
        c["envelope"]["content"]["source"]
        for c in prepared["cases.json"][f"generalization-{family}-positive"][
            "material"
        ]["candidates"]
        if c["role"] == "code"
    )
    path = tmp_path / "control.c"
    path.write_text(source + "\n" + expected_main + "\n")
    compiled = subprocess.run(
        [
            "clang",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(path),
            "-o",
            str(tmp_path / "control"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert compiled.returncode == 0, compiled.stderr
    assert subprocess.run([str(tmp_path / "control")], timeout=5).returncode == 0
    fact = prepared["cases.json"][f"generalization-{family}-fact"]["material"]
    assert (
        next(
            c["envelope"]["content"]["source"]
            for c in fact["candidates"]
            if c["role"] == "code"
        )
        == source
    )
    assert next(
        c["envelope"]["content"]["markdown"]
        for c in fact["candidates"]
        if c["role"] == "explanation"
    ) != next(
        c["envelope"]["content"]["markdown"]
        for c in prepared["cases.json"][f"generalization-{family}-positive"][
            "material"
        ]["candidates"]
        if c["role"] == "explanation"
    )


def test_unsafe_cases_have_concrete_reachable_operations_no_execution(prepared):
    for family in ["search", "stack"]:
        for kind in ["safety", "mixed"]:
            m = prepared["cases.json"][f"generalization-{family}-{kind}"]["material"]
            source = next(
                c["envelope"]["content"]["source"]
                for c in m["candidates"]
                if c["role"] == "code"
            )
            if family == "search":
                assert "i<=4" in source and "a[4]={4,7,9,12}" in source
            else:
                assert (
                    "top=3" in source
                    and "a[3]={3,6,0}" in source
                    and "a[top++]" in source
                )


def test_wrong_selected_model_cannot_pass_as_name_only_change(prepared):
    from app.services.provider_gateway import (
        ChatMessage,
        StructuredRequest,
        TaskProfile,
        TextRequest,
    )
    import asyncio

    router = p.OfflineRouter({})
    router.review.request.route.model_id = "deepseek-flash"
    c = prepared["cases.json"][p.SCREEN[0]]
    body = json.loads(bytes.fromhex(c["candidate_wire_hex"]))
    request = StructuredRequest(
        TextRequest(
            tuple(ChatMessage(m["role"], m["content"]) for m in body["messages"]),
            task_profile=TaskProfile.QUALITY,
        ),
        body["response_format"]["json_schema"]["schema"],
    )
    with pytest.raises(ValueError, match="ROUTE_CAPABILITY_MISMATCH"):
        asyncio.run(router.generate_structured(request))
    assert not router.review.wires and not router.generation_wires


def test_stale_policy_cannot_reach_candidate_http(prepared):
    from app.services.provider_gateway import (
        ChatMessage,
        StructuredRequest,
        TaskProfile,
        TextRequest,
    )
    import asyncio

    router = p.OfflineRouter({})
    c = prepared["cases.json"][p.SCREEN[0]]
    body = json.loads(bytes.fromhex(c["candidate_wire_hex"]))
    user = json.loads(body["messages"][1]["content"])
    user["unit"]["binding"]["policy_digest"] = "0" * 64
    messages = (
        ChatMessage(body["messages"][0]["role"], body["messages"][0]["content"]),
        ChatMessage("user", json.dumps(user)),
    )
    request = StructuredRequest(
        TextRequest(messages, task_profile=TaskProfile.QUALITY),
        body["response_format"]["json_schema"]["schema"],
    )
    with pytest.raises(ValueError, match="POLICY_MISMATCH"):
        asyncio.run(router.generate_structured(request))
    assert not router.review.wires and not router.generation_wires
