"""Run one disposable loopback browser server, then gracefully remove its test session."""

import argparse
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", choices=["pending", "rejected", "published"], required=True
    )
    parser.add_argument("--attempt", choices=["r01", "r02"], default="r01")
    args = parser.parse_args()
    command = [
        sys.executable,
        str(ROOT / "scripts/serve_stored_acceptance.py"),
        "--case",
        args.case,
        "--attempt",
        args.attempt,
    ]
    process = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("read-only server exited before readiness")
            try:
                with socket.create_connection(("127.0.0.1", 18179), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("read-only server readiness deadline")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/check_stored_browser.py"),
                "--case",
                args.case,
                "--attempt",
                args.attempt,
            ],
            cwd=ROOT,
        )
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise RuntimeError("graceful cleanup incomplete")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
