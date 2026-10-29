"""Check documented output leaves against the approved frozen schema; no I/O to providers."""

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
book_path = ROOT / "docs/acceptance/phase-1.5-minimal-output-contract-r01/schemas.json"
raw = book_path.read_bytes()
inv = json.loads((HERE / "field-inventory.json").read_text())
assert hashlib.sha256(raw).hexdigest() == inv["schema_sha256"]
book = json.loads(raw)
assert inv["stages"] == book["stage_schema"]


def leaves(schema, path=""):
    if schema["type"] == "object":
        assert set(schema["properties"]) == set(schema["required"])
        for name, child in schema["properties"].items():
            yield from leaves(child, path + "/" + name)
    elif schema["type"] == "array":
        yield from leaves(schema["items"], path + "/*")
    else:
        yield path


expected = {(name, path) for name, schema in book["schemas"].items() for path in leaves(schema)}
rows = inv["fields"]
actual = [(row["schema"], row["path"]) for row in rows]
assert len(actual) == len(set(actual)) and set(actual) == expected
assert all(all(isinstance(row[k], str) and row[k] for k in ("output_owner", "mechanical", "semantic")) for row in rows)
for link in re.findall(r"\]\(([^)]+)\)", (HERE / "README.md").read_text()):
    if not link.startswith(("https://", "http://", "#")):
        assert (HERE / link.split("#", 1)[0]).exists(), link
print(f"Schema inventory verified: {len(rows)} leaves / {len(book['schemas'])} schemas / {len(book['stage_schema'])} stage mappings; links valid")
