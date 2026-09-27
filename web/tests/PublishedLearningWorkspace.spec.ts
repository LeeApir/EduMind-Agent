import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { QuizSubmissionResult } from "../src/api/quiz";
import PublishedLearningWorkspace from "../src/components/PublishedLearningWorkspace.vue";

const resources = [
  { id: "explanation-001", version: 1, type: "explanation" as const, content: { markdown: "先保存 next 指针。" } },
  { id: "code-resource-001", version: 1, type: "code" as const, content: { source: "node->next = head;" } },
  { id: "exercise-resource-001", version: 1, type: "exercise" as const, content: { items: [
    { id: "q1", question: "插入前先保存什么？" },
    { id: "q2", question: "第二题？" },
    { id: "q3", question: "第三题？" },
  ] } },
];
const receipt: QuizSubmissionResult = {
  evidence_id: "evidence-001", resource_id: "exercise-resource-001", resource_version: 1,
  question_results: [
    { question_id: "q1", correct: false, explanation: "先保存后继连接。", error_patterns: ["answer_mismatch"] },
    { question_id: "q2", correct: true, explanation: "正确解释。", error_patterns: [] },
    { question_id: "q3", correct: false, explanation: "这题已跳过。", error_patterns: ["skipped"] },
  ],
  score: 1 / 3, correct_count: 1, question_count: 3, quiz_schema_version: 1,
  scoring_rule_version: "quiz-exact-text-v1", profile_update_status: "no_change",
  mastery_changes: [{ knowledge_node_id: "c-pointer", previous_score: 0.2, score: 0.3, status: "weak", revision: 2, rule_version: "mastery-v1" }],
  path_replan_required: true,
};
const stubs = { NButton: { props: ["disabled", "attrType", "loading"], emits: ["click"], template: "<button :type=\"attrType || 'button'\" :disabled=\"disabled\" @click=\"$emit('click')\"><slot /></button>" } };
const loadQuizResult = () => Promise.resolve(null);

