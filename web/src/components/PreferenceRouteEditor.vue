<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { DATA_LABELS, type Category } from "../api/modelPreferences";
import { getModels, ProviderSettingsError, type Connection, type Model } from "../api/providers";

export interface RouteDraft { connection_id: string; model_id: string; data_categories: Category[]; }
const props = defineProps<{ route: RouteDraft; connections: Connection[]; label: string; disabled: boolean }>();
const emit = defineEmits<{ "update:route": [value: RouteDraft] }>();
const selected = computed(() => props.connections.find((item) => item.id === props.route.connection_id));
const models = ref<Model[]>([]);
const error = ref("");
const cacheBusy = ref(false);
let active = true;
let revision = 0;
function changeConnection(event: Event): void {
  emit("update:route", { ...props.route, connection_id: (event.target as HTMLSelectElement).value, model_id: "" });
}
function changeModel(event: Event): void {
  emit("update:route", { ...props.route, model_id: (event.target as HTMLInputElement).value });
}
function changeCategory(category: Category, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
  emit("update:route", { ...props.route, data_categories: checked ? [...props.route.data_categories, category]
    : props.route.data_categories.filter((value) => value !== category) });
}
watch(selected, async (item) => {
  const token = ++revision; models.value = []; error.value = "";
  if (!item) { cacheBusy.value = false; return; }
  cacheBusy.value = true;
  try { const result = await getModels(item); if (active && token === revision) models.value = result.models; }
  catch (failure) { if (active && token === revision) error.value = failure instanceof ProviderSettingsError ? failure.message : "模型缓存暂时无法读取。"; }
  finally { if (active && token === revision) cacheBusy.value = false; }
}, { immediate: true });
onBeforeUnmount(() => { active = false; ++revision; });
</script>

<template>
  <fieldset
    :disabled="disabled"
    class="preference-route"
  >
    <legend>{{ label }}</legend>
    <label>{{ label }}连接
      <select
        :value="route.connection_id"
        @change="changeConnection"
      >
        <option value="">选择连接</option>
        <option
          v-for="item in connections"
          :key="item.id"
          :value="item.id"
          :disabled="!item.enabled"
        >
          {{ item.display_name }} · {{ item.provider_type }}{{ item.enabled ? '' : '（已禁用）' }}
        </option>
      </select>
    </label>
    <label>{{ label }}模型 ID<input
      :value="route.model_id"
      maxlength="160"
      autocomplete="off"
      spellcheck="false"
      @input="changeModel"
    ></label>
    <p class="preferences-hint">
      {{ cacheBusy ? '正在读取缓存；不联系模型服务。' : models.length ? `已缓存 ${models.length} 个模型，示例：${models.slice(0, 12).map(item => item.id).join('、')}` : '没有模型缓存，可填写精确 ID；名称不证明能力。' }}
    </p>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="selected"
      class="route-target"
    >
      <strong>{{ selected.provider_type }} · {{ selected.is_local ? '服务端白名单目标' : '公网目标' }}</strong><code>{{ selected.base_url }}</code>配置 {{ selected.config_version }} · {{ selected.credential_mode === 'temporary' ? '调用时需该目标单次 Key' : selected.credential_mode === 'none' ? '明确无需 Key' : '原会话内加密 Key' }}
    </p>
    <div
      class="route-data"
      role="group"
      :aria-label="`${label}数据类型`"
    >
      <label
        v-for="(name, category) in DATA_LABELS"
        :key="category"
        class="preferences-check"
      ><input
        type="checkbox"
        :checked="route.data_categories.includes(category)"
        @change="changeCategory(category, $event)"
      >{{ name }}</label>
    </div>
    <p class="preferences-hint">
      这是允许发送的类别上限。实际调用前仍需确认本次数据；本地服务也可能转发到云端。
    </p>
  </fieldset>
</template>
