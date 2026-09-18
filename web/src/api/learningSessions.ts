export type LearningEventType =
  | "agent_start"
  | "token"
  | "stage_changed"
  | "review_pass"
  | "review_reject"
  | "scene_ready"
  | "error"
  | "done";

export interface LearningEvent {
  type: LearningEventType;
  data: Record<string, unknown>;
}

export interface StartLearningSessionOptions {
  goal: string;
  csrfToken: string;
  idempotencyKey?: string;
  onEvent: (event: LearningEvent) => void;
  fetchImpl?: FetchLike;
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface ApiErrorPayload {
  code?: string;
  message?: string;
  retryable?: boolean;
  operation_id?: string;
}

export class LearningRequestError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly operationId?: string;

  constructor({
    message,
    code = "CONNECTION_FAILED",
    retryable = true,
    operationId,
  }: {
    message: string;
    code?: string;
    retryable?: boolean;
    operationId?: string;
  }) {
    super(message);
    this.name = "LearningRequestError";
    this.code = code;
    this.retryable = retryable;
    this.operationId = operationId;
  }
}

export async function startLearningSession({
  goal,
  csrfToken,
  idempotencyKey = crypto.randomUUID(),
  onEvent,
  fetchImpl = fetch,
}: StartLearningSessionOptions): Promise<void> {
  const stream = await requestLearningStream({
    goal,
    csrfToken,
    idempotencyKey,
    fetchImpl,
  });

  const seenLifecycleEvents = new Set<string>();
  try {
    for await (const event of parseSseStream(stream)) {
      if (isDuplicateLifecycleEvent(event, seenLifecycleEvents)) {
        continue;
      }
      onEvent(event);
      if (event.type === "error") {
        throw errorFromPayload(event.data);
      }
    }
  } catch (error: unknown) {
    if (error instanceof LearningRequestError) {
      throw error;
    }
    throw new LearningRequestError({
      message: "学习请求连接中断，请重试。",
      code: "CONNECTION_INTERRUPTED",
      retryable: true,
    });
  }
}

async function requestLearningStream({
  goal,
  csrfToken,
  idempotencyKey,
  fetchImpl,
}: {
  goal: string;
  csrfToken: string;
  idempotencyKey: string;
  fetchImpl: FetchLike;
}): Promise<ReadableStream<Uint8Array>> {
  let response: Response;
  try {
    response = await fetchImpl("/api/learning-sessions", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ goal, preferred_language: "c" }),
    });
  } catch {
    throw new LearningRequestError({
      message: "学习请求连接失败，请检查网络后重试。",
      code: "CONNECTION_FAILED",
      retryable: true,
    });
  }

  if (!response.ok) {
    throw errorFromPayload(await readErrorPayload(response), response.status);
  }
  if (!response.body) {
    throw new LearningRequestError({
      message: "学习服务未返回流式内容，请重试。",
      code: "EMPTY_STREAM",
      retryable: true,
    });
  }
  return response.body;
}

async function readErrorPayload(response: Response): Promise<ApiErrorPayload> {
  try {
    return (await response.json()) as ApiErrorPayload;
  } catch {
    return {};
  }
}

function errorFromPayload(payload: Record<string, unknown> | ApiErrorPayload, status?: number): LearningRequestError {
  const message = typeof payload.message === "string"
    ? payload.message
    : "学习请求暂时无法完成，请重试。";
  const code = typeof payload.code === "string" ? payload.code : "REQUEST_FAILED";
  const retryable = typeof payload.retryable === "boolean"
    ? payload.retryable
    : status === undefined || status >= 500 || status === 429;
  const operationId = typeof payload.operation_id === "string" ? payload.operation_id : undefined;
  return new LearningRequestError({ message, code, retryable, operationId });
}

export async function* parseSseStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<LearningEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];

  const dispatch = (): LearningEvent | undefined => {
    if (dataLines.length === 0) {
      eventName = "message";
      return undefined;
    }
    const data = parseEventData(dataLines.join("\n"));
    const type = eventName as LearningEventType;
    eventName = "message";
    dataLines = [];
    return { type, data };
  };

  const consumeLine = (line: string): LearningEvent | undefined => {
    if (line === "") {
      return dispatch();
    }
    if (line.startsWith(":")) {
      return undefined;
    }
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");
    if (field === "event") {
      eventName = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
    return undefined;
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer) {
          const event = consumeLine(stripTrailingCarriageReturn(buffer));
          if (event) {
            yield event;
          }
        }
        const event = dispatch();
        if (event) {
          yield event;
        }
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        const event = consumeLine(stripTrailingCarriageReturn(buffer.slice(0, newlineIndex)));
        if (event) {
          yield event;
        }
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseEventData(rawData: string): Record<string, unknown> {
  try {
    const data = JSON.parse(rawData) as unknown;
    if (data && typeof data === "object" && !Array.isArray(data)) {
      return data as Record<string, unknown>;
    }
  } catch {
    // The API contract requires object JSON; surface malformed data as a safe client error.
  }
  throw new LearningRequestError({
    message: "学习服务返回了无法识别的数据，请重试。",
    code: "INVALID_EVENT",
    retryable: true,
  });
}

function stripTrailingCarriageReturn(line: string): string {
  return line.endsWith("\r") ? line.slice(0, -1) : line;
}

function isDuplicateLifecycleEvent(event: LearningEvent, seen: Set<string>): boolean {
  if (event.type === "token") {
    return false;
  }
  const signature = `${event.type}:${JSON.stringify(event.data)}`;
  if (seen.has(signature)) {
    return true;
  }
  seen.add(signature);
  return false;
}
