import { parseSseStream } from "./learningSessions";

export type ClassroomMode = "focus" | "interactive";
export type CompanionRole = "beginner" | "advanced";
export type ClassroomMessageRole =
  | "student"
  | "tutor"
  | "beginner"
  | "advanced"
  | "system"
  | "performance"
  | "engineering"
  | "academic"
  | "moderator";

export type ClassroomSpeechEventType =
  | "agent_start"
  | "token"
  | "review_pass"
  | "stage_changed"
  | "debate_ready"
  | "message_ready"
  | "scene_ready"
  | "content_retracted"
  | "error"
  | "done";

export interface ClassroomSpeechEvent {
  type: ClassroomSpeechEventType;
  data: Record<string, unknown>;
}

export interface ClassroomDetour {
  scene_key: string;
  scene_version: number;
  scene_progress: number;
  kind?: "prerequisite" | "debate";
  target_node_id?: string;
  path_version_id?: string;
  result_id?: string;
  mode?: ClassroomMode;
  enabled_roles?: CompanionRole[];
  paused?: boolean;
}

export interface ClassroomSnapshot {
  learning_unit_id: string;
  revision: number;
  message_cursor: number;
  scene_key: string;
  scene_version: number;
  scene_progress: number;
  mode: ClassroomMode;
  enabled_roles: CompanionRole[];
  paused: boolean;
  generation_id?: string;
  detour?: ClassroomDetour;
  version_changed?: boolean;
}

export interface DebateResult {
  id: string;
  scene_key: string;
  scene_version: number;
  status: "published";
  question: string;
  question_conditions: { stated: string[]; unknown: string[] };
  perspectives: { performance: string; engineering: string; academic: string };
  moderator: { objective_conclusion: string; tradeoffs: string; learner_advice: string };
  moderator_summary: string;
  candidate_schema_version: string;
  candidate_prompt_version: string;
  generation_model_id: string;
  review_version: string;
  review_model_id: string;
  correction_attempts: number;
}

export interface StreamDebateOptions {
  unitId: string;
  question: string;
  revision: number;
  csrfToken: string;
  idempotencyKey: string;
  onEvent: (event: ClassroomSpeechEvent) => void;
  fetchImpl?: FetchLike;
}

export interface ClassroomMessage {
  id: string;
  cursor: number;
  role: ClassroomMessageRole;
  scene_key: string;
  scene_version: number;
  text?: string;
  resource_id?: string;
}

export interface ClassroomMessagePage {
  messages: ClassroomMessage[];
  last_message_cursor: number;
}

export type ClassroomOperationStatus =
  | "accepted"
  | "running"
  | "published"
  | "failed"
  | "cancelled"
  | "superseded";

export interface ClassroomOperation {
  id: string;
  status: ClassroomOperationStatus;
  learning_unit_id: string;
  kind: "speech" | "reexplanation" | "debate";
  base_revision: number;
  generation_id?: string;
  result_id?: string;
  error?: { code: string; message: string; retryable: boolean };
}

export interface SetClassroomModeOptions {
  mode: ClassroomMode;
  enabledRoles: CompanionRole[];
  revision: number;
  csrfToken: string;
  idempotencyKey: string;
}

export interface StreamClassroomSpeechOptions {
  unitId: string;
  text: string;
  sceneVersion: number;
  csrfToken: string;
  idempotencyKey: string;
  revision: number;
  onEvent: (event: ClassroomSpeechEvent) => void;
  fetchImpl?: FetchLike;
}

export type LearningControlAction = "pause" | "resume" | "skip" | "prerequisite" | "select_resource";
export type LearningResourceType = "explanation" | "code" | "exercise" | "animation";

export interface ControlClassroomOptions {
  unitId: string;
  action: LearningControlAction;
  revision: number;
  csrfToken: string;
  idempotencyKey: string;
  resourceType?: LearningResourceType;
  targetNodeId?: string;
  fetchImpl?: FetchLike;
}