describe("PublishedLearningWorkspace", () => {
  it("preserves objective options and submits a single answer token without prose", async () => {
    const question = "[单选题] 指针保存什么？\nA. 地址\nB. 值\nC. 类型\nD. 长度\n仅填 A、B、C 或 D";
    const objectiveResources = resources.map((resource) => resource.type === "exercise"
      ? { ...resource, content: { items: [{ id: "q1", question }] } } : resource);
    const submitQuiz = vi.fn().mockRejectedValue(new Error("test pending"));
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources: objectiveResources, csrfToken: "csrf", loadQuizResult, submitQuiz }, global: { stubs } });
    await flushPromises();
    await wrapper.get("button:nth-child(3)").trigger("click");
    expect(wrapper.get("label").element.textContent).toBe(question);
    await wrapper.get("input").setValue("A");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(submitQuiz).toHaveBeenCalledWith(expect.objectContaining({ answers: [{ question_id: "q1", answer: "A" }] }));
  });
  it("switches among reviewed explanation, code, and three exercises", async () => {
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources, loadQuizResult }, global: { stubs } });
    expect(wrapper.get('[data-testid="explanation-tab"]').text()).toContain("保存 next");
    await wrapper.get("button:nth-child(2)").trigger("click");
    expect(wrapper.get('[data-testid="code-tab"]').text()).toContain("node->next");
    await wrapper.get("button:nth-child(3)").trigger("click");
    expect(wrapper.get('[data-testid="exercise-tab"]').findAll("article")).toHaveLength(3);
    expect(wrapper.text()).toContain("服务端评分并记录学习证据");
  });

  it("submits the exact resource version and renders only server feedback", async () => {
    const submitQuiz = vi.fn().mockResolvedValue(receipt);
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources, csrfToken: "csrf", loadQuizResult, submitQuiz }, global: { stubs } });
    await flushPromises();
    await wrapper.get("button:nth-child(3)").trigger("click");
    await wrapper.get("input").setValue("next");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(submitQuiz).toHaveBeenCalledWith(expect.objectContaining({ resourceId: "exercise-resource-001", resourceVersion: 1, csrfToken: "csrf", answers: [{ question_id: "q1", answer: "next" }, { question_id: "q2", answer: "" }, { question_id: "q3", answer: "" }] }));
    expect(wrapper.text()).toContain("这题需要再想一想");
    expect(wrapper.text()).toContain("20% → 30%");
    expect(wrapper.text()).toContain("需要巩固");
    expect(wrapper.emitted("quiz-submitted")?.[0]).toEqual([receipt]);
  });

  it("retries a failed submission with the same key and changes it for edited answers", async () => {
    const submitQuiz = vi.fn().mockRejectedValueOnce(new Error("连接中断")).mockRejectedValueOnce(new Error("连接中断")).mockResolvedValue(receipt);
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources, csrfToken: "csrf", loadQuizResult, submitQuiz }, global: { stubs } });
    await flushPromises();
    await wrapper.get("button:nth-child(3)").trigger("click");
    await wrapper.get("input").setValue("answer");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.text()).not.toContain("本次掌握度变化");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(submitQuiz.mock.calls[1][0].idempotencyKey).toBe(submitQuiz.mock.calls[0][0].idempotencyKey);
    await wrapper.get("input").setValue("changed answer");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(submitQuiz.mock.calls[2][0].idempotencyKey).not.toBe(submitQuiz.mock.calls[0][0].idempotencyKey);
  });

  it("restores the latest server receipt on remount without synthesizing mastery", async () => {
    const restore = vi.fn().mockResolvedValue(receipt);
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources, loadQuizResult: restore }, global: { stubs } });
    await flushPromises();
    await wrapper.get("button:nth-child(3)").trigger("click");
    expect(restore).toHaveBeenCalledWith({ resourceId: "exercise-resource-001", resourceVersion: 1 });
    expect(wrapper.text()).toContain("最近一次提交");
    expect(wrapper.text()).toContain("20% → 30%");
    expect(wrapper.find("input").exists()).toBe(false);
    expect(wrapper.emitted("quiz-submitted")).toBeUndefined();
  });

  it("offers a recovery action when the saved result cannot be read", async () => {
    const restore = vi.fn().mockRejectedValueOnce(new Error("结果暂时无法读取")).mockResolvedValue(null);
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources, loadQuizResult: restore }, global: { stubs } });
    await flushPromises();
    await wrapper.get("button:nth-child(3)").trigger("click");
    expect(wrapper.text()).toContain("结果暂时无法读取");
    await wrapper.get('[role="alert"] button').trigger("click"); await flushPromises();
    expect(restore).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("blocks duplicate loading submits and ignores receipts after resource changes", async () => {
    let resolveReceipt!: (value: QuizSubmissionResult) => void;
    const submitQuiz = vi.fn(() => new Promise<QuizSubmissionResult>((resolve) => { resolveReceipt = resolve; }));
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources, csrfToken: "csrf", loadQuizResult, submitQuiz }, global: { stubs } });
    await flushPromises();
    await wrapper.get("button:nth-child(3)").trigger("click");
    await wrapper.get("input").setValue("answer");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("input").attributes("disabled")).toBeDefined();
    await wrapper.get("form").trigger("submit");
    expect(submitQuiz).toHaveBeenCalledTimes(1);
    await wrapper.setProps({ resources: resources.map((resource) => resource.type === "exercise" ? { ...resource, id: "new-exercise-001" } : resource) });
    await flushPromises();
    resolveReceipt(receipt);
    await flushPromises();
    expect(wrapper.text()).not.toContain("本次掌握度变化");
    expect(wrapper.emitted("quiz-submitted")).toBeUndefined();
  });

  it("renders model markdown, links, and code as inert text", async () => {
    const hostileResources = [
      { id: "explanation-001", version: 1, type: "explanation" as const, content: { markdown: '<img src=x onerror="window.pwned=1"><a href="javascript:alert(1)">链接</a>' } },
      { id: "code-resource-001", version: 1, type: "code" as const, content: { source: '</code><script>window.pwned=1</script>' } },
      { id: "exercise-resource-001", version: 1, type: "exercise" as const, content: { items: [{ id: "q1", question: '<a href="javascript:alert(1)">题目</a>' }] } },
    ];
    const wrapper = mount(PublishedLearningWorkspace, { props: { resources: hostileResources, loadQuizResult }, global: { stubs } });

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
