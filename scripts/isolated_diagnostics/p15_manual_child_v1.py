"""Synthetic-only one-shot child, invoked by absolute path in Python isolated mode."""

import json
import os
import sys
import time


def main() -> None:
    data = json.loads(sys.stdin.buffer.readline())
    if set(data) != {"role", "key", "body", "delay"}:
        raise SystemExit(2)
    if data["role"] not in ("generation", "review") or not data["key"].startswith("synthetic-"):
        raise SystemExit(2)
    if not isinstance(data["delay"], (int, float)) or not 0 <= data["delay"] <= 20:
        raise SystemExit(2)
    time.sleep(data["delay"])
    result = {
        "role": data["role"],
        "body": data["body"],
        "pid": os.getpid(),
        "paths": sys.path,
        "provider_call": False,
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
