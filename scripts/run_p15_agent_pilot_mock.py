"""Offline demo only. No .env, provider config, databases or live transport."""

import argparse
import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics.p15_agent_pilot import Pilot, write_mock_evidence  # noqa: E402
from scripts.isolated_diagnostics.p15_agent_pilot_mock import (  # noqa: E402
    course_markdown,
    mock_gateway,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    gateway = mock_gateway()
    spec = dict(
        version="head-insertion-spec-v1",
        initial_values=[9],
        insert_values=[1, 2],
        variant="normal",
        allocation_success=[True, True],
    )
    result = asyncio.run(
        Pilot(gateway, gateway).run(
            run_id="development", slot_id="seen_normal", spec=spec
        )
    )
    write_mock_evidence(args.output, result, [gateway])
    fd = os.open(
        args.output / "course.md",
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "w") as stream:
        stream.write(course_markdown(result))
    print("Mock only:", result["state"], "calls:", result["calls"], "real HTTP: 0")
    return 0 if result["state"] == "mock_advisory_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
