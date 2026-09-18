import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PublishedLearningWorkspace from "../src/components/PublishedLearningWorkspace.vue";

const resources = [
  { type: "explanation" as const, content: { markdown: "先保存 next 指针。" } },
  { type: "code" as const, content: { source: "node->next = head;" } },
  { type: "exercise" as const, content: { items: [
    { id: "q1", question: "插入前先保存什么？", answer: "next", explanation: "先保存 next。" },
    { id: "q2", question: "第二题？", answer: "x", explanation: "解释。" },
    { id: "q3", question: "第三题？", answer: "y", explanation: "解释。" },
  ] } },
];
const stubs = { NButton: { emits: ["click"], template: "<button @click=\"$emit('click')\"><slot /></button>" } };

describe("PublishedLearningWorkspace", () => {
  it("switches among reviewed explanation, code, and three exercises", async () => {
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources }, global: { stubs } });
    expect(wrapper.get('[data-testid="explanation-tab"]').text()).toContain("保存 next");
    await wrapper.get("button:nth-child(2)").trigger("click");
    expect(wrapper.get('[data-testid="code-tab"]').text()).toContain("node->next");
    await wrapper.get("button:nth-child(3)").trigger("click");
    expect(wrapper.get('[data-testid="exercise-tab"]').findAll("article")).toHaveLength(3);
    expect(wrapper.text()).toContain("不会更新掌握度或学习路径");
  });

  it("gives local feedback for an answer without persisting it", async () => {
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources }, global: { stubs } });
    await wrapper.get("button:nth-child(3)").trigger("click");
    await wrapper.get("input").setValue("wrong");
    await wrapper.get("article button").trigger("click");
    expect(wrapper.text()).toContain("还不对");
    await wrapper.get("input").setValue("next");
    await wrapper.get("article button").trigger("click");
    expect(wrapper.text()).toContain("回答正确");
  });

  it("renders model markdown, links, and code as inert text", async () => {
    const hostileResources = [
      { type: "explanation" as const, content: { markdown: '<img src=x onerror="window.pwned=1"><a href="javascript:alert(1)">链接</a>' } },
      { type: "code" as const, content: { source: '</code><script>window.pwned=1</script>' } },
      { type: "exercise" as const, content: { items: [{ id: "q1", question: '<a href="javascript:alert(1)">题目</a>', answer: "a", explanation: "正常解释" }] } },
    ];
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources: hostileResources }, global: { stubs } });

    expect(wrapper.find("script").exists()).toBe(false);
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find("a").exists()).toBe(false);
    expect(wrapper.get('[data-testid="explanation-tab"] p').attributes("onerror")).toBeUndefined();
    expect(wrapper.text()).toContain("javascript:alert(1)");
    await wrapper.get("button:nth-child(2)").trigger("click");
    expect(wrapper.get("code").text()).toContain("<script>window.pwned=1</script>");
    await wrapper.get("button:nth-child(3)").trigger("click");
    expect(wrapper.get("label").text()).toContain("javascript:alert(1)");
  });
});