export interface StreamReexplanationOptions {
  unitId: string;
  sceneKey: string;
  baseSceneVersion: number;
  action: "simpler" | "deeper" | "another_example";
  revision: number;
  csrfToken: string;
  idempotencyKey: string;
  onEvent: (event: ClassroomSpeechEvent) => void;
  fetchImpl?: FetchLike;
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface ApiErrorPayload {
  code?: string;
  message?: string;
  retryable?: boolean;
  operation_id?: string;
}

export class ClassroomSpeechError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly operationId?: string;
  readonly status?: number;

  constructor({
    message,
    code = "CONNECTION_FAILED",
    retryable = true,
    operationId,
    status,
  }: {
    message: string;
    code?: string;
    retryable?: boolean;
    operationId?: string;
    status?: number;
  }) {
    super(message);
    this.name = "ClassroomSpeechError";
    this.code = code;
    this.retryable = retryable;
    this.operationId = operationId;
    this.status = status;
  }
}

async function readErrorPayload(response: Response): Promise<ApiErrorPayload> {
  try {
    return (await response.json()) as ApiErrorPayload;
  } catch {
    return {};
  }
}

function defaultCodeForStatus(status: number): string {
  if (status === 401) return "UNAUTHORIZED";
  if (status === 403) return "CSRF_FAILED";
  if (status === 404) return "NOT_FOUND";
  if (status === 409) return "CLASSROOM_VERSION_CONFLICT";
  if (status === 422) return "VALIDATION_ERROR";
  if (status === 503) return "REVIEW_UNAVAILABLE";
  return "REQUEST_FAILED";
}

async function classroomErrorFromResponse(response: Response): Promise<ClassroomSpeechError> {
  const payload = await readErrorPayload(response);
  const code = typeof payload.code === "string" ? payload.code : defaultCodeForStatus(response.status);
  const retryable = typeof payload.retryable === "boolean"
    ? payload.retryable
    : response.status >= 500 || response.status === 429;
  const message = typeof payload.message === "string"
    ? payload.message
    : "课堂请求暂时无法完成，请重试。";
  return new ClassroomSpeechError({
    message,
    code,
    retryable,
    operationId: typeof payload.operation_id === "string" ? payload.operation_id : undefined,
    status: response.status,
  });
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await classroomErrorFromResponse(response);
  }
  return (await response.json()) as T;
}

/** Read the current classroom snapshot; throws NOT_FOUND when none exists yet. */
export async function loadClassroom(
  unitId: string,
  fetchImpl: FetchLike = fetch,
): Promise<ClassroomSnapshot> {
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom`,
    { credentials: "same-origin", headers: { Accept: "application/json" } },
  );
  return readJson<ClassroomSnapshot>(response);
}

/** Create the default focus classroom; idempotent by key so a lost response replays. */
export async function createClassroom(
  unitId: string,
  csrfToken: string,
  idempotencyKey: string,
  fetchImpl: FetchLike = fetch,
): Promise<ClassroomSnapshot> {
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
      },
    },
  );
  return readJson<ClassroomSnapshot>(response);
}

/** Switch focus/interactive mode and enabled companion roles with CAS revision. */
export async function setClassroomMode(
  unitId: string,
  { mode, enabledRoles, revision, csrfToken, idempotencyKey }: SetClassroomModeOptions,
  fetchImpl: FetchLike = fetch,
): Promise<ClassroomSnapshot> {
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom/mode`,
    {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
        "If-Match-Classroom-Revision": String(revision),
      },
      body: JSON.stringify({ mode, enabled_roles: enabledRoles }),
    },
  );
  return readJson<ClassroomSnapshot>(response);
}

