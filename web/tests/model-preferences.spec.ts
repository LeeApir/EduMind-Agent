import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ModelPreferences from "../src/components/ModelPreferences.vue";
import * as api from "../src/api/modelPreferences";
import type { Connection } from "../src/api/providers";

const cid = "00000000-0000-4000-8000-000000000001";
const other = "00000000-0000-4000-8000-000000000002";
const connection: Connection = { id: cid, provider_type: "openai-compatible", display_name: "云端 A",
  base_url: "https://a.example/v1", is_local: false, enabled: true, config_version: 2,
  credential_mode: "persistent", credential_state: "present", credential_expires_at: "2030-01-01T00:00:00Z" };
const route: api.Route = { connection_id: cid, config_version: 2, model_id: "model-a", data_categories: ["learning_goal"] };
const saved: api.Preference = { task_profile: "default", version: 1, route, fallbacks: [], state: "available" };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
let preferences: api.Preference[];
let connections: Connection[];
let fail: string;
let fetchMock: ReturnType<typeof vi.fn>;
const wrappers: ReturnType<typeof mount>[] = [];
function mounted() { const wrapper = mount(ModelPreferences); wrappers.push(wrapper); return wrapper; }
function button(wrapper: ReturnType<typeof mount>, name: string) { return wrapper.findAll("button").find((item) => item.text() === name)!; }
async function click(wrapper: ReturnType<typeof mount>, name: string) { await button(wrapper, name).trigger("click"); await flushPromises(); }
async function agree(wrapper: ReturnType<typeof mount>) { await wrapper.get(".preferences-consent input").setValue(true); }
async function primary(wrapper: ReturnType<typeof mount>, id = cid, model = "model-a") {
  await wrapper.findAll("select")[0].setValue(id); await flushPromises();
  await wrapper.findAll('input:not([type="checkbox"])')[0].setValue(model);
}
function writes() { return fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT"); }
beforeEach(() => {
  fail = ""; preferences = []; connections = [connection, { ...connection, id: other, display_name: "本地 B",
    provider_type: "ollama", base_url: "http://localhost:11434", credential_mode: "none", is_local: true }];
  fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/auth/session") return json({ user: { id: "owner" }, csrf_token: "csrf" });
    if (path === "/api/providers/connections") return json({ items: connections });
    if (path.endsWith("/models")) return json({ connection_id: path.split("/").at(-2), config_version: 2,
      models: [], refreshed_at: null });
    if (path === "/api/model-preferences") return json({ preferences });
    if (init?.method === "PUT") {
      if (fail) return json({ code: fail, message: "secret-from-upstream" }, 409);
      const body = JSON.parse(String(init.body));
      const value = { task_profile: path.split("/").at(-1), version: body.expected_version + 1,
        route: body.route, fallbacks: body.fallbacks, state: "available" };
      preferences = [...preferences.filter((item) => item.task_profile !== value.task_profile), value];
      return json(value);
    }
    throw new Error("Unexpected Mock API");
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); vi.unstubAllGlobals(); });

describe("preference contract and configuration priority", () => {
  it("resolves direct, user default and system default without bypassing unavailable selections", () => {
    const unavailable: api.Preference = { ...saved, task_profile: "review", state: "unavailable" };
    expect(api.resolveConfiguration([saved, unavailable], "review")).toEqual({ source: "user_task_profile", preference: unavailable });
    expect(api.resolveConfiguration([saved], "fast")).toEqual({ source: "user_default", preference: saved });
    expect(api.resolveConfiguration([], "quality")).toEqual({ source: "system_default", preference: undefined });
  });
  it("copies only safe metadata and rejects duplicate profiles, routes and forbidden errors", async () => {
    const response = vi.fn().mockResolvedValue(json({ preferences: [{ ...saved, secret: "discard" }] }));
    expect(await api.listPreferences(response)).toEqual([saved]);
    response.mockResolvedValue(json({ preferences: [saved, saved] }));
    await expect(api.listPreferences(response)).rejects.toThrow();
    response.mockResolvedValue(json({ preferences: [{ ...saved, fallbacks: [{ route, on_errors: ["TIMEOUT"] }] }] }));
    await expect(api.listPreferences(response)).rejects.toThrow();
    response.mockResolvedValue(json({ preferences: [{ ...saved, fallbacks: [{ route: { ...route, connection_id: other }, on_errors: ["AUTHENTICATION_FAILED"] }] }] }));
    await expect(api.listPreferences(response)).rejects.toThrow();
  });
  it("checks the exact profile/version/route receipt and sends CSRF without Provider calls", async () => {
    const input: api.PreferenceWrite = { expected_version: 0, route, fallbacks: [], consent_accepted: true };
    const response = vi.fn().mockResolvedValue(json(saved));
    expect(await api.savePreference("default", input, "csrf", response)).toEqual(saved);
    expect(response.mock.calls[0][1]).toMatchObject({ method: "PUT", cache: "no-store", credentials: "same-origin",
      headers: { "X-CSRF-Token": "csrf" } });
    response.mockResolvedValue(json({ ...saved, task_profile: "review" }));
    await expect(api.savePreference("default", input, "csrf", response)).rejects.toThrow();
    response.mockResolvedValue(json({ ...saved, route: { ...route, model_id: "unexpected" } }));
    await expect(api.savePreference("default", input, "csrf", response)).rejects.toThrow();
    response.mockResolvedValue(json({ ...saved, version: 2 }));
    await expect(api.savePreference("default", input, "csrf", response)).rejects.toThrow();
  });
});

