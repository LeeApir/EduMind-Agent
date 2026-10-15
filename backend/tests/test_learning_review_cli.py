"""Trusted local identity and explicit private export; no actual course approval."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_learning_review_cases import URL, case_fixture

from app.core.database import create_database_engine
from app.services.learning_contract import LearningContractError
from app.services.learning_review_cli import export_case, maintainer_identity

ROOT = Path(__file__).resolve().parents[2]


def config(tmp_path):
    p = tmp_path / "reviewers.json"
    p.write_text(
        json.dumps(
            {
                "version": "local-reviewers-v1",
                "operators": [{"uid": os.geteuid(), "reviewer_id": "synthetic-maintainer"}],
            }
        )
    )
    p.chmod(0o600)
    return p


def test_identity_requires_os_allowlist_and_private_regular_file(tmp_path):
    p = config(tmp_path)
    assert maintainer_identity(p)[0] == "synthetic-maintainer"
    p.chmod(0o644)
    with pytest.raises(LearningContractError):
        maintainer_identity(p)
    p.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(p)
    with pytest.raises(LearningContractError):
        maintainer_identity(link)
    p.write_text(json.dumps({"version": "local-reviewers-v1", "operators": []}))
    with pytest.raises(LearningContractError):
        maintainer_identity(p)


def test_export_is_explicit_private_and_never_overwrites(tmp_path):
    p = tmp_path / "case.json"
    export_case(p, {"synthetic": True})
    assert p.stat().st_mode & 0o777 == 0o600
    with pytest.raises(LearningContractError):
        export_case(p, {"overwrite": True})
    assert json.loads(p.read_text()) == {"synthetic": True}


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_cli_reads_summary_and_full_case_only_explicitly(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "review_cli", ROOT / "scripts/review_learning_cases.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_REVIEWER_CONFIG", str(config(tmp_path)))

    async def exercise():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                *_, case = await case_fixture(db)
                await db.commit()
                cid = str(case.id)
            value = await cli.run(cli.parser().parse_args(["show", cid]))
            assert "payload" not in value and "automatic_reviews" not in value
            full = await cli.run(cli.parser().parse_args(["show", cid, "--body"]))
            assert len(full["automatic_reviews"]) == 4 and full["payload"]["material"]["plan"]
            args = cli.parser().parse_args(
                [
                    "decide",
                    cid,
                    "--case-digest",
                    value["case_digest"],
                    "--verdict",
                    "reject",
                    "--reason",
                    "Synthetic CLI lifecycle test only.",
                    "--idempotency-key",
                    "synthetic-cli-" + cid,
                ]
            )
            rejected = await cli.run(args)
            assert rejected["state"] == "rejected"
            assert (await cli.run(args))["decision_id"] == rejected["decision_id"]
            monkeypatch.delenv("EDUMIND_REVIEWER_CONFIG")
            with pytest.raises(LearningContractError):
                await cli.run(cli.parser().parse_args(["show", cid]))
        finally:
            await engine.dispose()

    asyncio.run(exercise())
