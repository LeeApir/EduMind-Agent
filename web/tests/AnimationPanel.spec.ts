import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AnimationPanel from "../src/components/AnimationPanel.vue";
import {
  cancelAnimationJob, loadAnimationJob, requestAnimation, retryAnimationJob,
  type AnimationJob,
} from "../src/api/animationJobs";

vi.mock("../src/api/animationJobs", async () => {
  const actual = await vi.importActual<typeof import("../src/api/animationJobs")>("../src/api/animationJobs");
  return {
    ...actual,
    requestAnimation: vi.fn(), loadAnimationJob: vi.fn(),
    cancelAnimationJob: vi.fn(), retryAnimationJob: vi.fn(),
  };
});

const queued: AnimationJob = {
  id: "job-1", learning_unit_id: "unit-1", template_id: "linked-list-insertion",
  status: "queued", attempt: 0, progress: 0, last_event_id: 1,
};
const stubs = {
  NButton: {
    props: ["disabled"], emits: ["click"],
    template: "<button :disabled=\"disabled\" @click=\"$emit('click')\"><slot /></button>",
  },
  NTag: { template: "<span><slot /></span>" },
};

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  onerror: (() => void) | null = null;
  closed = false;
  constructor(readonly url: string, readonly options: EventSourceInit) { FakeEventSource.instances.push(this); }
  addEventListener(type: string, callback: EventListenerOrEventListenerObject): void {
    const handler = callback as (event: MessageEvent) => void;
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), handler]);
  }
  emit(type: string, id: number, data: Record<string, unknown>): void {
    for (const handler of this.listeners.get(type) ?? []) {
      handler({ lastEventId: String(id), data: JSON.stringify(data) } as MessageEvent);
    }
  }
  close(): void { this.closed = true; }
}

function mountPanel(unitId = "unit-1", nodeId = "linked-list-insertion") {
  return mount(AnimationPanel, {
    props: { unitId, nodeId, sceneVersion: 1, csrfToken: "csrf" },
    global: { stubs },
  });
}

