export type EvidenceSource =
  | "initial_query"
  | "learner_statement"
  | "learning_behavior"
  | "explicit_feedback"
  | "manual_correction";

export interface ProfileEvidenceRecord {
  source: EvidenceSource;
  confidence: number;
  observed_at: string;
  profile_version: number;
}

export const PROFILE_FIELDS = [
  "professional_background",
  "knowledge_base",
  "cognitive_style",
  "learning_goals",
  "error_preferences",
  "engineering_preference",
] as const;

export type ProfileField = (typeof PROFILE_FIELDS)[number];

export const EDITABLE_PROFILE_FIELDS = [
  "professional_background",
  "learning_goals",
  "error_preferences",
  "engineering_preference",
] as const;

export type EditableProfileField = (typeof EDITABLE_PROFILE_FIELDS)[number];

export interface Profile {
  id: string;
  version: number;
  initial_query: string;
  professional_background: Record<string, unknown> | null;
  knowledge_base: Record<string, unknown> | null;
  cognitive_style: Record<string, unknown> | null;
  learning_goals: Record<string, unknown> | null;
  error_preferences: unknown[] | null;
  engineering_preference: Record<string, unknown> | null;
  extended_dimensions: Record<string, unknown> | null;
  evidence: Record<string, ProfileEvidenceRecord[]>;
  updated_at: string;
}

export interface ProfileHistoryPage {
  items: Profile[];
  next_before_version: number | null;
}

export type ProfileFieldStatus = "unknown" | "known" | "inferred" | "corrected";

export const PROFILE_FIELD_LABELS: Record<ProfileField, string> = {
  professional_background: "专业背景",
  knowledge_base: "知识基础",
  cognitive_style: "认知风格",
  learning_goals: "学习目标",
  error_preferences: "易错偏好",
  engineering_preference: "工程偏好",
};

export const PROFILE_FIELD_STATUS_LABELS: Record<ProfileFieldStatus, string> = {
  unknown: "未知",
  known: "已知",
  inferred: "推断",
  corrected: "用户修正",
};

export const EVIDENCE_SOURCE_LABELS: Record<EvidenceSource, string> = {
  initial_query: "初始目标",
  learner_statement: "学习者陈述",
  learning_behavior: "学习行为",
  explicit_feedback: "明确反馈",
  manual_correction: "用户修正",
};

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface ApiErrorPayload {
  code?: string;
  message?: string;
  retryable?: boolean;
}

export class ProfileRequestError extends Error {
  readonly code: string;
  readonly retryable: boolean;

  constructor({
    message,
    code = "CONNECTION_FAILED",
    retryable = true,
  }: {
    message: string;
    code?: string;
    retryable?: boolean;
  }) {
    super(message);
    this.name = "ProfileRequestError";
    this.code = code;
    this.retryable = retryable;
  }
}

export function isProfileField(field: string): field is ProfileField {
  return (PROFILE_FIELDS as readonly string[]).includes(field);
}

export function isEditableProfileField(field: string): field is EditableProfileField {
  return (EDITABLE_PROFILE_FIELDS as readonly string[]).includes(field);
}

const SOURCE_PRECEDENCE: readonly EvidenceSource[] = [
  "manual_correction",
  "explicit_feedback",
  "learner_statement",
  "learning_behavior",
  "initial_query",
];

export function strongestEvidenceSource(field: ProfileField, profile: Profile): EvidenceSource | null {
  const records = profile.evidence[field] ?? [];
  if (records.length === 0) {
    return null;
  }
  let best: EvidenceSource = records[0].source;
  let bestRank = SOURCE_PRECEDENCE.indexOf(best);
  for (const record of records) {
    const rank = SOURCE_PRECEDENCE.indexOf(record.source);
    if (rank >= 0 && rank < bestRank) {
      best = record.source;
      bestRank = rank;
    }
  }
  return best;
}

export function profileFieldStatus(field: ProfileField, profile: Profile): ProfileFieldStatus {
  const value = profile[field];
  if (value === null || value === undefined) {
    return "unknown";
  }
  const source = strongestEvidenceSource(field, profile);
  if (source === "manual_correction") {
    return "corrected";
  }
  if (source === "explicit_feedback" || source === "learner_statement") {
    return "known";
  }
  return "inferred";
}

