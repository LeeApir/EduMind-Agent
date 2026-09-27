import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App.vue";
import { startLearningSession, type StartLearningSessionOptions } from "../src/api/learningSessions";

vi.mock("../src/api/learningSessions", async (importOriginal) => ({
  ...await importOriginal<typeof import("../src/api/learningSessions")>(),
  startLearningSession: vi.fn(),
}));
const start = vi.mocked(startLearningSession);
const stubs = {
  NButton: { props: ["disabled"], emits: ["click"], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  NInput: { props: ["value"], emits: ["update:value"], template: '<textarea @input="$emit(\'update:value\', $event.target.value)" />' },
  NTag: { template: "<span><slot /></span>" },
  ProfileCard: true, LearningPathPanel: true, PublishedLearningWorkspace: true,
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
function broken(options: StartLearningSessionOptions) {
  options.onEvent({ type: "agent_start", data: { operation_id: "op-original", stage: "preparing" } });
  return Promise.reject(new Error("network interrupted"));
}
const unit = (text = "原资源") => Response.json({ scenes: [{ resources: [
  { id: "resource-original", type: "explanation", version: 1, review_status: "passed", content: { markdown: text } },
] }] });

describe("learning request identity recovery", () => {
  let state: string;
  let reads: number;
  let unavailable: number;
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    sessionStorage.clear(); start.mockReset(); state = "published"; reads = 0; unavailable = 0;
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
      if (url === "/api/learning-operations/op-original") {
        reads++;
        if (reads <= unavailable) throw new Error("lookup unavailable");
        return Response.json({ id: "op-original", status: state, learning_unit_id: state === "published" ? "unit-original" : null });
      }
      if (url === "/api/learning-units/unit-original") return unit();
      throw new Error("unexpected fetch");
    });
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });
  async function begin() {
    const wrapper = mount(App, { global: { stubs } });
    await wrapper.get("textarea").setValue("学习指针");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    return wrapper;
  }

  it("recovers the same published resource after the response is lost without a second POST", async () => {
    unavailable = 1; start.mockImplementation(broken);
    const wrapper = await begin();
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    expect(start).toHaveBeenCalledTimes(1);
    expect(reads).toBe(2);
    expect(wrapper.text()).toContain("已审核正式资源");
    expect(sessionStorage.getItem("edumind:last-learning-unit")).toBe("unit-original");
  });

  it("keeps the original operation across repeated lookup failures and preserves the goal", async () => {
    unavailable = 2; start.mockImplementation(broken);
    const wrapper = await begin();
    await wrapper.get("textarea").setValue("草稿不应改变原目标");
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    expect(start).toHaveBeenCalledTimes(1);
    expect(start.mock.calls[0]![0].goal).toBe("学习指针");
    expect(reads).toBe(3);
    expect(wrapper.text()).toContain("已审核正式资源");
  });

  it("waits for a running operation without generating again", async () => {
    state = "reviewing"; start.mockImplementation(broken);
    const wrapper = await begin();
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("请等待后重试恢复");
    expect(start).toHaveBeenCalledTimes(1);
    expect(reads).toBe(2);
  });

  it("reuses the same key and frozen goal when no operation ID was received", async () => {
    start.mockRejectedValue(new Error("response lost before first event"));
    const wrapper = await begin();
    await wrapper.get("textarea").setValue("未提交草稿");
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    expect(start.mock.calls[1]![0].idempotencyKey).toBe(start.mock.calls[0]![0].idempotencyKey);
    expect(start.mock.calls[1]![0].goal).toBe("学习指针");
  });

  it("handles a failed same-key SSE replay without silently treating done as success", async () => {
    state = "failed";
    start.mockImplementation(async (options) => {
      options.onEvent({ type: "agent_start", data: { operation_id: "op-original", stage: "failed" } });
      options.onEvent({ type: "done", data: { operation_id: "op-original", status: "failed" } });
    });
    const wrapper = await begin();
    expect(wrapper.text()).toContain("原请求已失败或取消");
    expect(reads).toBe(1);
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    expect(start).toHaveBeenCalledTimes(1);
    expect(reads).toBe(2);
  });

  it("replays explicit failure without new generation; explicit regenerate and new goal use new keys", async () => {
    state = "failed"; start.mockImplementation(broken);
    const wrapper = await begin();
    const original = start.mock.calls[0]![0].idempotencyKey;
    await wrapper.get(".error-state button").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("原请求已失败或取消");
    expect(start).toHaveBeenCalledTimes(1);
    await wrapper.get('[data-testid="regenerate-learning"]').trigger("click"); await flushPromises();
    const regenerated = start.mock.calls[1]![0].idempotencyKey;
    expect(regenerated).not.toBe(original);
    await wrapper.get("textarea").setValue("学习数组");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(start.mock.calls[2]![0].idempotencyKey).not.toBe(regenerated);
    expect(start.mock.calls[2]![0].goal).toBe("学习数组");
  });

  it.each(["success", "error"] as const)("ignores late old stream events and %s after a new goal", async (outcome) => {
    const old = deferred<void>();
    start.mockImplementationOnce(() => old.promise).mockRejectedValue(new Error("new target network failure"));
    const wrapper = await begin();
    const oldOptions = start.mock.calls[0]![0];
    await wrapper.get("textarea").setValue("学习数组");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    oldOptions.onEvent({ type: "token", data: { operation_id: "op-old", temporary: true, delta: "旧目标迟到内容" } });
    oldOptions.onEvent({ type: "scene_ready", data: { learning_unit_id: "unit-old" } });
    if (outcome === "success") old.resolve(); else old.reject(new Error("old failure"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("旧目标迟到内容");
    expect(wrapper.text()).toContain("new target network failure");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("op-old") || String(url).includes("unit-old"))).toBe(false);
  });

  it("ignores a late resource read after a new goal", async () => {
    const oldRead = deferred<Response>(); start.mockImplementation(broken);
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
      if (String(input).includes("learning-operations")) return Response.json({ id: "op-original", status: "published", learning_unit_id: "unit-original" });
      return oldRead.promise;
    });
    const wrapper = await begin();
    start.mockRejectedValue(new Error("new target"));
    await wrapper.get("textarea").setValue("新目标");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    oldRead.resolve(unit("迟到资源")); await flushPromises();
    expect(wrapper.text()).toContain("new target");
    expect(wrapper.text()).not.toContain("已审核正式资源");
    expect(sessionStorage.getItem("edumind:last-learning-unit")).toBeNull();
  });

  it("ignores a late operation lookup after a new goal without fetching old resources", async () => {
    const lookup = deferred<Response>(); start.mockImplementation(broken);
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
      return lookup.promise;
    });
    const wrapper = await begin();
    start.mockRejectedValue(new Error("new goal failure"));
    await wrapper.get("textarea").setValue("新目标");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    lookup.resolve(Response.json({ id: "op-original", status: "published", learning_unit_id: "unit-original" }));
    await flushPromises();
    expect(wrapper.text()).toContain("new goal failure");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("learning-units"))).toBe(false);
    expect(sessionStorage.length).toBe(0);
  });
});
