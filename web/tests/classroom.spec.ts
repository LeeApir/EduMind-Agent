import { describe, expect, it, vi } from "vitest";

import {
  ClassroomSpeechError,
  createClassroom,
  loadClassroom,
  loadClassroomMessages,
  loadClassroomOperation,
  setClassroomMode,
  streamClassroomSpeech,
  type ClassroomSpeechEvent,
} from "../src/api/classroom";

const encoder = new TextEncoder();

function streamResponse(chunks: Array<string | Uint8Array>): Response {
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  }), { headers: { "Content-Type": "text/event-stream" } });
}

const snapshot = {
  learning_unit_id: "unit-1", revision: 1, message_cursor: 0,
  scene_key: "intro", scene_version: 1, scene_progress: 0,
  mode: "focus", enabled_roles: [], paused: false,
};

function speechOptions(overrides: Record<string, unknown> = {}) {
  return {
    unitId: "unit-1",
    text: "继续讲解",
    sceneVersion: 1,
    csrfToken: "c".repeat(64),
    idempotencyKey: "k".repeat(16),
    revision: 1,
    onEvent: vi.fn(),
    ...overrides,
  };
}

describe("classroom API client", () => {
  it("streams speech events with the required headers, body, and typed event data", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse([
      'event: agent_start\ndata: {"operation_id":"op-1","revision":1,"scene_version":1,"generation_id":null}\n\n',
      'event: token\ndata: {"revision":1,"scene_version":1,"generation_id":null,"temporary":true,"delta":"先保存后继","role":"tutor"}\n\n',
      'event: review_pass\ndata: {"operation_id":"op-1","kind":"speech"}\n\n',
      'event: message_ready\ndata: {"revision":1,"message_cursor":1,"message_id":"m-1"}\n\n',
      'event: done\ndata: {"status":"published"}\n\n',
    ]));
    const events: ClassroomSpeechEvent[] = [];

    await streamClassroomSpeech(speechOptions({ onEvent: (event: ClassroomSpeechEvent) => events.push(event), fetchImpl }));

    expect(events.map((event) => event.type)).toEqual([
      "agent_start", "token", "review_pass", "message_ready", "done",
    ]);
    expect(events[1].data).toEqual({
      revision: 1, scene_version: 1, generation_id: null,
      temporary: true, delta: "先保存后继", role: "tutor",
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom/messages",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({
          Accept: "text/event-stream",
          "Content-Type": "application/json",
          "X-CSRF-Token": "c".repeat(64),
          "Idempotency-Key": "k".repeat(16),
          "If-Match-Classroom-Revision": "1",
        }),
        body: JSON.stringify({ text: "继续讲解", scene_version: 1 }),
      }),
    );
  });

  it("surfaces a stream error event as a retryable ClassroomSpeechError with the operation id", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse([
      'event: agent_start\ndata: {"operation_id":"op-1","revision":1,"scene_version":1}\n\n',
      'event: error\ndata: {"code":"PROVIDER_UNAVAILABLE","retryable":true}\n\n',
      'event: done\ndata: {"status":"failed"}\n\n',
    ]));

    await expect(streamClassroomSpeech(speechOptions({ fetchImpl }))).rejects.toMatchObject({
      code: "PROVIDER_UNAVAILABLE",
      retryable: true,
      operationId: "op-1",
    });
  });

  it("maps an HTTP error before streaming to a ClassroomSpeechError with status", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "CLASSROOM_VERSION_CONFLICT",
      message: "Classroom revision is now 2.",
      retryable: false,
    }), { status: 409 }));

    await expect(streamClassroomSpeech(speechOptions({ fetchImpl }))).rejects.toMatchObject({
      code: "CLASSROOM_VERSION_CONFLICT",
      status: 409,
      retryable: false,
    });
  });

  it("reads a snapshot and creates a classroom with CSRF and idempotency headers", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify(snapshot)));
    await expect(loadClassroom("unit-1", fetchImpl)).resolves.toMatchObject({ mode: "focus" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    const createFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(snapshot), { status: 201 }));
    await expect(createClassroom("unit-1", "c".repeat(64), "k".repeat(16), createFetch))
      .resolves.toMatchObject({ revision: 1 });
    expect(createFetch).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-CSRF-Token": "c".repeat(64),
          "Idempotency-Key": "k".repeat(16),
        }),
      }),
    );
  });

  it("switches mode with a CAS revision header and role body", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...snapshot, revision: 2, mode: "interactive", enabled_roles: ["beginner", "advanced"],
    })));
    await expect(setClassroomMode("unit-1", {
      mode: "interactive",
      enabledRoles: ["beginner", "advanced"],
      revision: 1,
      csrfToken: "c".repeat(64),
      idempotencyKey: "k".repeat(16),
    }, fetchImpl)).resolves.toMatchObject({ revision: 2, mode: "interactive" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom/mode",
      expect.objectContaining({
        method: "PATCH",
        headers: expect.objectContaining({ "If-Match-Classroom-Revision": "1" }),
        body: JSON.stringify({ mode: "interactive", enabled_roles: ["beginner", "advanced"] }),
      }),
    );
  });

  it("pages messages with an after cursor and reads operation status", async () => {
    const messagesFetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      messages: [], last_message_cursor: 3,
    }))));
    await expect(loadClassroomMessages("unit-1", 0, messagesFetch)).resolves.toMatchObject({ last_message_cursor: 3 });
    expect(messagesFetch).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom/messages",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await loadClassroomMessages("unit-1", 3, messagesFetch);
    expect(messagesFetch).toHaveBeenLastCalledWith(
      "/api/learning-units/unit-1/classroom/messages?after=3",
      expect.anything(),
    );

    const operationFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: "op-1", status: "published", learning_unit_id: "unit-1", kind: "speech", base_revision: 1,
    })));
    await expect(loadClassroomOperation("op-1", operationFetch)).resolves.toMatchObject({ status: "published" });
    expect(operationFetch).toHaveBeenCalledWith(
      "/api/classroom-operations/op-1",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("reports a connection failure as a retryable ClassroomSpeechError", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("offline"));
    await expect(streamClassroomSpeech(speechOptions({ fetchImpl }))).rejects.toMatchObject({
      code: "CONNECTION_FAILED",
      retryable: true,
    });
    expect(fetchImpl).toBeInstanceOf(Function);
    expect(ClassroomSpeechError).toBeTruthy();
  });
});
