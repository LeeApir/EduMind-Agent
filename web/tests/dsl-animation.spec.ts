import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AnimationPanel from "../src/components/AnimationPanel.vue";
import { generateAnimation, loadPreparation } from "../src/api/animationGeneration";
import { loadAnimationJob } from "../src/api/animationJobs";

const operation = "123e4567-e89b-42d3-a456-426614174000";
const scene = "123e4567-e89b-42d3-a456-426614174001";
const deadline = "2030-01-01T00:00:00Z";
const request = { scene_id: scene, scene_version: 1, goal_kind: "trace_insert" as const,
  parameters: {values: [1, 3, 5], index: 1, value: 4} };
const dslJob = {id: "dsl-job", learning_unit_id: "unit", template_id: null, render_kind: "dsl",
  candidate_id: "candidate", generation_id: operation, status: "queued", attempt: 0, progress: 0, last_event_id: 1};
const stubs = { NButton: {props: ["disabled"], emits: ["click"], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'},
  NTag: {template: '<span><slot /></span>'} };
class Source {
  static instances: Source[] = [];
  listeners = new Map<string, EventListener>(); onerror: (() => void) | null = null; closed = false;
  constructor(readonly url: string) { Source.instances.push(this); }
  addEventListener(type: string, handler: EventListener) { this.listeners.set(type, handler); }
  close() { this.closed = true; }
  emit(type: string, id: number, data: object) { this.listeners.get(type)?.({lastEventId: String(id), data: JSON.stringify(data)} as MessageEvent); }
}
function stream() {
  let writer!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({start(c) {writer = c;}});
  return {response: new Response(body, {headers: {"Content-Type": "text/event-stream"}}),
    send(type: string, data: object) {writer.enqueue(new TextEncoder().encode(`event: ${type}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`));},
    close() {writer.close();}};
}
function panel(dynamicEnabled = true) {
  return mount(AnimationPanel, {props: {unitId: "unit", nodeId: "linked-list-insertion", sceneId: scene,
    sceneVersion: 1, csrfToken: "csrf", dynamicEnabled}, global: {stubs}});
}
function saved(jobId?: string) {
  sessionStorage.setItem(`edumind:animation:unit:${scene}`, JSON.stringify({sceneId: scene, nodeId: "linked-list-insertion",
    requestKey: "original-request-key", operationId: operation, generatedRequest: request, jobId, source: "generated_dsl"}));
}
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  sessionStorage.clear(); Source.instances = [];
  vi.stubGlobal("EventSource", Source);
  vi.spyOn(crypto, "randomUUID").mockReturnValue(operation);
  fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("URL", {createObjectURL: vi.fn(() => "blob:subtitle"), revokeObjectURL: vi.fn()});
});
afterEach(() => {vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear();});

describe("DSL animation HTTP contract", () => {
  it("decodes fragmented POST SSE with CSRF, operation correlation and explicit fallback", async () => {
    const s = stream(); fetchMock.mockResolvedValue(s.response);
    const states = vi.fn();
    const promise = generateAnimation("unit", request, "csrf", "request-key", operation, true, new AbortController().signal, states);
    s.send("agent_start", {id: operation, stage: "reserved", deadline, secret: "must-not-survive"});
    s.send("stage_changed", {id: operation, stage: "generating"});
    s.send("stage_changed", {id: operation, stage: "reviewing"});
    s.send("done", {id: operation, stage: "handed_off", deadline, job_id: "dsl-job", source: "generated_dsl"}); s.close();
    await promise;
    expect(states.mock.calls.map(c => c[0].stage)).toEqual(["reserved", "generating", "reviewing", "handed_off"]);
    expect(states.mock.calls[0][0]).not.toHaveProperty("secret");
    expect(fetchMock).toHaveBeenCalledWith("/api/learning-units/unit/animations/generate", expect.objectContaining({
      method: "POST", credentials: "same-origin", body: JSON.stringify(request),
      headers: expect.objectContaining({"X-CSRF-Token": "csrf", "X-Animation-Operation-ID": operation,
        "Idempotency-Key": "request-key", "X-Animation-Allow-Template-Fallback": "true"})}));
  });
  it("rejects truncated or mismatched streams and malformed handed-off snapshots", async () => {
    for (const id of [operation, "another-operation"]) {
      const s = stream(); fetchMock.mockResolvedValue(s.response);
      s.send("agent_start", {id, stage: "reserved", deadline}); s.close();
      await expect(generateAnimation("unit", request, "csrf", "request-key", operation, false, new AbortController().signal, vi.fn()))
        .rejects.toMatchObject({code: id === operation ? "CONNECTION_INTERRUPTED" : "INVALID_RESPONSE"});
    }
    fetchMock.mockResolvedValue(Response.json({id: operation, deadline, stage: "handed_off"}));
    await expect(loadPreparation(operation)).rejects.toMatchObject({code: "INVALID_RESPONSE"});
  });
  it("accepts honest DSL receipts and rejects fake template identity", async () => {
    fetchMock.mockResolvedValue(Response.json(dslJob)); expect(await loadAnimationJob("dsl-job")).toEqual(dslJob);
    fetchMock.mockResolvedValue(Response.json({...dslJob, template_id: "linked-list-insertion"}));
    await expect(loadAnimationJob("dsl-job")).rejects.toMatchObject({code: "INVALID_RESPONSE"});
  });
});

