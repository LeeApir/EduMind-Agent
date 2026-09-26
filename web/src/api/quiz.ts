export type MasteryStatus = "unseen" | "learning" | "weak" | "mastered";
export interface MasteryChange {
  knowledge_node_id: string;
  previous_score: number;
  score: number;
  status: MasteryStatus;
  revision: number;
  rule_version: string;
  evidence_summary?: string[];
}
export interface QuizSubmissionResult {
  evidence_id: string;
  resource_id: string;
  resource_version: number;
  question_results: Array<{ question_id: string; correct: boolean; explanation: string; error_patterns: string[] }>;
  score: number;
  correct_count: number;
  question_count: number;
  quiz_schema_version: number;
  scoring_rule_version: string;
  mastery_changes: MasteryChange[];
  path_replan_required: boolean;
  profile_update_status: "updated" | "no_change" | "provider_failed" | "conflict";
}
export interface QuizResourceRef { resourceId: string; resourceVersion: number; }
type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export interface SubmitQuizOptions extends QuizResourceRef {
  answers: Array<{ question_id: string; answer: string }>;
  csrfToken: string;
  idempotencyKey: string;
  fetchImpl?: FetchLike;
}

export class QuizRequestError extends Error {
  constructor(message: string, readonly code = "CONNECTION_FAILED") {
    super(message);
    this.name = "QuizRequestError";
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function unitScore(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}
function isMasteryChange(value: unknown): value is MasteryChange {
  return record(value) && typeof value.knowledge_node_id === "string"
    && unitScore(value.previous_score) && unitScore(value.score)
    && ["unseen", "learning", "weak", "mastered"].includes(String(value.status))
    && Number.isInteger(value.revision) && Number(value.revision) >= 1
    && typeof value.rule_version === "string";
}
export function parseQuizResult(value: unknown): QuizSubmissionResult {
  if (!record(value) || typeof value.evidence_id !== "string" || typeof value.resource_id !== "string"
    || !Number.isInteger(value.resource_version) || Number(value.resource_version) < 1
    || !unitScore(value.score) || !Number.isInteger(value.correct_count)
    || !Number.isInteger(value.question_count) || Number(value.question_count) < 1
    || Number(value.correct_count) < 0 || Number(value.correct_count) > Number(value.question_count)
    || !Number.isInteger(value.quiz_schema_version) || Number(value.quiz_schema_version) < 1 || typeof value.scoring_rule_version !== "string"
    || typeof value.path_replan_required !== "boolean"
    || !["updated", "no_change", "provider_failed", "conflict"].includes(String(value.profile_update_status))
    || !Array.isArray(value.mastery_changes) || !value.mastery_changes.every(isMasteryChange)
    || !Array.isArray(value.question_results) || !value.question_results.every((item: unknown) =>
      record(item) && typeof item.question_id === "string" && typeof item.correct === "boolean"
      && typeof item.explanation === "string" && Array.isArray(item.error_patterns)
      && item.error_patterns.every((pattern: unknown) => typeof pattern === "string"))) {
    throw new QuizRequestError("练习结果响应无效，请重新读取。", "INVALID_RESPONSE");
  }
  if (value.question_results.length !== value.question_count
    || new Set(value.question_results.map((item) => item.question_id)).size !== value.question_count) {
    throw new QuizRequestError("练习结果题目不一致，请重新读取。", "INVALID_RESPONSE");
  }
  return value as unknown as QuizSubmissionResult;
}
async function readReceipt(response: Response, resourceId: string, resourceVersion: number): Promise<QuizSubmissionResult> {
  let receipt: QuizSubmissionResult;
  try { receipt = parseQuizResult(await response.json()); } catch (error) {
    if (error instanceof QuizRequestError) throw error;
    throw new QuizRequestError("练习结果响应无效，请重新读取。", "INVALID_RESPONSE");
  }
  if (receipt.resource_id !== resourceId || receipt.resource_version !== resourceVersion) {
    throw new QuizRequestError("练习结果与资源版本不一致，请重新读取。", "INVALID_RESPONSE");
  }
  return receipt;
}
async function responseError(response: Response): Promise<QuizRequestError> {
  let payload: unknown;
  try { payload = await response.json(); } catch { payload = null; }
  return new QuizRequestError(
    record(payload) && typeof payload.message === "string" ? payload.message : "练习请求失败，请重试。",
    record(payload) && typeof payload.code === "string" ? payload.code : "REQUEST_FAILED",
  );
}
export async function submitQuizAttempt({
  resourceId, resourceVersion, answers, csrfToken, idempotencyKey, fetchImpl = fetch,
}: SubmitQuizOptions): Promise<QuizSubmissionResult> {
  let response: Response;
  try {
    response = await fetchImpl("/api/quiz-submissions", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrfToken, "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ resource_id: resourceId, resource_version: resourceVersion, answers }),
    });
  } catch {
    throw new QuizRequestError("练习提交连接中断。请使用同一次作答重试，避免重复记录。");
  }
  if (!response.ok) throw await responseError(response);
  return readReceipt(response, resourceId, resourceVersion);
}
export async function loadLatestQuizResult({ resourceId, resourceVersion, fetchImpl = fetch }:
  QuizResourceRef & { fetchImpl?: FetchLike }): Promise<QuizSubmissionResult | null> {
  let response: Response;
  try {
    response = await fetchImpl(`/api/quiz-submissions/latest?${new URLSearchParams({ resource_id: resourceId, resource_version: String(resourceVersion) })}`, { credentials: "same-origin", headers: { Accept: "application/json" } });
  } catch {
    throw new QuizRequestError("已提交的练习结果暂时无法读取，请重试读取。");
  }
  if (response.status === 404) return null;
  if (!response.ok) throw await responseError(response);
  return readReceipt(response, resourceId, resourceVersion);
}
