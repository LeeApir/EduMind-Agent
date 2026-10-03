import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DebatePanel from "../src/components/DebatePanel.vue";
import {
  ClassroomSpeechError, type ClassroomSnapshot, type DebateResult,
  type StreamDebateOptions,
} from "../src/api/classroom";

const classroom: ClassroomSnapshot = {
  learning_unit_id: "unit-1", revision: 1, message_cursor: 4,
  scene_key: "intro", scene_version: 1, scene_progress: 3,
  mode: "interactive", enabled_roles: ["beginner"], paused: false,
};
const debateSnapshot: ClassroomSnapshot = {
  ...classroom, revision: 2, scene_key: "array-vs-linked-list", scene_progress: 0,
  mode: "focus", enabled_roles: [], paused: true,
  detour: { kind: "debate", result_id: "result-1", scene_key: "intro",
    scene_version: 1, scene_progress: 3, mode: "interactive", enabled_roles: ["beginner"], paused: false },
};
const result: DebateResult = {
  id: "result-1", scene_key: "array-vs-linked-list", scene_version: 1,
  status: "published", question: "频繁随机访问时怎么选？",
  question_conditions: { stated: ["频繁随机访问"], unknown: ["插入频率"] },
  perspectives: { performance: "数组下标访问更快", engineering: "考虑维护成本",
    academic: "需说明操作模型" },
  moderator: { objective_conclusion: "给定条件下优先数组", tradeoffs: "插入时需搬移",
    learner_advice: "用操作表对比" },
  moderator_summary: "给定条件下优先数组。插入时需搬移。用操作表对比。",
  candidate_schema_version: "v1", candidate_prompt_version: "v1",
  generation_model_id: "mock-generation", review_version: "v1",
  review_model_id: "mock-review", correction_attempts: 0,
};
const stubs = {
  NButton: {
    props: ["disabled", "loading"], emits: ["click"],
    template: "<button :disabled=\"disabled\" @click=\"$emit('click')\"><slot /></button>",
  },
};
function makeProps(overrides: Record<string, unknown> = {}) {
  return {
    unitId: "unit-1", csrfToken: "csrf",
    loadSnapshot: vi.fn().mockResolvedValue(classroom),
    create: vi.fn().mockResolvedValue(classroom),
    loadOperation: vi.fn(),
    loadResult: vi.fn().mockResolvedValue(result),
    start: vi.fn().mockResolvedValue(undefined),
    exit: vi.fn().mockResolvedValue(classroom),
    feedback: vi.fn().mockResolvedValue({ evidence_id: "evidence-1",
      profile_version: 2, update_status: "updated" }),
    ...overrides,
  };
}
function mountPanel(props = makeProps()) {
  return mount(DebatePanel, { props, global: { stubs } });
}

