import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import App from "../src/App.vue";

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
};

describe("learning entry", () => {
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
    expect(wrapper.get('[data-testid="loading-state"]').text()).toContain("想理解链表");
  });
});