/** Persist one learning control with an original receipt for idempotent retries. */
export async function controlClassroom({
  unitId, action, revision, csrfToken, idempotencyKey,
  resourceType, targetNodeId, fetchImpl = fetch,
}: ControlClassroomOptions): Promise<ClassroomSnapshot> {
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom/controls`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
        "If-Match-Classroom-Revision": String(revision),
      },
      body: JSON.stringify({
        action,
        ...(resourceType ? { resource_type: resourceType } : {}),
        ...(targetNodeId ? { target_node_id: targetNodeId } : {}),
      }),
    },
  );
  return readJson<ClassroomSnapshot>(response);
}

/** Stream temporary explanation text; only scene_ready identifies a published version. */
export async function streamReexplanation({
  unitId, sceneKey, baseSceneVersion, action, revision, csrfToken,
  idempotencyKey, onEvent, fetchImpl = fetch,
}: StreamReexplanationOptions): Promise<void> {
  let response: Response;
  try {
    response = await fetchImpl(
      `/api/learning-units/${encodeURIComponent(unitId)}/classroom/scenes/${encodeURIComponent(sceneKey)}/reexplanations`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": idempotencyKey,
          "If-Match-Classroom-Revision": String(revision),
        },
        body: JSON.stringify({ action, base_scene_version: baseSceneVersion }),
      },
    );
  } catch {
    throw new ClassroomSpeechError({
      message: "重解释连接失败，请检查网络后恢复原请求。",
      code: "CONNECTION_FAILED", retryable: true,
    });
  }
  if (!response.ok) throw await classroomErrorFromResponse(response);
  if (!response.body) throw new ClassroomSpeechError({
    message: "重解释未返回流式内容。", code: "EMPTY_STREAM", retryable: true,
  });
  let operationId: string | undefined;
  try {
    for await (const raw of parseSseStream(response.body)) {
      const event = raw as unknown as ClassroomSpeechEvent;
      if (event.type === "agent_start" && typeof event.data.operation_id === "string") {
        operationId = event.data.operation_id;
      }
      onEvent(event);
      if (event.type === "error") throw speechErrorFromPayload(event.data, operationId);
    }
  } catch (error) {
    if (error instanceof ClassroomSpeechError) throw error;
    throw new ClassroomSpeechError({
      message: "重解释连接中断，请先恢复原操作状态。",
      code: "CONNECTION_INTERRUPTED", retryable: true, operationId,
    });
  }
}

/** Start the fixed P0 debate; provisional candidate text is never exposed. */
export async function streamDebate({
  unitId, question, revision, csrfToken, idempotencyKey, onEvent, fetchImpl = fetch,
}: StreamDebateOptions): Promise<void> {
  let response: Response;
  try {
    response = await fetchImpl(
      `/api/learning-units/${encodeURIComponent(unitId)}/classroom/debate`,
      {
        method: "POST", credentials: "same-origin",
        headers: {
          Accept: "text/event-stream", "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken, "Idempotency-Key": idempotencyKey,
          "If-Match-Classroom-Revision": String(revision),
        },
        body: JSON.stringify({ preset: "array-vs-linked-list", question }),
      },
    );
  } catch {
    throw new ClassroomSpeechError({ message: "多视角演示连接失败，请恢复原请求。", code: "CONNECTION_FAILED" });
  }
  if (!response.ok) throw await classroomErrorFromResponse(response);
  if (!response.body) throw new ClassroomSpeechError({ message: "演示没有返回状态流。", code: "EMPTY_STREAM" });
  let operationId: string | undefined;
  try {
    for await (const raw of parseSseStream(response.body)) {
      const event = raw as unknown as ClassroomSpeechEvent;
      if (event.type === "agent_start" && typeof event.data.operation_id === "string") {
        operationId = event.data.operation_id;
      }
      onEvent(event);
      if (event.type === "error") throw speechErrorFromPayload(event.data, operationId);
    }
  } catch (error) {
    if (error instanceof ClassroomSpeechError) throw error;
    throw new ClassroomSpeechError({
      message: "演示连接中断，请先查询原操作状态。", code: "CONNECTION_INTERRUPTED",
      retryable: true, operationId,
    });
  }
}

export async function loadDebateResult(
  unitId: string, resultId: string, fetchImpl: FetchLike = fetch,
): Promise<DebateResult> {
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom/debate/${encodeURIComponent(resultId)}`,
    { credentials: "same-origin", headers: { Accept: "application/json" } },
  );
  return readJson<DebateResult>(response);
}

