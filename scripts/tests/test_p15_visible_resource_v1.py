"""Resource and exact outer-request tests; no Provider calls."""

import json
from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics import p15_visible_worker_v1 as worker
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


@pytest.mark.parametrize("arm", ["B", "C"])
def test_expansion_in_limited_child_and_actual_full_request(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] += '\\n文字 "quoted" \\ slash'
    identity = c.identity("dev", "slot", arm, 0, SPEC, None)
    expanded = worker.expand(value, identity, catalog)
    policy = budget.DevelopmentPolicy(4_000_000, 4_100_000, 8000)
    raw, receipt = budget.build("review_" + arm, expanded["view"], policy)
    outer = json.loads(raw)
    assert json.loads(outer["input"][1]["content"]) == expanded["view"]
    assert outer["text"]["format"]["schema"] == c.schema_for("review_" + arm)
    assert outer["text"]["format"]["strict"] is True
    assert receipt["body_bytes"] == len(raw)
    assert receipt["body_bytes"] > receipt["user_json_bytes"]
    assert receipt["local_input_reservation"] == len(raw) + 8192
    assert not receipt["token_estimate_is_provider_bound"]


def test_byte_gate_and_token_reservation_are_independent():
    payload = {"text": '"\\' * 100}
    ample = budget.DevelopmentPolicy(100_000, 110_000, 8000)
    raw, receipt = budget.build("review_B", payload, ample)
    assert len(raw) > len(json.dumps(payload, ensure_ascii=False).encode())
    with pytest.raises(c.ContractError, match="REQUEST_BYTES_LIMIT"):
        budget.build(
            "review_B", payload, budget.DevelopmentPolicy(len(raw) - 1, 110_000, 8000)
        )
    with pytest.raises(c.ContractError, match="LOCAL_INPUT_RESERVATION_LIMIT"):
        budget.build(
            "review_B",
            payload,
            budget.DevelopmentPolicy(
                100_000, receipt["local_input_reservation"] - 1, 8000
            ),
        )


def test_pre_expansion_rejects_invalid_input_before_worker(monkeypatch):
    catalog = c.make_catalog(SPEC)
    value = deepcopy(b_fixture(SPEC))
    value["paragraphs"][0]["text"] = "x" * 4001
    monkeypatch.setattr(
        worker.subprocess, "Popen", lambda *a, **kw: pytest.fail("worker started")
    )
    with pytest.raises(c.ContractError):
        worker.expand(value, c.identity("dev", "slot", "B", 0, SPEC, None), catalog)


def test_worker_launch_failure_is_unknown_no_unbounded_retry(monkeypatch):
    catalog = c.make_catalog(SPEC)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise OSError("synthetic launch failure")

    monkeypatch.setattr(worker.subprocess, "Popen", fail)
    with pytest.raises(c.ContractError, match="EXPANSION_RESOURCE_UNKNOWN"):
        worker.expand(
            b_fixture(SPEC), c.identity("dev", "slot", "B", 0, SPEC, None), catalog
        )
    assert calls == [1]


def test_missing_process_is_accepted_only_after_confirmed_exit():
    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

        def wait(self, timeout):
            assert timeout == 0.2
            return 0

    child = FakeProcess()
    assert worker._reaped_after_missing(child)

    def still_waiting(timeout):
        raise worker.subprocess.TimeoutExpired("child", timeout)

    child.wait = still_waiting
    assert not worker._reaped_after_missing(child)