describe("task profiles and data destinations", () => {
  it("opens read-only with empty fallback and no implicit consent or dynamic action", async () => {
    const wrapper = mounted(); await flushPromises();
    expect(button(wrapper, "保存当前档位").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("显式回退 · 0/3");
    expect(wrapper.text()).toContain("动态学习须另行验收与批准");
    expect(writes()).toHaveLength(0); expect(fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
    expect(wrapper.find('input[type="password"]').exists()).toBe(false);
  });
  it("saves a default target with minimal data, displays server receipt and inherited profiles", async () => {
    const wrapper = mounted(); await flushPromises(); await primary(wrapper); await agree(wrapper);
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(writes()).toHaveLength(1); const body = JSON.parse(writes()[0][1].body);
    expect(body).toEqual({ expected_version: 0, route, fallbacks: [], consent_accepted: true });
    expect(wrapper.get('[role="status"]').text()).toContain("本次没有调用模型");
    const result = wrapper.get(".preferences-resolution").text();
    expect(result).toContain("快速 · 用户默认连接"); expect(result).toContain("云端 A · openai-compatible · model-a · 公网目标");
    expect(result).toContain("回退：未启用");
  });
  it("resets consent for target, model and category changes and uses exact saved version", async () => {
    preferences = [saved]; const wrapper = mounted(); await flushPromises(); await agree(wrapper);
    await wrapper.findAll('input:not([type="checkbox"])')[0].setValue("new-model");
    expect((wrapper.get(".preferences-consent input").element as HTMLInputElement).checked).toBe(false);
    await agree(wrapper); await wrapper.get(".route-data input").setValue(false);
    expect((wrapper.get(".preferences-consent input").element as HTMLInputElement).checked).toBe(false);
    await wrapper.get(".route-data input").setValue(true); await agree(wrapper);
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(JSON.parse(writes()[0][1].body).expected_version).toBe(1);
  });
  it("requires conditions for each explicitly added fallback and preserves its order/data consent", async () => {
    const wrapper = mounted(); await flushPromises(); await primary(wrapper); await click(wrapper, "添加回退目标");
    const fallback = wrapper.get(".fallback-settings article");
    await fallback.get("select").setValue(other); await fallback.get('input:not([type="checkbox"])').setValue("local-model");
    await agree(wrapper); await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("选择触发条件"); expect(writes()).toHaveLength(0);
    await fallback.findAll("fieldset")[1].findAll("input")[1].setValue(true);
    await agree(wrapper); await wrapper.get("form").trigger("submit"); await flushPromises();
    const body = JSON.parse(writes()[0][1].body);
    expect(body.fallbacks).toEqual([{ route: { ...route, connection_id: other, model_id: "local-model" }, on_errors: ["TIMEOUT"] }]);
    expect(wrapper.get(".preferences-resolution").text()).toContain("本地 B · ollama · local-model · 服务端白名单目标");
    expect(wrapper.text()).toContain("鉴权失败、无效结果或流式输出不会切换");
  });
  it("shows independent review with review-content data and does not inherit an unavailable explicit choice", async () => {
    preferences = [saved, { ...saved, task_profile: "review", route: { ...route, connection_id: other, model_id: "review-model",
      data_categories: ["content_for_review"] }, state: "unavailable" }];
    const wrapper = mounted(); await flushPromises(); await click(wrapper, "独立审核");
    expect(wrapper.text()).toContain("选择不可用，不自动降级");
    expect((wrapper.findAll('input:not([type="checkbox"])')[0].element as HTMLInputElement).value).toBe("review-model");
    expect(wrapper.get(".preferences-resolution").text()).toContain("独立审核 · 本档位设置");
    expect(writes()).toHaveLength(0);
  });
  it("keeps stale-version selection blocked and requires new confirmation after conflict", async () => {
    preferences = [{ ...saved, route: { ...route, config_version: 1 }, state: "consent_required" }]; fail = "VERSION_CONFLICT";
    const wrapper = mounted(); await flushPromises();
    expect(wrapper.get(".preferences-resolution").text()).toContain("当前目标不可确认");
    await agree(wrapper); await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("连接已修改");
    expect(wrapper.html()).not.toContain("secret-from-upstream");
    expect(button(wrapper, "保存当前档位").attributes("disabled")).toBeDefined(); expect(writes()).toHaveLength(1);
    expect(JSON.parse(writes()[0][1].body).route.config_version).toBe(2);
  });
  it("limits fallback to three and rejects duplicate targets or missing data", async () => {
    const wrapper = mounted(); await flushPromises(); await primary(wrapper);
    await click(wrapper, "添加回退目标"); await click(wrapper, "添加回退目标"); await click(wrapper, "添加回退目标");
    expect(button(wrapper, "添加回退目标").attributes("disabled")).toBeDefined();
    await click(wrapper, "移除回退 3"); await click(wrapper, "移除回退 2");
    const fallback = wrapper.get(".fallback-settings article"); await fallback.get("select").setValue(cid);
    await fallback.get('input:not([type="checkbox"])').setValue("model-a");
    await fallback.findAll("fieldset")[1].findAll("input")[0].setValue(true); await agree(wrapper);
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("不可重复"); expect(writes()).toHaveLength(0);
    await click(wrapper, "移除回退 1"); await wrapper.get(".route-data input").setValue(false); await agree(wrapper);
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("数据类型"); expect(writes()).toHaveLength(0);
  });
  it("retains a readable load failure and rejects missing credentials before saving", async () => {
    connections[0] = { ...connection, credential_state: "missing" };
    const wrapper = mounted(); await flushPromises(); await primary(wrapper); await agree(wrapper);
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("目标凭据不可用"); expect(writes()).toHaveLength(0);
    fetchMock.mockImplementation(async () => json({ code: "UNAUTHORIZED" }, 401)); await click(wrapper, "重新读取设置");
    expect(wrapper.get('[role="alert"]').text()).toContain("会话已到期");
  });
});
