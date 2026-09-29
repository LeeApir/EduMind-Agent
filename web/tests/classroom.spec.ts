import { describe, expect, it, vi } from "vitest";

import {
  ClassroomSpeechError,
  controlClassroom,
  createClassroom,
  exitDebate,
  loadClassroom,
  loadClassroomMessages,
  loadClassroomOperation,
  loadDebateResult,
  setClassroomMode,
  streamClassroomSpeech,
  streamDebate,
  streamReexplanation,
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
  it("starts the fixed debate with CAS and only emits durable ready after review", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse([
      'event: agent_start\ndata: {"operation_id":"op-debate"}\n\n',
      'event: stage_changed\ndata: {"stage":"reviewing"}\n\n',
      'event: review_pass\ndata: {"operation_id":"op-debate","kind":"debate"}\n\n',
      'event: debate_ready\ndata: {"result_id":"result-1"}\n\n',
      'event: done\ndata: {"status":"published"}\n\n',
    ]));
    const received: ClassroomSpeechEvent[] = [];
    await streamDebate({ unitId: "unit-1", question: "怎么选？", revision: 3,
      csrfToken: "csrf", idempotencyKey: "debate-request-key-1", fetchImpl,
      onEvent: (event) => received.push(event) });
    expect(received.map((event) => event.type)).toEqual([
      "agent_start", "stage_changed", "review_pass", "debate_ready", "done",
    ]);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom/debate",
      expect.objectContaining({ method: "POST", body: JSON.stringify({
        preset: "array-vs-linked-list", question: "怎么选？",
      }), headers: expect.objectContaining({
        "If-Match-Classroom-Revision": "3", "Idempotency-Key": "debate-request-key-1",
        "X-CSRF-Token": "csrf",
      }) }),
    );
  });

  it("does not turn a rejected review into a published debate", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse([
      'event: agent_start\ndata: {"operation_id":"op-debate"}\n\n',
      'event: error\ndata: {"code":"REVIEW_REJECTED","retryable":false}\n\n',
    ]));
    await expect(streamDebate({ unitId: "unit-1", question: "怎么选？", revision: 1,
      csrfToken: "csrf", idempotencyKey: "debate-request-key-2", fetchImpl,
      onEvent: vi.fn() })).rejects.toMatchObject({
      code: "REVIEW_REJECTED", retryable: false, operationId: "op-debate",
    });
  });

  it("reads the reviewed result and exits with the original CAS receipt key", async () => {
    const fetchImpl = vi.fn().mockImplementation(async () =>
      Response.json({ id: "result-1", status: "published" }));
    await expect(loadDebateResult("unit-1", "result-1", fetchImpl)).resolves.toMatchObject({
      id: "result-1", status: "published",
    });
    await exitDebate("unit-1", "result-1", 2, "csrf", "debate-exit-key-01", fetchImpl);
    expect(fetchImpl).toHaveBeenLastCalledWith(
      "/api/learning-units/unit-1/classroom/debate/result-1/exit",
      expect.objectContaining({ method: "POST", headers: expect.objectContaining({
        "If-Match-Classroom-Revision": "2", "Idempotency-Key": "debate-exit-key-01",
      }) }),
    );
  });
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

  it("sends learning controls with revision, idempotency, and selected resource", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(Response.json({ ...snapshot, revision: 2 }));
    await controlClassroom({
      unitId: "unit-1", action: "select_resource", resourceType: "code",
      revision: 1, csrfToken: "csrf", idempotencyKey: "request-1", fetchImpl,
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom/controls",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "If-Match-Classroom-Revision": "1", "Idempotency-Key": "request-1",
          "X-CSRF-Token": "csrf",
        }),
        body: JSON.stringify({ action: "select_resource", resource_type: "code" }),
      }),
    );
  });

  it("streams reexplanation and treats temporary tokens as distinct from publication", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(streamResponse([
      'event: agent_start\ndata: {"operation_id":"op-reexplain"}\n\n',
      'event: token\ndata: {"temporary":true,"delta":"候选讲解"}\n\n',
      'event: scene_ready\ndata: {"scene_key":"intro","scene_version":2}\n\n',
      'event: done\ndata: {"status":"published"}\n\n',
    ]));
    const events: ClassroomSpeechEvent[] = [];
    await streamReexplanation({
      unitId: "unit-1", sceneKey: "intro", baseSceneVersion: 1,
      action: "simpler", revision: 1, csrfToken: "csrf", idempotencyKey: "request-2",
      fetchImpl, onEvent: (event) => events.push(event),
    });
    expect(events.map((event) => event.type)).toEqual(["agent_start", "token", "scene_ready", "done"]);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/learning-units/unit-1/classroom/scenes/intro/reexplanations",
      expect.objectContaining({
        headers: expect.objectContaining({ "If-Match-Classroom-Revision": "1" }),
        body: JSON.stringify({ action: "simpler", base_scene_version: 1 }),
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
