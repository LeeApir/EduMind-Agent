"""Existing UI contracts against explicit mock HTTP, on an isolated local Vite."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def ready(url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1):
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Isolated Vite did not start")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[3]
    base = "http://127.0.0.1:4239"
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4239", "--strictPort"],
        cwd=root / "web",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready(base)
        for name in ("provider_settings", "model_preferences"):
            subprocess.run(
                [
                    sys.executable,
                    f"web/tests/e2e/{name}.py",
                    "--url",
                    base,
                    "--evidence",
                    str(args.output / name),
                ],
                cwd=root,
                check=True,
            )
        # All native adapter selection UI checks remain mock; no real credentials.
        for native in ("anthropic", "gemini", "spark"):
            subprocess.run(
                [
                    sys.executable,
                    "web/tests/e2e/provider_settings.py",
                    "--url",
                    base,
                    "--evidence",
                    str(args.output / native),
                    "--native-type",
                    native,
                ],
                cwd=root,
                check=True,
            )
        os.environ["EDUMIND_EXPANDED_UI_URL"] = base
        import expanded_path_flow

        expanded_path_flow.EVIDENCE = args.output / "expanded-path"
        expanded_path_flow.main()
    finally:
        web.terminate()
        try:
            web.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web.kill()
            web.wait(timeout=5)
    print(
        "Mock connections / native settings / explicit routes / expanded paths passed"
    )


if __name__ == "__main__":
    main()
