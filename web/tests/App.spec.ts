import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import App from "../src/App.vue";

describe("learning entry", () => {
  it("shows the one-sentence learning entry", () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          NButton: { template: "<button><slot /></button>" },
          NInput: { template: "<textarea />" },
          NTag: { template: "<span><slot /></span>" },
        },
      },
    });

    expect(wrapper.get("h1").text()).toContain("你现在想弄懂什么？");
    expect(wrapper.get("label").text()).toBe("学习目标");
    expect(wrapper.text()).toContain("不需要先填写画像");
  });
});
