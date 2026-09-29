import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LearningControlsPanel from "../src/components/LearningControlsPanel.vue";
import type {
  ClassroomSnapshot,
  ControlClassroomOptions,
  StreamReexplanationOptions,
} from "../src/api/classroom";

const snapshot: ClassroomSnapshot = {
  learning_unit_id: "unit-1", revision: 1, message_cursor: 0,
  scene_key: "intro", scene_version: 1, scene_progress: 0,
  mode: "focus", enabled_roles: [], paused: false,
};
const scenes = [
  { id: "scene-new", sceneKey: "intro", version: 1, isCurrent: true },
  { id: "scene-old", sceneKey: "intro", version: 0, isCurrent: false },
];
const stubs = {
  NButton: {
    props: ["disabled"], emits: ["click"],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  NTag: { template: "<span><slot /></span>" },
};

function makeProps(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    unitId: "unit-1", csrfToken: "csrf", scenes, selectedSceneId: "scene-new",
    loadSnapshot: vi.fn().mockResolvedValue(snapshot),
    create: vi.fn().mockResolvedValue(snapshot),
    control: vi.fn().mockResolvedValue({ ...snapshot, revision: 2, paused: true }),
    loadOperation: vi.fn(),
    stream: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function mountPanel(props = makeProps()) {
  return mount(LearningControlsPanel, { props, global: { stubs } });
}

describe("LearningControlsPanel", () => {
  beforeEach(() => sessionStorage.clear());

  it("shows versions and disables reexplanation while viewing history", async () => {
    const wrapper = mountPanel(makeProps({ selectedSceneId: "scene-old" }));
    await flushPromises();
    const versionButtons = wrapper.findAll('[aria-label="场景版本"] button');
    expect(versionButtons.map((button) => button.text())).toEqual([
      "intro · 版本 1 · 当前", "intro · 版本 0 · 旧版只读",
    ]);
    await versionButtons[0].trigger("click");
    expect(wrapper.emitted("select-scene")?.[0]).toEqual(["scene-new"]);
    expect(wrapper.findAll('[aria-label="重解释当前场景"] button').every((button) => button.attributes("disabled") !== undefined)).toBe(true);
  });

  it("persists a pause request and reuses its key after an uncertain response", async () => {
    const control = vi.fn()
      .mockRejectedValueOnce(new Error("connection lost"))
      .mockResolvedValueOnce({ ...snapshot, revision: 2, paused: true });
    const wrapper = mountPanel(makeProps({ control }));
    await flushPromises();
    await wrapper.get(".control-actions button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("connection lost");
    const first = control.mock.calls[0][0] as ControlClassroomOptions;
    expect(sessionStorage.getItem("edumind:control:unit-1:pending")).toContain(first.idempotencyKey);
    await wrapper.findAll("button").find((button) => button.text() === "恢复原控制请求")?.trigger("click");
    await flushPromises();
    expect((control.mock.calls[1][0] as ControlClassroomOptions).idempotencyKey).toBe(first.idempotencyKey);
    expect(sessionStorage.getItem("edumind:control:unit-1:pending")).toBeNull();
    expect(wrapper.text()).toContain("已暂停");
  });

  it("moves to the server-selected scene after skip without inventing mastery", async () => {
    const control = vi.fn().mockResolvedValue({
      ...snapshot, revision: 2, scene_key: "next", scene_version: 1, scene_progress: 1,
    });
    const wrapper = mountPanel(makeProps({ control }));
    await flushPromises();
    await wrapper.findAll(".control-actions button")[1].trigger("click");
    await flushPromises();
    expect(control).toHaveBeenCalledWith(expect.objectContaining({ action: "skip", revision: 1 }));
    expect(wrapper.emitted("scene-changed")?.[0]).toEqual(["scene-new", "next", 1]);
    expect(wrapper.text()).toContain("已跳过当前场景");
  });

  it("shows temporary explanation only until the reviewed scene is published", async () => {
    const stream = vi.fn(async (options: StreamReexplanationOptions) => {
      options.onEvent({ type: "agent_start", data: { operation_id: "op-1" } });
      options.onEvent({ type: "token", data: { temporary: true, delta: "<script>alert(1)</script>" } });
      options.onEvent({ type: "scene_ready", data: { scene_key: "intro", scene_version: 2 } });
    });
    const wrapper = mountPanel(makeProps({
      stream, loadSnapshot: vi.fn().mockResolvedValueOnce(snapshot)
        .mockResolvedValueOnce(snapshot).mockResolvedValue({ ...snapshot, revision: 2, scene_version: 2 }),
    }));
    await flushPromises();
    await wrapper.findAll('[aria-label="重解释当前场景"] button')[0].trigger("click");
    await flushPromises();
    expect(stream).toHaveBeenCalledWith(expect.objectContaining({
      action: "simpler", baseSceneVersion: 1, revision: 1,
    }));
    expect(wrapper.find("script").exists()).toBe(false);
    expect(wrapper.find('[aria-label="临时讲解"]').exists()).toBe(false);
    expect(wrapper.emitted("scene-changed")?.[0]).toEqual(["scene-new", "intro", 2]);
  });

  it("retracts rejected temporary output and keeps the current version available", async () => {
    const stream = vi.fn(async (options: StreamReexplanationOptions) => {
      options.onEvent({ type: "token", data: { temporary: true, delta: "未审核候选" } });
      options.onEvent({ type: "content_retracted", data: { code: "REVIEW_REJECTED" } });
      options.onEvent({ type: "error", data: { code: "REVIEW_REJECTED" } });
    });
    const wrapper = mountPanel(makeProps({ stream }));
    await flushPromises();
    await wrapper.findAll('[aria-label="重解释当前场景"] button')[1].trigger("click");
    await flushPromises();
    expect(wrapper.find('[aria-label="临时讲解"]').exists()).toBe(false);
    expect(wrapper.emitted("scene-changed")).toBeUndefined();
    expect(wrapper.text()).toContain("版本 1 · 当前");
    expect(wrapper.text()).toContain("请求状态尚未确认");
  });
});
