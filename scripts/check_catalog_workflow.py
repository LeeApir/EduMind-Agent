"""Check the approved catalog scope without touching services or providers."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
d = json.loads((root / "task.json").read_text())
by_id = {t["id"]: t for t in d["tasks"]}
assert len(by_id) == len(d["tasks"])
assert by_id["MVP-0.3-T033"]["status"] == "blocked"
assert by_id["MVP-0.3-T034"]["depends_on"] == ["MVP-0.3-T032", "MVP-0.3-T045", "MVP-0.3-T046"]
assert d["stage_scope"]["catalog_only"]["provider_requests"] == 0
assert all(dep in by_id for t in d["tasks"] for dep in t["depends_on"])
assert sum(t["status"] == "in_progress" for t in d["tasks"]) <= 1
assert "目录版" in (root / "docs/PRD.md").read_text()
assert "Accepted" in (root / "docs/ADR/0007-curated-course-catalog.md").read_text()
print("Catalog scope/task dependencies valid; T033 blocked; Provider calls 0")
