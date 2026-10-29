"""Read-only verification of the stopped T095 batch; never uses credentials or network."""

import hashlib
import json
from pathlib import Path
from scripts import run_p15_combined_candidate as cli
from scripts.isolated_diagnostics import p15_combined_candidate_runner as runner
from scripts.isolated_diagnostics.p15_pilot_wire import strict_json

here = Path(__file__).resolve().parent
manifest = json.loads((here / "manifest.json").read_text())
for row in manifest["files"]:
    path = here / row["path"]
    assert path.is_file() and not path.is_symlink()
    raw = path.read_bytes()
    assert len(raw) == row["size"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
package, _ = cli.load_package()
rawdir = here / "originals"
grant = strict_json((rawdir / "grant.json").read_bytes())
events = [strict_json(f.read_bytes()) for f in sorted(rawdir.glob("event-*.json"))]
state, w = runner.replay(events, rawdir, package, grant)
assert (
    state["phase"] == "terminal"
    and len(events) == 47
    and len(state["sent"]) == len(state["validated"]) == 9
)
assert events[-1]["data"] == {
    "outcome": "stopped",
    "reason": "COMBINED_PROTOCOL_OR_TRANSPORT_FAILURE",
}
assert w.stage == "course_review_0" and len(w.versions) == 1 and not w.opinions
assert w.versions[0] == json.loads((here / "candidate.json").read_text())
assert len((here / "review-request-unsent.json").read_bytes()) == 79305
try:
    w.next_request()
    raise AssertionError("oversize review must refuse")
except ValueError as exc:
    assert str(exc) == "COURSE_REQUEST_SIZE"
print(
    "verified 75 original files, 47 events, 9 real-dispatch markers; 7 roles admitted, course review unsent, size 79305/65536; teaching not evaluated; no new HTTP"
)
