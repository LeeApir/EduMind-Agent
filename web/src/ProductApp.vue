<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import { loadProductMode } from "./api/catalog";
import CatalogPage from "./components/CatalogPage.vue";

const DynamicApp = defineAsyncComponent(() => import("./App.vue"));
const ProviderSettings = defineAsyncComponent(() => import("./components/ProviderSettings.vue"));
const ModelPreferences = defineAsyncComponent(() => import("./components/ModelPreferences.vue"));
const settingsOpen = ref<"" | "connections" | "preferences">("");
const mode = ref<"catalog_only" | "dynamic" | "">("");
const error = ref("");
async function load(): Promise<void> {
  error.value = "";
  try { mode.value = await loadProductMode(); }
  catch { error.value = "无法读取课程入口，请重试。"; }
}
onMounted(load);
</script>

<template>
  <nav
    v-if="mode"
    class="product-navigation"
    aria-label="学习与模型设置"
  >
    <button
      type="button"
      :aria-current="!settingsOpen ? 'page' : undefined"
      @click="settingsOpen = ''"
    >
      课程学习
    </button>
    <button
      type="button"
      :aria-current="settingsOpen === 'connections' ? 'page' : undefined"
      @click="settingsOpen = 'connections'"
    >
      模型设置
    </button>
    <button
      type="button"
      :aria-current="settingsOpen === 'preferences' ? 'page' : undefined"
      @click="settingsOpen = 'preferences'"
    >
      档位与数据去向
    </button>
  </nav>
  <ProviderSettings
    v-if="settingsOpen === 'connections'"
    @close="settingsOpen = ''"
  />
  <ModelPreferences
    v-if="settingsOpen === 'preferences'"
    @close="settingsOpen = ''"
  />
  <div v-show="!settingsOpen">
    <CatalogPage v-if="mode === 'catalog_only'" />
    <DynamicApp v-else-if="mode === 'dynamic'" />
    <main
      v-else
      class="runtime-state"
      aria-live="polite"
    >
      <h1>启智学伴</h1>
      <p
        v-if="error"
        role="alert"
      >
        {{ error }}
      </p>
      <p v-else>
        正在读取课程目录。
      </p>
      <button
        v-if="error"
        type="button"
        @click="load"
      >
        重试读取
      </button>
    </main>
  </div>
</template>

<style scoped>
.runtime-state { padding: 48px; max-width: 800px; margin: auto; }
.product-navigation { max-width: 1400px; margin: auto; padding: 16px clamp(16px, 4vw, 56px) 0; display: flex; gap: 12px; flex-wrap: wrap; }
.product-navigation button { font: inherit; padding: 8px 14px; border: 1px solid #a6bcbd; color: #244c5a; border-radius: 5px; background: #fbfcf9; cursor: pointer; }
.product-navigation button[aria-current='page'] { background: #d7e4e0; }
.product-navigation button:focus-visible { outline: 3px solid #35656d; outline-offset: 3px; }
</style>
