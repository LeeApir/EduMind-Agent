<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { CatalogRequestError, ensureCatalogSession } from "../api/catalog";
import { listConnections, ProviderSettingsError, type Connection } from "../api/providers";
import { DATA_LABELS, ERROR_LABELS, PROFILES, listPreferences, resolveConfiguration, savePreference,
  type Category, type FallbackError, type Preference, type Profile, type Route } from "../api/modelPreferences";
import PreferenceRouteEditor, { type RouteDraft } from "./PreferenceRouteEditor.vue";

defineEmits<{ close: [] }>();
const connections = ref<Connection[]>([]);
const preferences = ref<Preference[]>([]);
const profile = ref<Profile>("default");
const csrf = ref("");
const busy = ref(false);
const error = ref("");
const notice = ref("");
const accepted = ref(false);
const primary = ref<RouteDraft>(emptyRoute());
const fallbacks = ref<{ route: RouteDraft; on_errors: FallbackError[] }[]>([]);
let active = true;
function emptyRoute(categories: Category[] = ["learning_goal"]): RouteDraft { return { connection_id: "", model_id: "", data_categories: categories }; }
const selectedPreference = computed(() => preferences.value.find((item) => item.task_profile === profile.value));
const sourceNames = { user_task_profile: "本档位设置", user_default: "用户默认连接", system_default: "服务端系统默认" };
const stateNames = { available: "配置有效，连通性与能力另验", consent_required: "配置已变化，需重新同意", unavailable: "选择不可用，不自动降级" };
watch([primary, fallbacks], () => { accepted.value = false; notice.value = ""; }, { deep: true });
function copy(item: Route): RouteDraft { return { connection_id: item.connection_id, model_id: item.model_id, data_categories: [...item.data_categories] }; }
function choose(value: Profile): void {
  if (busy.value) return;
  profile.value = value; error.value = ""; notice.value = ""; accepted.value = false;
  const saved = selectedPreference.value;
  primary.value = saved ? copy(saved.route) : emptyRoute(value === "review" ? ["content_for_review"] : ["learning_goal"]);
  fallbacks.value = saved ? saved.fallbacks.map((item) => ({ route: copy(item.route), on_errors: [...item.on_errors] })) : [];
}
function message(failure: unknown): string {
  if (failure instanceof CatalogRequestError && failure.status === 401) return new ProviderSettingsError("UNAUTHORIZED").message;
  return failure instanceof ProviderSettingsError ? failure.message : "模型档位设置暂时不可用，请重新读取。";
}
async function load(): Promise<void> {
  if (busy.value) return;
  busy.value = true; error.value = ""; accepted.value = false;
  let loaded = false;
  try {
    const session = await ensureCatalogSession();
    if (!active) return;
    const [items, saved] = await Promise.all([listConnections(), listPreferences()]);
    if (!active) return;
    csrf.value = session.csrf; connections.value = items; preferences.value = saved;
    loaded = true;
  } catch (failure) { if (active) error.value = message(failure); }
  finally { if (active) busy.value = false; }
  if (active && loaded) choose(profile.value);
}
function addFallback(): void {
  if (!busy.value && fallbacks.value.length < 3) fallbacks.value.push({ route: emptyRoute(), on_errors: [] });
}
function bind(draft: RouteDraft): Route {
  const item = connections.value.find((value) => value.id === draft.connection_id);
  if (!item || !item.enabled || !draft.model_id.trim() || !draft.data_categories.length) throw new Error("填写每个目标的连接、模型 ID 和数据类型。");
  if (Date.parse(item.credential_expires_at) <= Date.now() || item.credential_mode === "persistent" && item.credential_state !== "present") {
    throw new Error("目标凭据不可用，请先在连接管理中重新输入或选择临时模式。");
  }
  return { connection_id: item.id, config_version: item.config_version, model_id: draft.model_id.trim(), data_categories: [...draft.data_categories] };
}
async function save(): Promise<void> {
  if (busy.value || !accepted.value || !csrf.value) return;
  let input;
  try {
    input = { expected_version: selectedPreference.value?.version ?? 0, route: bind(primary.value),
      fallbacks: fallbacks.value.map((item) => ({ route: bind(item.route), on_errors: [...item.on_errors] })), consent_accepted: true as const };
    if (input.fallbacks.some((item) => !item.on_errors.length)) throw new Error("请为每个回退目标选择触发条件；默认不启用回退。");
    const routes = [input.route, ...input.fallbacks.map((item) => item.route)];
    if (new Set(routes.map((item) => `${item.connection_id}/${item.model_id}`)).size !== routes.length) throw new Error("主目标和回退目标不可重复。");
  } catch (failure) { error.value = failure instanceof Error ? failure.message : "请检查设置。"; accepted.value = false; return; }
  busy.value = true; error.value = ""; notice.value = ""; accepted.value = false;
  try {
    const saved = await savePreference(profile.value, input, csrf.value);
    if (!active) return;
    preferences.value = [...preferences.value.filter((item) => item.task_profile !== saved.task_profile), saved];
    notice.value = "档位已保存；下方按服务端回执展示配置解析。本次没有调用模型。";
  } catch (failure) { if (active) error.value = message(failure); }
  finally { if (active) busy.value = false; }
}
function target(route: Route): string {
  const item = connections.value.find((value) => value.id === route.connection_id && value.config_version === route.config_version);
  return item ? `${item.display_name} · ${item.provider_type} · ${route.model_id} · ${item.is_local ? '服务端白名单目标' : '公网目标'} · ${item.base_url}`
    : `连接 ${route.connection_id} · 模型 ${route.model_id} · 已保存配置 ${route.config_version}（当前目标不可确认）`;
}
onMounted(load);
onBeforeUnmount(() => { active = false; accepted.value = false; });
</script>

