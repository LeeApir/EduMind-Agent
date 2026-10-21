import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import TeachingNodeSummary from "../src/components/TeachingNodeSummary.vue";
import App from "../src/App.vue";
import { startLearningSession } from "../src/api/learningSessions";
import type { TeachingContext } from "../src/api/teachingContext";

const context: TeachingContext = { version: "teaching-node-binding-v1", teaching_mode: "recommended",
  target_node_id: "linked-list-insertion", recommended_node_id: "c-pointer", teaching_node_id: "c-pointer",
  original_request: "学习头插法", segment_goal: "先补指针", segment_scope: "prerequisite_segment",
  selection_reason: "recommended_prerequisite", path_version_id: "frozen-path", path_version: 1,
  graph_version: "g1", graph_digest: "a".repeat(64) };
const stubs = { ProfileCard: true, LearningPathPanel: true, KnowledgeExplorer: true, PublishedLearningWorkspace: true,
  AnimationPanel: true, ClassroomPanel: true, DebatePanel: true, LearningControlsPanel: true, NotesDownload: true };
beforeEach(() => sessionStorage.clear());
afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });

it("posts explicit modes and receives selection before content", async () => {
  for (const teachingMode of ["target", "recommended"] as const) {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('event: teaching_selected\ndata: {"binding_status":"bound"}\n\n'));
    const onEvent = vi.fn();
    await startLearningSession({ goal: "学习头插法", teachingMode, csrfToken: "test", onEvent, fetchImpl });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body).teaching_mode).toBe(teachingMode);
    expect(onEvent).toHaveBeenCalledWith({ type: "teaching_selected", data: { binding_status: "bound" } });
  }
});
it("distinguishes original target, advice and prerequisite without claiming completion", () => {
  const wrapper = mount(TeachingNodeSummary, { props: { context, bindingStatus: "bound" } });
  expect(wrapper.get('[data-testid="target-node"]').text()).toBe("链表插入");
  expect(wrapper.get('[data-testid="teaching-node"]').text()).toBe("C 指针");
  expect(wrapper.text()).toContain("原目标尚未交付");
  wrapper.unmount();
});
it("does not invent a node from a missing historical context", () => {
  const wrapper = mount(TeachingNodeSummary, { props: { context: null, bindingStatus: "legacy_unverified" } });
  expect(wrapper.find('[data-testid="teaching-node"]').exists()).toBe(false);
  expect(wrapper.text()).toContain("历史课程未绑定"); wrapper.unmount();
});
it("refresh recovers exact publication and frozen context through GET only", async () => {
  sessionStorage.setItem("edumind:last-learning-unit", "unit-frozen-0001");
  sessionStorage.setItem("edumind:publication:unit-frozen-0001", "2");
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
    if (String(input) === "/api/learning-units/unit-frozen-0001?publication_version=2") return Response.json({
      publication_version: 2, teaching_context: context, binding_status: "bound", knowledge_node_id: "c-pointer",
      path_target_node_id: "linked-list-insertion", scenes: [{ id: "s1", scene_key: "explanation", version: 2,
        resources: [{ id: "r1", type: "explanation", version: 2, review_status: "passed", content: { markdown: "指针" } }] }],
    });
    throw new Error(`Unexpected request ${input}`);
  });
  vi.stubGlobal("fetch", fetchImpl);
  const wrapper = mount(App, { global: { stubs } });
  await flushPromises();
  expect(wrapper.get('[data-testid="teaching-node"]').text()).toBe("C 指针");
  expect(fetchImpl.mock.calls.map((c) => String(c[0]))).toContain("/api/learning-units/unit-frozen-0001?publication_version=2");
  expect(fetchImpl.mock.calls.every((c) => !String(c[0]).includes("learning-sessions"))).toBe(true);
  wrapper.unmount();
});
it("retry preserves submitted mode and key even if the next-request selector changes", async () => {
  const posts: RequestInit[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) === "/api/auth/session") return Response.json({ csrf_token: "csrf" });
    if (String(input) === "/api/learning-sessions") {
      posts.push(init!);
      return new Response('event: error\ndata: {"code":"TEMPORARILY_UNAVAILABLE","message":"稍后重试","retryable":false}\n\n');
    }
    throw new Error(`Unexpected ${input}`);
  }));
  const wrapper = mount(App, { global: { stubs } });
  await wrapper.get("textarea").setValue("学习头插法");
  await wrapper.get("#teaching-mode").setValue("recommended");
  await wrapper.get("form").trigger("submit"); await flushPromises();
  await wrapper.get("#teaching-mode").setValue("target");
  await wrapper.get(".error-state button").trigger("click"); await flushPromises();
  expect(posts).toHaveLength(2);
  expect(posts.map((p) => JSON.parse(String(p.body)).teaching_mode)).toEqual(["recommended", "recommended"]);
  expect(posts[1].headers).toEqual(posts[0].headers);
  wrapper.unmount();
});
