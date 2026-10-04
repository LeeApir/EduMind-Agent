import type { FetchLike } from "./catalog";

export type ProviderType = "openai-compatible" | "ollama" | "anthropic" | "gemini" | "spark";
export type CredentialMode = "persistent" | "temporary" | "none";
export interface Connection {
  id: string; provider_type: ProviderType; display_name: string; base_url: string; is_local: boolean;
  enabled: boolean; config_version: number; credential_mode: CredentialMode;
  credential_state: "present" | "missing" | "expired" | "revoked"; credential_expires_at: string;
}
export const CAPABILITY_LABELS = {
  streaming: "流式文本", structured_output: "结构化输出", tool_calling: "工具调用",
  vision: "图像理解", embedding: "向量", tts: "语音合成", asr: "语音识别",
} as const;
export type Capability = Record<keyof typeof CAPABILITY_LABELS, boolean | null> & {
  source: "declared" | "verified" | "unknown"; version: string;
};
export interface Model { id: string; capabilities: Capability; }
export interface ModelList { connection_id: string; config_version: number; models: Model[]; refreshed_at: string | null; }
export interface ProbeResult {
  connection_id: string; config_version: number; model_id: string; target: string; is_local: boolean;
  capabilities: Capability; requests: number; usage: { input_tokens?: number | null; output_tokens?: number | null } | null;
}
export interface ConnectionWrite {
  provider_type: ProviderType; display_name: string; base_url: string; credential_mode: CredentialMode;
  enabled: boolean; secret?: { api_key: string } | null;
}
export interface ProbeInput {
  operation_id: string; consent: { accepted: true; config_version: number; model_id: string; data_categories: ["probe"] };
  temporary_handle?: string;
}
const messages: Record<string, string> = {
  UNAUTHORIZED: "本次匿名会话已到期，请重新打开设置并重新输入凭据。",
  CSRF_FAILED: "会话验证失败，请重新打开设置。",
  NOT_FOUND: "这条连接已删除或不属于当前会话，请重新读取。",
  VERSION_CONFLICT: "连接已修改，请重新读取并确认新的目标。",
  CONSENT_REQUIRED: "请确认本次连接、模型与发送的数据。",
  INVALID_TARGET: "服务地址被拒绝。云端需公网 HTTPS；本地地址须由服务端明确放行。",
  VALIDATION_ERROR: "设置格式有误，请检查服务地址、名称和模型 ID。",
  CREDENTIAL_MISSING: "凭据已清除，请重新输入 Key 或明确选择无需 Key。",
  CREDENTIAL_EXPIRED: "这条连接的凭据已到期，请重新输入。",
  CREDENTIAL_UNAVAILABLE: "凭据不可用。临时 Key 只能用于一次操作，请重新输入。",
  CONFIGURATION_MISSING: "服务端凭据保护配置不可用，请联系管理员；目录课程仍可学习。",
  BUDGET_NOT_AUTHORIZED: "尚未授权测试预算。请由管理员配置预算后再试；目录课程仍可学习。",
  CAPABILITY_UNAVAILABLE: "模型或接口不支持这次操作，请检查模型 ID 和服务类型。",
  AUTHENTICATION_FAILED: "服务拒绝了凭据，请检查 Key。",
  RATE_LIMITED: "服务正在限流，请稍后主动重试。",
  TIMEOUT: "操作已超时，请检查服务后主动重试。",
  INVALID_OUTPUT: "服务响应不符合协议，未更新模型缓存。请检查服务配置。",
  TEMPORARILY_UNAVAILABLE: "服务暂时不可用，请稍后重试。",
};
export class ProviderSettingsError extends Error {
  constructor(readonly code: string) { super(messages[code] ?? "连接设置暂时不可用，请重试。"); }
}
function invalid(): never { throw new ProviderSettingsError("INVALID_OUTPUT"); }
function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown, max: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max && !/[\u0000-\u001f\u007f]/.test(value);
}
function positive(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) > 0; }
function time(value: unknown): value is string { return typeof value === "string" && Number.isFinite(Date.parse(value)); }
function connection(value: unknown): Connection {
  if (!object(value) || !text(value.id, 36) || !text(value.display_name, 80) || !text(value.base_url, 500)
    || !["openai-compatible", "ollama", "anthropic", "gemini", "spark"].includes(String(value.provider_type))
    || !["persistent", "temporary", "none"].includes(String(value.credential_mode))
    || !["present", "missing", "expired", "revoked"].includes(String(value.credential_state))
    || typeof value.enabled !== "boolean" || typeof value.is_local !== "boolean"
    || !positive(value.config_version) || !time(value.credential_expires_at)) invalid();
  // Copy the public allowlist; never carry raw response extras into component state.
  return {
    id: value.id, display_name: value.display_name, base_url: value.base_url,
    provider_type: value.provider_type as ProviderType, credential_mode: value.credential_mode as CredentialMode,
    credential_state: value.credential_state as Connection["credential_state"], enabled: value.enabled,
    is_local: value.is_local, config_version: value.config_version, credential_expires_at: value.credential_expires_at,
  };
}
function capability(value: unknown): Capability {
  if (!object(value) || !["declared", "verified", "unknown"].includes(String(value.source)) || !text(value.version, 100)) invalid();
  const result = { source: value.source, version: value.version } as Capability;
  for (const key of Object.keys(CAPABILITY_LABELS) as (keyof typeof CAPABILITY_LABELS)[]) {
    if (value[key] !== null && typeof value[key] !== "boolean") invalid();
    result[key] = value[key] as boolean | null;
  }
  return result;
}
async function request(path: string, init: RequestInit, fetchImpl: FetchLike): Promise<unknown> {
  let response: Response;
  try { response = await fetchImpl(path, { credentials: "same-origin", cache: "no-store", ...init }); }
  catch { throw new ProviderSettingsError("CONNECTION_FAILED"); }
  if (response.status === 204 && response.ok) return null;
  let value: unknown;
  try { value = await response.json(); } catch { invalid(); }
  if (!response.ok) throw new ProviderSettingsError(object(value) && typeof value.code === "string" ? value.code : "REQUEST_FAILED");
  return value;
}
export { request as providerRequest };
function headers(csrf: string, version?: number): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf,
    ...(version === undefined ? {} : { "If-Match": String(version) }) };
}
const ROOT = "/api/providers/connections";
export async function listConnections(fetchImpl: FetchLike = fetch): Promise<Connection[]> {
  const value = await request(ROOT, {}, fetchImpl);
  if (!object(value) || !Array.isArray(value.items) || value.items.length > 100) invalid();
  return value.items.map(connection);
}
export async function saveConnection(input: ConnectionWrite, csrf: string, current?: Connection,
  fetchImpl: FetchLike = fetch): Promise<Connection> {
  const saved = connection(await request(current ? `${ROOT}/${encodeURIComponent(current.id)}` : ROOT,
    { method: current ? "PATCH" : "POST", headers: headers(csrf, current?.config_version), body: JSON.stringify(input) }, fetchImpl));
  if (current && (saved.id !== current.id || saved.config_version !== current.config_version + 1)) invalid();
  return saved;
}
export async function deleteConnection(current: Connection, csrf: string, fetchImpl: FetchLike = fetch): Promise<void> {
  await request(`${ROOT}/${encodeURIComponent(current.id)}`, { method: "DELETE", headers: headers(csrf, current.config_version) }, fetchImpl);
}
function models(value: unknown, current: Connection): ModelList {
  if (!object(value) || value.connection_id !== current.id || value.config_version !== current.config_version
    || !Array.isArray(value.models) || value.models.length > 1000 || (value.refreshed_at !== null && !time(value.refreshed_at))) invalid();
  const parsed = value.models.map((model): Model => {
    if (!object(model) || !text(model.id, 160)) invalid();
    return { id: model.id, capabilities: capability(model.capabilities) };
  });
  if (new Set(parsed.map((model) => model.id)).size !== parsed.length) invalid();
  return { connection_id: current.id, config_version: current.config_version, models: parsed, refreshed_at: value.refreshed_at as string | null };
}
export async function getModels(current: Connection, fetchImpl: FetchLike = fetch): Promise<ModelList> {
  return models(await request(`${ROOT}/${encodeURIComponent(current.id)}/models`, {}, fetchImpl), current);
}
export async function refreshModels(current: Connection, input: ProbeInput, csrf: string, fetchImpl: FetchLike = fetch): Promise<ModelList> {
  return models(await request(`${ROOT}/${encodeURIComponent(current.id)}/models/refresh`,
    { method: "POST", headers: headers(csrf), body: JSON.stringify(input) }, fetchImpl), current);
}
export async function uploadTemporary(current: Connection, key: string, input: ProbeInput,
  purpose: "connection_test" | "model_refresh", csrf: string, fetchImpl: FetchLike = fetch): Promise<string> {
  const value = await request(`${ROOT}/${encodeURIComponent(current.id)}/temporary-credentials`,
    { method: "POST", headers: headers(csrf), body: JSON.stringify({ secret: { api_key: key }, operation_id: input.operation_id, purpose, consent: input.consent }) }, fetchImpl);
  if (!object(value) || !text(value.handle, 200) || value.handle.length < 32 || value.config_version !== current.config_version
    || !time(value.expires_at) || !positive(value.operation_deadline_seconds)) invalid();
  return value.handle;
}
export async function testConnection(current: Connection, input: ProbeInput, csrf: string, fetchImpl: FetchLike = fetch): Promise<ProbeResult> {
  const value = await request(`${ROOT}/${encodeURIComponent(current.id)}/test`,
    { method: "POST", headers: headers(csrf), body: JSON.stringify(input) }, fetchImpl);
  if (!object(value) || value.connection_id !== current.id || value.config_version !== current.config_version
    || value.model_id !== input.consent.model_id || !text(value.target, 500) || typeof value.is_local !== "boolean"
    || value.requests !== 1 || (value.usage !== null && !object(value.usage))) invalid();
  let usage: ProbeResult["usage"] = null;
  if (object(value.usage)) {
    usage = {};
    for (const key of ["input_tokens", "output_tokens"] as const) {
      const count = value.usage[key];
      if (count !== null && count !== undefined && (!Number.isSafeInteger(count) || Number(count) < 0)) invalid();
      usage[key] = count as number | null | undefined;
    }
  }
  return { connection_id: current.id, config_version: current.config_version, model_id: value.model_id,
    target: value.target, is_local: value.is_local, requests: 1, capabilities: capability(value.capabilities), usage };
}