export async function fetchProfile(
  { fetchImpl = fetch }: { fetchImpl?: FetchLike } = {},
): Promise<Profile> {
  let response: Response;
  try {
    response = await fetchImpl("/api/profile/me", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ProfileRequestError({
      message: "画像读取连接失败，请检查网络后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }
  if (response.status === 404) {
    throw new ProfileRequestError({
      message: "还没有生成学习画像。",
      code: "NOT_FOUND",
      retryable: false,
    });
  }
  if (!response.ok) {
    throw profileErrorFromPayload(await readErrorPayload(response), response.status);
  }
  return (await response.json()) as Profile;
}

export interface CorrectProfileOptions {
  corrections: Record<string, unknown>;
  expectedVersion: number;
  csrfToken: string;
  idempotencyKey: string;
  fetchImpl?: FetchLike;
}

export async function correctProfile({
  corrections,
  expectedVersion,
  csrfToken,
  idempotencyKey,
  fetchImpl = fetch,
}: CorrectProfileOptions): Promise<Profile> {
  let response: Response;
  try {
    response = await fetchImpl("/api/profile/me", {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
        "If-Match-Profile-Version": String(expectedVersion),
      },
      body: JSON.stringify(corrections),
    });
  } catch {
    throw new ProfileRequestError({
      message: "画像修正连接失败，请检查网络后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }
  if (!response.ok) {
    const payload = await readErrorPayload(response);
    if (payload.code === "PROFILE_VERSION_CONFLICT") {
      throw new ProfileRequestError({
        message: "画像已在别处更新，请重新加载后再修改。",
        code: "PROFILE_VERSION_CONFLICT",
        retryable: true,
      });
    }
    if (payload.code === "IDEMPOTENCY_CONFLICT") {
      throw new ProfileRequestError({
        message: "修正请求重复，请重新加载后再试。",
        code: "IDEMPOTENCY_CONFLICT",
        retryable: false,
      });
    }
    throw profileErrorFromPayload(payload, response.status);
  }
  return (await response.json()) as Profile;
}

export interface FetchProfileHistoryOptions {
  limit?: number;
  beforeVersion?: number;
  fetchImpl?: FetchLike;
}

export async function fetchProfileHistory({
  limit = 20,
  beforeVersion,
  fetchImpl = fetch,
}: FetchProfileHistoryOptions = {}): Promise<ProfileHistoryPage> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (beforeVersion !== undefined) {
    params.set("before_version", String(beforeVersion));
  }
  let response: Response;
  try {
    response = await fetchImpl(`/api/profile/me/history?${params.toString()}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ProfileRequestError({
      message: "画像历史读取连接失败，请检查网络后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }
  if (!response.ok) {
    throw profileErrorFromPayload(await readErrorPayload(response), response.status);
  }
  return (await response.json()) as ProfileHistoryPage;
}

let cachedCsrfToken = "";

export async function ensureProfileSession(
  { fetchImpl = fetch }: { fetchImpl?: FetchLike } = {},
): Promise<string> {
  if (cachedCsrfToken) {
    return cachedCsrfToken;
  }
  let response: Response;
  try {
    response = await fetchImpl("/api/auth/session", { credentials: "same-origin" });
  } catch {
    throw new ProfileRequestError({
      message: "无法建立安全会话，请刷新页面后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }
  if (response.status === 401) {
    response = await fetchImpl("/api/auth/guest", {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  }
  if (!response.ok) {
    throw new ProfileRequestError({
      message: "无法建立安全会话，请刷新页面后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }
  const payload = (await response.json()) as { csrf_token?: string };
  if (typeof payload.csrf_token !== "string") {
    throw new ProfileRequestError({
      message: "会话响应无效，请刷新页面后重试。",
      code: "INVALID_SESSION",
      retryable: true,
    });
  }
  cachedCsrfToken = payload.csrf_token;
  return cachedCsrfToken;
}

async function readErrorPayload(response: Response): Promise<ApiErrorPayload> {
  try {
    return (await response.json()) as ApiErrorPayload;
  } catch {
    return {};
  }
}

function profileErrorFromPayload(payload: ApiErrorPayload, status?: number): ProfileRequestError {
  const message = typeof payload.message === "string"
    ? payload.message
    : "画像请求暂时无法完成，请重试。";
  const code = typeof payload.code === "string" ? payload.code : "REQUEST_FAILED";
  const retryable = typeof payload.retryable === "boolean"
    ? payload.retryable
    : status === undefined || status >= 500 || status === 429;
  return new ProfileRequestError({ message, code, retryable });
}
