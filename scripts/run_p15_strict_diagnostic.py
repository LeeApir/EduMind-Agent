"""T050 r03 one-slot entry. New exact T038 approval required; no r02 authority is inherited."""

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.p15_diagnostic_execution import (  # noqa: E402
    Execution,
    run_slot,
    verify_approval,
)
from acceptance_support.p15_diagnostic_ledger import Ledger, Refused  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-development-diagnostic-r03"
OUTPUT = Path("/tmp/edumind-p15-t038-r03")


def load_package(base=BASE):
    raw = (base / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise Refused("FROZEN_SOURCE_OR_MATERIAL_CHANGED")
    return manifest, hashlib.sha256(raw).hexdigest()


def gate(base=BASE):
    manifest, package = load_package(base)
    path = base / "execution-approval.json"
    if not path.is_file():
        raise Refused("EXACT_T038_HUMAN_APPROVAL_REQUIRED")
    approval = json.loads(path.read_text())
    verify_approval(manifest, package, approval)
    return manifest, package, approval


def settings_after_approval():
    # Only called after the complete gate. Never echo values or load arbitrary shell code.
    values = {}
    if (ROOT / ".env").is_file():
        for line in (ROOT / ".env").read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() in {
                "EDUMIND_PROVIDER_BASE_URL",
                "EDUMIND_PROVIDER_MODEL",
                "EDUMIND_PROVIDER_API_KEY",
                "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
            }:
                values[name.strip()] = value.strip().strip("\"'")
    values.update(
        {k: v for k, v in os.environ.items() if k.startswith("EDUMIND_PROVIDER_")}
    )
    if (
        values.get("EDUMIND_PROVIDER_BASE_URL") != "https://www.cbbb.fun/v1"
        or values.get("EDUMIND_PROVIDER_MODEL") != "gpt-6-luna"
        or values.get("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT")
        != "responses_json_schema"
        or not values.get("EDUMIND_PROVIDER_API_KEY")
    ):
        raise Refused("FROZEN_PROVIDER_CONFIG_REQUIRED")
    from app.core.config import ProviderSettings

    return ProviderSettings(
        values["EDUMIND_PROVIDER_BASE_URL"],
        values["EDUMIND_PROVIDER_API_KEY"],
        values["EDUMIND_PROVIDER_MODEL"],
    )


async def advance(execution, env):
    import httpx
    from acceptance_support.p15_strict_transport import StrictDiagnosticAdapter
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import create_database_engine
    from app.core.provider_target import ProviderTargetGuard, TargetPolicy

    settings = settings_after_approval()
    adapter = StrictDiagnosticAdapter(
        settings,
        ProviderTargetGuard(settings.base_url, TargetPolicy()),
        execution.ledger,
        execution.batch,
        execution.package,
        OUTPUT / "wire",
        lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False),
    )
    engine = create_database_engine(env["EDUMIND_DATABASE_URL"])
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def runner(slot):
            return await asyncio.wait_for(
                run_slot(
                    slot,
                    sessions,
                    adapter,
                    execution.ledger,
                    execution.batch,
                    execution.package,
                ),
                timeout=120 if slot["kind"] == "probe" else 600,
            )

        return await execution.advance(runner)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--start", action="store_true")
    group.add_argument("--advance", action="store_true")
    group.add_argument("--review", type=Path)
    args = parser.parse_args()
    # This precedes credentials, DNS, Docker, database access and output creation.
    manifest, package, approval = gate()
    if args.start:
        OUTPUT.mkdir(mode=0o700, exist_ok=False)
    elif not OUTPUT.is_dir():
        raise Refused("NOT_STARTED")
    with (OUTPUT / "executor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = Ledger(OUTPUT / "ledger.sqlite")
        try:
            execution = Execution(ledger, manifest, package, manifest["slots"], OUTPUT)
            if args.start:
                execution.start(approval)
                print(
                    "Started. Use --advance for exactly one slot; human review is required next."
                )
            elif args.review:
                with ledger.transaction():
                    ledger.guard(execution.batch, package)
                execution.review(json.loads(args.review.read_text()))
                print("Human review recorded; no model request sent.")
            else:
                import subprocess

                import run_catalog_db_tests

                with ledger.transaction():
                    ledger.guard(execution.batch, package)
                run_catalog_db_tests.CONTAINER = "edumind-phase1-t037-pg"
                env = run_catalog_db_tests.test_environment(
                    "edumind_catalog_p15_t038_r03"
                )
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    cwd=ROOT / "backend",
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                print(json.dumps(asyncio.run(advance(execution, env))))
        finally:
            ledger.close()


if __name__ == "__main__":
    try:
        main()
    except (Refused, FileExistsError):
        raise SystemExit(
            "REFUSED: missing approval, changed package, prior start or stopped batch. No retry."
        ) from None
    except Exception:
        # Never print provider/body/credential-bearing exception details.
        raise SystemExit(
            "STOPPED: execution error; inspect protected receipts. No automatic retry."
        ) from None
