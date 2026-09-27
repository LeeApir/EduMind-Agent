"""Three bounded public-course format probes; no original report replacement."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.agents.learning_resource_prompt import learning_resource_prompt
from app.agents.learning_resource_schema import resource_output_schema
from app.agents.objective_exercises import objective_exercise_issues
from app.core.provider_factory import build_default_provider_gateway
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.provider_gateway import ChatMessage, StructuredRequest, TaskProfile, TextRequest


async def run():
    gateway = build_default_provider_gateway()
    graph = default_knowledge_graph_repository()
    samples = []
    for node_id in ("single-linked-list", "linked-list-traversal", "c-pointer"):
        node = graph.get_node(node_id)
        request = StructuredRequest(
            TextRequest(
                messages=(
                    ChatMessage("system", learning_resource_prompt("exercise")),
                    ChatMessage(
                        "user",
                        f"Knowledge point: {node.name}: {node.description}; "
                        f"{node.ai_context}\nLearner goal: 学习{node.name}",
                    ),
                ),
                task_profile=TaskProfile.QUALITY,
                max_output_tokens=2048,
            ),
            resource_output_schema("exercise"),
        )
        result = await gateway.generate_structured(request, retry_safe=False)
        samples.append(
            {
                "node_id": node_id,
                "format_valid": not objective_exercise_issues(result.value["content"]),
                "public_questions": [
                    {"question": item["question"], "answer_length": len(item["answer"])}
                    for item in result.value["content"]["items"]
                ],
            }
        )
    print(json.dumps({"provider_calls": 3, "samples": samples}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--confirm-billable" not in sys.argv:
        raise SystemExit("Explicit billable confirmation required")
    asyncio.run(run())
