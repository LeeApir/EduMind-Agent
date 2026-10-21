import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProviderSettings from "../src/components/ProviderSettings.vue";
import ProductApp from "../src/ProductApp.vue";
import * as api from "../src/api/providers";
import { ensureCatalogSession } from "../src/api/catalog";

vi.mock("../src/components/CatalogPage.vue", () => ({ default: {
  data: () => ({ answer: "" }), template: '<div data-test="course"><input v-model="answer" aria-label="课程草稿"></div>',
} }));
const cid = "00000000-0000-4000-8000-000000000001";
const connection: api.Connection = { id: cid, provider_type: "openai-compatible", display_name: "我的兼容服务",
  base_url: "https://provider.example/v1", is_local: false, enabled: true, config_version: 1,
  credential_mode: "persistent", credential_state: "present", credential_expires_at: "2026-10-05T00:00:00Z" };
const caps: api.Capability = { streaming: null, structured_output: null, tool_calling: null, vision: null,
  embedding: null, tts: null, asr: null, source: "unknown", version: "probe-v1" };
const cache = (item = connection): api.ModelList => ({ connection_id: item.id, config_version: item.config_version,
  models: [{ id: "mock-model", capabilities: caps }], refreshed_at: "2026-10-04T00:00:00Z" });
const probe: api.ProbeResult = { connection_id: cid, config_version: 1, model_id: "mock-model",
  target: connection.base_url, is_local: false, capabilities: caps, requests: 1, usage: null };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const input: api.ProbeInput = { operation_id: "00000000-0000-4000-8000-000000000002",
  consent: { accepted: true, config_version: 1, model_id: "mock-model", data_categories: ["probe"] } };
