import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { watchHybridOperation, type HybridOperation } from "../src/api/hybridReview";
import { startLearningSession } from "../src/api/learningSessions";
import LearningProgressPanel from "../src/components/LearningProgressPanel.vue";

const pending: HybridOperation = { id: "operation-test", status: "awaiting_human" };
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe("hybrid review recovery", () => {
  it("polls only GET state, stops at its bound, and does not restart generation", async () => {
    vi.useFakeTimers();
    const read = vi.fn().mockResolvedValue(pending);
    const update = vi.fn();
    const stop = watchHybridOperation({ id: pending.id, read, onUpdate: update, onError: vi.fn(), intervalMs: 10, maxReads: 2 });
    await vi.advanceTimersByTimeAsync(100);
    expect(read).toHaveBeenCalledTimes(2);
    expect(update).toHaveBeenCalledTimes(2);
    stop();
    await vi.advanceTimersByTimeAsync(100);
    expect(read).toHaveBeenCalledTimes(2);
  });
  it("pauses while hidden, resumes when visible and stops after terminal approval", async () => {
    vi.useFakeTimers();
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const read = vi.fn().mockResolvedValue({ ...pending, status: "completed", publication_version: 2 });
    const update = vi.fn();
    const stop = watchHybridOperation({ id: pending.id, read, onUpdate: update, onError: vi.fn(), intervalMs: 10 });
    await vi.advanceTimersByTimeAsync(50);
    expect(read).not.toHaveBeenCalled();
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(100);
    expect(read).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ status: "completed" }));
    stop();
  });
  it("does not apply a late response after leaving the page", async () => {
    let resolve!: (value: HybridOperation) => void;
    const read = vi.fn().mockImplementation(() => new Promise<HybridOperation>((r) => { resolve = r; }));
    const update = vi.fn();
    const stop = watchHybridOperation({ id: pending.id, read, onUpdate: update, onError: vi.fn() });
    stop(); resolve(pending); await Promise.resolve();
    expect(update).not.toHaveBeenCalled();
  });
  it("labels human wait without publishing or promising processing time", () => {
    const wrapper = mount(LearningProgressPanel, { props: { temporaryText: "", reviewState: "awaiting_human" } });
    expect(wrapper.text()).toContain("内容待人工复核，暂不可作为正式课程使用");
    expect(wrapper.text()).toContain("处理时间尚未确定");
    expect(wrapper.find('[data-testid="published-state"]').exists()).toBe(false);
    wrapper.unmount();
  });
  it("sends the new protocol and accepts review_required plus ended waiting stream", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(
      'event: review_required\ndata: {"operation_id":"operation-test"}\n\nevent: done\ndata: {"status":"awaiting_human"}\n\n',
    ));
    const onEvent = vi.fn();
    await startLearningSession({ goal: "学习栈", csrfToken: "test", onEvent, fetchImpl });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body).generation_protocol).toBe("shared-plan-v1");
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "review_required" }));
  });
});
