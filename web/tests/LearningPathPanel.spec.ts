import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import LearningPathPanel from "../src/components/LearningPathPanel.vue";
import { PathRequestError, type LearningPath, type MasterySnapshot } from "../src/api/paths";

const graph = { graph_version: "g1", nodes: [
  { id: "array", name: "数组", prerequisites: [] },
  { id: "c-pointer", name: "C 指针", prerequisites: [] },
  { id: "linked-list-concept", name: "链表概念", prerequisites: ["array", "c-pointer"] },
] };
const mastery: MasterySnapshot = { graph_version: "g1", items: [
  { knowledge_node_id: "array", previous_score: 0.8, score: 0.9, status: "mastered", revision: 3, rule_version: "mastery-v1", evidence_summary: ["数组测验通过"] },
  { knowledge_node_id: "c-pointer", previous_score: 0, score: 0.3, status: "weak", revision: 1, rule_version: "mastery-v1", evidence_summary: ["指针测验需要巩固"] },
] };
const path: LearningPath = { version: 1, target_node_id: "linked-list-concept", graph_version: "g1", profile_version: 1, mastery_revision_watermark: 4,
  planner_rule_version: "path-v2", nodes: ["c-pointer", "linked-list-concept"], node_details: [
    { node_id: "c-pointer", score: 0.3, status: "weak", cost: 0.2, recommended_resource: "review", estimated_minutes: 12 },
    { node_id: "linked-list-concept", score: 0, status: "unseen", cost: 0, recommended_resource: "explanation", estimated_minutes: 16 },
  ], current_node_id: "c-pointer", prerequisite_node_ids: [], next_node_id: "linked-list-concept",
  reasons: [{ kind: "mastery_evidence", summary: "先巩固 C 指针。", knowledge_node_id: "c-pointer" }, { kind: "goal", summary: "继续目标链表概念。" }],
  changes: { kind: "initial_plan", trigger: "initial_plan", added_node_ids: ["c-pointer", "linked-list-concept"], removed_node_ids: [], reordered_node_ids: [] }, is_stale: false,
};
const stubs = { NButton: { props: ["disabled"], emits: ["click"], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' } };
function props() { return { targetNodeId: "linked-list-concept", csrfToken: "csrf", readPath: vi.fn().mockResolvedValue(path), readGraph: vi.fn().mockResolvedValue(graph), readMastery: vi.fn().mockResolvedValue(mastery), replan: vi.fn().mockResolvedValue({ ...path, version: 2 }) }; }

describe("lightweight learning path", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("uses default API callbacks as functions rather than executing prop factories", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/path/current?target_node_id=linked-list-concept") return Response.json(path);
      if (url === "/api/graph") return Response.json(graph);
      if (url === "/api/mastery") return Response.json(mastery);
      throw new Error(`unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);
    const wrapper = mount(LearningPathPanel, { props: { targetNodeId: "linked-list-concept", csrfToken: "csrf" }, global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("当前：C 指针 · 下一步：链表概念");
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
  it("shows current/next, completed prerequisite and four-state accessible legend with server evidence", async () => {
    const wrapper = mount(LearningPathPanel, { props: props(), global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("当前：C 指针 · 下一步：链表概念");
    expect(wrapper.get('[aria-label="节点状态说明"]').text()).toContain("学习中");
    expect(wrapper.get('[data-node-id="array"]').text()).toContain("已掌握 · 90%");
    const pointer = wrapper.get('[data-node-id="c-pointer"] button');
    expect(pointer.attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[aria-label="节点推荐依据"]').text()).toContain("指针测验需要巩固");
    await wrapper.get('[data-node-id="array"] button').trigger("click");
    expect(wrapper.get('[aria-label="节点推荐依据"]').text()).toContain("数组测验通过");
    expect(wrapper.get('[data-node-id="array"] button').attributes("type")).toBe("button");
  });
  it("replans stale version after quiz and preserves unchanged nodes and selected details", async () => {
    const options = props();
    const wrapper = mount(LearningPathPanel, { props: options, global: { stubs } });
    await flushPromises();
    await wrapper.get('[data-node-id="array"] button').trigger("click");
    const arrayElement = wrapper.get('[data-node-id="array"]').element;
    options.readPath.mockResolvedValue({ ...path, is_stale: true });
    options.readMastery.mockResolvedValue({ ...mastery, items: [mastery.items[0], { ...mastery.items[1], status: "learning", score: 0.6, revision: 2 }] });
    options.replan.mockResolvedValue({ ...path, version: 2, mastery_revision_watermark: 5 });
    await wrapper.setProps({ refreshToken: 1 }); await flushPromises();
    expect(options.replan).toHaveBeenCalledWith(expect.objectContaining({ expectedVersion: 1, reason: "mastery_changed", csrfToken: "csrf" }));
    expect(wrapper.get('[data-node-id="array"]').element).toBe(arrayElement);
    expect(wrapper.get('[data-node-id="array"]').attributes("data-changed")).toBe("false");
    expect(wrapper.get('[data-node-id="c-pointer"]').attributes("data-changed")).toBe("true");
    expect(wrapper.get('[data-node-id="array"] button').attributes("aria-pressed")).toBe("true");
    expect(options.readGraph).toHaveBeenCalledTimes(1);
  });
  it("retains old view on failure and retries the same durable replan key", async () => {
    const options = props();
    const wrapper = mount(LearningPathPanel, { props: options, global: { stubs } }); await flushPromises();
    options.readPath.mockResolvedValue({ ...path, is_stale: true });
    options.replan.mockRejectedValueOnce(new Error("网络中断"));
    await wrapper.setProps({ refreshToken: 1 }); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("上次读取的推荐");
    await wrapper.get('[role="alert"] button').trigger("click"); await flushPromises();
    expect(options.replan.mock.calls[1][0]).toEqual(options.replan.mock.calls[0][0]);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
  it("handles no path without fabricated nodes and recovers version conflicts through a fresh read", async () => {
    const options = props(); options.readPath.mockResolvedValueOnce(null);
    const wrapper = mount(LearningPathPanel, { props: options, global: { stubs } }); await flushPromises();
    expect(wrapper.text()).toContain("暂无已保存路径");
    expect(wrapper.find('[data-node-id]').exists()).toBe(false);
    options.readPath.mockResolvedValue({ ...path, is_stale: true });
    options.replan.mockRejectedValueOnce(new PathRequestError("版本冲突", "PATH_VERSION_CONFLICT"));
    await wrapper.setProps({ refreshToken: 1 }); await flushPromises();
    const firstKey = options.replan.mock.calls[0][0].idempotencyKey;
    await wrapper.get('[role="alert"] button').trigger("click"); await flushPromises();
    expect(options.replan.mock.calls[1][0].idempotencyKey).not.toBe(firstKey);
    expect(wrapper.find('[data-node-id]').exists()).toBe(true);
  });
  it("rejects mismatched graph versions and ignores obsolete target responses", async () => {
    const options = props(); options.readGraph.mockResolvedValue({ ...graph, graph_version: "g2" });
    const wrapper = mount(LearningPathPanel, { props: options, global: { stubs } }); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("版本已变化");
    let finish!: (value: LearningPath) => void;
    options.readPath.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockResolvedValue(null);
    await wrapper.setProps({ targetNodeId: "array" });
    await wrapper.setProps({ targetNodeId: "queue" }); await flushPromises();
    finish(path); await flushPromises();
    expect(wrapper.find('[data-node-id]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("C 指针");
  });
  it("does not combine newer mastery with an older recommendation snapshot", async () => {
    const options = props();
    options.readMastery.mockResolvedValue({ ...mastery, items: [mastery.items[0], { ...mastery.items[1], revision: 2 }] });
    const wrapper = mount(LearningPathPanel, { props: options, global: { stubs } }); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("掌握度已变化");
    expect(wrapper.find('[data-node-id]').exists()).toBe(false);
  });
  it("shows completed targets without inventing a new next step", async () => {
    const options = props();
    options.readPath.mockResolvedValue({ ...path, nodes: [], node_details: [], current_node_id: null, next_node_id: null, mastery_revision_watermark: 5 });
    options.readMastery.mockResolvedValue({ ...mastery, items: [mastery.items[0], { ...mastery.items[1], status: "mastered", score: 0.9 },
      { ...mastery.items[1], knowledge_node_id: "linked-list-concept", status: "mastered", score: 0.9 }] });
    const wrapper = mount(LearningPathPanel, { props: options, global: { stubs } }); await flushPromises();
    expect(wrapper.text()).toContain("这条目标路径已完成");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.findAll('[data-node-id]')).toHaveLength(3);
  });
});