type Intercept = (path: string, init?: RequestInit) => Promise<Response> | undefined;
function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null, key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key); }, setItem: (key, value) => { values.set(String(key), String(value)); } };
}
let items: api.Connection[];
let intercept: Intercept;
let fetchMock: ReturnType<typeof vi.fn>;
const wrappers: ReturnType<typeof mount>[] = [];
function mounted(component = ProviderSettings) { const wrapper = mount(component); wrappers.push(wrapper); return wrapper; }
function button(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll("button").find((item) => item.text() === label)!;
}
async function click(wrapper: ReturnType<typeof mount>, label: string) {
  await button(wrapper, label).trigger("click"); await flushPromises();
}
async function consent(wrapper: ReturnType<typeof mount>) {
  await wrapper.get(".provider-consent input").setValue(true);
}
function providerPosts() { return fetchMock.mock.calls.filter(([path, init]) => String(path).startsWith("/api/providers") && init?.method === "POST"); }
beforeEach(() => {
  items = [{ ...connection }]; intercept = () => undefined;
  vi.stubGlobal("localStorage", storage());
  vi.stubGlobal("sessionStorage", storage());
  localStorage.clear(); sessionStorage.clear();
  fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    const override = intercept(path, init); if (override) return override;
    if (path === "/api/runtime") return json({ mode: "catalog_only" });
    if (path === "/api/auth/session") return json({ user: { id: "owner" }, csrf_token: "csrf" });
    if (path.endsWith("/models")) return json(cache(items[0]));
    if (path.endsWith("/models/refresh")) return json(cache(items[0]));
    if (path.endsWith("/temporary-credentials")) return json({ handle: "h".repeat(40), config_version: 1,
      expires_at: "2026-10-04T01:00:00Z", operation_deadline_seconds: 10 }, 201);
    if (path.endsWith("/test")) return json(probe);
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    if (init?.method === "POST" || init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      items = [{ ...items[0], ...body, id: cid, config_version: init.method === "PATCH" ? 2 : 1,
        credential_state: "present", credential_expires_at: connection.credential_expires_at }];
      return json(items[0], init.method === "POST" ? 201 : 200);
    }
    if (path === "/api/providers/connections") return json({ items });
    throw new Error(`Unexpected Mock route ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); vi.unstubAllGlobals(); });

describe("safe provider transport", () => {
  it("discards response secrets and rejects stale or unrelated mutation receipts", async () => {
    const response = vi.fn().mockResolvedValue(json({ items: [{ ...connection, secret: "never-store", api_key: "never-store" }] }));
    expect(await api.listConnections(response)).toEqual([connection]);
    response.mockResolvedValue(json({ ...connection, id: "another", config_version: 2 }));
    await expect(api.saveConnection({ ...connection }, "csrf", connection, response)).rejects.toThrow();
    response.mockResolvedValue(json(connection));
    await expect(api.saveConnection({ ...connection }, "csrf", connection, response)).rejects.toThrow();
  });
  it("binds cache and probe results to the current config and selected model", async () => {
    const response = vi.fn().mockResolvedValue(json({ ...cache(), config_version: 2 }));
    await expect(api.getModels(connection, response)).rejects.toThrow();
    response.mockResolvedValue(json({ ...probe, model_id: "unexpected-model" }));
    await expect(api.testConnection(connection, input, "csrf", response)).rejects.toThrow();
    response.mockResolvedValue(json({ ...cache(), models: [{ id: "same", capabilities: caps }, { id: "same", capabilities: caps }] }));
    await expect(api.getModels(connection, response)).rejects.toThrow();
    response.mockResolvedValue(json({ ...probe, capabilities: { ...caps, structured_output: "yes" } }));
    await expect(api.testConnection(connection, input, "csrf", response)).rejects.toThrow();
  });
  it("never exposes upstream messages or unknown error strings", async () => {
    const response = vi.fn().mockResolvedValue(json({ code: "INVALID_TARGET", message: "sk-secret <script>" }, 422));
    await expect(api.listConnections(response)).rejects.toThrow("服务地址被拒绝");
    response.mockResolvedValue(json({ code: "sk-secret", message: "sk-secret" }, 500));
    await expect(api.listConnections(response)).rejects.toThrow("连接设置暂时不可用，请重试。");
  });
  it("sends CSRF, config preconditions and one-operation temporary binding", async () => {
    const response = vi.fn().mockResolvedValue(json({ ...connection, config_version: 2 }));
    await api.saveConnection({ ...connection, secret: { api_key: "synthetic-key" } }, "csrf", connection, response);
    expect(response.mock.calls[0][1]).toMatchObject({ method: "PATCH", credentials: "same-origin", cache: "no-store",
      headers: { "X-CSRF-Token": "csrf", "If-Match": "1" } });
    response.mockResolvedValue(json({ handle: "h".repeat(40), config_version: 1, expires_at: connection.credential_expires_at,
      operation_deadline_seconds: 10 }));
    await api.uploadTemporary(connection, "synthetic-key", input, "model_refresh", "csrf", response);
    expect(JSON.parse(response.mock.calls[1][1].body)).toEqual({ secret: { api_key: "synthetic-key" },
      operation_id: input.operation_id, purpose: "model_refresh", consent: input.consent });
  });
  it("shares concurrent identity creation and reads identity again after settlement", async () => {
    let finish!: (value: Response) => void;
    const response = vi.fn().mockResolvedValueOnce(json({}, 401)).mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce(json({ user: { id: "new-owner" }, csrf_token: "new-csrf" }));
    const first = ensureCatalogSession(response); const second = ensureCatalogSession(response);
    await flushPromises(); expect(response).toHaveBeenCalledTimes(2);
    finish(json({ user: { id: "owner" }, csrf_token: "csrf" }));
    expect(await first).toEqual(await second);
    expect(await ensureCatalogSession(response)).toEqual({ owner: "new-owner", csrf: "new-csrf" });
    expect(response).toHaveBeenCalledTimes(3);
  });
});

describe("connection settings", () => {
  it.each(["anthropic", "gemini", "spark"])("adds an implemented native %s connection with a cleared password field", async (providerType) => {
    const wrapper = mounted(); await flushPromises(); await click(wrapper, "新增连接");
    await wrapper.get("#provider-name").setValue("原生审核服务");
    await wrapper.get("#provider-type").setValue(providerType);
    await wrapper.get("#provider-url").setValue("https://provider.example/v1");
    await wrapper.get("#provider-key").setValue("synthetic-native-secret");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    const body = JSON.parse(providerPosts()[0][1].body);
    expect(body.provider_type).toBe(providerType); expect(body.secret.api_key).toBe("synthetic-native-secret");
    expect((wrapper.get("#provider-key").element as HTMLInputElement).value).toBe("");
    expect(wrapper.html()).not.toContain("synthetic-native-secret"); expect(providerPosts()).toHaveLength(1);
  });
  it("opens with only cache reads, no Provider operation, and preserves unrelated learning storage", async () => {
    sessionStorage.setItem("edumind:catalog:last:owner", "unit");
    const wrapper = mounted(); await flushPromises();
    expect(providerPosts()).toHaveLength(0);
    expect(wrapper.text()).toContain(connection.base_url);
    expect(wrapper.get("#provider-key").attributes("type")).toBe("password");
    expect(wrapper.findAll(".provider-capabilities dd").map((item) => item.text())).toEqual(Array(7).fill("未知"));
    expect(localStorage.length).toBe(0); expect(sessionStorage.getItem("edumind:catalog:last:owner")).toBe("unit");
  });
  it("requires exact-model consent, resets it on model changes and sends only a probe", async () => {
    const wrapper = mounted(); await flushPromises();
    expect(button(wrapper, "测试连接一次").attributes("disabled")).toBeDefined();
    await consent(wrapper); await wrapper.get("#provider-model").setValue("changed");
    expect((wrapper.get(".provider-consent input").element as HTMLInputElement).checked).toBe(false);
    await wrapper.get("#provider-model").setValue("mock-model"); await consent(wrapper);
    await click(wrapper, "测试连接一次");
    expect(providerPosts()).toHaveLength(1);
    const body = JSON.parse(providerPosts()[0][1].body);
    expect(body.consent).toEqual(input.consent); expect(body.prompt).toBeUndefined();
    expect(wrapper.text()).toContain("文本连接测试完成");
    expect(wrapper.text()).toContain("高级能力仍以各项标记为准");
    expect(button(wrapper, "测试连接一次").attributes("disabled")).toBeDefined();
  });
  it("clears replacement Key before a failed save and reports a safe unsafe-target error", async () => {
    let finish!: (value: Response) => void;
    intercept = (_path, init) => init?.method === "PATCH" ? new Promise<Response>((resolve) => { finish = resolve; }) : undefined;
    const wrapper = mounted(); await flushPromises();
    await wrapper.get("#provider-key").setValue("synthetic-persistent-secret");
    await wrapper.get("form").trigger("submit");
    expect((wrapper.get("#provider-key").element as HTMLInputElement).value).toBe("");
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(JSON.parse(call[1].body).secret).toEqual({ api_key: "synthetic-persistent-secret" });
    finish(json({ code: "INVALID_TARGET", message: "synthetic-persistent-secret <img onerror=evil()>" }, 422));
    await flushPromises(); expect(wrapper.get('[role="alert"]').text()).toContain("服务地址被拒绝");
    expect(wrapper.html()).not.toContain("synthetic-persistent-secret");
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
  it("adds Ollama metadata without a Key or model call, and requires explicit deletion", async () => {
    const wrapper = mounted(); await flushPromises(); await click(wrapper, "新增连接");
    await wrapper.get("#provider-name").setValue("本地 Ollama");
    await wrapper.get("#provider-type").setValue("ollama");
    await wrapper.get("#provider-url").setValue("http://localhost:11434");
    await wrapper.get("#provider-mode").setValue("none");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(providerPosts()).toHaveLength(1); const body = JSON.parse(providerPosts()[0][1].body);
    expect(body.provider_type).toBe("ollama"); expect(body.secret).toBeUndefined();
    expect(button(wrapper, "删除连接").attributes("disabled")).toBeDefined();
    await wrapper.get(".provider-delete input").setValue(true); await click(wrapper, "删除连接");
    expect(fetchMock.mock.calls.find(([, init]) => init?.method === "DELETE")?.[1].headers).toMatchObject({ "If-Match": "1" });
    expect(wrapper.text()).toContain("连接已删除");
  });
  it("uploads a temporary Key once, clears it immediately, and never retains its handle", async () => {
    items[0] = { ...connection, credential_mode: "temporary", credential_state: "missing" };
    const wrapper = mounted(); await flushPromises();
    await wrapper.get("#provider-temporary-key").setValue("synthetic-temporary-secret"); await consent(wrapper);
    await click(wrapper, "测试连接一次");
    expect(providerPosts()).toHaveLength(2);
    const upload = JSON.parse(providerPosts()[0][1].body); const test = JSON.parse(providerPosts()[1][1].body);
    expect(upload.purpose).toBe("connection_test"); expect(upload.operation_id).toBe(test.operation_id);
    expect(test.temporary_handle).toBe("h".repeat(40)); expect(test.secret).toBeUndefined();
    expect((wrapper.get("#provider-temporary-key").element as HTMLInputElement).value).toBe("");
    expect(wrapper.html()).not.toContain("h".repeat(40)); expect(wrapper.html()).not.toContain("synthetic-temporary-secret");
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
  it("does not initiate a probe if the settings close while temporary upload is pending", async () => {
    items[0] = { ...connection, credential_mode: "temporary", credential_state: "missing" };
    let finish!: (value: Response) => void;
    intercept = (path) => path.endsWith("/temporary-credentials") ? new Promise<Response>((resolve) => { finish = resolve; }) : undefined;
    const wrapper = mounted(); await flushPromises();
    await wrapper.get("#provider-temporary-key").setValue("synthetic-temporary-secret"); await consent(wrapper);
    await button(wrapper, "测试连接一次").trigger("click");
    expect((wrapper.get("#provider-temporary-key").element as HTMLInputElement).value).toBe("");
    wrapper.unmount();
    finish(json({ handle: "h".repeat(40), config_version: 1, expires_at: connection.credential_expires_at, operation_deadline_seconds: 10 }));
    await flushPromises(); expect(providerPosts()).toHaveLength(1);
  });
  it("keeps cache after an unauthorized refresh, gives an actionable message and does not retry", async () => {
    intercept = (path) => path.endsWith("/models/refresh") ? Promise.resolve(json({ code: "BUDGET_NOT_AUTHORIZED" }, 403)) : undefined;
    const wrapper = mounted(); await flushPromises(); await consent(wrapper); await click(wrapper, "刷新模型一次");
    expect(wrapper.get('[role="alert"]').text()).toContain("尚未授权测试预算");
    expect((wrapper.get("#provider-model").element as HTMLInputElement).value).toBe("mock-model");
    expect(providerPosts()).toHaveLength(1);
  });
  it("blocks missing-model operations and escapes service-provided names", async () => {
    items[0].display_name = '<img src=x onerror="evil()">';
    intercept = (path) => path.endsWith("/models") ? Promise.resolve(json({ ...cache(), models: [], refreshed_at: null })) : undefined;
    const wrapper = mounted(); await flushPromises(); await consent(wrapper);
    expect(wrapper.find("img").exists()).toBe(false);
    expect(button(wrapper, "测试连接一次").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("可输入已知模型 ID"); expect(providerPosts()).toHaveLength(0);
  });
  it("returns to the same mounted course draft even when settings fail", async () => {
    intercept = (path) => path === "/api/providers/connections" ? Promise.resolve(json({ code: "CONFIGURATION_MISSING" }, 503)) : undefined;
    const wrapper = mounted(ProductApp as typeof ProviderSettings); await flushPromises();
    await wrapper.get('[aria-label="课程草稿"]').setValue("保留我的练习");
    await click(wrapper, "模型设置");
    expect(wrapper.text()).toContain("目录课程仍可学习");
    await click(wrapper, "返回课程");
    expect((wrapper.get('[aria-label="课程草稿"]').element as HTMLInputElement).value).toBe("保留我的练习");
    expect(providerPosts()).toHaveLength(0);
  });
});
