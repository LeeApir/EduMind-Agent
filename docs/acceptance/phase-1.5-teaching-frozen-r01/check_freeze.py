"""Verify the frozen isolated candidate without credentials or network."""

import hashlib
import json
from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_teaching_revision as t
from scripts.isolated_diagnostics import p15_review_engineering as r
from scripts.run_p15_schema_probe_p02 import runtime_versions

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
manifest = json.loads((HERE / "manifest.json").read_text())
assert (
    manifest["version"] == t.PROMPT_VERSION
    and manifest["runtime"] == runtime_versions()
)
paths = []
for row in manifest["files"]:
    path = Path(row["path"])
    assert not path.is_absolute() and ".." not in path.parts
    file = ROOT / path
    assert file.is_file() and all(not p.is_symlink() for p in (file, *file.parents))
    assert hashlib.sha256(file.read_bytes()).hexdigest() == row["sha256"]
    paths.append(row["path"])
assert len(paths) == len(set(paths))
snapshot = json.loads((HERE / "prompt-snapshot.json").read_text())
assert snapshot == dict(
    prompt_version=t.PROMPT_VERSION,
    rule_version=t.RULE_VERSION,
    instructions={s: t.instruction(s) for s in c.STAGES},
)
policy = json.loads((HERE / "policy.json").read_text())
assert (
    policy["review_limits"] == r.POLICY.__dict__
    and policy["per_arm_supported"] == 10
    and policy["per_arm_refused"] == 4
)
print(
    f"candidate frozen: {len(paths)} files, {len(c.STAGES)} role instructions; no Provider calls; not a live execution grant"
)
