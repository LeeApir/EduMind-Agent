export type AnimationStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type AnimationTemplateId = "linked-list-insertion" | "linked-list-deletion";

export interface AnimationJob {
  id: string;
  status: AnimationStatus;
  learning_unit_id: string;
  template_id: AnimationTemplateId;
  attempt: number;
  progress: number;
  last_event_id: number;
  media_id?: string;
  retry_of?: string;
  error?: { code: string; message: string; retryable: boolean };
}

export interface AnimationRequest {
  template_id: AnimationTemplateId;
  template_version: "1.0.0";
  scene_version: number;
  parameters: { values: number[]; index: number; value?: number };
}

export class AnimationApiError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "AnimationApiError";
  }
}

function isJob(value: unknown): value is AnimationJob {
  if (!value || typeof value !== "object") return false;
  const job = value as Record<string, unknown>;
  return typeof job.id === "string" && typeof job.learning_unit_id === "string"
    && ["queued", "running", "succeeded", "failed", "cancelled"].includes(String(job.status))
    && ["linked-list-insertion", "linked-list-deletion"].includes(String(job.template_id))
    && Number.isInteger(job.attempt) && typeof job.progress === "number"
    && Number.isInteger(job.last_event_id);
}

async function readJob(response: Response): Promise<AnimationJob> {
  let payload: unknown;
  try { payload = await response.json(); } catch { throw new AnimationApiError("INVALID_RESPONSE", "动画服务响应无效。"); }
  if (!response.ok) {
    const error = payload as Record<string, unknown>;
    throw new AnimationApiError(
      typeof error?.code === "string" ? error.code : "REQUEST_FAILED",
      typeof error?.message === "string" ? error.message : "动画请求失败，请重试。",
    );
  }
  if (!isJob(payload)) throw new AnimationApiError("INVALID_RESPONSE", "动画服务响应无效。");
  return payload;
}

function actionHeaders(csrfToken: string, idempotencyKey: string): HeadersInit {
  return { "X-CSRF-Token": csrfToken, "Idempotency-Key": idempotencyKey, Accept: "application/json" };
}

export async function requestAnimation(
  unitId: string, request: AnimationRequest, csrfToken: string, idempotencyKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AnimationJob> {
  const response = await fetchImpl(`/api/learning-units/${encodeURIComponent(unitId)}/animations`, {
    method: "POST", credentials: "same-origin",
    headers: { ...actionHeaders(csrfToken, idempotencyKey), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return readJob(response);
}

export async function loadAnimationJob(
  jobId: string, fetchImpl: typeof fetch = fetch,
): Promise<AnimationJob> {
  const response = await fetchImpl(`/api/animation-jobs/${encodeURIComponent(jobId)}`, {
    credentials: "same-origin", headers: { Accept: "application/json" },
  });
  return readJob(response);
}

export async function cancelAnimationJob(
  jobId: string, csrfToken: string, idempotencyKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AnimationJob> {
  const response = await fetchImpl(`/api/animation-jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST", credentials: "same-origin", headers: actionHeaders(csrfToken, idempotencyKey),
  });
  return readJob(response);
}

export async function retryAnimationJob(
  jobId: string, csrfToken: string, idempotencyKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AnimationJob> {
  const response = await fetchImpl(`/api/animation-jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST", credentials: "same-origin", headers: actionHeaders(csrfToken, idempotencyKey),
  });
  return readJob(response);
}

export function mediaUrl(mediaId: string, extension: "mp4" | "srt"): string {
  return `/api/animation-media/${encodeURIComponent(mediaId)}/${extension}`;
}
