"""Read-only proposal and exact T085 content regression; unchanged strict validators."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import socket

import pytest

from scripts.isolated_diagnostics import p15_minimal_probe as live
from scripts.isolated_diagnostics import p15_minimal_probe_contract as contract
from scripts.isolated_diagnostics import p15_minimal_contract as local
from scripts.tests.test_p15_minimal_probe import response, execute

BASE = (
    Path(__file__).resolve().parents[2]
    / "docs/acceptance/phase-1.5-separated-protocol-repair-r01"
)
DESIGN = runpy.run_path(str(BASE / "check_design.py"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No live DNS/network in regression")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def captured():
    return (BASE / "fixtures/t085-s5-output-text.txt").read_bytes().decode()


def observe_text(text):
    envelope = response("S5")
    envelope["output"][0]["content"][0]["text"] = text
    body = json.loads(contract.bodies()["S5"])
    return live.observe("S5", body, live.canonical(envelope))


def test_original_exact_text_not_sanitized_or_reconstructed():
    raw = (BASE / "fixtures/t085-s5-output-text.txt").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "fb558f5f285d786a539462fdeaa36697e83a3be9792dbc62bb69c7e07e023156"
    )
    assert len(raw) == 3306 and not raw.endswith(b"\n")
    with pytest.raises(json.JSONDecodeError, match="Extra data") as error:
        observe_text(raw.decode())
    assert error.value.pos == 3287


@pytest.mark.parametrize(
    "file", ["schema-as-answer.json", "parsed-prefix-as-answer.json"]
)
def test_valid_json_schema_or_salvaged_prefix_is_never_an_answer(file):
    raw = (BASE / "fixtures" / file).read_text()
    assert isinstance(json.loads(raw), dict)
    with pytest.raises(live.pilot.PilotError, match="ROLE_SCHEMA"):
        observe_text(raw)


def test_first_parsed_prefix_and_tail_trace_the_real_failure():
    first, end = json.JSONDecoder().raw_decode(captured())
    schema = json.loads(contract.bodies()["S5"])["text"]["format"]["schema"]
    assert first == {k: v for k, v in schema.items() if k != "type"}
    assert end == 3287 and captured()[end:] == ', "type": "object"}'


@pytest.mark.parametrize(
    "attack",
    ["concatenated", "fenced", "extra_root", "duplicate", "nonfinite", "wrong_echo"],
)
def test_strict_guards_are_not_relaxed_to_rescue_output(attack):
    value = deepcopy(contract.FIXTURES["S5"])
    text = json.dumps(value)
    if attack == "concatenated":
        text += "\n" + json.dumps(value)
    elif attack == "fenced":
        text = "```json\n" + text + "\n```"
    elif attack == "extra_root":
        value["schema"] = {}
        text = json.dumps(value)
    elif attack == "duplicate":
        text = '{"actions":{},' + text[1:]
    elif attack == "nonfinite":
        text = '{"extra":NaN,' + text[1:]
    else:
        value["paragraphs"][0]["text"] = "Changed but structurally valid."
        text = json.dumps(value)
    with pytest.raises((ValueError, live.Refused, live.pilot.PilotError)):
        observe_text(text)


def test_valid_original_instance_still_passes_strict_observer():
    result = observe_text(json.dumps(contract.FIXTURES["S5"]))
    assert result["original_local_schema_verified"]
    assert not result["teaching_evaluated"]


def test_original_failure_stops_mock_at_fifth_slot_without_sixth_dispatch(tmp_path):
    def replace(value):
        value["output"][0]["content"][0]["text"] = captured()

    runner, result, seen, _ = execute(tmp_path, 4, replace)
    assert len(seen) == 5 and result["admitted_roles"] == 4
    assert result["outcome"] == "inconclusive_stopped" and result["unrun_roles"] == 2
    assert not (runner.output / "S6-request.json").exists()
    assert not (runner.output / "S7-request.json").exists()


@pytest.mark.parametrize(
    "row",
    json.loads((BASE / "matrix.json").read_bytes())["rows"],
    ids=lambda r: r["id"],
)
def test_every_exact_input_keeps_current_schema_settings_and_one_factor(row):
    body = DESIGN["request"](row["id"])
    old = json.loads(contract.bodies()["S5"])
    assert {k: v for k, v in body.items() if k != "input"} == {
        k: v for k, v in old.items() if k != "input"
    }
    assert body["text"]["format"]["strict"] is True
    if row["parent"]:
        assert DESIGN["differences"](
            DESIGN["user"](row["parent"]), DESIGN["user"](row["id"])
        ) == [row["user_payload_patch"][0]["path"]]
        assert DESIGN["patch_once"](
            DESIGN["user"](row["parent"]), row["user_payload_patch"][0]
        ) == DESIGN["user"](row["id"])


def test_echo_family_has_one_goal_and_real_repair_has_no_prescribed_output():
    echo = DESIGN["user"]("P0")
    assert set(echo) == {"expected_output"}
    for name in ["W0", "W1", "W2", "W3", "W4"]:
        assert DESIGN["user"](name)["expected_output"] == echo["expected_output"]
        assert (
            DESIGN["request"](name)["input"][0] == DESIGN["request"]("P0")["input"][0]
        )
    repair = DESIGN["user"]("R0")
    assert "expected_output" not in json.dumps(repair)
    assert DESIGN["request"]("R0")["input"][0] != DESIGN["request"]("P0")["input"][0]
    assert {"original", "original_input", "issues", "previous_candidate_digest"} <= set(
        repair
    )
    assert repair["issues"][0]["area"] == "difficulty"


@pytest.mark.parametrize(
    "case",
    json.loads((BASE / "repair-output-examples.json").read_bytes())["examples"],
    ids=lambda c: c["id"],
)
def test_repair_is_not_exact_echo_or_program_filled_answer(case):
    original = deepcopy(DESIGN["user"]("R0")["original"])
    assert (
        DESIGN["repair_mechanical_outcome"](case["value"])
        == case["mechanical_expected"]
    )
    assert DESIGN["user"]("R0")["original"] == original


def test_different_good_wordings_and_false_teaching_both_need_independent_review():
    cases = json.loads((BASE / "repair-output-examples.json").read_bytes())["examples"]
    assert cases[0]["value"] != cases[1]["value"]
    for case in cases[:3]:
        assert (
            DESIGN["repair_mechanical_outcome"](case["value"])
            == "pending_independent_semantic_review"
        )
    assert cases[2]["developer_label"] == "deliberately_wrong"


def test_echo_wrong_value_is_not_a_success_even_when_structurally_valid():
    value = deepcopy(DESIGN["user"]("P0")["expected_output"])
    value["paragraphs"][0]["text"] = "different"
    assert DESIGN["protocol_value_outcome"]("P0", value) == "reject_wrong_echo"


def test_real_repair_wrong_schema_stays_rejected():
    with pytest.raises(local.ContractError, match="ROLE_SCHEMA"):
        DESIGN["repair_mechanical_outcome"](
            json.loads((BASE / "fixtures/schema-as-answer.json").read_text())
        )


def test_matrix_is_finite_nonadaptive_and_has_no_live_allowance():
    matrix = json.loads((BASE / "matrix.json").read_bytes())
    assert matrix["actual_provider_calls_authorized"] == 0
    assert matrix["proposed_later_max_http"] == 7
    assert (
        matrix["repetitions"]
        == matrix["adaptive_rows"]
        == matrix["transport_retries"]
        == 0
    )
    assert matrix["global_stop_on_any_protocol_failure"]
