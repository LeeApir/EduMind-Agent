"""Exercise real SSE error propagation with a local session double, no Provider."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import hybrid_learning
from app.services.knowledge_graph import default_knowledge_graph_repository


@pytest.mark.parametrize("goal", ["学习数组和队列", "不要讲数组"])
def test_clarification_persists_details_clears_phase_and_never_calls_provider(monkeypatch, goal):
    operation = SimpleNamespace(status="accepted", phase=None, generation_deadline=None, error=None)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def commit(self):
            pass

    class ForbiddenGateway:
        async def generate_structured(self, *args, **kwargs):
            pytest.fail("zero-call clarification reached Provider")

    async def owned(*args, **kwargs):
        return operation

    monkeypatch.setattr(hybrid_learning, "owned_operation", owned)

    async def exercise():
        frames = [
            frame
            async for frame in hybrid_learning.hybrid_events(
                operation_id=uuid4(),
                owner_id=uuid4(),
                goal=goal,
                language="c",
                gateway=ForbiddenGateway(),
                graph=default_knowledge_graph_repository(),
                sessions=Session,
            )
        ]
        error_frame = next(frame for frame in frames if frame.startswith("event: error"))
        detail = json.loads(error_frame.split("data: ")[1])
        assert detail["code"] == "GOAL_CLARIFICATION_REQUIRED"
        assert detail["reason"] in ("ambiguous_aliases", "negated_target")
        assert detail["message"] and detail["candidate_nodes"]
        assert operation.error["reason"] == detail["reason"]
        assert operation.status == "failed"
        assert operation.phase is None and operation.generation_deadline is None
        assert '"status": "failed"' in frames[-1] or '"status":"failed"' in frames[-1]

    asyncio.run(exercise())
