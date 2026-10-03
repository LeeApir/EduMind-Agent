import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App.vue";
import LearningControlsPanel from "../src/components/LearningControlsPanel.vue";

const stubs = {
  NButton: {
    props: ["disabled"],
    emits: ["click"],
    template: "<button :disabled=\"disabled\" @click=\"$emit('click', $event)\"><slot /></button>",
  },
  NInput: {
    props: ["value"],
    emits: ["update:value"],
    template: "<textarea @input=\"$emit('update:value', $event.target.value)\" />",
  },
  NTag: { template: "<span><slot /></span>" },
  ProfileCard: {
    props: ["refreshToken"],
    template: "<section data-testid=\"profile-card\">学习画像 {{ refreshToken }}</section>",
  },
};

describe("learning entry", () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });
  it("shows the one-sentence learning entry", () => {
    const wrapper = mount(App, {
      global: {
        stubs,
      },
    });

    expect(wrapper.get("h1").text()).toContain("你现在想弄懂什么？");
    expect(wrapper.get("label").text()).toBe("学习目标");
    expect(wrapper.text()).toContain("不需要先填写画像");
  });

  it("renders the viewable and correctable profile card", () => {
    const wrapper = mount(App, {
      global: { stubs },
    });

    expect(wrapper.get('[data-testid="profile-card"]').text()).toContain("学习画像");
  });

  it("notifies the profile card after a learning request succeeds", async () => {
    const wrapper = mount(App, {
      props: { startLearningRequest: vi.fn().mockResolvedValue(undefined) },
      global: { stubs },
    });
    expect(wrapper.get('[data-testid="profile-card"]').text()).toContain("0");

    await wrapper.get("textarea").setValue("想理解链表");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[data-testid="profile-card"]').text()).toContain("1");
  });

  it("enters a clear pending state from one sentence", async () => {
    const wrapper = mount(App, {
      global: { stubs },
    });
    await wrapper.get("textarea").setValue("想理解链表");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get('[data-testid="loading-state"]').text()).toContain("想理解链表");
  });

  it("shows a request error and retries the same goal", async () => {
    const startLearningRequest = vi
      .fn<(...args: [string]) => Promise<void>>()
      .mockRejectedValueOnce(new Error("网络连接中断，请重试。"))
      .mockResolvedValueOnce(undefined);
    const wrapper = mount(App, {
      props: { startLearningRequest },
      global: { stubs },
    });

    await wrapper.get("textarea").setValue("想理解链表");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.text()).toContain("网络连接中断，请重试。");
    await wrapper.get(".error-state button").trigger("click");

    expect(startLearningRequest).toHaveBeenCalledTimes(2);
    expect(startLearningRequest).toHaveBeenLastCalledWith("想理解链表");
    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(false);
    expect(wrapper.find(".error-state").exists()).toBe(false);
  });

  it("restores reviewed resources and the server quiz receipt after a page reload", async () => {
    sessionStorage.setItem("edumind:last-learning-unit", "unit-restored-0001");
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
      if (url === "/api/learning-units/unit-restored-0001/classroom") return Response.json({
        learning_unit_id: "unit-restored-0001", revision: 1, message_cursor: 0,
        scene_key: "intro", scene_version: 0, scene_progress: 0,
        mode: "focus", enabled_roles: [], paused: false,
      });
      if (url === "/api/learning-units/unit-restored-0001/classroom/controls") return Response.json({
        learning_unit_id: "unit-restored-0001", revision: 2, message_cursor: 0,
        scene_key: "intro", scene_version: 0, scene_progress: 0,
        mode: "focus", enabled_roles: [], paused: false,
      });
      if (url === "/api/learning-units/unit-restored-0001/classroom/messages") return Response.json({ messages: [], last_message_cursor: 0 });
      if (url === "/api/learning-units/unit-restored-0001") return Response.json({ scenes: [{ resources: [
        { id: "exercise-resource-001", type: "exercise", version: 1, review_status: "passed", content: { items: [{ id: "q1", question: "指针是什么？" }] } },
      ] }] });
      if (url.startsWith("/api/quiz-submissions/latest?")) return Response.json({
        evidence_id: "evidence-001", resource_id: "exercise-resource-001", resource_version: 1,
        question_results: [{ question_id: "q1", correct: true, explanation: "服务端反馈", error_patterns: [] }],
        score: 1, correct_count: 1, question_count: 1, quiz_schema_version: 1, scoring_rule_version: "quiz-exact-text-v1",
        mastery_changes: [{ knowledge_node_id: "c-pointer", previous_score: 0, score: 0.55, status: "learning", revision: 1, rule_version: "mastery-v1" }],
        path_replan_required: true, profile_update_status: "no_change",
      });
      throw new Error(`unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);
    const wrapper = mount(App, { global: { stubs } });
    await flushPromises();
    await wrapper.get(".published-workspace nav button:nth-child(3)").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("服务端反馈");
    expect(wrapper.text()).toContain("0% → 55%");
    expect(fetchImpl.mock.calls.some(([url]) => String(url).startsWith("/api/quiz-submissions/latest?"))).toBe(true);
    expect(sessionStorage.getItem("edumind:last-learning-unit")).toBe("unit-restored-0001");
  });

  it("keeps a manual history selection when a late new version arrives", async () => {
    sessionStorage.setItem("edumind:last-learning-unit", "unit-history");
    let published = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
      if (url === "/api/learning-units/unit-history") return Response.json({ scenes: [
        ...(published ? [{
          id: "new", scene_key: "intro", version: 3, is_current: true,
          resources: [{ id: "explanation-new", type: "explanation", version: 3,
            review_status: "passed", content: { markdown: "第三版讲解" } }],
        }] : []),
        { id: "current", scene_key: "intro", version: 2, is_current: !published,
          resources: [{ id: "explanation-current", type: "explanation", version: 2,
            review_status: "passed", content: { markdown: "第二版讲解" } }] },
        { id: "old", scene_key: "intro", version: 1, is_current: false,
          resources: [{ id: "explanation-old", type: "explanation", version: 1,
            review_status: "passed", content: { markdown: "第一版讲解" } }] },
      ] });
      if (url === "/api/learning-units/unit-history/classroom") return Response.json({
        learning_unit_id: "unit-history", revision: 1, message_cursor: 0,
        scene_key: "intro", scene_version: 2, scene_progress: 0,
        mode: "focus", enabled_roles: [], paused: false,
      });
      if (url === "/api/learning-units/unit-history/classroom/messages") return Response.json({ messages: [], last_message_cursor: 0 });
      if (url.startsWith("/api/quiz-submissions/latest")) return Response.json({ code: "NOT_FOUND" }, { status: 404 });
      throw new Error(`unexpected request ${url}`);
    }));
    const wrapper = mount(App, { global: { stubs } });
    await flushPromises();
    expect(wrapper.get('[data-testid="explanation-tab"]').text()).toContain("第二版讲解");
    const controls = wrapper.getComponent(LearningControlsPanel);
    controls.vm.$emit("select-scene", "old");
    await flushPromises();
    published = true;
    controls.vm.$emit("scene-changed", "current", "intro", 3);
    await flushPromises();
    expect(wrapper.get('[data-testid="explanation-tab"]').text()).toContain("第一版讲解");
    expect(sessionStorage.getItem("edumind:scene-selection:unit-history")).toBe("old");
  });
});
