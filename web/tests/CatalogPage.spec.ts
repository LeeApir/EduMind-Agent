import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../src/api/catalog";
import CatalogPage from "../src/components/CatalogPage.vue";
import ProductApp from "../src/ProductApp.vue";

vi.mock("../src/api/catalog", async (original) => ({ ...await original<typeof import("../src/api/catalog")>(),
  ensureCatalogSession: vi.fn(), loadCatalog: vi.fn(), loadCatalogUnit: vi.fn(), enrollCatalog: vi.fn(),
  loadPresetDemo: vi.fn(), createCatalogClassroom: vi.fn(), controlPresetDemo: vi.fn(), loadProductMode: vi.fn(),
}));
const release = { id: "release", package_id: "linear", version: "1.0.0", digest: "hash", nodes: [
  { id: "array", name: "数组", description: "数组基础", prerequisites: [] },
  { id: "linked-list-insertion", name: "链表插入", description: "保存连接", prerequisites: ["array"] },
] };
const classroom = { revision: 1, scene_key: "intro", scene_version: 1, scene_progress: 3, paused: false };
const unit = { id: "unit", status: "ready" as const, origin_type: "curated" as const,
  catalog_release_id: "release", knowledge_node_id: "array", scenes: [{ id: "scene", scene_key: "intro",
    version: 1, is_current: true, resources: [
      { id: "r1", version: 1, type: "explanation" as const, content: { markdown: "固定讲解" } },
      { id: "r2", version: 1, type: "code" as const, content: { source: "C" } },
      { id: "r3", version: 1, type: "exercise" as const, content: { items: [] } },
    ] }] };
const demo = { preset: true as const, release_id: "release", demo_digest: "hash", script: {
  title: "数组 vs 链表", perspectives: [0, 1, 2].map((i) => ({ title: String(i), text: "固定观点" })), summary: "固定总结",
}, classroom };
const stubs = {
  PublishedLearningWorkspace: { props: ["selectedResource"], template: "<div data-test='workspace'>{{ selectedResource }}</div>" },
  LearningPathPanel: { template: "<div data-test='path'>学习进度与推荐</div>" },
  AnimationPanel: { template: "<div data-test='animation'>动画</div>" },
};
async function click(wrapper: ReturnType<typeof mount>, text: string): Promise<void> {
  await wrapper.findAll("button").find((button) => button.text().includes(text))!.trigger("click");
  await flushPromises();
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  vi.mocked(api.ensureCatalogSession).mockResolvedValue({ owner: "owner", csrf: "csrf" });
  vi.mocked(api.loadCatalog).mockResolvedValue({ status: "ready", releases: [release] });
  vi.mocked(api.loadCatalogUnit).mockResolvedValue(unit);
  vi.mocked(api.enrollCatalog).mockResolvedValue("unit");
  vi.mocked(api.loadPresetDemo).mockResolvedValue(demo);
});
describe("catalog learning page", () => {
  it("shows only the pending message when no approved course exists", async () => {
    vi.mocked(api.loadCatalog).mockResolvedValue({ status: "not_ready", releases: [] });
    const wrapper = mount(CatalogPage, { global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("课程正在准备");
    expect(api.enrollCatalog).not.toHaveBeenCalled();
    expect(wrapper.find("textarea").exists()).toBe(false);
    wrapper.unmount();
  });
  it("keeps the same enrollment key after a lost response and loads fixed resources", async () => {
    vi.mocked(api.enrollCatalog).mockRejectedValueOnce(new Error("连接中断"));
    const wrapper = mount(CatalogPage, { global: { stubs } });
    await flushPromises(); await click(wrapper, "数组");
    expect(wrapper.text()).toContain("连接中断");
    await click(wrapper, "数组");
    expect(api.enrollCatalog).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.enrollCatalog).mock.calls[0][3]).toBe(vi.mocked(api.enrollCatalog).mock.calls[1][3]);
    expect(wrapper.find('[data-test="workspace"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="animation"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("重新解释");
    wrapper.unmount();
  });
  it("restores only this owner unit and preset return tab, then exits at current revision", async () => {
    sessionStorage.setItem("edumind:catalog:last:other", "foreign");
    sessionStorage.setItem("edumind:catalog:last:owner", "unit");
    const active = { ...classroom, revision: 2, paused: true,
      detour: { kind: "catalog_demo", return_point: { resource_type: "exercise" as const } } };
    vi.mocked(api.loadPresetDemo).mockResolvedValue({ ...demo, classroom: active });
    vi.mocked(api.controlPresetDemo).mockResolvedValue({ classroom: { ...classroom, revision: 3 }, return_resource_type: "exercise" });
    const wrapper = mount(CatalogPage, { global: { stubs } });
    await flushPromises();
    expect(api.loadCatalogUnit).toHaveBeenCalledWith("unit");
    expect(api.enrollCatalog).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("预设教学演示");
    expect(api.createCatalogClassroom).not.toHaveBeenCalled();
    await click(wrapper, "退出演示");
    expect(api.controlPresetDemo).toHaveBeenCalledWith("unit", "exit", "exercise", 2, "csrf", expect.any(String));
    expect(wrapper.get('[data-test="workspace"]').text()).toBe("exercise");
    wrapper.unmount();
  });
  it("clears stale withdrawn resources and does not create a replacement automatically", async () => {
    sessionStorage.setItem("edumind:catalog:last:owner", "revoked");
    vi.mocked(api.loadCatalogUnit).mockRejectedValue(new api.CatalogRequestError("课程已撤回", 404));
    const wrapper = mount(CatalogPage, { global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("课程已撤回");
    expect(sessionStorage.getItem("edumind:catalog:last:owner")).toBeNull();
    expect(api.enrollCatalog).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it("shows animations only at their fixed linked-list nodes", async () => {
    vi.mocked(api.loadCatalogUnit).mockResolvedValue({ ...unit, knowledge_node_id: "linked-list-insertion" });
    const wrapper = mount(CatalogPage, { global: { stubs } });
    await flushPromises(); await click(wrapper, "链表插入");
    expect(wrapper.find('[data-test="animation"]').exists()).toBe(true);
    wrapper.unmount();
  });
});
describe("product scope entry", () => {
  it("fails closed without mounting either learning flow when runtime is unavailable", async () => {
    vi.mocked(api.loadProductMode).mockRejectedValue(new Error("down"));
    const wrapper = mount(ProductApp, { global: { stubs: { CatalogPage: true, DynamicApp: true } } });
    await flushPromises();
    expect(wrapper.text()).toContain("无法读取课程入口");
    expect(api.ensureCatalogSession).not.toHaveBeenCalled();
    expect(wrapper.find("catalog-page-stub").exists()).toBe(false);
    wrapper.unmount();
  });
});
