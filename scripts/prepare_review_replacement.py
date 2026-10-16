"""Zero-call candidate screening freeze with real review-entry / mocked HTTP capture."""

# ruff: noqa: E402
import argparse
import asyncio
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import httpx
from acceptance_support.om_diagnostic import stable, valid_review
from acceptance_support.phase1_budget import sha
from acceptance_support.review_replacement import (
    CandidateReviewGateway,
    candidate_config,
)
from app.agents.hybrid_resource_review import review_once
from app.agents.planned_scene_generation import SceneCandidate
from app.agents.shared_learning_plan import CallWindow
from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.learning_policy import active_policy_digest
from run_review_replacement import core as r

BASE = r.BASE
PRIOR = "docs/acceptance/phase-1-evidence-v45-r01"
CRITERIA = {
    "reachable-safety:candidate": "reject with major/severe reachable code_safety (length3, index4); no deterministic UB return, inequality or crash. Audit every finding/impact and all citations. Judgment-question propositions are not automatically endorsed facts.",
    "fact-contradiction:candidate": "reject with major/severe fact: stated18 versus actual16 in defined loop. Each cited field supports its actual proposition; do not borrow neighboring content or treat an F answer as numeric evidence.",
    "gap-and-safety:candidate": "reject with major/severe reachable code_safety despite teaching gap; identify gaps as uncertainty, do not downgrade serious errors or invent factual contradictions; all accompanying claims/citations correct.",
    "trace-complete:candidate": "pass with all five checks and empty findings/unchecked/unresolved; no accompanying false positives.",
}


def read(path):
    return json.loads(path.read_text())


def review_document(data):
    lines = [
        "# 单候选high筛选：预先冻结材料与逐项淘汰判据",
        "",
        "尚未批准真实调用/标签。四条各最多一次，任何完整性、断言或引用失败即淘汰本配置并停止；不得调整后重跑本包。",
    ]
    for slot, case in data.items():
        lines += [
            "",
            "## " + slot,
            CRITERIA[slot],
            "材料摘要：" + stable(case["material"]),
            "```json",
            json.dumps(case["material"], ensure_ascii=False, indent=2),
            "```",
        ]
    return "\n".join(lines) + "\n"


class OfflineGuard:
    def approve_base(self):
        return ApprovedTarget(
            "https://api.deepseek.com", "api.deepseek.com", 443, ("8.8.8.8",)
        )


async def capture_case(case):
    """No DNS, credential or network access. Synthetic replies prove protocol only."""
    calls = []

    def send(request):
        calls.append(request.content)  # Never record headers or credentials.
        payload = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(valid_review("unit")),
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 90, "output_tokens": 100},
        }
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(payload).encode())
        )

    config = candidate_config()
    gateway = CandidateReviewGateway(
        config,
        ProviderSettings(config["base_url"], "OFFLINE_SYNTHETIC_KEY", config["model"]),
        OfflineGuard(),
        transport=httpx.MockTransport(send),
    )
    material = case["material"]
    candidates = tuple(
        SceneCandidate(
            c["resource_id"],
            c["role"],
            c["envelope"],
            c["content_digest"],
            c["dependency_digest"],
            tuple(c["upstream"]),
        )
        for c in material["candidates"]
    )
    record = await review_once(
        gateway,
        CallWindow(),
        binding=material["binding"],
        target_digest=material["unit_digest"],
        payload={"unit": material, "reference_context": material["reference_context"]},
        candidates=candidates,
        scope="unit",
        input_snapshot=case["input_snapshot"],
    )
    assert len(calls) == len(gateway.calls) == 1
    actual = calls[0]
    body = json.loads(actual)
    baseline = json.loads(bytes.fromhex(case["wire_hex"]))
    changed = {k for k in body if body[k] != baseline[k]}
    assert changed == {"reasoning"}
    assert body["reasoning"] == {"effort": "high"}
    expected_config = {
        "provider": "deepseek_responses",
        "host": "api.deepseek.com",
        "model": "deepseek-flash",
        "reasoning": {"effort": "high"},
        "temperature": 0.0,
        "max_output_tokens": 8192,
    }
    expected_digest = hashlib.sha256(
        json.dumps(expected_config, sort_keys=True).encode()
    ).hexdigest()
    assert record["provider_config_digest"] == expected_digest
    assert record["request_digest"] == sha(actual)
    assert (
        record["binding"]["policy_digest"]
        == config["policy_digest"]
        == active_policy_digest()
    )
    assert record["prompt_version"] == config["review_prompt_version"]
    assert gateway.calls[0].prompt.max_output_tokens == 2048
    evidence = {
        "kind": "OFFLINE_SYNTHETIC_NOT_QUALITY_EVIDENCE",
        "entry": "hybrid_resource_review.review_once(unit)",
        "task_profile": "quality",
        "business_entry_output_default": 2048,
        "unchanged_diagnostic_output_override": 8192,
        "gateway": "CandidateReviewGateway -> DeepSeekResponsesAdapter -> httpx.MockTransport",
        "actual_wire_sha256": sha(actual),
        "baseline_wire_sha256": sha(bytes.fromhex(case["wire_hex"])),
        "changed_path_only": "reasoning.effort: low -> high",
        "captured_model": body["model"],
        "captured_reasoning": body["reasoning"],
        "captured_total_output_limit": body["max_output_tokens"],
        "provider_config_digest": record["provider_config_digest"],
        "expected_adapter_config": {**expected_config, "temperature": 0},
        "policy_digest": record["binding"]["policy_digest"],
        "prompt_version": record["prompt_version"],
        "candidate_config_sha256": stable(config),
        "request_input_sha256": stable(body["input"]),
        "output_format_sha256": stable(body["text"]),
        "material_sha256": stable(material),
        "anchors_sha256": stable(record["anchor_catalog"]),
        "real_provider_requests": 0,
    }
    assert record["anchor_catalog"] == case["anchors"]
    return actual, evidence


