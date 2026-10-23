<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import { ensureCatalogSession, loadProductMode } from "./api/catalog";
import WorkspaceShell from "./components/WorkspaceShell.vue";
import WorkspaceState from "./components/WorkspaceState.vue";
import { readStored, writeStored } from "./api/freeCourses";
import CourseOutline from "./components/CourseOutline.vue";
import CourseWorkspace from "./components/CourseWorkspace.vue";
import LearningHome from "./components/LearningHome.vue";
import CatalogPage from "./components/CatalogPage.vue";

const DynamicApp = defineAsyncComponent(() => import("./App.vue"));
const ProviderSettings = defineAsyncComponent(() => import("./components/ProviderSettings.vue"));
const ModelPreferences = defineAsyncComponent(() => import("./components/ModelPreferences.vue"));
const page = ref("learning");
const opened = ref(new Set(["learning"]));
const owner = ref("");
const settingsReturn = ref("learning");
function navigate(value: string): void { if (["connections","preferences"].includes(value) && !["connections","preferences"].includes(page.value)) settingsReturn.value=page.value; page.value = value; opened.value.add(value); persist(); }
function persist(): void { if (owner.value) writeStored(`edumind:free:location:${owner.value}`, { page: page.value, course: selectedCourse.value, operation: selectedOperation.value, version: selectedVersion.value, scene: selectedScene.value }); }
const mode = ref<"catalog_only" | "dynamic" | "">("");
const error = ref("");
const selectedCourse = ref("");
const selectedOperation = ref("");
const selectedVersion = ref(1); const selectedScene = ref("");
function learn(version: number, scene: string): void { selectedVersion.value = version; selectedScene.value = scene; navigate("course"); }
function setOperation(id: string): void { selectedOperation.value = id; persist(); }
function openCourse(course: string, operation: string): void {
  selectedCourse.value = course; selectedOperation.value = operation;
  const saved = readStored<{version:number;scene:string}>(`edumind:free:reading:${owner.value}:${course}`);
  if (saved && Number.isInteger(saved.version) && saved.version>0 && typeof saved.scene==='string' && saved.scene) { selectedVersion.value=saved.version;selectedScene.value=saved.scene;navigate('course'); } else navigate('outline');
}
function position(version: number, scene: string): void { selectedVersion.value=version;selectedScene.value=scene;persist(); }
async function load(): Promise<void> {
  error.value = "";
  try {
    const runtime = await loadProductMode(); const session = await ensureCatalogSession(); if (owner.value && owner.value !== session.owner) { selectedCourse.value='';selectedOperation.value='';selectedScene.value='';page.value='learning'; }
    owner.value = session.owner;
    const saved = readStored<{page:string;course:string;operation:string;version:number;scene:string}>(`edumind:free:location:${owner.value}`);
    if (saved && ['outline','course'].includes(saved.page) && typeof saved.course === 'string' && typeof saved.operation === 'string') { selectedCourse.value=saved.course; selectedOperation.value=saved.operation; selectedVersion.value=Number.isInteger(saved.version) && saved.version>0 ? saved.version:1; selectedScene.value=typeof saved.scene==='string'?saved.scene:''; page.value=saved.page==='course' && !selectedScene.value?'outline':saved.page; }
    mode.value = runtime;
  }
  catch { error.value = "无法读取课程入口，请重试。"; }
}
onMounted(load);
</script>

<template>
  <WorkspaceShell
    :page="['outline','course'].includes(page) ? 'learning' : page"
    :focus-key="page"
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
          @close="navigate(settingsReturn)"
        />
      </section>
      <section v-show="page === 'preferences'">
        <ModelPreferences
          v-if="opened.has('preferences')"
          @close="navigate(settingsReturn)"
        />
      </section>
      <section v-show="page === 'learning'">
        <LearningHome
          :active="page === 'learning'"
          :mode="mode"
          @open="openCourse"
          @catalog="navigate('catalog')"
        />
      </section>
      <CourseOutline
        v-if="page === 'outline' && selectedCourse"
        :key="selectedCourse"
        :course-id="selectedCourse"
        :operation-id="selectedOperation"
        :mode="mode"
        @learn="learn"
        @operation="setOperation"
        @back="navigate('learning')"
      />
      <template v-if="page === 'course' && selectedCourse">
        <CourseWorkspace
          :key="selectedCourse"
          :mode="mode"
          :course-id="selectedCourse"
          :initial-version="selectedVersion"
          :initial-scene="selectedScene"
          :operation-id="selectedOperation"
          @outline="navigate('outline')"
          @home="navigate('learning')"
          @position="position"
        />
      </template>
      <section v-show="page === 'catalog'">
        <CatalogPage v-if="opened.has('catalog')" />
      </section>
      <section v-show="page === 'legacy'">
        <DynamicApp v-if="opened.has('legacy') && mode === 'dynamic'" />
      </section>
    </template>
  </WorkspaceShell>
</template>
