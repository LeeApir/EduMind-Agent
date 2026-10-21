"""Fixed ownership evidence regressions, no actual C execution here."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from offline_c_fixtures import AdmissionError  # noqa: E402
from offline_c_ownership import DIRECTORY, check_ownership  # noqa: E402
from offline_c_ownership_results import observe  # noqa: E402
from test_offline_c_runner import controller  # noqa: E402


def test_reviewed_driver_and_three_minimal_negatives():
    manifest = check_ownership()
    assert len(manifest["artifacts"]) == 5 and len(manifest["derivations"]) == 3
    original = (
        ROOT / "docs/acceptance/offline-c-fixtures/edumind/candidate.c"
    ).read_bytes()
    assert (
        b"new_node->next = head;" in original
        and b"head = insert_head(head, 1);" in original
    )


def command(events, stdout=b"3 2 1 \n", stderr_tail=b"", code=0):
    return {
        "stdout": controller.encoded(stdout),
        "stderr": controller.encoded(
            b"".join(b"EVENT " + json.dumps(e).encode() + b"\n" for e in events)
            + stderr_tail
        ),
        "exit_code": code,
        "timeout": False,
        "output_limit": False,
    }


def normal_events():
    return (
        [{"event": "allocate", "slot": n} for n in range(3)]
        + [
            {
                "event": "insert_state",
                "step": n,
                "basis": "caller_head_after_assignment",
                "values": list(range(n, 0, -1)),
                "count": n,
            }
            for n in range(1, 4)
        ]
        + [{"event": "free", "slot": n} for n in [2, 1, 0]]
        + [
            {
                "event": "summary",
                "attempts": 3,
                "allocated": 3,
                "released": 3,
                "live": 0,
                "caller_reset": True,
                "reset_by": "driver_caller",
            }
        ]
    )


def test_actual_trace_checks_chain_and_every_release():
    compile_cmd = command([])
    events = normal_events()
    obs, matched = observe(
        "edumind-r02-original",
        "contract-0",
        {"status": "pass", "reason": "success"},
        [compile_cmd, command(events)],
        ROOT,
    )
    assert matched and obs["free_call_sequence"] == [2, 1, 0]
    for mutation in ["drop_state", "wrong_chain", "repeat_free", "live_leak"]:
        bad = copy.deepcopy(events)
        if mutation == "drop_state":
            bad = [e for e in bad if e.get("step") != 2]
        if mutation == "wrong_chain":
            next(e for e in bad if e.get("step") == 2)["values"] = [2]
        if mutation == "repeat_free":
            next(e for e in bad if e["event"] == "free")["slot"] = 1
        if mutation == "live_leak":
            bad[-1]["live"] = 1
        _, matched = observe(
            "edumind-r02-original",
            "contract-0",
            {"status": "pass", "reason": "success"},
            [compile_cmd, command(bad)],
            ROOT,
        )
        assert not matched, mutation


def test_ub_detection_never_infers_final_counts_or_output():
    event = {"event": "attempt", "step": 2, "injected": True, "prior_live": 1}
    value = {"status": "fail", "reason": "runtime_error"}
    obs, matched = observe(
        "om-original",
        "contract-2",
        value,
        [
            command([]),
            command(
                [event],
                stdout=b"",
                stderr_tail=b"runtime error: member access within null pointer",
                code=1,
            ),
        ],
        ROOT,
    )
    assert matched
    assert all(
        obs[k] is None
        for k in [
            "allocated",
            "released",
            "live",
            "numeric_sequence",
            "caller_head_reset",
        ]
    )


def test_plain_failure_or_timeout_cannot_pass_as_negative_detection():
    for code, text, timeout in [
        (1, b"unrelated error", False),
        (137, b"snapshot Assertion", True),
    ]:
        result = command([], stdout=b"", stderr_tail=text, code=code)
        result["timeout"] = timeout
        _, matched = observe(
            "edumind-r02-original",
            "negative-drop-link",
            {"status": "fail", "reason": "runtime_error"},
            [command([]), result],
            ROOT,
        )
        assert not matched


def test_ownership_artifact_tamper_rejected(tmp_path):
    import shutil

    shutil.copytree(ROOT / DIRECTORY, tmp_path / DIRECTORY)
    path = tmp_path / DIRECTORY / "edumind/ownership-driver.c"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(AdmissionError):
        check_ownership(tmp_path)


def test_combined_bundle_copies_once_and_stays_readonly(tmp_path):
    from offline_c_runner import prepare_bundle, verify_bundle
    bundle = tmp_path / "bundle"
    manifest = prepare_bundle(bundle, ownership=True)
    assert len(manifest["artifacts"]) == 15
    verify_bundle(bundle, manifest)
    assert all((bundle / name).stat().st_mode & 0o222 == 0 for name in manifest["artifacts"])
