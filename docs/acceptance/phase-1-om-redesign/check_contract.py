"""Check proposal schemas and synthetic examples; no runtime or Provider validation."""

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

b = Path("docs/acceptance/phase-1-om-redesign")
schema = json.loads((b / "minimum-contract.schema.json").read_text())
Draft202012Validator.check_schema(schema)
v = Draft202012Validator(schema, format_checker=FormatChecker())
samples = json.loads((b / "contract-examples.json").read_text())
for k in ["plan_record", "review_record"]:
    v.validate(samples[k])
draft_schema = {k: value for k, value in schema.items() if k != "oneOf"}
draft_schema["$ref"] = "#/$defs/plan_generation"
draft_validator = Draft202012Validator(draft_schema, format_checker=FormatChecker())
draft_validator.validate(samples["plan_generation"])
negative = []


def bad(label, key, mutate):
    x = copy.deepcopy(samples[key])
    mutate(x)
    assert list(v.iter_errors(x)), label
    negative.append(label)


bad("missing goal", "plan_record", lambda x: x["plan"].pop("goal"))
bad("extra field", "plan_record", lambda x: x["plan"].update(extra=True))
bad(
    "wrong scene key",
    "plan_record",
    lambda x: x["plan"]["scenes"][0].update(scene_key="intro"),
)
bad("wrong scene order", "plan_record", lambda x: x["plan"]["scenes"].reverse())
bad(
    "missing dependency",
    "plan_record",
    lambda x: x["plan"]["scenes"][2].update(depends_on=[]),
)
bad("invalid digest", "plan_record", lambda x: x["binding"].update(plan_digest="bad"))
bad(
    "invalid verdict", "review_record", lambda x: x["result"].update(verdict="approved")
)
bad(
    "old protocol",
    "review_record",
    lambda x: x["result"].update(schema_version="resource-review-v3"),
)
bad("missing local routing", "review_record", lambda x: x.pop("local_routing"))
invalid_draft = copy.deepcopy(samples["plan_generation"])
invalid_draft["graph_digest"] = "0" * 64
assert list(draft_validator.iter_errors(invalid_draft))
negative.append("model supplied server digest")
print(
    json.dumps(
        {
            "schema": "Draft202012 valid",
            "positive_examples": 3,
            "negative_examples": negative,
            "scope": "structure only; cross-field and runtime checks planned, not run",
        },
        ensure_ascii=False,
    )
)

# Approval binds files and task contracts, without making mutable task status immutable.

manifest_path = b / "proposal-manifest.json"
manifest = json.loads(manifest_path.read_text())
approval = json.loads(Path("docs/ADR/0015-approval-20261015.json").read_text())
assert (
    approval["approved_manifest_sha256"]
    == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
)
assert approval["approved_sections"] == ["A", "B", "C", "D"]
assert approval["provider_requests_authorized"] == 0
assert approval["fee_authorized"] == 0
assert approval["dynamic_opening_authorized"] is False
for entry in manifest["documents"]:
    actual = hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
    assert actual == entry["sha256"], entry["path"]
    assert approval["approved_files"][entry["path"]] == actual
active = {t["id"]: t for t in json.loads(Path("task.json").read_text())["tasks"]}
for contract in manifest["task_contracts"]:
    assert contract == {k: active[contract["id"]][k] for k in contract}
print(
    json.dumps(
        {
            "manifest_documents": len(manifest["documents"]),
            "task_contracts": len(manifest["task_contracts"]),
            "approval": "A-D; zero Provider implementation only",
        },
        ensure_ascii=False,
    )
)