describe("on-demand animation panel", () => {
  beforeEach(() => {
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.mocked(requestAnimation).mockReset();
    vi.mocked(loadAnimationJob).mockReset();
    vi.mocked(cancelAnimationJob).mockReset();
    vi.mocked(retryAnimationJob).mockReset();
  });
  afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });

  it("waits for a click, then shows queue, progress, cancellation and explicit retry", async () => {
    vi.mocked(requestAnimation).mockResolvedValue(queued);
    vi.mocked(cancelAnimationJob).mockResolvedValue({ ...queued, status: "cancelled", last_event_id: 2 });
    vi.mocked(retryAnimationJob).mockResolvedValue({
      ...queued, id: "job-2", retry_of: "job-1", last_event_id: 1,
    });
    const wrapper = mountPanel();
    await flushPromises();
    expect(requestAnimation).not.toHaveBeenCalled();
    expect(loadAnimationJob).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("在 [1, 3, 5] 的第 1 位插入 4");
    await wrapper.get('[data-testid="request-animation"]').trigger("click");
    await flushPromises();
    expect(requestAnimation).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("排队中");
    const first = FakeEventSource.instances[0];
    expect(first.url).toBe("/api/animation-jobs/job-1/events?after=1");
    expect(first.options.withCredentials).toBe(true);
    first.emit("running", 2, { job_id: "job-1", progress: 0.2, attempt: 1 });
    await flushPromises();
    expect(wrapper.text()).toContain("20%");
    await wrapper.get('[data-testid="cancel-animation"]').trigger("click");
    await flushPromises();
    expect(cancelAnimationJob).toHaveBeenCalledTimes(1);
    expect(first.closed).toBe(true);
    expect(wrapper.text()).toContain("已取消");
    await wrapper.get('[data-testid="retry-animation"]').trigger("click");
    await flushPromises();
    expect(retryAnimationJob).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("排队中");
    expect(JSON.parse(sessionStorage.getItem("edumind:animation:unit-1") ?? "{}").jobId).toBe("job-2");
    wrapper.unmount();
  });

  it("restores a snapshot without POST, ignores duplicates and late events after node change", async () => {
    sessionStorage.setItem("edumind:animation:unit-1", JSON.stringify({
      requestKey: "original-key",
      request: { template_id: "linked-list-insertion", template_version: "1.0.0", scene_version: 1,
        parameters: { values: [1, 3, 5], index: 1, value: 4 } },
      jobId: "job-1",
    }));
    vi.mocked(loadAnimationJob).mockResolvedValue({ ...queued, status: "running", attempt: 1,
      progress: 0.3, last_event_id: 3 });
    const wrapper = mountPanel();
    await flushPromises();
    expect(requestAnimation).not.toHaveBeenCalled();
    expect(loadAnimationJob).toHaveBeenCalledWith("job-1");
    const old = FakeEventSource.instances[0];
    expect(old.url).toContain("after=3");
    old.emit("progress", 3, { job_id: "job-1", progress: 0.8 });
    await flushPromises();
    expect(wrapper.text()).toContain("30%");
    old.emit("progress", 4, { job_id: "job-1", progress: 0.8 });
    await flushPromises();
    expect(wrapper.text()).toContain("80%");
    old.onerror?.();
    await flushPromises();
    expect(loadAnimationJob).toHaveBeenCalledTimes(2);
    expect(requestAnimation).not.toHaveBeenCalled();
    await wrapper.setProps({ unitId: "unit-2", nodeId: "linked-list-deletion" });
    expect(old.closed).toBe(true);
    old.emit("succeeded", 5, { job_id: "job-1", media_id: "old-media" });
    await flushPromises();
    expect(wrapper.text()).toContain("删除 [1, 3, 5]");
    expect(wrapper.find('[data-testid="animation-video"]').exists()).toBe(false);
    expect(requestAnimation).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("isolates downloads when two selected scenes share a node and version", async () => {
    sessionStorage.setItem("edumind:animation:unit-1:scene-a", JSON.stringify({
      sceneId: "scene-a", requestKey: "old-key", jobId: "job-a",
      request: { template_id: "linked-list-insertion", template_version: "1.0.0", scene_version: 1,
        parameters: { values: [1, 3, 5], index: 1, value: 4 } },
    }));
    vi.mocked(loadAnimationJob).mockResolvedValue({ ...queued, id: "job-a", status: "succeeded", media_id: "media-a" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("subtitles")));
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:subtitle"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const wrapper = mount(AnimationPanel, {
      props: { unitId: "unit-1", nodeId: "linked-list-insertion", sceneVersion: 1,
        sceneId: "scene-a", sceneKey: "intro", csrfToken: "csrf" }, global: { stubs },
    });
    await flushPromises();
    expect(wrapper.get("video source").attributes("src")).toContain("media-a");
    await wrapper.setProps({ sceneId: "scene-b" });
    await flushPromises();
    expect(wrapper.find('[data-testid="download-mp4"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="request-animation"]').exists()).toBe(true);
    expect(loadAnimationJob).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("uses the MP4 endpoint and converts authenticated SRT to a VTT track", async () => {
    const completed = { ...queued, status: "succeeded" as const, media_id: "media-1", progress: 1 };
    vi.mocked(requestAnimation).mockResolvedValue(completed);
    const fetchImpl = vi.fn(async () => new Response("1\n00:00:00,000 --> 00:00:01,000\n你好\n"));
    vi.stubGlobal("fetch", fetchImpl);
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:subtitle"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="request-animation"]').trigger("click");
    await flushPromises();
    expect(wrapper.get("video source").attributes("src")).toBe("/api/animation-media/media-1/mp4");
    expect(wrapper.get("video track").attributes("src")).toBe("blob:subtitle");
    expect(fetchImpl).toHaveBeenCalledWith("/api/animation-media/media-1/srt", { credentials: "same-origin" });
    const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
    const caption = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(blob);
    });
    expect(caption).toContain("WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000");
    wrapper.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:subtitle");
  });

  it("downloads the reviewed MP4/SRT pair by media ID and retries a missing file without a new Job", async () => {
    const completed = { ...queued, status: "succeeded" as const, media_id: "media-1", progress: 1 };
    vi.mocked(requestAnimation).mockResolvedValue(completed);
    const requests: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.endsWith("/mp4?download=true") && requests.filter((item) => item === url).length === 1) {
        return new Response("unavailable", { status: 503 });
      }
      return new Response(url.endsWith("/mp4?download=true") ? "mp4-bytes" : "srt-bytes", {
        headers: { "Content-Disposition": `attachment; filename="animation-media-1.${url.includes("/mp4") ? "mp4" : "srt"}"` },
      });
    });
    vi.stubGlobal("fetch", fetchImpl);
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:media"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="request-animation"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="download-mp4"]').text()).toContain("MP4");
    await wrapper.get('[data-testid="download-mp4"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("文件缺失");
    await wrapper.get('[data-testid="download-mp4"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="download-srt"]').trigger("click");
    await flushPromises();
    expect(requests).toContain("/api/animation-media/media-1/mp4?download=true");
    expect(requests).toContain("/api/animation-media/media-1/srt?download=true");
    expect(click).toHaveBeenCalledTimes(2);
    expect(requestAnimation).toHaveBeenCalledTimes(1);
    expect(retryAnimationJob).not.toHaveBeenCalled();
    wrapper.unmount();
    click.mockRestore();
  });

  it("offers an explicit new animation request only after verified media is unavailable", async () => {
    const completed = { ...queued, status: "succeeded" as const, media_id: "media-1", progress: 1 };
    vi.mocked(requestAnimation).mockResolvedValueOnce(completed).mockResolvedValueOnce({ ...queued, id: "job-2" });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
      new Response("unavailable", { status: String(input).includes("?download=true") ? 503 : 200 })));
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:subtitle"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="request-animation"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="download-mp4"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="request-missing-animation"]').text()).toContain("重新请求动画");
    await wrapper.get('[data-testid="request-missing-animation"]').trigger("click");
    await flushPromises();
    expect(requestAnimation).toHaveBeenCalledTimes(2);
    expect(vi.mocked(requestAnimation).mock.calls[0][3]).not.toBe(vi.mocked(requestAnimation).mock.calls[1][3]);
    expect(wrapper.text()).toContain("排队中");
    wrapper.unmount();
  });

  it("keeps a clicked request key for recovery after a lost response", async () => {
    vi.mocked(requestAnimation).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(queued);
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="request-animation"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("相同请求键恢复");
    const firstKey = vi.mocked(requestAnimation).mock.calls[0][3];
    await wrapper.get('[data-testid="recover-animation-request"]').trigger("click");
    await flushPromises();
    expect(vi.mocked(requestAnimation).mock.calls[1][3]).toBe(firstKey);
    expect(wrapper.text()).toContain("排队中");
    wrapper.unmount();
  });

  it("recovers an existing Job after an offline page reload without creating another", async () => {
    sessionStorage.setItem("edumind:animation:unit-1", JSON.stringify({
      requestKey: "original-key",
      request: { template_id: "linked-list-insertion", template_version: "1.0.0", scene_version: 1,
        parameters: { values: [1, 3, 5], index: 1, value: 4 } },
      jobId: "job-1",
    }));
    vi.mocked(loadAnimationJob).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(queued);
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain("暂时无法读取动画状态");
    await wrapper.get('[data-testid="recover-animation-job"]').trigger("click");
    await flushPromises();
    expect(loadAnimationJob).toHaveBeenCalledTimes(2);
    expect(requestAnimation).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("排队中");
    wrapper.unmount();
  });
});
