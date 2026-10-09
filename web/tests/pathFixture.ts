export const pathFixture = {
  version: 1, target_node_id: "linked-list-concept", graph_version: "graph-v1", profile_version: 1,
  mastery_revision_watermark: 1, planner_rule_version: "path-v2", nodes: ["c-pointer", "linked-list-concept"],
  node_details: [
    { node_id: "c-pointer", score: 0.3, status: "weak", cost: 0.2, recommended_resource: "review", estimated_minutes: 12 },
    { node_id: "linked-list-concept", score: 0, status: "unseen", cost: 0, recommended_resource: "explanation", estimated_minutes: 16 },
  ],
  current_node_id: "c-pointer", prerequisite_node_ids: [], next_node_id: "linked-list-concept",
  reasons: [{ kind: "mastery_evidence", summary: "最近指针题需要巩固。", knowledge_node_id: "c-pointer" }],
  changes: { kind: "initial_plan", trigger: "initial_plan", added_node_ids: ["c-pointer", "linked-list-concept"], removed_node_ids: [], reordered_node_ids: [] },
  is_stale: false,
};
