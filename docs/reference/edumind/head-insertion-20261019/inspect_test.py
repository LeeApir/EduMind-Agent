"""Read-only evidence export for the original single submission."""

import asyncio
import json

from serve_test import OUT, configure, save


async def main():
    import asyncpg

    url = configure()
    from app.agents.goal_node_resolver import _alias_candidates, resolve_goal_node
    from app.api.knowledge_graph import knowledge_graph_repository

    goal = (OUT / "submitted-input.txt").read_text()
    graph = knowledge_graph_repository()

    class NoNetwork:
        async def generate_structured(self, *args, **kwargs):
            raise AssertionError("Resolver unexpectedly attempted a model call")

    result = await resolve_goal_node(goal, graph=graph, gateway=NoNetwork())
    save("resolver-reproduction.json", {
        "method": "original resolver + actual graph + gateway forbidding any call",
        "reason": result.reason,
        "selected_node": result.node.id if result.node else None,
        "candidates": [{"id": n.id, "name": n.name} for n in _alias_candidates(goal, graph)],
        "graph_node_count": len(graph.all_nodes()),
    })
    connection = await asyncpg.connect(
        host=url.host, port=url.port, user=url.username, password=url.password,
        database=url.database, timeout=10,
    )
    try:
        operations = await connection.fetch(
            "SELECT id,status,goal,phase,generation_call_count,error,"
            "created_at,updated_at FROM learning_operations ORDER BY created_at"
        )
        tables = ["learning_units", "learning_plan_versions", "learning_scenes",
                  "generated_resources", "learning_review_records", "learning_review_cases",
                  "learning_publications", "student_profiles"]
        counts = {table: await connection.fetchval(f'SELECT count(*) FROM "{table}"')
                  for table in tables}
        save("database-evidence.json", {
            "database": url.database,
            "operations": [json.loads(json.dumps(dict(row), default=str)) for row in operations],
            "counts": counts,
        })
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
