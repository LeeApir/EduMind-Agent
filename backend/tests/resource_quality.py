"""Versioned quality benchmark; offline mode never creates a network Provider."""

import argparse
import asyncio
import hashlib
import json
import sys
from os import getenv
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
from app.agents.objective_exercises import objective_exercise_issues, objective_format_diagnostics
from app.agents.review_agent import REVIEW_INSTRUCTION_VERSION, ReviewAgent
from app.agents.review_context import build_review_context
from app.agents.review_schema import REVIEW_PROMPT_VERSION, severe_code_issues
from app.core.config import get_provider_settings
from app.core.provider_factory import build_default_provider_gateway
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.provider_gateway import (
    P0_DEFAULT_MAX_OUTPUT_TOKENS,
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
        "structured_transport": getenv(
            "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema"
        )
        if mode != "offline"
        else "mock",
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "graph_version": default_knowledge_graph_repository().graph_version,
        "resource_prompt_version": RESOURCE_PROMPT_VERSION,
        "resource_instruction_version": RESOURCE_INSTRUCTION_VERSION,
        "review_prompt_version": REVIEW_PROMPT_VERSION,
        "review_instruction_version": REVIEW_INSTRUCTION_VERSION,
        "generation_max_output_tokens": P0_DEFAULT_MAX_OUTPUT_TOKENS,
        "review_max_output_tokens": P0_DEFAULT_MAX_OUTPUT_TOKENS,
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

    def __init__(
        self, gateway: ProviderGateway, limit: int = 86, *, progress: bool = False
    ) -> None:
        self.gateway = gateway
        self.limit = limit
        self.calls = 0
        self.attempts = []
        self.progress = progress

    async def generate_structured(self, request: StructuredRequest, *, retry_safe: bool = False):
        if self.calls >= self.limit:
            raise RuntimeError("BENCHMARK_CALL_LIMIT")
        self.calls += 1
        if self.progress:
            print(f"Provider attempt {self.calls}/{self.limit}", file=sys.stderr, flush=True)
        attempt = {
            "number": self.calls,
            "max_output_tokens": request.prompt.max_output_tokens
            if request.prompt.max_output_tokens is not None
            else P0_DEFAULT_MAX_OUTPUT_TOKENS,
        }
        self.attempts.append(attempt)
        try:
            result = await self.gateway.generate_structured(request, retry_safe=False)
        except ProviderError as error:
            if self.progress:
                print(f"Attempt {self.calls}: {error.code.value}", file=sys.stderr, flush=True)
            attempt["error_code"] = error.code.value
            if error.output_text_counts is not None:
                attempt["output_text_counts"] = {
                    "messages": error.output_text_counts.messages,
                    "blocks": error.output_text_counts.blocks,
                }
            for name in ("output_failure_reason", "json_syntax_reason", "json_extra_data_kind"):
                value = getattr(error, name)
                if value is not None:
                    attempt[name] = value.value
            if error.schema_keyword is not None:
                attempt["schema_keyword"] = error.schema_keyword
            if error.usage is not None:
                attempt["usage"] = {
                    "input_tokens": error.usage.input_tokens,
                    "output_tokens": error.usage.output_tokens,
                }
            raise
        attempt["model_id"] = result.model_id
        if result.output_text_counts is not None:
            attempt["output_text_counts"] = {
                "messages": result.output_text_counts.messages,
                "blocks": result.output_text_counts.blocks,
            }
        if result.usage is not None:
            attempt["usage"] = {
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
            }
        return result


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
    gateway: BoundedGateway, model: str, *, diagnostic: bool = False, circular: bool = False,
    repair: bool = False, array: bool = False, review_diagnostic: bool = False,
    objective_diagnostic: bool = False, safety_diagnostic: bool = False,
) -> dict:
    dataset = load_dataset()
    graph = default_knowledge_graph_repository()
    started = perf_counter()
    report = base_report(
        dataset, "circular-diagnostic" if circular else "diagnostic" if diagnostic else "provider"
    )
    if repair:
        report["mode"] = "repair-diagnostic"
        report["structured_transport"] = getenv(
            "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema"
        )
    if array:
        report["mode"] = "array-diagnostic"
        report["structured_transport"] = getenv(
            "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema"
        )
    if objective_diagnostic:
        report["mode"] = "objective-diagnostic"
    schema_samples = []
    # Each call is one fresh output; failed calls remain in the denominator.
    for repetition in range(3 if array else dataset["schema_generation_repetitions"]):
        for node in graph.all_nodes():
            for kind in LearningResourceType:
                if objective_diagnostic and (
                    kind is not LearningResourceType.EXERCISE
                    or (node.id, repetition) not in {
                        ("linked-list-deletion", 0), ("linked-list-deletion", 1),
                        ("circular-queue", 0),
                    }
                ):
                    continue
                if review_diagnostic or safety_diagnostic:
                    continue
                if array and (node.id != "array" or kind is not LearningResourceType.EXPLANATION):
                    continue
                if repair and (
                    repetition != 0 or (node.id, kind.value) not in {
                        ("stack", "code"), ("array", "explanation"),
                        ("linked-list-deletion", "exercise"),
                        ("linked-list-insertion", "exercise"),
                        ("single-linked-list", "exercise"),
                        ("circular-queue", "code"),
                    }
                ):
                    continue
                if circular and (
                    node.id != "circular-queue"
                    or (kind.value, repetition)
                    not in {
                        ("code", 0),
                        ("exercise", 0),
                        ("code", 1),
                    }
                ):
                    continue
                if diagnostic and (
                    repetition != 0
                    or (node.id, kind.value)
                    not in {
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
                        max_output_tokens=P0_DEFAULT_MAX_OUTPUT_TOKENS,
                    ),
                    resource_output_schema(kind),
                )
                try:
                    result = await gateway.generate_structured(request)
                    envelope = validate_learning_resource(result.value, expected_type=kind)
                    sample.update({"valid": True, "model_id": result.model_id})
                    if kind is LearningResourceType.EXERCISE:
                        sample["objective_format_valid"] = not objective_exercise_issues(
                            envelope["content"]
                        )
                        if not sample["objective_format_valid"]:
                            sample["objective_format_diagnostics"] = objective_format_diagnostics(
                                envelope["content"]
                            )
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
    if diagnostic or circular or repair or array or objective_diagnostic:
        report.update(
            {
                "configured_model": model,
                "provider_calls": gateway.calls,
                "call_limit": gateway.limit,
                "schema_samples": schema_samples,
                "provider_attempts": gateway.attempts,
                "schema_sample_count": len(schema_samples),
                "schema_generation_rate": None,
                "severe_error_recall": None,
                "retries": 0,
                "corrections": 0,
                "elapsed_seconds": round(perf_counter() - started, 2),
                "note": "Fixed diagnostic probes only; not a quality gate or baseline rerun.",
            }
        )
        return report
    review_samples = []
    for group in ("semantic_errors", "local_code_errors", "controls"):
        for case in dataset[group]:
            if safety_diagnostic and case["id"] not in {
                "list-traversal-stop", "list-delete-head", "correct-array"
            }:
                continue
            if review_diagnostic and case["id"] not in {
                "array-index-complexity", "pointer-value", "correct-array"
            }:
                continue
            resource = candidate(case)
            reference = build_review_context(
                graph,
                node_id=case["node_id"],
                profile_version=1,
                profile={},
                code_language="Python" if "source" in case else "C",
            )
            # Measure the original verdict before corrections, not a repaired candidate.
            before = len(gateway.attempts)
            verdict, model_id = await ReviewAgent(gateway)._review(resource, reference)
            local = bool(severe_code_issues(resource.resource_type, resource.content))
            sample = {
                "id": case["id"],
                "group": group,
                "model_id": model_id,
                "local_gate": local,
                "verdict": verdict["verdict"],
                "issues": verdict["issues"],
                "provider_attempts": gateway.attempts[before:],
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
    if review_diagnostic or safety_diagnostic:
        report.update(
            mode="safety-diagnostic" if safety_diagnostic else "review-diagnostic",
            configured_model=model,
            structured_transport=getenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
                                        "responses_json_schema"),
            provider_calls=gateway.calls, call_limit=gateway.limit,
            retries=0, corrections=0, review_samples=review_samples,
            provider_attempts=gateway.attempts,
            elapsed_seconds=round(perf_counter() - started, 2),
            note="Three independent review probes only; not a full quality gate.",
        )
        return report
    severe = [item for item in review_samples if item["group"] != "controls"]
    semantic = [item for item in severe if not item["local_gate"]]
    controls = [item for item in review_samples if item["group"] == "controls"]
    schema_rate = sum(item["valid"] for item in schema_samples) / len(schema_samples)
    recall = sum(item["detected"] for item in severe) / len(severe)
    semantic_recall = sum(item["detected"] for item in semantic) / len(semantic)
    objective = [item for item in schema_samples if ":exercise:" in item["id"]]
    objective_rate = sum(item.get("objective_format_valid", False) for item in objective) / len(
        objective
    )
    report.update(
        {
            "configured_model": model,
            "provider_calls": gateway.calls,
            "call_limit": gateway.limit,
            "retries": 0,
            "corrections": 0,
            "schema_sample_count": len(schema_samples),
            "schema_generation_rate": schema_rate,
            "objective_exercise_count": len(objective),
            "objective_exercise_format_rate": objective_rate,
            "severe_error_count": len(severe),
            "severe_error_recall": recall,
            "model_only_severe_error_count": len(semantic),
            "model_only_severe_error_recall": semantic_recall,
            "control_count": len(controls),
            "control_pass_rate": sum(item["correctly_passed"] for item in controls) / len(controls),
            "schema_samples": schema_samples,
            "review_samples": review_samples,
            "provider_attempts": gateway.attempts,
            "elapsed_seconds": round(perf_counter() - started, 2),
            "stage_gate_passed": (
                schema_rate >= 0.98
                and recall >= 0.9
                and semantic_recall >= 0.9
                and objective_rate == 1
            ),
            "requires_issue_audit": True,
        }
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("offline", "provider", "diagnostic", "circular-diagnostic", "repair-diagnostic",
                 "array-diagnostic", "review-diagnostic", "objective-diagnostic",
                 "safety-diagnostic"),
        default="offline",
    )
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, help="Save the sanitized benchmark report as JSON")
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        raise SystemExit("Refusing to overwrite an existing report")
    if args.mode == "offline":
        report = offline_report()
    else:
        if not args.confirm_billable:
            raise SystemExit("Refusing real Provider calls without --confirm-billable")
        settings = get_provider_settings()
        report = asyncio.run(
            provider_report(
                BoundedGateway(
                    build_default_provider_gateway(),
                    progress=True,
                    limit=(
                        6
                        if args.mode == "repair-diagnostic"
                        else 3
                        if args.mode in {"circular-diagnostic", "array-diagnostic",
                                         "review-diagnostic", "objective-diagnostic",
                                         "safety-diagnostic"}
                        else 5
                        if args.mode == "diagnostic"
                        else 86
                    ),
                ),
                settings.model,
                diagnostic=args.mode == "diagnostic",
                circular=args.mode == "circular-diagnostic",
                repair=args.mode == "repair-diagnostic",
                array=args.mode == "array-diagnostic",
                review_diagnostic=args.mode == "review-diagnostic",
                objective_diagnostic=args.mode == "objective-diagnostic",
                safety_diagnostic=args.mode == "safety-diagnostic",
            )
        )
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(serialized + "\n")
    print(serialized)
    if args.mode == "provider" and not report["stage_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
