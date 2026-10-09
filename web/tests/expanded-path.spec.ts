import { readFileSync } from "node:fs";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import KnowledgeExplorer from "../src/components/KnowledgeExplorer.vue";
import LearningPathPanel from "../src/components/LearningPathPanel.vue";
import { loadGraphVersion, parseLearningPath, planPath, type GraphSnapshot, type LearningPath, type MasterySnapshot } from "../src/api/paths";
import { pathFixture } from "./pathFixture";

const graph = JSON.parse(readFileSync("../data/knowledge/phase-1.1.0.json", "utf8")) as GraphSnapshot;
const mastery: MasterySnapshot = { graph_version: graph.graph_version, items: [{ knowledge_node_id: "array",
  previous_score: .5, score: .9, status: "mastered", revision: 1, rule_version: "mastery-v1", evidence_summary: ["TEST_ONLY quiz"] }] };
const catalog = { status: "ready" as const, releases: [{ id: "release-1", package_id: "TEST_ONLY", version: "1", digest: "TEST_ONLY",
  nodes: [{ id: "array", name: "数组", description: "TEST_ONLY", prerequisites: [] }] }] };
function options() { return { csrfToken: "csrf", catalog, canEnroll: true, canPlan: true,
  readGraph: vi.fn().mockResolvedValue(graph), readMastery: vi.fn().mockResolvedValue(mastery),
  plan: vi.fn().mockResolvedValue({ target_node_id: "breadth-first-search" }) }; }
const stubs = { LearningPathPanel: { props: ["targetNodeId"], template: "<p>路径目标 {{ targetNodeId }}</p>" } };

