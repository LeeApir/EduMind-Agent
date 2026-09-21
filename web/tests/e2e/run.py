"""Start an isolated Vite server and run the Python Playwright suite."""

import os
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

WEB_DIR = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
PORT = 4173


def wait_for_server() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://{HOST}:{PORT}", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Vite E2E server did not become ready within 30 seconds")


def main() -> None:
    environment = os.environ.copy()
    environment["EDUMIND_E2E_BASE_URL"] = f"http://{HOST}:{PORT}"
    process = subprocess.Popen(
        ["pnpm", "dev", "--host", HOST, "--port", str(PORT)],
        cwd=WEB_DIR,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()
        os.environ["EDUMIND_E2E_BASE_URL"] = environment["EDUMIND_E2E_BASE_URL"]
        from learning_flow import run

        run()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
