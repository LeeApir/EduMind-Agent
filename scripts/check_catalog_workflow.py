"""Check the approved catalog scope without touching services or providers."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
active = json.loads((root / "task.json").read_text())
active_by_id = {t["id"]: t for t in active["tasks"]}
assert len(active_by_id) == len(active["tasks"])
assert all(t["phase"] == active["active_phase"] for t in active["tasks"])
assert all(t["status"] in {"todo", "in_progress", "blocked", "done"} for t in active["tasks"])
assert all(dep in active_by_id for t in active["tasks"] for dep in t["depends_on"])
assert sum(t["status"] == "in_progress" for t in active["tasks"]) <= 1


def visit(task_id, path, visited):
    assert task_id not in path, "Cyclic task dependency: " + task_id
    if task_id in visited:
        return
    for dependency in active_by_id[task_id]["depends_on"]:
        visit(dependency, path | {task_id}, visited)
    visited.add(task_id)


visited = set()
for task_id in active_by_id:
    visit(task_id, set(), visited)

d = active if active["active_phase"] == "MVP 0.3" else json.loads(
    (root / "docs/tasks/mvp-0.3.json").read_text()
)
assert d["active_phase"] == "MVP 0.3"
by_id = {t["id"]: t for t in d["tasks"]}
assert len(by_id) == len(d["tasks"])
assert by_id["MVP-0.3-T033"]["status"] == "blocked"
assert by_id["MVP-0.3-T034"]["depends_on"] == ["MVP-0.3-T032", "MVP-0.3-T045", "MVP-0.3-T046"]
assert d["stage_scope"]["catalog_only"]["provider_requests"] == 0
assert all(dep in by_id for t in d["tasks"] for dep in t["depends_on"])
assert sum(t["status"] == "in_progress" for t in d["tasks"]) <= 1
assert "目录版" in (root / "docs/PRD.md").read_text()
assert "Accepted" in (root / "docs/ADR/0007-curated-course-catalog.md").read_text()
print(f"Active {active['active_phase']} dependencies valid; catalog ledger valid; T033 blocked")
