<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ensureCatalogSession } from "../api/catalog";
import {
  CAPABILITY_LABELS, ProviderSettingsError, deleteConnection, getModels, listConnections,
  refreshModels, saveConnection, testConnection, uploadTemporary,
  type Connection, type ConnectionWrite, type CredentialMode, type ModelList, type ProbeInput,
  type ProbeResult, type ProviderType,
} from "../api/providers";

defineEmits<{ close: [] }>();
const connections = ref<Connection[]>([]);
const selectedId = ref("");
const csrf = ref("");
const busy = ref(false);
const error = ref("");
const notice = ref("");
const key = ref("");
const temporaryKey = ref("");
const clearSecret = ref(false);
const deleteConfirmed = ref(false);
const consent = ref(false);
const modelId = ref("");
const cache = ref<ModelList | null>(null);
const tested = ref<ProbeResult | null>(null);
const form = reactive({ display_name: "", provider_type: "openai-compatible" as ProviderType,
  base_url: "", credential_mode: "persistent" as CredentialMode, enabled: true });
let active = true;
let revision = 0;
const selected = computed(() => connections.value.find((item) => item.id === selectedId.value));
const dirty = computed(() => Boolean(key.value || clearSecret.value) || !selected.value
  || Object.entries(form).some(([field, value]) => selected.value?.[field as keyof Connection] !== value));
const canOperate = computed(() => Boolean(selected.value?.enabled && !dirty.value && modelId.value.trim()
  && consent.value && !busy.value && (selected.value.credential_mode !== "temporary" || temporaryKey.value)));
const capabilities = computed(() => tested.value?.capabilities
  ?? cache.value?.models.find((model) => model.id === modelId.value)?.capabilities);
const sourceLabel = computed(() => ({ declared: "服务声明", verified: "已验证", unknown: "未知" })[capabilities.value?.source ?? "unknown"]);
const modeNames: Record<CredentialMode, string> = { persistent: "会话内持久化", temporary: "单次临时 Key", none: "明确无需 Key" };
const stateNames: Record<Connection["credential_state"], string> = { present: "已保存", missing: "未保存", expired: "已到期", revoked: "已撤销" };
function credentialLabel(item: Connection): string {
  return item.credential_mode === "none" ? "无需 Key"
    : item.credential_mode === "temporary" ? "每次操作需输入 Key" : stateNames[item.credential_state];
}
const expiration = computed(() => selected.value ? new Date(selected.value.credential_expires_at).toLocaleString("zh-CN") : "");
function message(failure: unknown): string {
  return failure instanceof ProviderSettingsError ? failure.message : "连接设置暂时不可用，请检查网络后重试。";
}
function erase(): void { key.value = ""; temporaryKey.value = ""; clearSecret.value = false; }
function resetConfirmation(): void { consent.value = false; tested.value = null; deleteConfirmed.value = false; }
watch([() => form.provider_type, () => form.base_url, () => form.credential_mode], () => { erase(); resetConfirmation(); });
watch(modelId, resetConfirmation);

