"""Offline evidence verifier rejects broken provenance without executing services."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "p15_integration_check", ROOT / "scripts/check_p15_free_course_integration.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    xml = tmp_path / "group.xml"
    xml.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase name="closed_loop"/></testsuite></testsuites>'
    )
    log = tmp_path / "group.log"
    log.write_text("1 passed\n")
    group = dict(
        test="fixture.py",
        prefix="t020",
        database="edumind_catalog_p15_t020_t035_r01_0",
        exit_code=0,
        counts=dict(tests=1, failures=0, errors=0, skipped=0),
        xml=str(xml),
        log=str(log),
        xml_sha256=checker.sha(xml),
        log_sha256=checker.sha(log),
    )
    path = tmp_path / "results.json"
    data = dict(
        run_id="r01",
        real_provider_calls=0,
        production_mode="catalog_only",
        test_mode="isolated dynamic fixtures only",
        transport="synthetic FakeAdapter; real ASGI HTTP and PostgreSQL",
        integrity={"approved": 41, "historical": 50},
        groups=[group],
        passed=1,
    )
    monkeypatch.setattr(checker, "EVIDENCE", path)
    monkeypatch.setattr(checker, "GROUPS", [("fixture.py", "t020")])
    monkeypatch.setattr(checker, "integrity", lambda: {"approved": 41, "historical": 50})
    # Redirect only path containment to the synthetic fixture directory.
    original = Path.is_relative_to
    monkeypatch.setattr(Path, "is_relative_to", lambda p, parent: original(p, tmp_path))

    def forbidden(*a, **k):
        pytest.fail("Offline checker executed an external command")

    monkeypatch.setattr(checker.subprocess, "run", forbidden)
    return path, data, xml, log


def test_valid_offline_evidence_uses_no_subprocess(evidence):
    path, data, _, _ = evidence
    path.write_text(json.dumps(data))
    checker.check()


@pytest.mark.parametrize(
    "change",
    [
        "skip",
        "failure",
        "exit",
        "real_call",
        "production_mode",
        "missing_group",
        "total",
        "tampered_log",
        "tampered_xml",
        "missing_xml",
    ],
)
def test_broken_or_incomplete_evidence_is_rejected(evidence, change):
    path, data, xml, log = evidence
    if change in ["skip", "failure"]:
        data["groups"][0]["counts"]["skipped" if change == "skip" else "failures"] = 1
    elif change == "exit":
        data["groups"][0]["exit_code"] = 1
    elif change == "real_call":
        data["real_provider_calls"] = 1
    elif change == "production_mode":
        data["production_mode"] = "dynamic"
    elif change == "missing_group":
        data["groups"] = []
    elif change == "total":
        data["passed"] = 2
    elif change == "tampered_log":
        log.write_text("tampered")
    elif change == "tampered_xml":
        xml.write_text("<testsuites/>")
    elif change == "missing_xml":
        xml.unlink()
    path.write_text(json.dumps(data))
    with pytest.raises((AssertionError, FileNotFoundError)):
        checker.check()