<template>
  <main
    class="preferences-desk"
    :aria-busy="busy"
  >
    <header class="preferences-heading">
      <div><p>启智学伴 · 模型分工</p><h1>档位与数据去向</h1><p>为不同任务选择模型，逐一确认允许发送的数据。</p></div><button
        type="button"
        @click="$emit('close')"
      >
        返回课程
      </button>
    </header>
    <p class="preferences-hint">
      设置只保存元数据。课程目录仍独立可用；动态学习须另行验收与批准。默认档位同时是用户默认连接，审核档位可以独立选择。
    </p>
    <p
      v-if="error"
      role="alert"
      class="preferences-message"
    >
      {{ error }}
    </p><p
      v-if="notice"
      role="status"
      class="preferences-message"
    >
      {{ notice }}
    </p>
    <div class="preferences-layout">
      <aside aria-label="任务档位">
        <button
          v-for="(name, value) in PROFILES"
          :key="value"
          type="button"
          :disabled="busy"
          :aria-current="profile === value ? 'page' : undefined"
          @click="choose(value)"
        >
          {{ name }}
        </button><button
          type="button"
          :disabled="busy"
          @click="load"
        >
          重新读取设置
        </button>
      </aside>
      <form
        class="preferences-form"
        @submit.prevent="save"
      >
        <h2>{{ PROFILES[profile] }}</h2>
        <p
          v-if="selectedPreference"
          class="preferences-hint"
        >
          已保存版本 {{ selectedPreference.version }} · {{ stateNames[selectedPreference.state] }}。改动后需重新同意；不可用的显式选择不会使用默认连接。
        </p>
        <PreferenceRouteEditor
          v-model:route="primary"
          :connections="connections"
          label="主目标"
          :disabled="busy"
        />
        <section
          class="fallback-settings"
          aria-label="显式回退"
        >
          <h3>显式回退 · {{ fallbacks.length }}/3</h3><p class="preferences-hint">
            默认不回退。只有所选错误才按顺序联系下一个目标；鉴权失败、无效结果或流式输出不会切换。
          </p>
          <article
            v-for="(fallback, index) in fallbacks"
            :key="index"
          >
            <PreferenceRouteEditor
              v-model:route="fallback.route"
              :connections="connections"
              :label="`回退 ${index + 1}`"
              :disabled="busy"
            />
            <fieldset :disabled="busy">
              <legend>{{ `回退 ${index + 1} 触发条件` }}</legend><label
                v-for="(name, code) in ERROR_LABELS"
                :key="code"
                class="preferences-check"
              ><input
                v-model="fallback.on_errors"
                type="checkbox"
                :value="code"
              >{{ name }}</label>
            </fieldset>
            <button
              type="button"
              :disabled="busy"
              @click="fallbacks.splice(index, 1)"
            >
              {{ `移除回退 ${index + 1}` }}
            </button>
          </article>
          <button
            type="button"
            :disabled="busy || fallbacks.length >= 3"
            @click="addFallback"
          >
            添加回退目标
          </button>
        </section>
        <label class="preferences-check preferences-consent"><input
          v-model="accepted"
          type="checkbox"
          :disabled="busy"
        >我同意以上主目标和每个回退目标的服务、模型、当前配置版本及数据类型。保存不代表授权实际请求预算，调用前仍需确认本次数据去向。</label>
        <button
          type="submit"
          :disabled="busy || !accepted || !csrf"
        >
          保存当前档位
        </button>
      </form>
    </div>
    <section
      class="preferences-resolution"
      aria-label="配置解析结果"
    >
      <h2>配置解析结果</h2><p class="preferences-hint">
        仅展示当前保存配置；实际调用前还会核验能力、有效期、单次同意及预算。临时覆盖仅对本次任务生效。未配置档位才继承用户默认或系统默认。
      </p>
      <article
        v-for="(name, value) in PROFILES"
        :key="value"
      >
        <h3>{{ name }} · {{ sourceNames[resolveConfiguration(preferences, value).source] }}</h3>
        <template v-if="resolveConfiguration(preferences, value).preference">
          <p>{{ stateNames[resolveConfiguration(preferences, value).preference!.state] }}</p><code>{{ target(resolveConfiguration(preferences, value).preference!.route) }}</code>
          <p>数据类型：{{ resolveConfiguration(preferences, value).preference!.route.data_categories.map(item => DATA_LABELS[item]).join('、') }}</p>
          <ol v-if="resolveConfiguration(preferences, value).preference!.fallbacks.length">
            <li
              v-for="(fallback, index) in resolveConfiguration(preferences, value).preference!.fallbacks"
              :key="index"
            >
              <code>{{ target(fallback.route) }}</code><p>触发：{{ fallback.on_errors.map(item => ERROR_LABELS[item]).join('、') }}；数据类型：{{ fallback.route.data_categories.map(item => DATA_LABELS[item]).join('、') }}</p>
            </li>
          </ol><p v-else>
            回退：未启用
          </p>
        </template><p v-else>
          未配置用户选择，使用服务端默认配置。尚未实际调用；本页面不读取系统 Key。
        </p>
      </article>
    </section>
  </main>