async function load(): Promise<void> {
  if (busy.value) return;
  const token = ++revision;
  busy.value = true; error.value = ""; erase(); resetConfirmation();
  try {
    const session = await ensureCatalogSession();
    if (!active || token !== revision) return;
    csrf.value = session.csrf;
    const items = await listConnections();
    if (!active || token !== revision) return;
    connections.value = items;
    selectLocal(items.find((item) => item.id === selectedId.value) ?? items[0]);
  } catch (failure) { if (active && token === revision) error.value = message(failure); }
  finally { if (active && token === revision) busy.value = false; }
  if (active && token === revision && selected.value) await loadCache(selected.value);
}
function selectLocal(item?: Connection): void {
  erase(); resetConfirmation(); cache.value = null; modelId.value = ""; notice.value = "";
  selectedId.value = item?.id ?? "";
  Object.assign(form, item ? {
    display_name: item.display_name, provider_type: item.provider_type, base_url: item.base_url,
    credential_mode: item.credential_mode, enabled: item.enabled,
  } : { display_name: "", provider_type: "openai-compatible", base_url: "", credential_mode: "persistent", enabled: true });
}
async function loadCache(item: Connection): Promise<void> {
  const token = ++revision;
  busy.value = true;
  try {
    const result = await getModels(item);
    if (active && token === revision && selectedId.value === item.id) {
      cache.value = result; modelId.value = result.models[0]?.id ?? "";
    }
  } catch (failure) { if (active && token === revision) error.value = message(failure); }
  finally { if (active && token === revision) busy.value = false; }
}
async function choose(item: Connection): Promise<void> {
  if (busy.value) return;
  error.value = ""; selectLocal(item); await loadCache(item);
}
function add(): void { if (!busy.value) { ++revision; error.value = ""; selectLocal(); } }
async function save(): Promise<void> {
  if (busy.value || !csrf.value) return;
  if (!form.display_name.trim() || !form.base_url.trim()
    || (!selected.value && form.credential_mode === "persistent" && !key.value)) {
    error.value = "请填写连接名称、服务地址；持久化连接还需输入 Key。"; return;
  }
  if (!selected.value && clearSecret.value) return;
  const current = selected.value;
  const input: ConnectionWrite = { ...form, display_name: form.display_name.trim(), base_url: form.base_url.trim() };
  if (form.credential_mode === "persistent" && key.value) input.secret = { api_key: key.value };
  else if (current && (clearSecret.value || form.credential_mode !== "persistent" && current.credential_mode === "persistent")) input.secret = null;
  erase(); busy.value = true; error.value = ""; notice.value = ""; resetConfirmation();
  let saved: Connection | undefined;
  try {
    saved = await saveConnection(input, csrf.value, current);
    if (!active) return;
    connections.value = current ? connections.value.map((item) => item.id === current.id ? saved! : item) : [...connections.value, saved];
    selectLocal(saved); notice.value = "连接已保存。保存不会测试或下载模型。";
  } catch (failure) { if (active) error.value = message(failure); }
  finally { delete input.secret; if (active) busy.value = false; }
  if (active && saved) await loadCache(saved);
}
async function remove(): Promise<void> {
  const item = selected.value;
  if (!item || !deleteConfirmed.value || busy.value) return;
  erase(); busy.value = true; error.value = "";
  try {
    await deleteConnection(item, csrf.value);
    if (!active) return;
    connections.value = connections.value.filter((value) => value.id !== item.id);
    selectLocal(); notice.value = "连接已删除，凭据和旧选择已失效。";
  } catch (failure) { if (active) error.value = message(failure); }
  finally { if (active) busy.value = false; }
}
async function operate(purpose: "connection_test" | "model_refresh"): Promise<void> {
  const item = selected.value;
  if (!item || !canOperate.value) return;
  const input: ProbeInput = { operation_id: crypto.randomUUID(), consent: {
    accepted: true, config_version: item.config_version, model_id: modelId.value.trim(), data_categories: ["probe"],
  } };
  let secret = temporaryKey.value;
  erase(); busy.value = true; error.value = ""; notice.value = "";
  try {
    if (item.credential_mode === "temporary") {
      input.temporary_handle = await uploadTemporary(item, secret, input, purpose, csrf.value);
      secret = "";
      if (!active) return;
    }
    if (purpose === "connection_test") {
      const result = await testConnection(item, input, csrf.value);
      if (active) { tested.value = result; notice.value = "文本连接测试完成。高级能力仍以各项标记为准。"; }
    } else {
      const result = await refreshModels(item, input, csrf.value);
      if (active) { cache.value = result; notice.value = result.models.length ? "模型缓存已更新。" : "服务返回空模型列表，请确认已安装或已授权模型。"; }
    }
  } catch (failure) { if (active) error.value = message(failure); }
  finally { secret = ""; delete input.temporary_handle; if (active) { busy.value = false; consent.value = false; } }
}
onMounted(load);
onBeforeUnmount(() => { active = false; ++revision; erase(); resetConfirmation(); });
</script>

