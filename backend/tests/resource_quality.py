"""Versioned quality benchmark; offline mode never creates a network Provider."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from time import perf_counter

from app.agents.learning_resource_prompt import (
    RESOURCE_INSTRUCTION_VERSION,
    learning_resource_prompt,
)
from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
    ResourceSchemaError,
    resource_output_schema,
    validate_learning_resource,
)
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import ReviewAgent
from app.agents.review_context import build_review_context
from app.agents.review_schema import REVIEW_PROMPT_VERSION, severe_code_issues
from app.core.config import get_provider_settings
from app.core.provider_factory import build_default_provider_gateway
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderGateway,
    StructuredRequest,
    TaskProfile,
    TextRequest,
)

DATASET = Path(__file__).resolve().parents[2] / "data/quality/resource_review_v1.json"


def load_dataset() -> dict:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    assert dataset["benchmark_version"] == "resource-quality-v1"
    assert dataset["schema_generation_repetitions"] == 2
    cases = dataset["semantic_errors"] + dataset["local_code_errors"] + dataset["controls"]
    assert len(cases) == 30 and len({item["id"] for item in cases}) == 30
    graph = default_knowledge_graph_repository()
    assert all(graph.get_node(item["node_id"]) is not None for item in cases)
    return dataset


def candidate(case: dict) -> PendingLearningResource:
    if "source" in case:
        kind = LearningResourceType.CODE
        content = {
            "language": "Python",
            "source": case["source"],
            "expected_output": "display only",
            "key_steps": ["教学代码，禁止执行"],
            "display_only": True,
        }
    else:
        kind = LearningResourceType.EXPLANATION
        content = {"markdown": case["text"]}
    validate_learning_resource(
        {
            "resource_type": kind.value,
            "prompt_version": RESOURCE_PROMPT_VERSION,
            "content": content,
        },
        expected_type=kind,
    )
    return PendingLearningResource(kind, content, RESOURCE_PROMPT_VERSION, "authored-fixture", None)


def base_report(dataset: dict, mode: str) -> dict:
    return {
        "benchmark_version": dataset["benchmark_version"],
        "mode": mode,
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "graph_version": default_knowledge_graph_repository().graph_version,
        "resource_prompt_version": RESOURCE_PROMPT_VERSION,
        "resource_instruction_version": RESOURCE_INSTRUCTION_VERSION,
        "review_prompt_version": REVIEW_PROMPT_VERSION,
        "thresholds": {"schema_rate": 0.98, "severe_error_recall": 0.90},
        "stage_gate_passed": False,
    }


def offline_report() -> dict:
    dataset = load_dataset()
    cases = dataset["semantic_errors"] + dataset["local_code_errors"] + dataset["controls"]
    resources = [candidate(case) for case in cases]
    detected = sum(bool(severe_code_issues(item.resource_type, item.content)) for item in resources)
    report = base_report(dataset, "offline")
    report.update(
        {
            "authored_fixture_schema_valid": len(resources),
            "authored_fixture_count": len(cases),
            "local_code_errors_detected": detected,
            "local_code_error_count": 4,
            "semantic_errors_not_evaluated": 16,
            "provider_calls": 0,
            "schema_generation_rate": None,
            "severe_error_recall": None,
            "note": "Fixture/schema and deterministic safety checks only; no model quality claim.",
        }
    )
    if detected != 4:
        raise ValueError("OFFLINE_SAFETY_GATE_FAILED")
    return report


class BoundedGateway:
    """Disable retries and stop at the predeclared billable request count."""

    def __init__(self, gateway: ProviderGateway, limit: int = 86) -> None:
        self.gateway = gateway
        self.limit = limit
        self.calls = 0

    async def generate_structured(self, request: StructuredRequest, *, retry_safe: bool = False):
        if self.calls >= self.limit:
            raise RuntimeError("BENCHMARK_CALL_LIMIT")
        self.calls += 1
        return await self.gateway.generate_structured(request, retry_safe=False)


def detection(verdict: dict, *, expected_area: str, model_id: str | None, local: bool) -> bool:
    return bool(
        (model_id is not None or local)
        and verdict["verdict"] != "pass"
        and any(
            issue["area"] == expected_area and issue["severity"] in {"major", "severe"}
            for issue in verdict["issues"]
        )
    )


async def provider_report(
    gateway: BoundedGateway, model: str, *, diagnostic: bool = False, circular: bool = False
) -> dict:
    dataset = load_dataset()
    graph = default_knowledge_graph_repository()
    started = perf_counter()
    report = base_report(dataset, "circular-diagnostic" if circular else
                         "diagnostic" if diagnostic else "provider")
    schema_samples = []
    # Each call is one fresh output; failed calls remain in the denominator.
    for repetition in range(dataset["schema_generation_repetitions"]):
        for node in graph.all_nodes():
            for kind in LearningResourceType:
                if circular and (node.id != "circular-queue" or (kind.value, repetition) not in {
                    ("code", 0), ("exercise", 0), ("code", 1),
                }):
                    continue
                if diagnostic and (
                    repetition != 0 or (node.id, kind.value) not in {
                        ("array", "explanation"),
                        ("c-pointer", "explanation"),
                        ("circular-queue", "explanation"),
                        ("linked-list-deletion", "explanation"),
                        ("linked-list-insertion", "code"),
                    }
                ):
                    continue
                sample = {"id": f"{node.id}:{kind.value}:{repetition + 1}", "valid": False}
                request = StructuredRequest(
                    TextRequest(
                        messages=(
                            ChatMessage("system", learning_resource_prompt(kind)),
                            ChatMessage(
                                "user",
                                f"Knowledge point: {node.name}: {node.description}; "
                                f"{node.ai_context}\nLearner goal: 学习{node.name}\n"
                                "Requested code language: C.",
                            ),
                        ),
                        task_profile=TaskProfile.QUALITY,
                        max_output_tokens=2048,
                    ),
                    resource_output_schema(kind),
                )
                try:
                    result = await gateway.generate_structured(request)
                    validate_learning_resource(result.value, expected_type=kind)
                    sample.update({"valid": True, "model_id": result.model_id})
                except (ProviderError, ResourceSchemaError) as cause:
                    sample["error"] = (
                        cause.code.value if isinstance(cause, ProviderError) else "SCHEMA_INVALID"
                    )
                    if isinstance(cause, ProviderError) and cause.output_failure_reason is not None:
                        sample["output_failure_reason"] = cause.output_failure_reason.value
                    if isinstance(cause, ProviderError) and cause.schema_keyword is not None:
                        sample["schema_keyword"] = cause.schema_keyword
                    if isinstance(cause, ProviderError) and cause.json_syntax_reason is not None:
                        sample["json_syntax_reason"] = cause.json_syntax_reason.value
                schema_samples.append(sample)
    if diagnostic or circular:
        report.update({
            "configured_model": model,
            "provider_calls": gateway.calls,
            "call_limit": gateway.limit,
            "schema_samples": schema_samples,
            "schema_sample_count": len(schema_samples),
            "schema_generation_rate": None,
            "severe_error_recall": None,
            "retries": 0,
            "corrections": 0,
            "elapsed_seconds": round(perf_counter() - started, 2),
            "note": "Fixed diagnostic probes only; not a quality gate or baseline rerun.",
        })
        return report
    review_samples = []
    for group in ("semantic_errors", "local_code_errors", "controls"):
        for case in dataset[group]:
            resource = candidate(case)
            reference = build_review_context(
                graph,
                node_id=case["node_id"],
                profile_version=1,
                profile={},
                code_language="Python" if "source" in case else "C",
            )
            # Measure the original verdict before corrections, not a repaired candidate.
            verdict, model_id = await ReviewAgent(gateway)._review(resource, reference)
            local = bool(severe_code_issues(resource.resource_type, resource.content))
            sample = {
                "id": case["id"],
                "group": group,
                "model_id": model_id,
                "local_gate": local,
                "verdict": verdict["verdict"],
                "issues": verdict["issues"],
            }
            if group != "controls":
                sample["detected"] = detection(
                    verdict,
                    expected_area=case.get("area", "code_safety"),
                    model_id=model_id,
                    local=local,
                )
            else:
                sample["correctly_passed"] = model_id is not None and verdict["verdict"] == "pass"
            review_samples.append(sample)
    severe = [item for item in review_samples if item["group"] != "controls"]
    semantic = [item for item in severe if not item["local_gate"]]
    controls = [item for item in review_samples if item["group"] == "controls"]
    schema_rate = sum(item["valid"] for item in schema_samples) / len(schema_samples)
    recall = sum(item["detected"] for item in severe) / len(severe)
    semantic_recall = sum(item["detected"] for item in semantic) / len(semantic)
    report.update(
        {
            "configured_model": model,
            "provider_calls": gateway.calls,
            "call_limit": gateway.limit,
            "retries": 0,
            "corrections": 0,
            "schema_sample_count": len(schema_samples),
            "schema_generation_rate": schema_rate,
            "severe_error_count": len(severe),
            "severe_error_recall": recall,
            "model_only_severe_error_count": len(semantic),
            "model_only_severe_error_recall": semantic_recall,
            "control_count": len(controls),
            "control_pass_rate": sum(item["correctly_passed"] for item in controls) / len(controls),
            "schema_samples": schema_samples,
            "review_samples": review_samples,
            "elapsed_seconds": round(perf_counter() - started, 2),
            "stage_gate_passed": schema_rate >= 0.98 and recall >= 0.9 and semantic_recall >= 0.9,
            "requires_issue_audit": True,
        }
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=(
        "offline", "provider", "diagnostic", "circular-diagnostic"
    ), default="offline")
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, help="Save the sanitized benchmark report as JSON")
    args = parser.parse_args()
    if args.mode == "offline":
        report = offline_report()
    else:
        if not args.confirm_billable:
            raise SystemExit("Refusing real Provider calls without --confirm-billable")
        settings = get_provider_settings()
        report = asyncio.run(
            provider_report(
                BoundedGateway(
                    build_default_provider_gateway(), limit=(
                        3 if args.mode == "circular-diagnostic" else
                        5 if args.mode == "diagnostic" else 86
                    )
                ),
                settings.model,
                diagnostic=args.mode == "diagnostic",
                circular=args.mode == "circular-diagnostic",
            )
        )
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output is not None:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if args.mode == "provider" and not report["stage_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
