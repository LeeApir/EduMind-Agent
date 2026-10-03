<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import { loadProductMode } from "./api/catalog";
import CatalogPage from "./components/CatalogPage.vue";

const DynamicApp = defineAsyncComponent(() => import("./App.vue"));
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
</template>

<style scoped>
.runtime-state { padding: 48px; max-width: 800px; margin: auto; }
</style>
