"""Conservative goal aliases and locally validated Provider candidates."""

import asyncio

import pytest

from app.agents.goal_node_resolver import resolve_goal_node
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.provider_gateway import ProviderError, ProviderErrorCode, StructuredResult


class StubGateway:
    def __init__(self, value: dict[str, object] | ProviderError) -> None:
        self.value = value
        self.calls = 0

    async def generate_structured(
        self, request: object, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.calls += 1
        if isinstance(self.value, ProviderError):
            raise self.value
        return StructuredResult(value=self.value, model_id="test")


@pytest.mark.parametrize(
    ("goal", "node_id"),
    [
        ("讲解数组", "array"),
        ("解释循环队列", "circular-queue"),
        ("链表插入总搞混，先看 C 代码", "linked-list-insertion"),
        ("讲解 single-linked-list", "single-linked-list"),
    ],
)
def test_explicit_aliases_resolve_without_provider(goal: str, node_id: str) -> None:
    async def exercise() -> None:
        gateway = StubGateway({})
        result = await resolve_goal_node(
            goal, graph=default_knowledge_graph_repository(), gateway=gateway
        )
        assert result.node is not None and result.node.id == node_id
        assert gateway.calls == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("goal", ["讲解链表", "数组和队列有什么区别"])
def test_ambiguous_goal_requires_clarification_without_default(goal: str) -> None:
    async def exercise() -> None:
        gateway = StubGateway({})
        result = await resolve_goal_node(
            goal, graph=default_knowledge_graph_repository(), gateway=gateway
        )
        assert result.node is None and len(result.candidates) >= 2
        assert gateway.calls == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("goal", ["不要讲数组", "数组和链表的区别"])
def test_negated_or_mixed_scope_does_not_silently_select_alias(goal: str) -> None:
    async def exercise() -> None:
        gateway = StubGateway({})
        result = await resolve_goal_node(
            goal, graph=default_knowledge_graph_repository(), gateway=gateway
        )
        assert result.node is None
        assert gateway.calls == 0

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "value",
    [
        {"node_id": "invented-node", "confidence": 0.99, "needs_clarification": False},
        {"node_id": "stack", "confidence": 0.5, "needs_clarification": False},
        {"node_id": "stack", "confidence": True, "needs_clarification": False},
        ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
    ],
)
def test_invalid_low_confidence_and_failed_candidates_require_clarification(
    value: dict[str, object] | ProviderError,
) -> None:
    async def exercise() -> None:
        result = await resolve_goal_node(
            "想理解后进先出", graph=default_knowledge_graph_repository(), gateway=StubGateway(value)
        )
        assert result.node is None

    asyncio.run(exercise())


def test_unambiguous_provider_candidate_is_checked_against_repository() -> None:
    async def exercise() -> None:
        result = await resolve_goal_node(
            "想理解后进先出",
            graph=default_knowledge_graph_repository(),
            gateway=StubGateway(
                {"node_id": "stack", "confidence": 0.95, "needs_clarification": False}
            ),
        )
        assert result.node is not None and result.node.id == "stack"

    asyncio.run(exercise())
