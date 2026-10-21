"""No-network bounds for the single A02 replay."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'a02_once', Path(__file__).resolve().parents[1] / 'retest_five_hour_a02_once.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_single_request_exhausted_even_after_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(module.previous.kernel, 'ORDER', ['A02'])
    ledger = module.SingleLedger(tmp_path / 'one.sqlite', 'a' * 64, t0=0, now=lambda: 1)
    ledger.start_case('A02')
    n = ledger.reserve('A02', 'b' * 64)
    ledger.complete_call(n, 'c' * 64)
    with pytest.raises(ValueError, match='SINGLE_REQUEST_EXHAUSTED'):
        ledger.reserve('A02', 'b' * 64)
    assert len(ledger.snapshot()['calls']) == 1


def test_persistent_stop_refuses_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(module.previous.kernel, 'ORDER', ['A02'])
    ledger = module.SingleLedger(tmp_path / 'one.sqlite', 'a' * 64, t0=0, now=lambda: 1)
    ledger.stop('SINGLE_RETEST_FINISHED_NO_FURTHER_CALLS')
    recovered = module.SingleLedger(ledger.path, ledger.digest, now=lambda: 2)
    with pytest.raises(ValueError, match='RUN_STOPPED'):
        recovered.start_case('A02')
    assert not recovered.snapshot()['calls']
