"""Final isolated diagnostic contract; no model, transport or credential access."""

import json
import sqlite3

from . import claim_review_prototype as p
from . import span_review_offline as span
from .derived_diagnostic_budget import require
from .fixed_focus_gate import FixedFocusGate

VERSION = "fixed-focus-contract-v2"
SYSTEM = (
    span.PROMPTS["focus"]
    + """
Instruction version: fixed-focus-contract-v2.
Report only concrete, evidenced defects in the supplied candidate under its stated preconditions.
The same evidence and classification rules apply to findings and other_findings. Neither list
has a minimum count. Other discoveries may be omitted when no actual defect is established.
Do not treat style, brevity, redundant includes, missing print statements or optional exposition
as defects. Do not invent requirements or speculate that an existing check has been deleted.
Evaluate actual supplied code, not a hypothetical program with different safeguards.
Classification: code_safety requires a reachable unsafe execution, invalid memory access, lost
ownership or memory leak. Identify the input/state, actual responsible operation and consequence.
An explanation can make a safety claim, but an unsafe path must still be evidenced. A call that
can fail is not itself a defect when supplied safeguards handle it. Respect explicit preconditions.
fact means a non-safety conceptual, algorithmic or complexity contradiction. difficulty requires
an explicit learner requirement and an evidenced mismatch. misconception requires an explicit
teaching objective and an evidenced conflict; do not infer missing learner needs or desired text.
Do not force an observation into an allowed category when it is only a style preference.
Do not supply repair code or replacement formulas. Keep uncertainty explicit, never invent proof.
"""
)


def fixture(item):
    payload = {
        "resource_type": item["resource_type"],
        "content": {"markdown": item["markdown"]},
        "reference_context": item["reference_context"],
    }
    snap = p.freeze(
        payload["resource_type"],
        payload["content"],
        payload["reference_context"],
        {"experiment": "span-offline-v1"},
    )
    block = snap.blocks[0]
    start = block["text"].index(item["claim_text"])
    claim = p.claim(
        snap,
        {
            "text": item["claim_text"],
            "anchors": [
                {
                    "block_id": block["block_id"],
                    "start": start,
                    "end": start + len(item["claim_text"]),
                    "quote": item["claim_text"],
                }
            ],
            "related_anchors": [],
        },
    )
    req = span.focus_request(snap, item["probe_id"], claim)
    req["system"] = SYSTEM
    return {"probe_id": item["probe_id"], "claim": claim, "payload": payload}, req


class FinalFocusGate(FixedFocusGate):
    """Retain frozen transport/counter; classify fact and safety defects separately."""

    def _gate(self, db):
        super()._gate(db)
        require(self.plan["round"] == 2 and self.plan["prompt_version"] == VERSION, "INVALID_ROUND")
        prior = self.guard._path("local-materials/phase-1-t040-focus-r10/budget.sqlite")
        self.guard._safe_file(prior)
        with sqlite3.connect(f"file:{prior}?mode=ro", uri=True) as previous:
            frozen, halted = previous.execute("SELECT freeze,halted FROM run").fetchone()
            count = previous.execute("SELECT count(*) FROM attempts").fetchone()[0]
        require(
            frozen == self.plan["prior_root_sha256"] and halted is not None, "PREREQUISITE_MISSING"
        )
        require(0 <= count <= 4, "LEDGER_MISMATCH")
        current = db.execute("SELECT count(*) FROM attempts").fetchone()[0]
        require(count + current <= 8, "BUDGET_EXHAUSTED")

    def _coarse_row(self, db, row):
        value = json.loads(row["value"])
        expected = self.plan["expected_by_probe"][row["slot"]]
        if expected == "pass":
            if value["verdict"] != "pass" or value["findings"] or value["other_findings"]:
                self._halt(db, "CONTROL_REJECTED")
        elif value["verdict"] == "pass":
            self._halt(db, "CONCRETE_DEFECT_MISSED")
        elif not value["findings"] or any(f["area"] != expected for f in value["findings"]):
            self._halt(db, "ADMISSION_FAILED")