def build(root=ROOT):
    previous = read(root / PRIOR / "proposal.json")
    if (
        stable(previous)
        != "d61ec628e5e3f7f30c420e1677fe4dcc361cddbeda4e4966c4dd8fa641c40de3"
    ):
        raise ValueError("HISTORICAL_FREEZE_CHANGED")
    old = read(root / PRIOR / "cases.json")
    assert stable(old) == previous["cases_sha256"]
    sources = deepcopy(previous["sources"])
    for name, expected in sources.items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError("SOURCE_CHANGED")
    data, captures, slots, labels = {}, {}, [], []
    for slot in r.SLOT_IDS:
        actual, evidence = asyncio.run(capture_case(old[slot]))
        data[slot] = {**deepcopy(old[slot]), "wire_hex": actual.hex()}
        captures[slot] = evidence
        cost = 2 * (1048576 + len(actual)) + 8 * 8192
        slots.append(
            {
                "id": slot,
                "wire_sha256": sha(actual),
                "wire_bytes": len(actual),
                "cost_micro_cny": cost,
            }
        )
        labels.append(
            {
                "id": slot,
                "material_sha256": stable(data[slot]["material"]),
                "criterion": CRITERIA[slot],
                "all_assertions_and_citations_required": True,
            }
        )
    config = candidate_config()
    proof = read(root / BASE / "official-terms.json")
    assert (
        proof["reasoning_efforts"] == ["high"]
        and proof["output_ceiling_per_request_including_reasoning"] == 8192
    )
    assert proof["verified_terms"]["reasoning_high_supported"] is True
    assert (
        proof["model"],
        proof["currency"],
        proof["context_input_ceiling"],
        proof["input_micro_cny_per_million"],
        proof["output_micro_cny_per_million"],
    ) == ("deepseek-flash", "CNY", 1048576, 2000000, 8000000)
    proof["candidate_config_sha256"] = stable(config)
    proposed = {
        "status": "PROPOSED_NOT_HUMAN_SIGNED",
        "rows": labels,
        "basis": "Same four v4.5 diagnostic materials, not independent holdouts; no new baseline calls.",
    }
    extra = [
        "scripts/acceptance_support/review_replacement.py",
        "scripts/prepare_review_replacement.py",
        "scripts/run_review_replacement.py",
        "scripts/tests/test_review_replacement.py",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        BASE + "/candidate-config.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        PRIOR + "/results/reachable-safety-01.json",
        PRIOR + "/results/reachable-safety-01-review.md",
        PRIOR + "/results/reachable-safety-01-validation.json",
    ]
    # candidate-config is a deterministic output and included in the kernel files below.
    sources.update(
        {
            n: sha((root / n).read_bytes())
            for n in extra
            if not n.endswith("/candidate-config.json")
        }
    )
    sources[BASE + "/candidate-config.json"] = sha(
        (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()
    )
    p = {
        **deepcopy(previous),
        "version": "review-replacement-r01",
        "implementation_baseline": "0657163",
        "sources": sources,
        "slots": slots,
        "cases_sha256": stable(data),
        "labels_sha256": stable(proposed),
        "proof_sha256": stable(proof),
        "requests_authorized": 0,
        "fees_authorized": 0,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "candidate_config_sha256": stable(config),
        "offline_capture_sha256": stable(captures),
        "single_changed_wire_path": "reasoning.effort: low -> high",
        "unchanged": [
            "exact student material, identities, goals, plan, references and anchors",
            "v4.5 Prompt/input/output Schema and active policy digest",
            "model/8192/60s/temperature0/streamfalse",
            "generation and production routing",
        ],
        "changed": ["diagnostic review reasoning.effort only: low -> high"],
        "semantic_checks": CRITERIA,
        "elimination_rule": "First completeness, assertion or citation failure eliminates this fixed configuration, persists halt, no retry, sample/Prompt/Schema/config/criterion edits or remaining-slot reuse; protocol, timeout and output-limit failures also stop this configuration. Every result requires exact-receipt three-part human signoff. Four signed results permit only T040 admission review, not formal acceptance or production activation.",
    }
    # The capture itself is part of the exact source closure, not just an unverified report.
    p["sources"][BASE + "/offline-capture.json"] = sha(
        (json.dumps(captures, ensure_ascii=False, indent=2) + "\n").encode()
    )
    p.pop("implementation_changes", None)
    p["stop_rule"] = p["elimination_rule"]
    return {
        "proposal.json": p,
        "cases.json": data,
        "proposed-labels.json": proposed,
        "token-cost-proof.json": proof,
        "candidate-config.json": config,
        "offline-capture.json": captures,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values = build()
    if args.write:
        content = {
            n: json.dumps(v, ensure_ascii=False, indent=2) + "\n"
            for n, v in values.items()
        }
        content["human-review.md"] = review_document(values["cases.json"])
        for name, text in content.items():
            path = ROOT / BASE / name
            if path.exists() and path.read_text() != text:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        for name, text in content.items():
            (ROOT / BASE / name).write_text(text)
    p = values["proposal.json"]
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "requests": 4,
                "cost_micro_cny": p["cost_micro_cny"],
                "authorized": False,
                "provider_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
