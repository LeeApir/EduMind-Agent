"""Offline single-variable and retirement guards, not model semantic acceptance."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_high_candidate import CONFIG, offline_router
from acceptance_support.luna_review_routing import CONFIG as LOW_CONFIG
from acceptance_support.qwen_review_budget import sha, canonical
from acceptance_support.luna_schema_projection import projection
from acceptance_support.om_diagnostic import valid_review
from prepare_last_review_candidate import build, BASE, CAL, OLD, LOW, SLOTS
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow
from prepare_luna_admission import candidates
from app.services.provider_gateway import TaskProfile, ProviderError


def read(path):
    return json.loads(path.read_bytes())


@pytest.fixture(scope="module")
def rebuilt():
    original = socket.getaddrinfo

    def deny(*a, **kw):
        pytest.fail("no DNS in candidate preparation")

    try:
        socket.getaddrinfo = deny
        return asyncio.run(build())
    finally:
        socket.getaddrinfo = original


def test_complete_packet_reproduces_with_no_network(rebuilt):
    for name, value in rebuilt.items():
        assert value == read(ROOT / BASE / name)


def test_exactly_one_config_variable_changes():
    high, low = asdict(CONFIG), asdict(LOW_CONFIG)
    assert {k for k in high if high[k] != low[k]} == {"review_reasoning"}
    assert high["review_reasoning"] == "high"
    for mutation in (
        replace(CONFIG, review_model="another"),
        replace(CONFIG, review_reasoning="max"),
        replace(CONFIG, review_output=16384),
    ):
        with pytest.raises(ValueError, match="CANDIDATE_CONFIG_CHANGED"):
            mutation.check()


def test_original_cases_and_truth_labels_unchanged(rebuilt):
    cal = read(ROOT / CAL / "cases.json")
    old = read(ROOT / OLD / "cases.json")
    for slot in SLOTS:
        source = "cal-01" if slot == "compat-schema" else slot
        expected = (cal if source.startswith("cal-") else old)[source]
        assert rebuilt["cases.json"][slot] == expected
        assert rebuilt["labels.json"][slot]["source_material_sha256"] == sha(
            canonical(expected)
        )
    assert rebuilt["cases.json"]["compat-schema"] == rebuilt["cases.json"]["cal-01"]


def test_every_wire_only_changes_effort_after_known_projection(rebuilt):
    originals = {
        **read(ROOT / OLD / "requests.json"),
        **read(ROOT / LOW / "requests.json"),
    }
    for slot, request in rebuilt["requests.json"].items():
        source = "cal-01" if slot == "compat-schema" else slot
        before = json.loads(bytes.fromhex(originals[source]["wire_hex"]))
        after = json.loads(bytes.fromhex(request["wire_hex"]))
        if not source.startswith("cal-"):
            before["text"]["format"]["schema"], _ = projection(
                before["text"]["format"]["schema"]
            )
        expected = deepcopy(before)
        expected["reasoning"] = {"effort": "high"}
        assert after == expected
        assert after["input"] == before["input"]
        assert request["target"]["host"] == request["target"]["sni"] == "www.cbbb.fun"
        assert after["max_output_tokens"] == 8192


def test_generation_routes_still_deepseek_and_none(rebuilt):
    captures = rebuilt["generation-capture.json"]
    assert set(captures) == {"plan", "explanation", "code", "exercise"}
    for value in captures.values():
        body = json.loads(bytes.fromhex(value["wire_hex"]))
        assert body["model"] == "deepseek-flash" and body["reasoning"] == {
            "effort": "none"
        }
        assert value["target"]["host"] == "api.deepseek.com"


def test_compatibility_then_calibration_then_severe_then_unused(rebuilt):
    plan = rebuilt["plan.json"]
    assert plan["slots"] == list(SLOTS) and len(SLOTS) == 12
    assert plan["candidate_count_max"] == 1 and plan["requests_max"] == 12
    assert plan["output_tokens_total_max"] == 12 * 8192
    assert plan["model_wait_total_seconds_max"] == 12 * 60
    assert plan["new_candidates_after_failure"] == 0
    assert plan["requests_authorized"] == plan["generation_calls_authorized"] == 0
    assert plan["retries"] == plan["corrections"] == 0 and plan["fallback"] is False
    assert plan["stage_counts"] == dict(
        full_schema_compatibility=1,
        four_calibration_cases=4,
        fact_safety_mixed=3,
        preexisting_unused_materials=4,
    )


def test_duplicate_checks_still_fail_full_schema():
    case = read(ROOT / CAL / "cases.json")["cal-01"]
    bad = valid_review("unit")
    bad["coverage"]["checked"][-1] = bad["coverage"]["checked"][0]
    router, gen, reviews, targets = offline_router(bad)
    m = case["material"]
    with pytest.raises(ProviderError) as error:
        asyncio.run(
            review_once(
                router,
                CallWindow(),
                binding=m["binding"],
                target_digest=m["unit_digest"],
                payload={"unit": m, "reference_context": m["reference_context"]},
                candidates=candidates(case),
                scope="unit",
                input_snapshot=case["input_snapshot"],
            )
        )
    assert error.value.schema_keyword == "uniqueItems"
    assert not gen and len(reviews) == 1 and targets[0]["host"] == "www.cbbb.fun"


def test_retired_low_and_unsent_remain_retired():
    retirement = read(ROOT / BASE / "retirement.json")
    assert (
        retirement["candidate"] == "Luna/low/v4.9" and retirement["state"] == "RETIRED"
    )
    assert retirement["actual_requests"] == 2
    assert retirement["unsent"] == ["cal-03", "cal-04"]
    assert retirement["resume_or_reuse_slots"] is False
    old = read(ROOT / LOW / "results/run-summary.json")
    assert old["persistent_halt"] is True and old["actual_requests_this_run"] == 2
    assert not (ROOT / BASE / "run-approval.json").exists()


def test_router_rejects_retry_flag_and_wrong_profile(monkeypatch):
    case = read(ROOT / CAL / "cases.json")["cal-01"]
    router, gen, reviews, _ = offline_router(valid_review("unit"))

    async def altered(self, request, **kwargs):
        with pytest.raises(ValueError, match="RETRY_FORBIDDEN"):
            await original(self, request, retry_safe=True)
        mutated = replace(
            request, prompt=replace(request.prompt, task_profile=TaskProfile.FAST)
        )
        with pytest.raises(ValueError, match="UNEXPECTED_TASK_PROFILE"):
            await original(self, mutated)
        return await original(self, request)

    original = type(router).generate_structured
    monkeypatch.setattr(type(router), "generate_structured", altered)
    m = case["material"]
    asyncio.run(
        review_once(
            router,
            CallWindow(),
            binding=m["binding"],
            target_digest=m["unit_digest"],
            payload={"unit": m, "reference_context": m["reference_context"]},
            candidates=candidates(case),
            scope="unit",
            input_snapshot=case["input_snapshot"],
        )
    )
    assert not gen and len(reviews) == 1
