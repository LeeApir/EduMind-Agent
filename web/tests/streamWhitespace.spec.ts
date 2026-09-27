import { readFileSync } from "node:fs";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App.vue";
import { startLearningSession } from "../src/api/learningSessions";

// Offline actual backend token frames, never a replay of T035's missing raw stream.
const fixture = JSON.parse(readFileSync("../docs/acceptance/mvp-0.2-t036-offline-sse.json", "utf8")) as {
  expected: string;
  sse: string;
};
function response(size: number): Response {
  const bytes = new TextEncoder().encode(`: heartbeat\n\n${fixture.sse}`);
  return new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += size) controller.enqueue(bytes.slice(i, i + size));
      controller.close();
    },
  }), { headers: { "Content-Type": "text/event-stream" } });
}
const stubs = {
  NButton: { props: ["disabled"], emits: ["click"], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  NInput: { props: ["value"], emits: ["update:value"], template: '<textarea @input="$emit(\'update:value\', $event.target.value)" />' },
  NTag: { template: "<span><slot /></span>" },
  ProfileCard: true, LearningPathPanel: true, PublishedLearningWorkspace: true,
};
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

describe("lossless streamed body", () => {
  it.each([1, 7, 65536])("decodes actual backend SSE with %i-byte transport chunks", async (size) => {
    const deltas: string[] = [];
    await startLearningSession({
      goal: "公开测试", csrfToken: "mock", idempotencyKey: "mock-key",
      fetchImpl: vi.fn().mockResolvedValue(response(size)),
      onEvent: (event) => { if (event.type === "token") deltas.push(event.data.delta as string); },
    });
    expect(deltas.join("")).toBe(fixture.expected);
    expect(deltas).toContain(" ");
    expect(deltas).toContain("\n");
    expect(deltas).toContain("\t");
    expect(deltas.join("")).not.toContain("heartbeat");
  });

  it("keeps exact body in App and escaped DOM, with whitespace-preserving presentation", async () => {
    sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/auth/session") return Response.json({ csrf_token: "mock" });
      if (String(input) === "/api/learning-sessions") return response(1);
      throw new Error("unexpected mock request");
    }));
    const wrapper = mount(App, { global: { stubs } });
    await flushPromises();
    await wrapper.get("textarea").setValue("学习链表");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    const body = wrapper.get(".temporary-body");
    // wrapper.text() trims whitespace, so inspect the real text node instead.
    expect(body.element.textContent).toBe(fixture.expected);
    expect(body.find("script").exists()).toBe(false);
    const component = readFileSync("src/components/LearningProgressPanel.vue", "utf8");
    expect(component).toContain("white-space: pre-wrap;");
    wrapper.unmount();
  });
});