export async function exitDebate(
  unitId: string, resultId: string, revision: number, csrfToken: string,
  idempotencyKey: string, fetchImpl: FetchLike = fetch,
): Promise<ClassroomSnapshot> {
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom/debate/${encodeURIComponent(resultId)}/exit`,
    {
      method: "POST", credentials: "same-origin",
      headers: {
        Accept: "application/json", "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
        "If-Match-Classroom-Revision": String(revision),
      },
    },
  );
  return readJson<ClassroomSnapshot>(response);
}

/** Read committed classroom messages after the given cursor (no temporary tokens). */
export async function loadClassroomMessages(
  unitId: string,
  after: number,
  fetchImpl: FetchLike = fetch,
): Promise<ClassroomMessagePage> {
  const query = after > 0 ? `?after=${after}` : "";
  const response = await fetchImpl(
    `/api/learning-units/${encodeURIComponent(unitId)}/classroom/messages${query}`,
    { credentials: "same-origin", headers: { Accept: "application/json" } },
  );
  return readJson<ClassroomMessagePage>(response);
}

/** Read the durable status of a classroom streaming operation for recovery. */
export async function loadClassroomOperation(
  operationId: string,
  fetchImpl: FetchLike = fetch,
): Promise<ClassroomOperation> {
  const response = await fetchImpl(
    `/api/classroom-operations/${encodeURIComponent(operationId)}`,
    { credentials: "same-origin", headers: { Accept: "application/json" } },
  );
  return readJson<ClassroomOperation>(response);
}

/** Stream a reviewed classroom turn; only durable message_ready events point at committed messages. */
export async function streamClassroomSpeech({
  unitId,
  text,
  sceneVersion,
  csrfToken,
  idempotencyKey,
  revision,
  onEvent,
  fetchImpl = fetch,
}: StreamClassroomSpeechOptions): Promise<void> {
  const stream = await requestSpeechStream({
    unitId, text, sceneVersion, csrfToken, idempotencyKey, revision, fetchImpl,
  });
  let operationId: string | undefined;
  try {
    for await (const raw of parseSseStream(stream)) {
      const event = raw as unknown as ClassroomSpeechEvent;
      if (event.type === "agent_start" && typeof event.data.operation_id === "string") {
        operationId = event.data.operation_id;
      }
      onEvent(event);
      if (event.type === "error") {
        throw speechErrorFromPayload(event.data, operationId);
      }
    }
  } catch (error: unknown) {
    if (error instanceof ClassroomSpeechError) {
      throw error;
    }
    throw new ClassroomSpeechError({
      message: "课堂发言连接中断，请重试。",
      code: "CONNECTION_INTERRUPTED",
      retryable: true,
      operationId,
    });
  }
}

async function requestSpeechStream({
  unitId,
  text,
  sceneVersion,
  csrfToken,
  idempotencyKey,
  revision,
  fetchImpl,
}: {
  unitId: string;
  text: string;
  sceneVersion: number;
  csrfToken: string;
  idempotencyKey: string;
  revision: number;
  fetchImpl: FetchLike;
}): Promise<ReadableStream<Uint8Array>> {
  let response: Response;
  try {
    response = await fetchImpl(
      `/api/learning-units/${encodeURIComponent(unitId)}/classroom/messages`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": idempotencyKey,
          "If-Match-Classroom-Revision": String(revision),
        },
        body: JSON.stringify({ text, scene_version: sceneVersion }),
      },
    );
  } catch {
    throw new ClassroomSpeechError({
      message: "课堂发言连接失败，请检查网络后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }
  if (!response.ok) {
    throw await classroomErrorFromResponse(response);
  }
  if (!response.body) {
    throw new ClassroomSpeechError({
      message: "课堂服务未返回流式内容，请重试。",
      code: "EMPTY_STREAM",
      retryable: true,
    });
  }
  return response.body;
}

function speechErrorFromPayload(
  payload: Record<string, unknown>,
  operationId?: string,
): ClassroomSpeechError {
  const code = typeof payload.code === "string" ? payload.code : "REQUEST_FAILED";
  const retryable = typeof payload.retryable === "boolean" ? payload.retryable : true;
  return new ClassroomSpeechError({
    message: code === "REVIEW_REJECTED"
      ? "本次发言未通过安全审核，未发布。"
      : "本次发言未能完成，请重试。",
    code,
    retryable,
    operationId,
  });
}