describe("DSL animation student UI", () => {
  it("keeps the directory template entry without exposing dynamic controls", async () => {
    const w = panel(false); await flushPromises();
    expect(w.find('[data-testid="request-animation"]').exists()).toBe(true);
    expect(w.find('[data-testid="generate-animation"]').exists()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled(); w.unmount();
  });
  it("shows preparation stages, render progress, playback and existing export actions", async () => {
    const s = stream();
    fetchMock.mockImplementation(async (url: string) => url.endsWith("/generate") ? s.response
      : url.endsWith("/srt") ? new Response("1\n00:00:00,000 --> 00:00:02,000\ntext") : Response.json(dslJob));
    const w = panel(); await w.get('[data-testid="generate-animation"]').trigger("click");
    s.send("agent_start", {id: operation, stage: "reserved", deadline});
    s.send("stage_changed", {id: operation, stage: "generating"}); await flushPromises(); expect(w.text()).toContain("生成分镜中");
    s.send("stage_changed", {id: operation, stage: "reviewing"}); await flushPromises(); expect(w.text()).toContain("审核动画中");
    s.send("stage_changed", {id: operation, stage: "compiled"}); await flushPromises(); expect(w.text()).toContain("审核通过，等待渲染");
    s.send("done", {id: operation, stage: "handed_off", deadline, job_id: "dsl-job", source: "generated_dsl"}); s.close();
    await flushPromises(); expect(w.text()).toContain("已审核生成动画");
    Source.instances.at(-1)!.emit("running", 2, {job_id: "dsl-job", progress: 0.2});
    Source.instances.at(-1)!.emit("progress", 3, {job_id: "dsl-job", progress: 0.6}); await flushPromises(); expect(w.text()).toContain("60%");
    fetchMock.mockImplementation(async (url: string) => url.endsWith("/srt") ? new Response("subtitle")
      : Response.json({...dslJob, status: "succeeded", media_id: "media", last_event_id: 4}));
    Source.instances.at(-1)!.emit("succeeded", 4, {job_id: "dsl-job", media_id: "media"}); await flushPromises();
    expect(w.get('video source').attributes('src')).toBe("/api/animation-media/media/mp4");
    expect(w.find('[data-testid="download-mp4"]').exists()).toBe(true);
    expect(w.find('[data-testid="download-srt"]').exists()).toBe(true);
    expect(sessionStorage.getItem(`edumind:animation:unit:${scene}`)).not.toMatch(/handle|secret|csrf/); w.unmount();
  });
  it("cancels preparation, then cancels the Job if handoff won the race", async () => {
    const s = stream();
    fetchMock.mockImplementation(async (url: string) => url.endsWith("/generate") ? s.response
      : url.includes("preparations") ? Response.json({id: operation, stage: "handed_off", deadline, job_id: "dsl-job"})
      : Response.json({...dslJob, status: url.endsWith("/cancel") ? "cancelled" : "queued"}));
    const w = panel(); await w.get('[data-testid="generate-animation"]').trigger("click");
    await w.get('[data-testid="cancel-preparation"]').trigger("click"); await flushPromises();
    expect(fetchMock.mock.calls.map(c => c[0])).toContain("/api/animation-jobs/dsl-job/cancel");
    expect(w.text()).toContain("已取消");
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal!.aborted).toBe(true); s.close(); w.unmount();
  });
  it("cancels preparation before handoff without creating a render Job", async () => {
    const s = stream(); fetchMock.mockImplementation(async (url: string) => url.endsWith("/generate") ? s.response
      : Response.json({id: operation, stage: "cancelled", deadline}));
    const w = panel(); await w.get('[data-testid="generate-animation"]').trigger("click");
    expect(fetchMock.mock.calls[0][1].headers["X-Animation-Allow-Template-Fallback"]).toBe("false");
    await w.get('[data-testid="cancel-preparation"]').trigger("click"); await flushPromises();
    expect(w.text()).toContain("已取消"); expect(fetchMock.mock.calls.some(c => String(c[0]).includes("animation-jobs"))).toBe(false);
    s.close(); w.unmount();
  });
  it("shows preparation-time template fallback with its failure cause", async () => {
    const s = stream(); fetchMock.mockImplementation(async (url: string) => url.endsWith("/generate") ? s.response
      : Response.json({...dslJob, template_id: "linked-list-insertion", render_kind: "template", candidate_id: undefined,
        fallback_reason_code: "DSL_REVIEW_FAILED"}));
    const w = panel(); await w.get('input[type="checkbox"]').setValue(true);
    await w.get('[data-testid="generate-animation"]').trigger("click");
    s.send("done", {id: operation, stage: "handed_off", deadline, job_id: "dsl-job", source: "template_fallback", error_code: "DSL_REVIEW_FAILED"});
    s.close(); await flushPromises(); expect(w.text()).toContain("生成动画失败，已改用审核模板");
    expect(w.text()).toContain("DSL_REVIEW_FAILED"); w.unmount();
  });
  it("does not display a receipt from another generation or replay a failed POST", async () => {
    saved("dsl-job"); fetchMock.mockResolvedValue(Response.json({...dslJob, generation_id: "another-generation", status: "succeeded", media_id: "wrong"}));
    const w = panel(); await flushPromises(); expect(w.find('video').exists()).toBe(false);
    expect(w.text()).toContain("暂时无法读取动画状态"); expect(fetchMock).toHaveBeenCalledTimes(1); w.unmount();
  });
  it("restores preparation using GET only and leaves failed learning content usable", async () => {
    saved(); fetchMock.mockResolvedValue(Response.json({id: operation, stage: "failed", deadline, error_code: "ANIMATION_UNAVAILABLE"}));
    const w = panel(); await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1); expect(fetchMock.mock.calls[0][0]).toContain("animation-preparations");
    expect(w.text()).toContain("ANIMATION_UNAVAILABLE"); expect(w.text()).toContain("讲解、代码和练习始终可以继续"); w.unmount();
  });
  it("restores render-failure fallback from the final event and keeps its reason/source", async () => {
    saved("dsl-job"); fetchMock.mockImplementation(async (url: string) => Response.json(url.endsWith("template-job")
      ? {...dslJob, id: "template-job", render_kind: "template", template_id: "linked-list-insertion", candidate_id: undefined,
        fallback_of: "dsl-job", fallback_reason_code: "DSL_RENDER_FAILED"}
      : {...dslJob, status: "failed", last_event_id: 5}));
    const w = panel(); await flushPromises();
    expect(Source.instances.at(-1)!.url).toContain("after=4");
    Source.instances.at(-1)!.emit("failed", 5, {job_id: "dsl-job", fallback_job_id: "template-job", fallback_source: "template_fallback"});
    await flushPromises(); expect(w.text()).toContain("生成动画失败，已改用审核模板"); expect(w.text()).toContain("DSL_RENDER_FAILED");
    expect(JSON.parse(sessionStorage.getItem(`edumind:animation:unit:${scene}`)!).jobId).toBe("template-job"); w.unmount();
  });
  it("retries a failed fallback template using an independent legacy receipt", async () => {
    saved("template-job");
    fetchMock.mockImplementation(async (url: string) => Response.json(url.endsWith("/retry")
      ? {id: "retry-job", learning_unit_id: "unit", template_id: "linked-list-insertion", status: "queued", attempt: 0, progress: 0, last_event_id: 1}
      : {...dslJob, id: "template-job", render_kind: "template", template_id: "linked-list-insertion", candidate_id: undefined,
        fallback_of: "dsl-job", status: "failed"}));
    const w = panel(); await flushPromises();
    await w.get('[data-testid="retry-animation"]').trigger("click"); await flushPromises();
    expect(w.text()).toContain("排队中"); expect(Source.instances.at(-1)!.url).toContain("retry-job/events");
    expect(JSON.parse(sessionStorage.getItem(`edumind:animation:unit:${scene}`)!).operationId).toBeUndefined();
    expect(fetchMock.mock.calls.some(c => String(c[0]).endsWith("/generate"))).toBe(false); w.unmount();
  });
  it("rejects a fallback belonging to another original Job", async () => {
    saved("dsl-job"); fetchMock.mockResolvedValue(Response.json({...dslJob, status: "failed", last_event_id: 4}));
    const w = panel(); await flushPromises();
    fetchMock.mockResolvedValue(Response.json({...dslJob, id: "template-job", render_kind: "template", template_id: "linked-list-insertion", fallback_of: "other-job"}));
    Source.instances.at(-1)!.emit("failed", 4, {job_id: "dsl-job", fallback_job_id: "template-job", fallback_source: "template_fallback"});
    await flushPromises(); expect(w.text()).toContain("模板替代状态暂不可用"); expect(w.text()).not.toContain("已改用审核模板"); w.unmount();
  });
  it("discards late preparation after scene changes and aborts its original stream", async () => {
    const s = stream(); fetchMock.mockResolvedValue(s.response); const w = panel();
    await w.get('[data-testid="generate-animation"]').trigger("click");
    await w.setProps({sceneVersion: 2});
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal!.aborted).toBe(true);
    s.send("done", {id: operation, stage: "handed_off", deadline, job_id: "old-job"}); s.close(); await flushPromises();
    expect(w.find('[data-testid="animation-video"]').exists()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1); w.unmount();
  });
  it("clears withdrawn media after revalidation and ignores old target events", async () => {
    saved("dsl-job"); fetchMock.mockImplementation(async (url: string) => url.endsWith("/srt") ? new Response("subtitle")
      : Response.json({...dslJob, status: "succeeded", media_id: "media"}));
    const w = panel(); await flushPromises(); expect(w.find('video').exists()).toBe(true);
    fetchMock.mockResolvedValue(Response.json({code: "NOT_FOUND"}, {status: 404}));
    window.dispatchEvent(new Event("focus")); await flushPromises(); expect(w.find('video').exists()).toBe(false);
    expect(w.text()).toContain("讲解、代码和练习可继续使用"); w.unmount();
  });
  it("does not restore media from a late GET after a newer withdrawal response", async () => {
    saved("dsl-job"); fetchMock.mockResolvedValue(Response.json(dslJob));
    const w = panel(); await flushPromises();
    let resolveOld!: (value: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>(resolve => {resolveOld = resolve;}))
      .mockResolvedValueOnce(Response.json({code: "NOT_FOUND"}, {status: 404}));
    window.dispatchEvent(new Event("focus")); window.dispatchEvent(new Event("focus")); await flushPromises();
    resolveOld(Response.json({...dslJob, status: "succeeded", media_id: "withdrawn-media", last_event_id: 8}));
    await flushPromises(); expect(w.find('video').exists()).toBe(false);
    expect(w.text()).toContain("暂时无法读取动画状态"); w.unmount();
  });
  it("reopens Job events from the fresh cursor after connection loss", async () => {
    saved("dsl-job"); fetchMock.mockResolvedValue(Response.json(dslJob)); const w = panel(); await flushPromises();
    const first = Source.instances.at(-1)!;
    fetchMock.mockResolvedValue(Response.json({...dslJob, status: "running", last_event_id: 3, progress: 0.4}));
    first.onerror!(); await flushPromises(); expect(first.closed).toBe(true); expect(Source.instances.at(-1)!.url).toContain("after=3");
    await w.setProps({sceneVersion: 2}); first.emit("succeeded", 6, {job_id: "dsl-job", media_id: "old-media"});
    await flushPromises(); expect(w.find('video').exists()).toBe(false); w.unmount();
  });
});
