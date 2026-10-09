"""Reject absent, substituted or incomplete fixed font before trusted scene execution."""

import ast
import hashlib
import subprocess
from pathlib import Path

FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
DIGEST = "b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
FAMILY = "Noto Sans CJK SC"


def check_font(source: bytes) -> None:
    if not FONT.is_file() or hashlib.sha256(FONT.read_bytes()).hexdigest() != DIGEST:
        raise ValueError("DSL_RENDER_UNAVAILABLE")
    matched = (
        subprocess.run(
            ["fc-match", FAMILY, "-f", "%{family}\n%{file}\n"],
            capture_output=True,
            timeout=2,
            check=True,
        )
        .stdout.decode()
        .splitlines()
    )
    if matched != [FAMILY, str(FONT)]:
        raise ValueError("DSL_RENDER_UNAVAILABLE")
    charset = subprocess.run(
        ["fc-query", "--index", "2", "--format", "%{charset}", str(FONT)],
        capture_output=True,
        timeout=2,
        check=True,
    ).stdout.decode()
    if len(charset) > 65536:
        raise ValueError("DSL_RENDER_UNAVAILABLE")
    ranges = []
    for entry in charset.split():
        bounds = entry.split("-")
        ranges.append((int(bounds[0], 16), int(bounds[-1], 16)))
    # Parse only; the AST checker already rejects all other candidate constructs.
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Text"
        ):
            text = node.args[0].value
            for char in text:
                if not char.isspace() and not any(lo <= ord(char) <= hi for lo, hi in ranges):
                    raise ValueError("DSL_RENDER_UNAVAILABLE")
