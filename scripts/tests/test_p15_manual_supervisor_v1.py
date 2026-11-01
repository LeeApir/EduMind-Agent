"""Synthetic-only tests for the proposed one-shot local supervisor."""

import threading
import time

import pytest

from scripts.isolated_diagnostics import p15_manual_supervisor_v1 as manual


def supervisor():
    return manual.ManualSupervisor(
        "generation", "synthetic-one-role", manual.child_digest(), manual.interpreter_digest()
    )


def test_untrusted_cwd_cannot_shadow_standard_library(tmp_path, monkeypatch):
    marker = tmp_path / "shadow-ran"
    (tmp_path / "json.py").write_text("open('shadow-ran','w').write('bad')\n")
    monkeypatch.chdir(tmp_path)
    now = time.monotonic()
    result = supervisor().dispatch("fixture", batch_deadline=now + 5, request_deadline=now + 5)
    assert not marker.exists()
    assert str(tmp_path) not in result["paths"]
    assert result["body"] == "fixture" and result["provider_call"] is False


def test_pre_dispatch_expired_and_bad_digest_are_rejected():
    instance = supervisor()
    now = time.monotonic()
    with pytest.raises(RuntimeError, match="PRE_SEND_DEADLINE"):
        instance.dispatch("fixture", batch_deadline=now - 1, request_deadline=now + 5)
    bad = manual.ManualSupervisor("generation", "synthetic-one-role", "0" * 64, manual.interpreter_digest())
    with pytest.raises(ValueError, match="CHILD_DIGEST"):
        bad.dispatch("fixture", batch_deadline=now + 5, request_deadline=now + 5)


def test_other_role_credential_name_in_current_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("EDUMIND_AIAPI_REVIEW_API_KEY", "synthetic-other-role")
    with pytest.raises(ValueError, match="OTHER_ROLE_ENV_PRESENT"):
        supervisor()


def test_stop_reaps_synthetic_child_and_disallows_new_dispatch():
    instance = supervisor()
    errors = []

    def run():
        try:
            now = time.monotonic()
            instance.dispatch("fixture", batch_deadline=now + 10, request_deadline=now + 10, delay=5)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    limit = time.monotonic() + 3
    while instance._process is None and time.monotonic() < limit:
        time.sleep(0.01)
    assert instance._process is not None
    assert instance.stop(2) == "local_stopped_confirmed"
    thread.join(3)
    assert not thread.is_alive() and errors
    now = time.monotonic()
    with pytest.raises(RuntimeError, match="STOPPED_OR_ALREADY_SENT"):
        instance.dispatch("again", batch_deadline=now + 5, request_deadline=now + 5)


def test_stop_during_spawn_does_not_deliver_job_or_result(monkeypatch):
    original = manual.SpawnOnlyPopen
    entered, release = threading.Event(), threading.Event()
    result, errors = [], []

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(manual, "SpawnOnlyPopen", delayed)
    instance = supervisor()

    def run():
        try:
            now = time.monotonic()
            result.append(instance.dispatch("fixture", batch_deadline=now + 10, request_deadline=now + 10))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(3)
    assert instance.stop(0.05) == "stop_unconfirmed"
    release.set()
    thread.join(3)
    assert not thread.is_alive() and not result
    assert errors and str(errors[0]) == "STOPPED_BEFORE_PERMIT"