</template>

<style>
.preferences-desk { color: #17253a; max-width: 1400px; margin: auto; padding: 24px clamp(16px, 4vw, 56px); }.preferences-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding-bottom: 24px; border-bottom: 1px solid #b8c7cb; }.preferences-heading h1 { font-size: 30px; margin: 8px 0; }.preferences-heading p { color: #536876; }.preferences-heading p:first-child { color: #35656d; font-size: 12px; letter-spacing: .06em; }
.preferences-layout { display: grid; grid-template-columns: 260px minmax(0,1fr); gap: clamp(24px,4vw,56px); margin-top: 28px; }.preferences-layout aside { display: flex; flex-direction: column; align-items: stretch; gap: 12px; }.preferences-layout aside button { text-align: left; }.preferences-layout aside button[aria-current='page'] { background: #d7e4e0; border-left: 3px solid #35656d; }.preferences-form { background: #fbfcf9; border: 1px solid #b8c7cb; padding: clamp(18px,3vw,32px); min-width: 0; }.preferences-form h2 { margin-top: 0; font-size: 20px; }
.preferences-desk button, .preferences-desk select, .preferences-desk input:not([type='checkbox']) { font: inherit; color: #244c5a; border: 1px solid #a6bcbd; padding: 10px 14px; border-radius: 5px; background: #fbfcf9; }.preferences-desk button { cursor: pointer; }.preferences-desk button:disabled { opacity: .5; cursor: default; }.preferences-desk :is(button,input,select):focus-visible { outline: 3px solid #35656d; outline-offset: 3px; }.preferences-desk fieldset { border: 0; padding: 0; min-width: 0; margin: 20px 0; }.preferences-desk legend { font-size: 14px; font-weight: 650; margin-bottom: 16px; }.preference-route > label { display: block; font-size: 14px; font-weight: 600; margin: 16px 0; }.preferences-desk input:not([type='checkbox']), .preferences-desk select { display: block; margin-top: 8px; width: 100%; max-width: 640px; }.preferences-check { display: flex; gap: 10px; align-items: flex-start; line-height: 1.8; font-size: 14px; margin: 12px 0; }.preferences-check input { margin-top: 6px; flex: 0 0 auto; }.preferences-hint { color: #536876; font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }.route-target { border-left: 3px solid #35656d; background: #eaf0f2; padding: 16px; font-size: 13px; line-height: 1.8; }.preferences-desk code { display: block; overflow-wrap: anywhere; font: 14px/1.8 'SFMono-Regular', Consolas, monospace; }.fallback-settings { border-top: 1px solid #b8c7cb; border-bottom: 1px solid #b8c7cb; padding: 20px 0; margin: 24px 0; }.fallback-settings article { border-left: 3px solid #b8c7cb; padding-left: 20px; margin: 28px 0; }.preferences-consent { background: #eaf0f2; padding: 16px; }.preferences-resolution { margin-top: 36px; border-top: 1px solid #b8c7cb; padding-top: 24px; }.preferences-resolution article { margin: 24px 0; background: #fbfcf9; border-left: 4px solid #35656d; padding: 20px; }.preferences-message { padding: 16px; background: #fbfcf9; border-left: 3px solid #f06e43; line-height: 1.8; }
@media(max-width:760px) { .preferences-layout { grid-template-columns: 1fr; }.preferences-layout aside { flex-direction: row; flex-wrap: wrap; }.preferences-desk { padding: 20px 16px; } }
</style>