describe("expanded graph and path availability", () => {
  it("browses actual thirty nodes with prerequisite links and evidence-backed states", async () => {
    const wrapper = mount(KnowledgeExplorer, { props: options(), global: { stubs } }); await flushPromises();
    expect(wrapper.findAll("[data-knowledge-id]")).toHaveLength(30);
    expect(wrapper.text()).toContain("30 个知识点");
    expect(wrapper.get('[data-knowledge-id="array"]').text()).toContain("已掌握");
    const button = wrapper.get('[data-knowledge-id="breadth-first-search"]');
    expect(button.attributes("type")).toBe("button");
    await button.trigger("click");
    expect(button.attributes("aria-pressed")).toBe("true");
    const detail = wrapper.get('[aria-label="知识点详情"]');
    expect(detail.text()).toContain("掌握度未知");
    expect(detail.text()).not.toContain("0%");
    expect(detail.text()).toContain("队列");
    expect(detail.text()).toContain("该知识点暂未提供已审核课程");
    expect(detail.findAll("button").some(item => item.text() === "学习已审核课程")).toBe(false);
    await detail.findAll("button").find(item => item.text() === "队列")!.trigger("click");
    expect(wrapper.get('[data-knowledge-id="queue"]').attributes("aria-pressed")).toBe("true");
    wrapper.unmount();
  });
  it("emits enrollment only for actual catalog membership and confirmed reads", async () => {
    const wrapper = mount(KnowledgeExplorer, { props: { ...options(), fixedCompletedNodeId: "array" }, global: { stubs } }); await flushPromises();
    await wrapper.get('[data-knowledge-id="array"]').trigger("click");
    expect(wrapper.text()).toContain("已完成固定题；这不等于已掌握");
    await wrapper.findAll("button").find(item => item.text() === "学习已审核课程")!.trigger("click");
    expect(wrapper.emitted("learn")).toEqual([["release-1", "array"]]);
    await wrapper.setProps({ catalogReady: false });
    expect(wrapper.text()).toContain("课程可用性尚未确认");
    expect(wrapper.findAll("button").some(item => item.text() === "学习已审核课程")).toBe(false);
    wrapper.unmount();
  });
  it("chooses a metadata target without inventing a learning unit", async () => {
    const props = options();
    const wrapper = mount(KnowledgeExplorer, { props, global: { stubs } }); await flushPromises();
    await wrapper.get('[data-knowledge-id="breadth-first-search"]').trigger("click");
    await wrapper.findAll("button").find(item => item.text() === "查看该目标路径")!.trigger("click"); await flushPromises();
    expect(props.plan).toHaveBeenCalledWith("breadth-first-search", "csrf", expect.any(String));
    expect(wrapper.text()).toContain("路径目标 breadth-first-search");
    expect(wrapper.emitted("learn")).toBeUndefined();
    wrapper.unmount();
  });
  it("keeps retry keys and ignores late planning after changing selection", async () => {
    const props = options(); props.plan.mockRejectedValueOnce(new Error("offline"));
    const wrapper = mount(KnowledgeExplorer, { props, global: { stubs } }); await flushPromises();
    await wrapper.get('[data-knowledge-id="breadth-first-search"]').trigger("click");
    const plan = () => wrapper.findAll("button").find(item => item.text() === "查看该目标路径")!;
    await plan().trigger("click"); await flushPromises();
    const key = props.plan.mock.calls[0][2];
    let resolve!: (value: unknown) => void;
    props.plan.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    await plan().trigger("click");
    expect(props.plan.mock.calls[1][2]).toBe(key);
    await wrapper.get('[data-knowledge-id="queue"]').trigger("click");
    resolve({ target_node_id: "breadth-first-search" }); await flushPromises();
    expect(wrapper.text()).not.toContain("路径目标 breadth-first-search");
    wrapper.unmount();
  });
  it("shows read failures separately from missing courses", async () => {
    const props = options(); props.readGraph.mockRejectedValue(new Error("GRAPH_UNAVAILABLE"));
    const wrapper = mount(KnowledgeExplorer, { props, global: { stubs } }); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("GRAPH_UNAVAILABLE");
    expect(wrapper.text()).not.toContain("暂未提供已审核课程");
    expect(props.plan).not.toHaveBeenCalled(); wrapper.unmount();
  });
  it("reads historical graph explicitly and preserves original steps without automatic replan", async () => {
    const old: LearningPath = { ...pathFixture, graph_version: "mvp-0.2.0", is_stale: true };
    const oldGraph = { graph_version: old.graph_version, nodes: [
      { id: "c-pointer", name: "C 指针", prerequisites: [] },
      { id: "linked-list-concept", name: "链表概念", prerequisites: ["c-pointer"] }] };
    const readGraph = vi.fn().mockResolvedValue(oldGraph);
    const replan = vi.fn();
    const wrapper = mount(LearningPathPanel, { props: { targetNodeId: old.target_node_id, csrfToken: "csrf",
      readPath: vi.fn().mockResolvedValue(old), readMastery: vi.fn().mockResolvedValue(mastery), readGraph, replan },
      global: { stubs: { NButton: { template: "<button><slot /></button>" } } } }); await flushPromises();
    expect(wrapper.text()).toContain("正在查看历史路径");
    expect(wrapper.findAll("[data-node-id]")).toHaveLength(2);
    expect(readGraph).toHaveBeenCalledWith("mvp-0.2.0");
    expect(replan).not.toHaveBeenCalled();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false); wrapper.unmount();
  });
  it("clears previous session evidence and target before a new session read finishes", async () => {
    const props = options();
    const wrapper = mount(KnowledgeExplorer, { props, global: { stubs } }); await flushPromises();
    await wrapper.get('[data-knowledge-id="breadth-first-search"]').trigger("click");
    await wrapper.findAll("button").find(item => item.text() === "查看该目标路径")!.trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("路径目标 breadth-first-search");
    props.readMastery.mockImplementationOnce(() => new Promise(() => {}));
    await wrapper.setProps({ csrfToken: "new-session" }); await flushPromises();
    expect(wrapper.text()).not.toContain("路径目标 breadth-first-search");
    expect(wrapper.get('[data-knowledge-id="array"]').text()).toContain("掌握度未知");
    expect(wrapper.get('[data-knowledge-id="array"]').text()).not.toContain("已掌握");
    wrapper.unmount();
  });
  it("validates eligibility, known mastery and explicit-version transport", async () => {
    const eligibility = { node_id: "c-pointer", status: "unavailable", reason: "no_reviewed_course", catalog_release_id: null, learning_unit_id: null };
    expect(() => parseLearningPath({ ...pathFixture, learning_availability: [eligibility] })).toThrow();
    expect(() => parseLearningPath({ ...pathFixture, node_details: pathFixture.node_details.map(node => ({ ...node, mastery_known: "true" })) })).toThrow();
    expect(() => parseLearningPath({ ...pathFixture, learning_availability: pathFixture.nodes.map(node_id => ({ ...eligibility, node_id, status: "available" })) })).toThrow();
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(graph)).mockResolvedValueOnce(Response.json(pathFixture));
    await loadGraphVersion(graph.graph_version, fetch);
    expect(fetch.mock.calls[0][0]).toBe("/api/graph?version=phase-1.1.0");
    await planPath(pathFixture.target_node_id, "csrf", "key", fetch);
    expect(fetch.mock.calls[1][1].headers).toMatchObject({ "X-CSRF-Token": "csrf", "Idempotency-Key": "key" });
  });
});
