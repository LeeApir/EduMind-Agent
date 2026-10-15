"""Prepare offline source-ID examples and an unsigned four-focus worksheet, no API access."""

import argparse
import hashlib
import json
from pathlib import Path

from acceptance_support import claim_review_prototype as p
from acceptance_support import span_review_offline as span

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1-t040-span-review-offline"
HISTORY = "docs/acceptance/phase-1-dynamic-v1/history.json"
DRAFTS = (
    (
        "queue:explanation:1",
        "- 元素个数：`size = rear - front`（在 rear 指向下一个空位的约定下）。",
        "在 rear 指向下一个空位的约定下，元素个数满足 size = rear - front。",
    ),
    (
        "queue:explanation:1",
        "- 空队列条件：`front == rear`。",
        "front == rear 是空队列条件。",
    ),
    ("correct-list-concept", "链表节点可以分散存储", "链表节点可以分散存储。"),
    ("correct-list-concept", "链域保存后继节点地址", "链域保存后继节点地址。"),
)


def locate(snap, quote):
    hits = []
    for b in snap.blocks:
        start = b["text"].find(quote)
        if start >= 0:
            if b["text"].find(quote, start + 1) >= 0:
                raise p.Invalid("AMBIGUOUS_MANUAL_EXCERPT")
            hits.append(
                {
                    "block_id": b["block_id"],
                    "start": start,
                    "end": start + len(quote),
                    "quote": quote,
                }
            )
    if len(hits) != 1:
        raise p.Invalid("MISSING_OR_AMBIGUOUS_MANUAL_EXCERPT")
    return hits


def build(root=ROOT):
    history = json.loads((root / HISTORY).read_text())
    by_id = {c["id"]: c for c in history["cases"]}
    snapshots = {}
    for c in history["cases"]:
        if p.digest(c["payload"]) != c["payload_sha256"]:
            raise p.Invalid("HISTORY_CHANGED")
        snapshots[c["id"]] = p.freeze(
            c["payload"]["resource_type"],
            c["payload"]["content"],
            c["payload"]["reference_context"],
            config={"experiment": "span-offline-v1"},
        )
    focused, previews, labels = [], [], []
    for i, (case_id, quote, description) in enumerate(DRAFTS, 1):
        snap = snapshots[case_id]
        probe_id = f"focus-{i:02d}"
        claim = p.claim(
            snap,
            {
                "text": description,
                "anchors": locate(snap, quote),
                "related_anchors": [],
            },
        )
        focused.append(
            {
                "probe_id": probe_id,
                "historical_case_id": case_id,
                "candidate_sha256": snap.candidate_sha256,
                "context_sha256": snap.context_sha256,
                "claim": claim,
                "scope": "selected-claim-only",
                "drafted_by": "assistant",
                "human_confirmed_by": None,
                "human_confirmation_source": None,
                "full_resource_coverage_verified": False,
            }
        )
        previews.append(span.focus_request(snap, probe_id, claim))
        # Existing expected judgments stay outside every model-facing preview.
        labels.append(
            {
                "probe_id": probe_id,
                "historical_case_id": case_id,
                "original_label_sha256": p.digest(by_id[case_id]),
                "expected": "concrete_defect_fact" if i <= 2 else "pass",
                "source": "original approved historical labels, not a new test outcome",
            }
        )
    selection = [
        span.request(snapshots[cid], "selection", f"selection-{i:02d}")
        for i, cid in enumerate(("queue:explanation:1", "correct-list-concept"), 1)
    ]
    measures = [
        {
            "historical_case_id": cid,
            "leaf_blocks": len(snap.blocks),
            "spans": len(span.spans(snap)),
            "requires_disposition": sum(
                s["requires_disposition"] for s in span.spans(snap)
            ),
            "candidate_context_bytes": len(snap.serialized),
            "semantic_claim_count": "NOT_MEASURED",
        }
        for cid, snap in snapshots.items()
    ]
    sources = [
        HISTORY,
        "scripts/acceptance_support/span_review_offline.py",
        "scripts/prepare_t040_span_review.py",
        "scripts/acceptance_support/claim_review_prototype.py",
        "backend/uv.lock",
        "backend/tests/test_span_review_offline.py",
    ]
    worksheet = {
        "version": "span-focus-worksheet-draft-v1",
        "status": "PENDING_HUMAN_SCOPE_CHECK",
        "human_approved": False,
        "scope": "four selected claims, not complete inventories",
        "items": focused,
        "source_sha256": {
            f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in sources
        },
    }
    policy = {
        "version": "span-redesign-exit-proposal-v1",
        "status": "OFFLINE_PROPOSAL_ONLY",
        "strategy_id": "span-selection-redesign-v1",
        "provider_requests_authorized": 0,
        "provider_cost_micro_authorized": 0,
        "r09_resumed": False,
        "old_remaining_slots_reused": False,
        "max_future_real_rounds": 2,
        "max_attempts_per_round": 4,
        "max_future_attempts_total": 8,
        "cost_cap_micro_cny": None,
        "rounds_cover_both_tracks": True,
        "order": [
            "human-confirmed focused reviewer calibration",
            "source-ID selection experiment only after reviewer evidence supports it",
        ],
        "stop": [
            "Any protocol, coverage, identity, unknown usage or budget failure stops a run.",
            "Concrete missed defect, wrong category, false rejection or new factual error fails the focused reviewer gate.",
            "Do not repeat identical configuration after failure; any second round needs a materially different, frozen, independently approved plan.",
            "After two real rounds or eight attempted requests, whichever first, end this strategy experiment without resetting its counter by track or case.",
            "No full resource/automatic extraction quality pass inferred from focused claims or synthetic tests.",
        ],
        "next_decision_if_failed": "Retain catalog_only and T040 blocked; explicitly choose a different model/strategy or human review. No automatic new paid round.",
    }
    return {
        "worksheet.json": worksheet,
        "focus-previews.json": previews,
        "selection-previews.json": selection,
        "expectations-not-for-model.json": labels,
        "historical-size-screen.json": measures,
        "exit-policy-proposal.json": policy,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    BASE.mkdir(parents=True, exist_ok=True)
    for name, value in generated.items():
        path = BASE / name
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if path.read_text() != raw:
                raise p.Invalid("OFFLINE_DRAFT_CHANGED")
        else:
            path.write_text(raw)
    print(
        "PASS: offline spans/four-focus unsigned worksheet; Provider calls=0; no real run approval."
    )


if __name__ == "__main__":
    main()
