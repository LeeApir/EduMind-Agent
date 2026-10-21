import type { FetchLike } from "./catalog";
import { ProviderSettingsError, providerRequest } from "./providers";

export const PROFILES = { fast: "快速", default: "默认 · 用户默认连接", quality: "质量", review: "独立审核" } as const;
export type Profile = keyof typeof PROFILES;
export const DATA_LABELS = { learning_goal: "学习目标", profile_evidence: "画像与答题证据", limited_history: "有限课堂历史",
  content_for_review: "待审核内容", probe: "连接探测数据" } as const;
export type Category = keyof typeof DATA_LABELS;
export const ERROR_LABELS = { RATE_LIMITED: "限流", TIMEOUT: "超时", TEMPORARILY_UNAVAILABLE: "暂时不可用" } as const;
export type FallbackError = keyof typeof ERROR_LABELS;
export interface Route { connection_id: string; config_version: number; model_id: string; data_categories: Category[]; }
export interface Fallback { route: Route; on_errors: FallbackError[]; }
export interface Preference { task_profile: Profile; version: number; route: Route; fallbacks: Fallback[];
  state: "available" | "consent_required" | "unavailable"; }
export interface PreferenceWrite { expected_version: number; route: Route; fallbacks: Fallback[]; consent_accepted: true; }
function invalid(): never { throw new ProviderSettingsError("INVALID_OUTPUT"); }
function object(value: unknown): value is Record<string, unknown> { return Boolean(value) && typeof value === "object" && !Array.isArray(value); }
function text(value: unknown, max: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max && !/[\u0000-\u001f\u007f]/.test(value);
}
function integer(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) > 0; }
function route(value: unknown): Route {
  if (!object(value) || !text(value.connection_id, 36) || !integer(value.config_version) || !text(value.model_id, 160)
    || !Array.isArray(value.data_categories) || !value.data_categories.length || value.data_categories.length > 5
    || !value.data_categories.every((category) => typeof category === "string" && Object.hasOwn(DATA_LABELS, category))
    || new Set(value.data_categories).size !== value.data_categories.length) invalid();
  return { connection_id: value.connection_id, config_version: value.config_version,
    model_id: value.model_id, data_categories: [...value.data_categories].sort() as Category[] };
}
function preference(value: unknown): Preference {
  if (!object(value) || typeof value.task_profile !== "string" || !Object.hasOwn(PROFILES, value.task_profile)
    || !integer(value.version) || !["available", "consent_required", "unavailable"].includes(String(value.state))
    || !Array.isArray(value.fallbacks) || value.fallbacks.length > 3) invalid();
  const primary = route(value.route);
  const fallbacks = value.fallbacks.map((item): Fallback => {
    if (!object(item) || !Array.isArray(item.on_errors) || !item.on_errors.length || item.on_errors.length > 3
      || !item.on_errors.every((code) => typeof code === "string" && Object.hasOwn(ERROR_LABELS, code))
      || new Set(item.on_errors).size !== item.on_errors.length) invalid();
    return { route: route(item.route), on_errors: [...item.on_errors].sort() as FallbackError[] };
  });
  const targets = [primary, ...fallbacks.map((item) => item.route)].map((r) => `${r.connection_id}/${r.config_version}/${r.model_id}`);
  if (new Set(targets).size !== targets.length) invalid();
  return { task_profile: value.task_profile as Profile, version: value.version, route: primary, fallbacks,
    state: value.state as Preference["state"] };
}
export async function listPreferences(fetchImpl: FetchLike = fetch): Promise<Preference[]> {
  const value = await providerRequest("/api/model-preferences", {}, fetchImpl);
  if (!object(value) || !Array.isArray(value.preferences) || value.preferences.length > 4) invalid();
  const result = value.preferences.map(preference);
  if (new Set(result.map((item) => item.task_profile)).size !== result.length) invalid();
  return result;
}
export async function savePreference(profile: Profile, input: PreferenceWrite, csrf: string,
  fetchImpl: FetchLike = fetch): Promise<Preference> {
  const expected = preference({ ...input, version: input.expected_version + 1, task_profile: profile, state: "available" });
  const value = preference(await providerRequest(`/api/model-preferences/${profile}`, {
    method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(input),
  }, fetchImpl));
  if (JSON.stringify(value) !== JSON.stringify(expected)) invalid();
  return value;
}
export function resolveConfiguration(items: Preference[], profile: Profile) {
  const direct = items.find((item) => item.task_profile === profile);
  const fallback = items.find((item) => item.task_profile === "default");
  return direct ? { source: "user_task_profile" as const, preference: direct }
    : fallback ? { source: "user_default" as const, preference: fallback }
      : { source: "system_default" as const, preference: undefined };
}
