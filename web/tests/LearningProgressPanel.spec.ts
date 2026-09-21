import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import LearningProgressPanel from "../src/components/LearningProgressPanel.vue";

const stubs = {
  NButton: { emits: ["click"], template: "<button @click=\"$emit('click')\"><slot /></button>" },
  NTag: { template: "<span><slot /></span>" },
};

describe("LearningProgressPanel", () => {
  it("marks streamed first text as temporary while review is ongoing", () => {
    const wrapper = mount(LearningProgressPanel, {
      props: { temporaryText: "先保存 next 指针。", reviewState: "reviewing" },
      global: { stubs },
    });
    expect(wrapper.get('[data-testid="temporary-explanation"]').text()).toContain("尚未审核");
    expect(wrapper.get('[data-testid="reviewing-state"]').text()).toContain("正在审核");
  });

  it("shows an understandable empty and review-rejected state", () => {
    const wrapper = mount(LearningProgressPanel, {
      props: { temporaryText: "", reviewState: "rejected" }, global: { stubs },
    });
    expect(wrapper.get('[data-testid="empty-state"]').text()).toContain("首段讲解会显示在这里");
    expect(wrapper.get('[data-testid="review-rejected-state"]').text()).toContain("不会被保存");
  });

  it("renders published resources and retries a failed reload", async () => {
    const reloadPublished = vi.fn<() => Promise<void>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(undefined);
    const wrapper = mount(LearningProgressPanel, {
      props: { temporaryText: "临时文本", reviewState: "published", reloadPublished, publishedResources: [{ id: "r1", type: "explanation", version: 1 }] },
      global: { stubs },
    });
    expect(wrapper.get('[data-testid="published-state"]').text()).toContain("已审核正式资源");
    await wrapper.get("button").trigger("click");
    expect(wrapper.text()).toContain("无法重新加载");
    await wrapper.get("button").trigger("click");
    expect(reloadPublished).toHaveBeenCalledTimes(2);
  });
});