<template>
  <main
    class="provider-desk"
    :aria-busy="busy"
  >
    <header class="provider-heading">
      <div>
        <p class="provider-eyebrow">
          启智学伴 · 连接管理
        </p><h1>模型设置</h1><p>先选择服务，再确认数据发往哪里。</p>
      </div>
      <button
        type="button"
        @click="$emit('close')"
      >
        返回课程
      </button>
    </header>
    <p class="provider-session">
      凭据随原匿名会话到期，最长 2 小时；到期后需重新输入。课程目录不依赖这些连接。
    </p>
    <p
      v-if="error"
      role="alert"
      class="provider-error"
    >
      {{ error }}
    </p>
    <p
      v-if="notice"
      role="status"
      class="provider-notice"
    >
      {{ notice }}
    </p>
    <div class="provider-layout">
      <aside
        class="provider-index"
        aria-label="已保存连接"
      >
        <div class="provider-actions">
          <h2>我的连接</h2><button
            type="button"
            :disabled="busy"
            @click="add"
          >
            新增连接
          </button>
        </div>
        <p v-if="!connections.length">
          还没有连接。可添加兼容服务，或由管理员放行的 Ollama。
        </p>
        <ul>
          <li
            v-for="item in connections"
            :key="item.id"
          >
            <button
              type="button"
              :disabled="busy"
              :aria-current="item.id === selectedId ? 'true' : undefined"
              @click="choose(item)"
            >
              <strong>{{ item.display_name }}</strong><small>{{ item.provider_type === 'ollama' ? 'Ollama' : item.provider_type }} · {{ modeNames[item.credential_mode] }}</small><small>{{ item.enabled ? credentialLabel(item) : '已禁用' }}</small>
            </button>
          </li>
        </ul>
        <button
          type="button"
          :disabled="busy"
          @click="load"
        >
          重新读取连接
        </button>
      </aside>
      <section
        class="provider-editor"
        aria-label="连接详情"
      >
        <form
          class="provider-form"
          @submit.prevent="save"
        >
          <h2>{{ selected ? '编辑连接' : '新增连接' }}</h2>
          <fieldset :disabled="busy">
            <legend>服务与凭据</legend>
            <label for="provider-name">连接名称</label><input
              id="provider-name"
              v-model="form.display_name"
              maxlength="80"
              autocomplete="off"
              placeholder="例如：我的学习服务"
            >
            <label for="provider-type">服务类型</label><select
              id="provider-type"
              v-model="form.provider_type"
            >
              <option value="openai-compatible">
                OpenAI-compatible
              </option><option value="ollama">
                Ollama（服务端本地白名单）
              </option><option value="anthropic">
                Anthropic（原生 Messages）
              </option><option value="gemini">
                Google Gemini（原生 GenerateContent）
              </option><option value="spark">
                讯飞星火（HTTP APIPassword）
              </option>
            </select>
            <label for="provider-url">服务地址</label><input
              id="provider-url"
              v-model="form.base_url"
              maxlength="500"
              autocomplete="off"
              spellcheck="false"
              :placeholder="form.provider_type === 'ollama' ? 'http://127.0.0.1:11434' : form.provider_type === 'gemini' ? 'https://服务地址/v1beta' : 'https://服务地址/v1'"
            >
            <p class="provider-hint">
              {{ form.provider_type === 'anthropic' ? 'Anthropic 地址需包含版本前缀（如 /v1）。' : form.provider_type === 'gemini' ? 'Gemini 地址需包含版本前缀（如 /v1beta）；不要包含模型路径或 Key。' : form.provider_type === 'spark' ? '星火使用对应模型的 HTTP 服务前缀（如 /v1、/v2 或 /x2），Key 填 HTTP APIPassword；不支持 WebSocket 签名凭据。' : 'Ollama 使用服务根地址。' }}地址相对于学伴服务端，本地地址需管理员明确放行。
            </p>
            <label for="provider-mode">Key 保存方式</label><select
              id="provider-mode"
              v-model="form.credential_mode"
            >
              <option value="persistent">
                会话内持久化（服务端加密）
              </option><option value="temporary">
                单次临时 Key（不写数据库）
              </option><option value="none">
                明确无需 Key（不借用系统 Key）
              </option>
            </select>
            <template v-if="form.credential_mode === 'persistent'">
              <label for="provider-key">{{ selected ? '替换 Key（留空保留，改变地址或类型会清除旧 Key）' : 'API Key' }}</label><input
                id="provider-key"
                v-model="key"
                type="password"
                autocomplete="off"
                spellcheck="false"
                maxlength="4096"
                :disabled="clearSecret"
              ><label
                v-if="selected"
                class="provider-check"
              ><input
                v-model="clearSecret"
                type="checkbox"
                @change="key = ''"
              >清除已保存的 Key</label>
            </template>
            <p
              v-else
              class="provider-hint"
            >
              {{ form.credential_mode === 'temporary' ? '只保存连接信息。测试或刷新时重新输入 Key，绑定那一次操作。' : '仅适合明确允许无 Key 访问的服务。' }}
            </p>
            <label class="provider-check"><input
              v-model="form.enabled"
              type="checkbox"
            >启用这条连接</label>
          </fieldset>
          <div class="provider-actions">
            <button
              type="submit"
              :disabled="busy || !csrf"
            >
              保存连接
            </button><span>保存不调用模型。</span>
          </div>
        </form>
        <section
          v-if="selected"
          class="provider-destination"
          aria-label="本次发送目标"
        >
          <p class="provider-eyebrow">
            本次发送目标 · 配置 {{ selected.config_version }}
          </p><h2>{{ selected.display_name }}</h2>
          <code>{{ tested?.target ?? selected.base_url }}</code>
          <p>{{ (tested?.is_local ?? selected.is_local) ? '服务端白名单内目标' : '公网目标' }} · {{ modeNames[selected.credential_mode] }} · {{ selected.enabled ? credentialLabel(selected) : '已禁用' }}</p>
          <p class="provider-hint">
            凭据到期：{{ expiration }}。本地目标不保证该服务不会转发到云端。
          </p>
          <p
            v-if="dirty"
            class="provider-hint"
          >
            有未保存的改动。请先保存，再确认新目标。
          </p>
          <fieldset :disabled="busy || dirty">
            <legend>选择模型并显式测试</legend>
            <label for="provider-model">模型 ID</label><input
              id="provider-model"
              v-model="modelId"
              list="provider-model-list"
              maxlength="160"
              autocomplete="off"
              spellcheck="false"
              placeholder="服务中已安装或已授权的精确模型 ID"
            >
            <datalist id="provider-model-list">
              <option
                v-for="model in cache?.models ?? []"
                :key="model.id"
                :value="model.id"
              />
            </datalist>
            <p class="provider-hint">
              {{ cache?.refreshed_at ? `缓存 ${cache.models.length} 个模型；更新时间 ${new Date(cache.refreshed_at).toLocaleString('zh-CN')}` : '暂无模型缓存，可输入已知模型 ID。页面打开不会自动刷新。' }}
            </p>
            <template v-if="selected.credential_mode === 'temporary'">
              <label for="provider-temporary-key">本次操作的临时 Key</label><input
                id="provider-temporary-key"
                v-model="temporaryKey"
                type="password"
                maxlength="4096"
                autocomplete="off"
                spellcheck="false"
              >
            </template>
            <label class="provider-check provider-consent"><input
              v-model="consent"
              type="checkbox"
            >我同意联系以上服务与模型，只发送连接探测数据，不发送学习目标、画像或历史。测试和刷新可能调用服务。</label>
          </fieldset>
          <div class="provider-actions">
            <button
              type="button"
              :disabled="!canOperate"
              @click="operate('connection_test')"
            >
              测试连接一次
            </button><button
              type="button"
              :disabled="!canOperate"
              @click="operate('model_refresh')"
            >
              刷新模型一次
            </button>
          </div>
          <dl class="provider-capabilities">
            <template
              v-for="(label, flag) in CAPABILITY_LABELS"
              :key="flag"
            >
              <dt>{{ label }}</dt><dd>{{ capabilities?.[flag] === true ? '支持' : capabilities?.[flag] === false ? '不支持' : '未知' }}</dd>
            </template>
          </dl>
          <p class="provider-hint">
            能力来源：{{ sourceLabel }}。服务声明不等于真实验证，文本连接成功不证明高级能力。
          </p>
          <section class="provider-delete">
            <label class="provider-check"><input
              v-model="deleteConfirmed"
              type="checkbox"
              :disabled="busy"
            >确认删除 {{ selected.display_name }} 的连接与凭据</label><button
              type="button"
              :disabled="busy || !deleteConfirmed"
              @click="remove"
            >
              删除连接
            </button>
          </section>
        </section>
      </section>
    </div>
  </main>
