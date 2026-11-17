"""Explicit pytest plugin: old pre-execution tests must not use a real evidence path.

Selected with -p only. Original frozen tests/assertions are unchanged; their output
target is an initially nonexistent test-local path, not the preserved r03 directory.
"""

import pytest


@pytest.fixture(autouse=True)
def isolate_pre_execution_output(request, monkeypatch, tmp_path):
    if (
        request.node.originalname
        == "test_r03_missing_approval_or_r02_grant_refused_before_any_side_effect"
    ):
        import run_p15_strict_diagnostic as cli

        monkeypatch.setattr(cli, "OUTPUT", tmp_path / cli.OUTPUT.name)
