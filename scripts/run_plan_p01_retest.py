"""One explicitly authorized P01 repeat; old stopped run remains immutable."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import httpx
import run_plan_admission as parent
from acceptance_support.five_hour_runtime import private_directory, require, write_once
from acceptance_support.plan_admission_live import execute, live_gateway
from acceptance_support.plan_admission_run import Ledger
from acceptance_support.qwen_review_budget import canonical, sha

PACKAGE = ROOT / "docs/acceptance/phase-1-plan-p01-retest-r01"
PRIVATE = ROOT / "local-materials/phase-1-plan-p01-retest-r01"
OLD_LEDGER = ROOT / "local-materials/phase-1-plan-admission-execution-r02/run.sqlite"
WIRE_SHA = "5377d9faa6594265af556cc73504a8ba6f25aeecd29976f449499a407885183b"


class SingleWire(httpx.AsyncBaseTransport):
    def __init__(self, role, inner=None):
        self.role, self.used = role, False
        self.inner = (
            inner
            if inner is not None
            else httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        )

    async def handle_async_request(self, request):
        require(
            self.role == "review"
            and not self.used
            and sha(request.content) == WIRE_SHA,
            "EXACT_SINGLE_WIRE_REQUIRED",
        )
        self.used = True  # Also consumes this transport on an uncertain send/failure.
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


def spec():
    return parent.slots()[0]


def freeze():
    require(not (PACKAGE / "manifest.json").exists(), "FROZEN_PACKAGE_CANNOT_REWRITE")
    h = parent.verify()
    summary = parent.read(
        ROOT / "docs/acceptance/phase-1-plan-admission-results-r02/summary.json"
    )
    require(
        sha(OLD_LEDGER.read_bytes()) == summary["artifacts"]["ledger_sha256"],
        "OLD_STOPPED_LEDGER_CHANGED",
    )
    tests = parent.read(PACKAGE / "offline-tests.json")
    require(
        tests["exit"] == 0 and tests["provider_calls"] == 0, "OFFLINE_CHECK_REQUIRED"
    )
    files = [
        ROOT / "scripts/run_plan_p01_retest.py",
        ROOT / "scripts/tests/test_plan_p01_retest.py",
    ]
    files += [p for p in PACKAGE.iterdir() if p.is_file()]
    write_once(
        PACKAGE / "manifest.json",
        dict(
            parent_manifest_sha256=h,
            spec=spec(),
            wire_sha256=WIRE_SHA,
            old_ledger_sha256=sha(OLD_LEDGER.read_bytes()),
            requests_max=1,
            per_request_seconds=60,
            case_seconds=180,
            retries=0,
            fallbacks=0,
            stop_after_response=True,
            source_user_message="重测一次",
            files={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in files},
        ),
    )


def verify():
    m = parent.read(PACKAGE / "manifest.json")
    require(parent.verify() == m["parent_manifest_sha256"], "PARENT_CHANGED")
    require(
        m["spec"] == spec()
        and m["wire_sha256"] == WIRE_SHA
        and m["requests_max"] == 1
        and m["retries"] == m["fallbacks"] == 0
        and m["source_user_message"] == "重测一次",
        "AUTHORIZATION_CHANGED",
    )
    require(
        sha(OLD_LEDGER.read_bytes()) == m["old_ledger_sha256"],
        "OLD_STOPPED_LEDGER_CHANGED",
    )
    for name, h in m["files"].items():
        p = ROOT / name
        require(
            p.resolve().is_relative_to(ROOT)
            and not p.is_symlink()
            and sha(p.read_bytes()) == h,
            "FREEZE_CHANGED",
        )
    return sha((PACKAGE / "manifest.json").read_bytes())


async def once(ledger, *, keys):
    directory = private_directory(PRIVATE / "P01")
    c = dict(ledger=ledger, spec=spec(), directory=directory, call_ids=[], calls=[])
    ledger.start(spec()["slot_id"])
    transports = []
    try:
        gateway, transports = live_gateway(
            c, keys=keys, inner_factory=lambda role: SingleWire(role)
        )
        async with asyncio.timeout(180):
            result = await execute(
                spec(), parent.read(ROOT / spec()["material"]), gateway
            )
        evidence = dict(
            material=parent.read(ROOT / spec()["material"]),
            result=result,
            calls=c["calls"],
            review_sources=c.get("review_sources", {}),
            parsed_calls=[
                parent.read(directory / f"{n:02}-parsed.json") for n in c["call_ids"]
            ],
            logical_requests=[
                parent.read(directory / f"{n:02}-logical.json") for n in c["call_ids"]
            ],
            artifact_hashes={
                p.name: sha(p.read_bytes()) for p in directory.iterdir() if p.is_file()
            },
        )
        write_once(directory / "result.json", evidence)
        ledger.finish(spec()["slot_id"], sha(canonical(evidence)))
        ledger.stop("SINGLE_REPEAT_FINISHED_STOP_NO_CONTINUATION")
    except BaseException:
        ledger.stop("SINGLE_REPEAT_FAILED_STOP_NO_RETRY")
        write_once(
            directory / "failure-summary.json",
            dict(
                call_ids=c["call_ids"],
                kind="single_repeat_failed",
                artifacts={
                    p.name: sha(p.read_bytes())
                    for p in directory.iterdir()
                    if p.is_file()
                },
            ),
        )
        raise
    finally:
        for transport in transports:
            await transport.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "check", "run", "report"])
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    h = verify()
    if args.action in ("freeze", "check"):
        print(
            json.dumps(
                dict(manifest_sha256=h, requests_max=1, old_run_still_stopped=True)
            )
        )
        return
    private_directory(PRIVATE)
    with (PRIVATE / "process.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "run":
            require(not (PRIVATE / "run.sqlite").exists(), "SINGLE_RUN_NO_REPLAY")
            keys = parent.load_keys(
                parent.read(parent.PACKAGE / "manifest.json")["env_metadata"]
            )
            ledger = Ledger(PRIVATE / "run.sqlite", h, [spec()], activate=True)
            asyncio.run(once(ledger, keys=keys))
        else:
            ledger = Ledger(PRIVATE / "run.sqlite", h, [spec()])
        print(json.dumps(ledger.snapshot()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Single P01 repeat failed closed; no retry or old-run reopening.",
            file=sys.stderr,
        )
        sys.exit(1)
