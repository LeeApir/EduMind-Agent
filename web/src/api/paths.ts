import type { MasteryChange, MasteryStatus } from "./quiz";

export interface PathNode {
  node_id: string;
  score: number;
  status: MasteryStatus;
  cost: number;
  recommended_resource: "explanation" | "code" | "exercise" | "review";
  estimated_minutes: number;
}
export interface PathReason {
  kind: "prerequisite" | "mastery_evidence" | "profile_field" | "goal";
  summary: string;
  knowledge_node_id?: string;
}
export interface LearningPath {
  version: number;
  target_node_id: string;
  graph_version: string;
  profile_version: number;
  mastery_revision_watermark: number;
  planner_rule_version: string;
  nodes: string[];
  node_details: PathNode[];
  current_node_id: string | null;
  prerequisite_node_ids: string[];
  next_node_id: string | null;
  reasons: PathReason[];
  changes: { kind: "initial_plan" | "path_change"; trigger: string; added_node_ids: string[]; removed_node_ids: string[]; reordered_node_ids: string[] };
  is_stale: boolean;
}
export interface GraphNode { id: string; name: string; prerequisites: string[]; }
export interface GraphSnapshot { graph_version: string; nodes: GraphNode[]; }
export interface MasterySnapshot { graph_version: string; items: MasteryChange[]; }
type FetchLike = typeof fetch;

export class PathRequestError extends Error {
  constructor(message: string, readonly code = "CONNECTION_FAILED") {
    super(message); this.name = "PathRequestError";
  }
}
function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
function score(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}
function positiveInteger(value: unknown): boolean { return Number.isInteger(value) && Number(value) >= 1; }
function status(value: unknown): boolean { return ["unseen", "learning", "weak", "mastered"].includes(String(value)); }
function invalid(): never { throw new PathRequestError("推荐数据响应无效，请重新读取。", "INVALID_RESPONSE"); }

