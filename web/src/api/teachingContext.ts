export type TeachingMode = "target" | "recommended";
export interface TeachingContext {
  version: "teaching-node-binding-v1";
  teaching_mode: TeachingMode;
  target_node_id: string;
  recommended_node_id: string | null;
  teaching_node_id: string;
  selection_reason: string;
  original_request: string;
  segment_goal: string;
  segment_scope: string;
  path_version_id: string | null;
  path_version: number | null;
  graph_version: string;
  graph_digest: string;
}
export type TeachingBindingStatus = "bound" | "legacy_unverified" | null;
