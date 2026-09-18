import { describe, expect, it, vi } from "vitest";

import {
  LearningRequestError,
  parseSseStream,
  startLearningSession,
} from "../src/api/learningSessions";

const encoder = new TextEncoder();

function streamFromChunks(chunks: Array<string | Uint8Array>): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  });
}

function streamResponse(chunks: Array<string | Uint8Array>): Response {
  return new Response(streamFromChunks(chunks), {
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("POST learning-session SSE client", () => {
  it("parses split Unicode chunks, multiple events, and stream completion", async () => {
    const events = [] as Array<{ type: string; data: Record<string, unknown> }>;
    const unicode = encoder.encode("链表");
    const chunks = [
      "event: agent_start\r\ndata: {\"operation_id\":\"op-1\",\"stage\":\"preparing\"}\r\n\r\n",
      "event: token\ndata: {\"operation_id\":\"op-1\",\"temporary\":true,\"delta\":\"",
      unicode.slice(0, 2),
      unicode.slice(2),
      "\"}\n\nevent: done\ndata: {\"operation_id\":\"op-1\",\"status\":\"published\"}\n\n",
    ];
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse(chunks));

    await startLearningSession({
      goal: "想理解链表",
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0001",
      fetchImpl,
      onEvent: (event) => events.push(event),
    });

    expect(events).toEqual([
      { type: "agent_start", data: { operation_id: "op-1", stage: "preparing" } },
      { type: "token", data: { operation_id: "op-1", temporary: true, delta: "链表" } },
      { type: "done", data: { operation_id: "op-1", status: "published" } },
    ]);
    expect(fetchImpl).toHaveBeenCalledWith("/api/learning-sessions", expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      headers: expect.objectContaining({
        "X-CSRF-Token": "c".repeat(64),
        "Idempotency-Key": "idempotency-key-0001",
      }),
    }));
  });

  it("does not duplicate replayed lifecycle events but retains repeated token text", async () => {
    const events: string[] = [];
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse([
      "event: agent_start\ndata: {\"operation_id\":\"op-1\",\"stage\":\"preparing\"}\n\n",
      "event: agent_start\ndata: {\"operation_id\":\"op-1\",\"stage\":\"preparing\"}\n\n",
      "event: token\ndata: {\"operation_id\":\"op-1\",\"temporary\":true,\"delta\":\"。\"}\n\n",
      "event: token\ndata: {\"operation_id\":\"op-1\",\"temporary\":true,\"delta\":\"。\"}\n\n",
    ]));

    await startLearningSession({
      goal: "链表",
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0002",
      fetchImpl,
      onEvent: (event) => events.push(event.type),
    });

    expect(events).toEqual(["agent_start", "token", "token"]);
  });

  it("surfaces API, SSE, and interrupted-stream errors as retryable request errors", async () => {
    const apiFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "RATE_LIMITED",
      message: "请稍后重试。",
      retryable: true,
    }), { status: 429 }));
    const interruptedStream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.error(new Error("connection reset"));
      },
    });
    const interruptedFetch = vi.fn().mockResolvedValue(new Response(interruptedStream));
    const streamEvents: string[] = [];
    const sseErrorFetch = vi.fn().mockResolvedValue(streamResponse([
      "event: error\ndata: {\"code\":\"PROVIDER_UNAVAILABLE\",\"message\":\"服务暂不可用\",\"retryable\":true,\"operation_id\":\"op-1\"}\n\n",
      "event: done\ndata: {\"operation_id\":\"op-1\",\"status\":\"failed\"}\n\n",
    ]));

    await expect(startLearningSession({
      goal: "链表",
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0003",
      fetchImpl: apiFetch,
      onEvent: vi.fn(),
    })).rejects.toMatchObject({ code: "RATE_LIMITED", retryable: true });
    await expect(startLearningSession({
      goal: "链表",
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0004",
      fetchImpl: sseErrorFetch,
      onEvent: (event) => streamEvents.push(event.type),
    })).rejects.toMatchObject({
      code: "PROVIDER_UNAVAILABLE",
      retryable: true,
      operationId: "op-1",
    });
    expect(streamEvents).toEqual(["error"]);
    await expect(startLearningSession({
      goal: "链表",
      csrfToken: "c".repeat(64),
      idempotencyKey: "idempotency-key-0005",
      fetchImpl: interruptedFetch,
      onEvent: vi.fn(),
    })).rejects.toBeInstanceOf(LearningRequestError);
  });

  it("rejects malformed SSE data rather than displaying it", async () => {
    const events = [] as unknown[];
    const stream = streamFromChunks(["event: token\ndata: not-json\n\n"]);

    await expect(async () => {
      for await (const event of parseSseStream(stream)) {
        events.push(event);
      }
    }).rejects.toMatchObject({ code: "INVALID_EVENT" });
    expect(events).toEqual([]);
  });
});