export function parseLearningPath(value: unknown): LearningPath {
  if (!object(value) || !positiveInteger(value.version) || typeof value.target_node_id !== "string"
    || typeof value.graph_version !== "string" || !positiveInteger(value.profile_version)
    || !Number.isInteger(value.mastery_revision_watermark) || Number(value.mastery_revision_watermark) < 0
    || typeof value.planner_rule_version !== "string" || !strings(value.nodes) || !strings(value.prerequisite_node_ids)
    || !(value.current_node_id === null || typeof value.current_node_id === "string")
    || !(value.next_node_id === null || typeof value.next_node_id === "string") || typeof value.is_stale !== "boolean"
    || !Array.isArray(value.node_details) || !value.node_details.every((item: unknown) => object(item)
      && typeof item.node_id === "string" && score(item.score) && status(item.status)
      && typeof item.cost === "number" && Number.isFinite(item.cost)
      && ["explanation", "code", "exercise", "review"].includes(String(item.recommended_resource))
      && positiveInteger(item.estimated_minutes))
    || !Array.isArray(value.reasons) || !value.reasons.length || !value.reasons.every((item: unknown) => object(item)
      && ["prerequisite", "mastery_evidence", "profile_field", "goal"].includes(String(item.kind))
      && typeof item.summary === "string" && (item.knowledge_node_id === undefined || typeof item.knowledge_node_id === "string"))
    || !object(value.changes) || !["initial_plan", "path_change"].includes(String(value.changes.kind))
    || !["initial_plan", "learner_request", "mastery_changed", "profile_changed"].includes(String(value.changes.trigger))
    || !strings(value.changes.added_node_ids) || !strings(value.changes.removed_node_ids) || !strings(value.changes.reordered_node_ids)) invalid();
  const nodes = value.nodes;
  if (new Set(nodes).size !== nodes.length || value.node_details.length !== nodes.length
    || value.node_details.some((item, index) => item.node_id !== nodes[index])
    || (value.current_node_id !== null && !value.nodes.includes(value.current_node_id))
    || (value.next_node_id !== null && !value.nodes.includes(value.next_node_id))) invalid();
  return value as unknown as LearningPath;
}
export function parseGraph(value: unknown): GraphSnapshot {
  if (!object(value) || typeof value.graph_version !== "string" || !Array.isArray(value.nodes)
    || !value.nodes.every((item: unknown) => object(item) && typeof item.id === "string"
      && typeof item.name === "string" && strings(item.prerequisites))) invalid();
  if (new Set(value.nodes.map((node) => node.id)).size !== value.nodes.length) invalid();
  return value as unknown as GraphSnapshot;
}
export function parseMastery(value: unknown): MasterySnapshot {
  if (!object(value) || typeof value.graph_version !== "string" || !Array.isArray(value.items)
    || !value.items.every((item: unknown) => object(item) && typeof item.knowledge_node_id === "string"
      && score(item.score) && score(item.previous_score) && status(item.status) && positiveInteger(item.revision)
      && typeof item.rule_version === "string" && strings(item.evidence_summary))) invalid();
  if (new Set(value.items.map((item) => item.knowledge_node_id)).size !== value.items.length) invalid();
  return value as unknown as MasterySnapshot;
}
async function request(url: string, init: RequestInit, fetchImpl: FetchLike): Promise<Response> {
  let response: Response;
  try { response = await fetchImpl(url, { credentials: "same-origin", ...init }); }
  catch { throw new PathRequestError("推荐暂时无法连接，请重试读取。重规划重试不会重复创建路径。"); }
  if (!response.ok && response.status !== 404) {
    let payload: unknown;
    try { payload = await response.json(); } catch { payload = null; }
    throw new PathRequestError("推荐请求失败，请重试读取。", object(payload) && typeof payload.code === "string" ? payload.code : "REQUEST_FAILED");
  }
  return response;
}
async function payload(response: Response): Promise<unknown> {
  try { return await response.json(); } catch { return invalid(); }
}
const readHeaders = { Accept: "application/json" };
export async function loadCurrentPath(targetNodeId: string, fetchImpl: FetchLike = fetch): Promise<LearningPath | null> {
  const response = await request(`/api/path/current?${new URLSearchParams({ target_node_id: targetNodeId })}`, { headers: readHeaders }, fetchImpl);
  if (response.status === 404) return null;
  const path = parseLearningPath(await payload(response));
  if (path.target_node_id !== targetNodeId) invalid();
  return path;
}
export async function loadGraph(fetchImpl: FetchLike = fetch): Promise<GraphSnapshot> {
  const response = await request("/api/graph", { headers: readHeaders }, fetchImpl);
  if (!response.ok) throw new PathRequestError("知识结构暂时无法读取。", "NOT_FOUND");
  return parseGraph(await payload(response));
}
export async function loadMastery(fetchImpl: FetchLike = fetch): Promise<MasterySnapshot> {
  const response = await request("/api/mastery", { headers: readHeaders }, fetchImpl);
  if (!response.ok) throw new PathRequestError("掌握度暂时无法读取。", "NOT_FOUND");
  return parseMastery(await payload(response));
}
export interface ReplanOptions { targetNodeId: string; expectedVersion: number; csrfToken: string; idempotencyKey: string; reason: "mastery_changed" | "learner_request" | "profile_changed"; }
export async function replanPath(options: ReplanOptions, fetchImpl: FetchLike = fetch): Promise<LearningPath> {
  const response = await request("/api/path/replan", {
    method: "POST", headers: { ...readHeaders, "Content-Type": "application/json", "X-CSRF-Token": options.csrfToken,
      "Idempotency-Key": options.idempotencyKey, "If-Match-Path-Version": String(options.expectedVersion) },
    body: JSON.stringify({ target_node_id: options.targetNodeId, reason: options.reason }),
  }, fetchImpl);
  if (!response.ok) throw new PathRequestError("推荐已不存在，请重新读取。", "NOT_FOUND");
  const path = parseLearningPath(await payload(response));
  if (path.target_node_id !== options.targetNodeId) invalid();
  return path;
}
