import { AnimationApiError } from "./animationJobs";
import { parseSseStream } from "./learningSessions";

export type PreparationStage = "reserved" | "generating" | "reviewing" | "compiled" | "handed_off" | "failed" | "cancelled";
export type AnimationSource = "reviewed_cache" | "parameterized_template" | "generated_dsl" | "reviewed_dsl_cache" | "template_fallback" | "unavailable";
export interface AnimationPreparation {
  id: string; stage: PreparationStage; deadline: string; job_id?: string;
  source?: AnimationSource; error_code?: string;
}
export interface GenerationRequest {
  scene_id: string; scene_version: number;
  goal_kind: "compare" | "swap" | "traverse" | "insert" | "delete" | "trace_insert" | "trace_delete";
  parameters: { values: number[]; index?: number; value?: number };
}
const stages = ["reserved", "generating", "reviewing", "compiled", "handed_off", "failed", "cancelled"];
const sources = ["reviewed_cache", "parameterized_template", "generated_dsl", "reviewed_dsl_cache", "template_fallback", "unavailable"];
function preparation(value: unknown): AnimationPreparation {
  if (!value || typeof value !== "object") throw new AnimationApiError("INVALID_RESPONSE", "动画状态无效。");
  const p = value as Record<string, unknown>;
  if (typeof p.id !== "string" || !stages.includes(String(p.stage)) || typeof p.deadline !== "string"
    || !Number.isFinite(Date.parse(p.deadline)) || (p.job_id !== undefined && typeof p.job_id !== "string")
    || (p.stage === "handed_off" && typeof p.job_id !== "string")
    || (p.source !== undefined && !sources.includes(String(p.source)))
    || (p.error_code !== undefined && typeof p.error_code !== "string")) {
    throw new AnimationApiError("INVALID_RESPONSE", "动画状态无效。");
  }
  // Keep only public state, never persist unexpected response fields.
  return { id: p.id, stage: p.stage as PreparationStage, deadline: p.deadline, job_id: p.job_id as string | undefined,
    source: p.source as AnimationSource | undefined, error_code: p.error_code as string | undefined };
}
async function checked(response: Response): Promise<void> {
  if (response.ok) return;
  let code = "REQUEST_FAILED";
  try {
    const payload = await response.json();
    if (typeof payload?.code === "string" && /^[A-Z_]{1,80}$/.test(payload.code)) code = payload.code;
  } catch { /* Fixed public error below. */ }
  throw new AnimationApiError(code, "动画服务暂不可用，请读取状态或重试。");
}
export async function loadPreparation(id: string): Promise<AnimationPreparation> {
  const response = await fetch(`/api/animation-preparations/${encodeURIComponent(id)}`, { credentials: "same-origin" });
  await checked(response);
  return preparation(await response.json());
}
export async function cancelPreparation(id: string, csrf: string, key: string): Promise<AnimationPreparation> {
  const response = await fetch(`/api/animation-preparations/${encodeURIComponent(id)}/cancel`, {
    method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf, "Idempotency-Key": key },
  });
  await checked(response);
  return preparation(await response.json());
}
export async function generateAnimation(unitId: string, request: GenerationRequest, csrf: string, key: string,
  operationId: string, allowFallback: boolean, signal: AbortSignal,
  onState: (state: AnimationPreparation) => void): Promise<void> {
  const response = await fetch(`/api/learning-units/${encodeURIComponent(unitId)}/animations/generate`, {
    method: "POST", credentials: "same-origin", signal,
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", "X-CSRF-Token": csrf,
      "Idempotency-Key": key, "X-Animation-Operation-ID": operationId,
      "X-Animation-Allow-Template-Fallback": String(allowFallback) }, body: JSON.stringify(request),
  });
  await checked(response);
  if (!response.body || !response.headers.get("Content-Type")?.includes("text/event-stream")) {
    throw new AnimationApiError("INVALID_RESPONSE", "动画流响应无效。");
  }
  let current: AnimationPreparation | undefined;
  let done = false;
  for await (const event of parseSseStream(response.body)) {
    if (signal.aborted) return;
    if (event.type === "agent_start" || event.type === "done") {
      current = preparation(event.data);
      if (current.id !== operationId) throw new AnimationApiError("INVALID_RESPONSE", "动画操作不匹配。");
      done = event.type === "done";
      if (done && !["handed_off", "failed", "cancelled"].includes(current.stage)) {
        throw new AnimationApiError("INVALID_RESPONSE", "动画终态无效。");
      }
      onState(current);
      if (done) return;
    } else if (event.type === "stage_changed") {
      if (!current || event.data.id !== operationId || !["generating", "reviewing", "compiled"].includes(String(event.data.stage))) {
        throw new AnimationApiError("INVALID_RESPONSE", "动画阶段无效。");
      }
      current = { ...current, stage: event.data.stage as PreparationStage };
      onState(current);
    } else if (event.type === "error") throw new AnimationApiError("REQUEST_FAILED", "动画准备失败。");
  }
  if (!done && !signal.aborted) throw new AnimationApiError("CONNECTION_INTERRUPTED", "动画连接中断，请读取状态。");
}