</template>

<style scoped>
.provider-desk { --ink: #17253a; --muted: #536876; --teal: #35656d; --paper: #fbfcf9; --line: #b8c7cb; max-width: 1400px; margin: auto; padding: 24px clamp(16px, 4vw, 56px); color: var(--ink); }
.provider-heading, .provider-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.provider-heading { border-bottom: 1px solid var(--line); padding-bottom: 24px; }.provider-heading h1 { font-size: 30px; margin: 6px 0; }.provider-heading p:last-child { color: var(--muted); margin-bottom: 0; }
.provider-eyebrow { font-size: 12px; letter-spacing: .06em; color: var(--teal); margin: 0; }.provider-session { line-height: 1.8; color: var(--muted); }
.provider-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: clamp(24px, 4vw, 56px); margin-top: 28px; }.provider-index h2 { font-size: 16px; }.provider-index p { font-size: 14px; line-height: 1.7; color: var(--muted); }
.provider-index ul { list-style: none; padding: 0; margin: 16px 0; }.provider-index li { border-top: 1px solid var(--line); }.provider-index li button { width: 100%; text-align: left; border: 0; border-radius: 0; padding: 16px 12px; background: transparent; }.provider-index li button[aria-current='true'] { background: #d7e4e0; border-left: 3px solid var(--teal); }.provider-index small { display: block; color: var(--muted); margin-top: 6px; }
.provider-editor { min-width: 0; }.provider-editor h2 { font-size: 20px; margin: 0 0 20px; }.provider-form, .provider-destination { background: var(--paper); border: 1px solid var(--line); padding: clamp(18px, 3vw, 32px); }.provider-destination { border-left: 4px solid var(--teal); margin-top: 24px; }.provider-destination h2 { margin: 10px 0; }.provider-destination code { display: block; overflow-wrap: anywhere; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 15px; line-height: 1.7; }.provider-destination > p { line-height: 1.7; }
.provider-desk button, .provider-desk input:not([type='checkbox']), .provider-desk select { font: inherit; border: 1px solid #a6bcbd; padding: 10px 14px; background: var(--paper); color: #244c5a; border-radius: 5px; }.provider-desk button { cursor: pointer; }.provider-desk button:disabled { opacity: .5; cursor: default; }.provider-desk :is(button,input,select):focus-visible { outline: 3px solid var(--teal); outline-offset: 3px; }
.provider-desk fieldset { border: 0; padding: 0; margin: 20px 0; min-width: 0; }.provider-desk legend { font-size: 14px; font-weight: 650; margin-bottom: 16px; }.provider-desk label:not(.provider-check) { display: block; font-size: 14px; font-weight: 600; margin: 16px 0 8px; }.provider-desk input:not([type='checkbox']), .provider-desk select { width: 100%; max-width: 640px; }.provider-check { display: flex; align-items: flex-start; gap: 10px; line-height: 1.8; margin: 16px 0; font-size: 14px; }.provider-check input { margin-top: 6px; flex: 0 0 auto; }.provider-consent { background: #eaf0f2; padding: 12px 16px; }.provider-hint, .provider-actions span { font-size: 13px; line-height: 1.8; color: var(--muted); }
.provider-capabilities { display: grid; grid-template-columns: 1fr 1fr; border-top: 1px solid var(--line); padding-top: 16px; font-size: 14px; }.provider-capabilities dt, .provider-capabilities dd { padding: 6px 0; margin: 0; }.provider-capabilities dd { text-align: right; color: var(--muted); }.provider-delete { border-top: 1px solid var(--line); margin-top: 24px; padding-top: 12px; }.provider-error, .provider-notice { border-left: 3px solid #f06e43; background: var(--paper); padding: 16px; line-height: 1.8; }.provider-notice { border-color: var(--teal); }
@media (max-width: 760px) { .provider-layout { grid-template-columns: minmax(0, 1fr); gap: 24px; }.provider-index ul { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }.provider-index strong, .provider-index small { overflow-wrap: anywhere; } }
</style>
