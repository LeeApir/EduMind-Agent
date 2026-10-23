<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import { loadProductMode } from "./api/catalog";
import WorkspaceShell from "./components/WorkspaceShell.vue";
import WorkspaceState from "./components/WorkspaceState.vue";
import CatalogPage from "./components/CatalogPage.vue";

const DynamicApp = defineAsyncComponent(() => import("./App.vue"));
const ProviderSettings = defineAsyncComponent(() => import("./components/ProviderSettings.vue"));
const ModelPreferences = defineAsyncComponent(() => import("./components/ModelPreferences.vue"));
const page = ref("learning");
const opened = ref(new Set(["learning"]));
function navigate(value: string): void { page.value = value; opened.value.add(value); }
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
  <WorkspaceShell
    :page="page"
    :dynamic="mode === 'dynamic'"
    @navigate="navigate"
  >
    <WorkspaceState
      v-if="!mode"
      :kind="error ? 'error' : 'loading'"
      :detail="error || '正在读取课程入口。'"
      :retry="Boolean(error)"
      @retry="load"
    />
    <template v-else>
      <section v-show="page === 'connections'">
        <ProviderSettings
          v-if="opened.has('connections')"
          @close="navigate('learning')"
        />
      </section>
      <section v-show="page === 'preferences'">
        <ModelPreferences
          v-if="opened.has('preferences')"
          @close="navigate('learning')"
        />
      </section>
      <section v-show="page === 'learning' || page === 'catalog'">
        <CatalogPage />
      </section>
      <section v-show="page === 'legacy'">
        <DynamicApp v-if="opened.has('legacy') && mode === 'dynamic'" />
      </section>
    </template>
  </WorkspaceShell>
</template>