describe("DebatePanel", () => {
  beforeEach(() => sessionStorage.clear());

  it("enters only after a published result, then restores the classroom on exit", async () => {
    let current = classroom;
    const loadSnapshot = vi.fn(async () => current);
    const start = vi.fn(async (options: StreamDebateOptions) => {
      options.onEvent({ type: "agent_start", data: { operation_id: "op-1" } });
      options.onEvent({ type: "stage_changed", data: { stage: "reviewing" } });
      current = debateSnapshot;
      options.onEvent({ type: "debate_ready", data: { result_id: "result-1" } });
    });
    const exit = vi.fn().mockResolvedValue({ ...classroom, revision: 3 });
    const wrapper = mountPanel(makeProps({ loadSnapshot, start, exit }));
    await flushPromises();
    await wrapper.get('[data-testid="debate-question"]').setValue("频繁随机访问时怎么选？");
    await wrapper.get('[data-testid="start-debate"]').trigger("click");
    await flushPromises();
    expect(start).toHaveBeenCalledWith(expect.objectContaining({
      question: "频繁随机访问时怎么选？", revision: 1,
    }));
    expect(wrapper.get('[data-testid="debate-perspectives"]').text()).toContain("性能视角");
    expect(wrapper.get('[data-testid="debate-moderator"]').text()).toContain("给定条件下优先数组");
    expect(wrapper.emitted("active")?.at(-1)).toEqual([true]);
    await wrapper.get('[data-testid="exit-debate"]').trigger("click");
    await flushPromises();
    expect(exit).toHaveBeenCalledWith("unit-1", "result-1", 2, "csrf", expect.any(String));
    expect(wrapper.emitted("active")?.at(-1)).toEqual([false]);
    expect(wrapper.get('[data-testid="start-debate"]').exists()).toBe(true);
  });

  it("uses the current classroom revision after mode and speech changed it", async () => {
    const loadSnapshot = vi.fn()
      .mockResolvedValueOnce(classroom)
      .mockResolvedValueOnce({ ...classroom, revision: 5, message_cursor: 8 });
    const start = vi.fn().mockRejectedValue(new ClassroomSpeechError({
      message: "review unavailable", code: "REVIEW_UNAVAILABLE", retryable: true,
    }));
    const wrapper = mountPanel(makeProps({ loadSnapshot, start }));
    await flushPromises();
    await wrapper.get('[data-testid="debate-question"]').setValue("随机访问怎么选？");
    await wrapper.get('[data-testid="start-debate"]').trigger("click");
    await flushPromises();
    expect(start).toHaveBeenCalledWith(expect.objectContaining({ revision: 5 }));
    expect(wrapper.get('[data-testid="debate-error"]').text()).toContain("审核暂时不可用");
  });

  it("restores a published result after refresh without generating again and escapes model text", async () => {
    const malicious = { ...result, perspectives: { ...result.perspectives,
      performance: '<img src=x onerror="alert(1)">' } };
    const start = vi.fn();
    const wrapper = mountPanel(makeProps({
      loadSnapshot: vi.fn().mockResolvedValue(debateSnapshot),
      loadResult: vi.fn().mockResolvedValue(malicious), start,
    }));
    await flushPromises();
    expect(wrapper.get('[data-testid="debate-perspectives"]').text()).toContain("<img src=x");
    expect(wrapper.find('[data-testid="debate-perspectives"] img').exists()).toBe(false);
    expect(start).not.toHaveBeenCalled();
    expect(wrapper.emitted("active")?.at(-1)).toEqual([true]);
  });

  it("records a perspective only after a deliberate click and refreshes profile", async () => {
    const feedback = vi.fn().mockResolvedValue({ evidence_id: "evidence-1",
      profile_version: 2, update_status: "updated" });
    const wrapper = mountPanel(makeProps({
      loadSnapshot: vi.fn().mockResolvedValue(debateSnapshot), feedback,
    }));
    await flushPromises();
    expect(feedback).not.toHaveBeenCalled();
    await wrapper.findAll(".perspectives article")[1].find("button").trigger("click");
    await flushPromises();
    expect(feedback).toHaveBeenCalledWith("unit-1", "result-1", "engineering",
      "csrf", expect.any(String));
    expect(wrapper.get('[data-testid="perspective-feedback-status"]').text()).toContain("已记录");
    expect(wrapper.emitted("profileChanged")).toHaveLength(1);
  });

  it("keeps the original classroom visible after review rejection", async () => {
    const start = vi.fn(async (options: StreamDebateOptions) => {
      options.onEvent({ type: "agent_start", data: { operation_id: "op-2" } });
      throw new ClassroomSpeechError({ message: "rejected", code: "REVIEW_REJECTED",
        retryable: false, operationId: "op-2" });
    });
    const wrapper = mountPanel(makeProps({ start }));
    await flushPromises();
    await wrapper.get('[data-testid="debate-question"]').setValue("怎么选？");
    await wrapper.get('[data-testid="start-debate"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="debate-error"]').text()).toContain("未通过审核");
    expect(wrapper.find('[data-testid="debate-perspectives"]').exists()).toBe(false);
    expect(wrapper.emitted("active")?.at(-1)).toEqual([false]);
    expect(sessionStorage.getItem("edumind:debate:unit-1:pending")).toBeNull();
  });

  it("shows Provider failure without exposing a partial perspective", async () => {
    const start = vi.fn(async (options: StreamDebateOptions) => {
      options.onEvent({ type: "agent_start", data: { operation_id: "op-provider" } });
      throw new ClassroomSpeechError({ message: "temporarily unavailable",
        code: "PROVIDER_UNAVAILABLE", retryable: true, operationId: "op-provider" });
    });
    const wrapper = mountPanel(makeProps({ start }));
    await flushPromises();
    await wrapper.get('[data-testid="debate-question"]').setValue("怎么选？");
    await wrapper.get('[data-testid="start-debate"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="debate-error"]').text()).toContain("生成服务暂时不可用");
    expect(wrapper.find('[data-testid="debate-perspectives"]').exists()).toBe(false);
    expect(wrapper.emitted("active")?.at(-1)).toEqual([false]);
  });

  it("checks a persisted operation after reload and shows only its published result", async () => {
    sessionStorage.setItem("edumind:debate:unit-1:pending", JSON.stringify({
      key: "debate-request-key-1", question: "怎么选？", revision: 1, operationId: "op-3",
    }));
    let current = classroom;
    const loadSnapshot = vi.fn(async () => current);
    const loadOperation = vi.fn(async () => {
      current = debateSnapshot;
      return { id: "op-3", status: "published", kind: "debate",
        learning_unit_id: "unit-1", base_revision: 1 };
    });
    const start = vi.fn();
    const wrapper = mountPanel(makeProps({ loadSnapshot, loadOperation, start }));
    await flushPromises();
    expect(loadOperation).toHaveBeenCalledWith("op-3");
    expect(start).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="debate-perspectives"]').exists()).toBe(true);
    expect(sessionStorage.getItem("edumind:debate:unit-1:pending")).toBeNull();
  });
});
