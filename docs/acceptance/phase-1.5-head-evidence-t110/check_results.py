"""Read-only T110 status/evidence delivery check. No Provider or private keys."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from scripts import prepare_head_course_evidence as prep  # noqa: E402

HERE = Path(__file__).resolve().parent
OLD = prep.OLD


def read(path):
    return json.loads(path.read_text())


def main():
    for name, raw in prep.outputs().items():
        assert (HERE / name).read_bytes() == raw, name
    old_index = read(OLD / "delivery-manifest.json")
    for name, sha in old_index["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
    frozen = read(ROOT / "docs/acceptance/phase-1.5-head-reuse-t109/manifest.json")
    for name, sha in frozen["files"].items():
        # The original executed source lives in Git, not in a silently re-frozen old package.
        raw = subprocess.check_output(["git", "show", "674fc06:" + name], cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest() == sha, name
    assert (
        hashlib.sha256(
            (
                ROOT / "docs/acceptance/phase-1.5-head-reuse-t109/manifest.json"
            ).read_bytes()
        ).hexdigest()
        == "f4c98c1a24d2943dd7f38350095932f1e933a46757eee3896156439d05bd239b"
    )
    before = read(OLD / "app-browser-stop.json")
    after = read(HERE / "actual-failed-page.json")
    assert after["operation_status"] == 200
    assert after["course"] == before["course"]
    assert after["operation"]["budget"] is None
    assert after["operation"]["execution_mode"] == "finite_head_foreground"
    for key, value in before["operation"].items():
        if key != "budget":
            assert after["operation"][key] == value, key
    assert all(after["assertions"].values())
    assert "生成已停止" in after["screen"]
    assert (
        "剩余 13" not in after["screen"] and "确认继续缺失内容" not in after["screen"]
    )
    ordinary = read(HERE / "actual-ordinary-budget.json")
    assert ordinary["fixture"] and ordinary["status"] == 200
    assert "execution_mode" not in ordinary["operation"]
    assert ordinary["operation"]["budget"]["attempts_remaining"] == 13
    assert ordinary["budget_visible"] and "尝试已用 0 · 剩余 13" in ordinary["screen"]
    assert (
        after["new_operations_submitted"] == ordinary["new_operations_submitted"] == 0
    )
    x = read(ROOT / "task.json")
    for tid in ("PHASE-1.5-T109", "PHASE-1.5-T102"):
        assert next(t for t in x["tasks"] if t["id"] == tid)["status"] == "blocked"
    assert x["stage_scope"]["provider_requests_authorized"] == 0
    print(
        "PASS: original candidate/request replay and410 frozen Git source hashes; new fact bindings; actual finite page/budget plus ordinary budget; T109/T102 blocked; Provider0"
    )


if __name__ == "__main__":
    main()
