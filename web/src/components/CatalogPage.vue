<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  CatalogRequestError, controlPresetDemo, createCatalogClassroom, enrollCatalog,
  ensureCatalogSession, loadCatalog, loadCatalogUnit, loadPresetDemo,
  type CatalogClassroom, type CatalogListing, type CatalogScene, type CatalogUnit,
  type PresetDemo, type ResourceType,
} from "../api/catalog";
import { downloadFile, notesUrl } from "../api/downloads";
import type { QuizSubmissionResult } from "../api/quiz";
import AnimationPanel from "./AnimationPanel.vue";
import LearningPathPanel from "./LearningPathPanel.vue";
import PublishedLearningWorkspace from "./PublishedLearningWorkspace.vue";

const catalog = ref<CatalogListing | null>(null);
const owner = ref("");
const csrf = ref("");
const selectedRelease = ref("");
const unit = ref<CatalogUnit | null>(null);
const scene = ref<CatalogScene | null>(null);
const demo = ref<PresetDemo | null>(null);
const classroom = ref<CatalogClassroom | null>(null);
const resourceType = ref<ResourceType>("explanation");
const receipt = ref<QuizSubmissionResult | null>(null);
const refreshToken = ref(0);
const busy = ref(false);
const error = ref("");
const downloading = ref(false);
const downloadError = ref("");
let generation = 0;
let pendingEnrollment: { release: string; node: string; key: string; unitId?: string } | null = null;
let pendingDemo: { unit: string; action: "begin" | "exit"; resource: ResourceType; revision: number; key: string } | null = null;
const release = computed(() => catalog.value?.releases.find((item) => item.id === selectedRelease.value));
const unitRelease = computed(() => catalog.value?.releases.find((item) => item.id === unit.value?.catalog_release_id));
const node = computed(() => unitRelease.value?.nodes.find((item) => item.id === unit.value?.knowledge_node_id));
const demoActive = computed(() => classroom.value?.detour?.kind === "catalog_demo");
const supportedAnimation = computed(() => ["linked-list-insertion", "linked-list-deletion"].includes(unit.value?.knowledge_node_id ?? ""));
const storageKey = () => `edumind:catalog:last:${owner.value}`;
function stored(key: string): string { try { return sessionStorage.getItem(key) ?? ""; } catch { return ""; } }
function store(key: string, value: string): void { try { sessionStorage.setItem(key, value); } catch { /* Optional. */ } }
function forget(key: string): void { try { sessionStorage.removeItem(key); } catch { /* Optional. */ } }
function message(failure: unknown): string { return failure instanceof Error ? failure.message : "课程暂时不可用，请重试。"; }

async function openUnit(id: string, token: number): Promise<void> {
  const loaded = await loadCatalogUnit(id);
  const currentScene = loaded.scenes.find((item) => item.is_current);
  if (!currentScene || new Set(currentScene.resources.map((item) => item.type)).size !== 3)
    throw new CatalogRequestError("课程资源不完整，请重新选择课程。");
  const approved = catalog.value?.releases.find((item) => item.id === loaded.catalog_release_id);
  if (!approved?.nodes.some((item) => item.id === loaded.knowledge_node_id))
    throw new CatalogRequestError("这份课程已不可用，请重新读取目录。");
  const preset = await loadPresetDemo(id);
  if (preset.release_id !== loaded.catalog_release_id) throw new CatalogRequestError("演示与课程版本不一致。");
  const session = preset.classroom ?? await createCatalogClassroom(id, csrf.value, crypto.randomUUID());
  if (token !== generation) return;
  unit.value = loaded; scene.value = currentScene; demo.value = preset; classroom.value = session;
  selectedRelease.value = approved.id; receipt.value = null; pendingDemo = null;
  const tab = stored(`${storageKey()}:tab:${id}`);
  resourceType.value = ["explanation", "code", "exercise"].includes(tab) ? tab as ResourceType : "explanation";
  if (session.detour?.kind === "catalog_demo" && session.detour.return_point?.resource_type)
    resourceType.value = session.detour.return_point.resource_type;
  store(storageKey(), id);
}
async function initialize(): Promise<void> {
  if (busy.value) return;
  const token = ++generation;
  busy.value = true; error.value = "";
  try {
    const session = await ensureCatalogSession();
    if (token !== generation) return;
    if (owner.value && owner.value !== session.owner) { unit.value = null; scene.value = null; demo.value = null; classroom.value = null; }
    owner.value = session.owner; csrf.value = session.csrf;
    const listing = await loadCatalog();
    if (token !== generation) return;
    catalog.value = listing;
    selectedRelease.value = listing.releases[0]?.id ?? "";
    const id = stored(storageKey());
    if (id && listing.status === "ready") {
      try { await openUnit(id, token); }
      catch (failure) {
        unit.value = null; scene.value = null; demo.value = null; classroom.value = null;
        if (failure instanceof CatalogRequestError && [404, 409].includes(failure.status)) forget(storageKey());
        throw failure;
      }
    } else if (listing.status === "not_ready") {
      unit.value = null; scene.value = null; demo.value = null; classroom.value = null;
    }
  } catch (failure) { if (token === generation) error.value = message(failure); }
  finally { if (token === generation) busy.value = false; }
}
async function chooseNode(nodeId: string): Promise<void> {
  if (busy.value || !release.value || !csrf.value) return;
  const token = ++generation;
  busy.value = true; error.value = "";
  if (!pendingEnrollment || pendingEnrollment.release !== release.value.id || pendingEnrollment.node !== nodeId)
    pendingEnrollment = { release: release.value.id, node: nodeId, key: crypto.randomUUID() };
  const pending = pendingEnrollment;
  try {
    const id = pending.unitId ?? await enrollCatalog(pending.release, pending.node, csrf.value, pending.key);
    pending.unitId = id;
    if (token !== generation) return;
    await openUnit(id, token);
    pendingEnrollment = null;
  } catch (failure) { if (token === generation) error.value = message(failure); }
  finally { if (token === generation) busy.value = false; }
}
function selectResource(type: ResourceType): void {
  resourceType.value = type;
  if (unit.value) store(`${storageKey()}:tab:${unit.value.id}`, type);
}
function restoredQuiz(result: QuizSubmissionResult): void { receipt.value = result; }
function submittedQuiz(result: QuizSubmissionResult): void { receipt.value = result; refreshToken.value += 1; }
async function toggleDemo(): Promise<void> {
  if (!unit.value || !classroom.value || busy.value) return;
  const token = generation;
  const action = demoActive.value ? "exit" : "begin";
  if (!pendingDemo || pendingDemo.unit !== unit.value.id || pendingDemo.action !== action)
    pendingDemo = { unit: unit.value.id, action, resource: resourceType.value,
      revision: classroom.value.revision, key: crypto.randomUUID() };
  const pending = pendingDemo;
  busy.value = true; error.value = "";
  try {
    const result = await controlPresetDemo(pending.unit, pending.action, pending.resource,
      pending.revision, csrf.value, pending.key);
    if (token !== generation) return;
    classroom.value = result.classroom;
    selectResource(result.return_resource_type);
    pendingDemo = null;
  } catch (failure) { if (token === generation) error.value = message(failure); }
  finally { if (token === generation) busy.value = false; }
}
async function downloadNotes(): Promise<void> {
  if (!unit.value || downloading.value) return;
  const id = unit.value.id;
  downloading.value = true; downloadError.value = "";
  try { await downloadFile(notesUrl(id), `${node.value?.name ?? "学习"}-笔记.md`, () => unit.value?.id === id); }
  catch (failure) { if (unit.value?.id === id) downloadError.value = message(failure); }
  finally { downloading.value = false; }
}
onMounted(initialize);
onBeforeUnmount(() => { generation += 1; });
</script>

<template>
  <main
    class="catalog-desk"
    :aria-busy="busy"
  >
    <header class="catalog-masthead">
      <div>
        <p class="catalog-eyebrow">
          启智学伴 · 数据结构
        </p><h1>课程目录</h1>
      </div>
      <p>从一个知识点开始，读代码、做练习、看动画。</p>
      <button
        type="button"
        :disabled="busy"
        @click="initialize"
      >
        重新读取
      </button>
    </header>
    <p
      v-if="error"
      class="catalog-error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="busy && !unit"
      role="status"
    >
      正在准备课程。
    </p>
    <section
      v-if="catalog?.status === 'not_ready'"
      class="catalog-empty"
    >
      <h2>课程正在准备</h2><p>内容完成审核后会出现在目录中。可稍后重新读取。</p>
    </section>
    <div
      v-else-if="catalog?.status === 'ready'"
      class="catalog-layout"
    >
      <aside
        class="catalog-list"
        aria-label="数据结构课程目录"
      >
        <label
          v-if="catalog.releases.length > 1"
          for="course-release"
        >课程版本</label>
        <select
          v-if="catalog.releases.length > 1"
          id="course-release"
          v-model="selectedRelease"
          :disabled="busy"
        >
          <option
            v-for="item in catalog.releases"
            :key="item.id"
            :value="item.id"
          >
            {{ item.package_id }} · {{ item.version }}
          </option>
        </select>
        <h2>知识点</h2>
        <ul>
          <li
            v-for="item in release?.nodes"
            :key="item.id"
          >
            <button
              type="button"
              :disabled="busy || Boolean(demoActive)"
              :aria-current="unit?.knowledge_node_id === item.id && unit?.catalog_release_id === release?.id ? 'page' : undefined"
              @click="chooseNode(item.id)"
            >
              <span>{{ item.name }}</span><small>{{ item.description }}</small>
            </button>
          </li>
        </ul>
      </aside>
      <section
        class="catalog-lesson"
        aria-label="课程学习区"
      >
        <div
          v-if="!unit || !scene"
          class="catalog-empty"
        >
          <h2>选择一个知识点</h2><p>讲解、C 代码和三道练习会一起打开。</p>
        </div>
        <template v-else>
          <header class="catalog-lesson-heading">
            <p class="catalog-eyebrow">
              固定课程 · {{ unitRelease?.version }}
            </p><h2>{{ node?.name }}</h2>
            <p>{{ node?.description }}</p>
            <div
              v-if="node?.prerequisites.length"
              class="catalog-prerequisites"
            >
              <span>先备知识</span><button
                v-for="id in node.prerequisites"
                :key="id"
                type="button"
                :disabled="busy || Boolean(demoActive)"
                @click="chooseNode(id)"
              >
                {{ unitRelease?.nodes.find(item => item.id === id)?.name }}
              </button>
            </div>
          </header>
          <div class="catalog-actions">
            <button
              type="button"
              :disabled="busy"
              @click="toggleDemo"
            >
              {{ demoActive ? '退出演示，返回学习' : '查看数组 vs 链表预设演示' }}
            </button>
            <button
              type="button"
              :disabled="downloading"
              @click="downloadNotes"
            >
              {{ downloading ? '正在下载' : '下载 Markdown 笔记' }}
            </button>
          </div>
          <p
            v-if="downloadError"
            role="alert"
          >
            {{ downloadError }}
          </p>
          <article
            v-if="demoActive && demo"
            class="catalog-demo"
            aria-label="预设演示"
          >
            <p class="catalog-eyebrow">
              预设教学演示 · 内容固定
            </p><h3>{{ demo.script.title }}</h3>
            <section
              v-for="perspective in demo.script.perspectives"
              :key="perspective.title"
            >
              <h4>{{ perspective.title }}</h4><p>{{ perspective.text }}</p>
            </section>
            <h4>结论</h4><p>{{ demo.script.summary }}</p>
          </article>
          <div v-show="!demoActive">
            <PublishedLearningWorkspace
              :key="scene.id"
              :resources="scene.resources"
              :csrf-token="csrf"
              :selected-resource="resourceType"
              @resource-selected="selectResource"
              @quiz-submitted="submittedQuiz"
              @quiz-restored="restoredQuiz"
            />
            <p
              v-if="receipt"
              class="catalog-practice"
              aria-live="polite"
            >
              最近练习：{{ receipt.correct_count }} / {{ receipt.question_count }} 题正确。完成练习与掌握度分别记录。
            </p>
            <AnimationPanel
              v-if="supportedAnimation"
              :key="unit.id"
              :unit-id="unit.id"
              :node-id="unit.knowledge_node_id"
              :scene-id="scene.id"
              :scene-key="scene.scene_key"
              :scene-version="scene.version"
              :csrf-token="csrf"
            />
          </div>
          <LearningPathPanel
            :key="unit.id"
            :target-node-id="unit.knowledge_node_id"
            :csrf-token="csrf"
            :refresh-token="refreshToken"
          />
        </template>
      </section>
    </div>
  </main>
</template>

<style scoped>
.catalog-desk { max-width: 1400px; margin: auto; padding: 24px clamp(16px, 4vw, 56px); color: #17253a; }
.catalog-masthead { display: flex; align-items: center; gap: 24px; border-bottom: 1px solid #b8c7cb; padding-bottom: 24px; }
.catalog-masthead h1 { font-size: 30px; font-weight: 650; margin: 6px 0 0; }
.catalog-masthead > p { flex: 1; color: #536876; }
.catalog-eyebrow { color: #35656d; font-size: 12px; letter-spacing: .06em; margin: 0; }
.catalog-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: clamp(24px, 4vw, 56px); padding-top: 28px; }
.catalog-list h2 { font-size: 16px; margin: 0 0 16px; }
.catalog-list ul { margin: 0; padding: 0; list-style: none; }
.catalog-list li { border-top: 1px solid #cbd6d4; }
.catalog-desk button, .catalog-desk select { font: inherit; cursor: pointer; border: 1px solid #a6bcbd; padding: 10px 14px; background: #fbfcf9; color: #244c5a; border-radius: 5px; }
.catalog-desk button:disabled { opacity: .55; cursor: default; }
.catalog-desk button:focus-visible, .catalog-desk select:focus-visible { outline: 3px solid #35656d; outline-offset: 3px; }
.catalog-list li button { border: 0; border-radius: 0; padding: 14px 12px; text-align: left; width: 100%; background: transparent; }
.catalog-list button[aria-current='page'] { background: #d7e4e0; border-left: 3px solid #35656d; }
.catalog-list small { display: block; font-size: 12px; color: #536876; line-height: 1.6; margin-top: 6px; }
.catalog-list span { font-weight: 600; }
.catalog-lesson { min-width: 0; }
.catalog-lesson-heading h2 { margin: 10px 0; font-size: clamp(28px, 4vw, 40px); line-height: 1.25; }
.catalog-lesson-heading > p:last-of-type { color: #536876; line-height: 1.8; }
.catalog-prerequisites, .catalog-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.catalog-prerequisites { font-size: 13px; }
.catalog-prerequisites button { padding: 5px 10px; }
.catalog-demo, .catalog-lesson :deep(.published-workspace), .catalog-empty { background: #fbfcf9; padding: clamp(20px, 3vw, 32px); border: 1px solid #cbd6d4; line-height: 1.8; }
.catalog-demo section { border-left: 3px solid #35656d; padding-left: 16px; margin: 24px 0; }
.catalog-demo h3, .catalog-demo h4 { margin: 0 0 8px; }
.catalog-demo p { white-space: pre-wrap; }
.catalog-lesson :deep(pre) { white-space: pre; overflow-x: auto; padding: 16px; background: #eaf0f2; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px; line-height: 1.7; }
.catalog-lesson :deep(.published-workspace nav) { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.catalog-lesson :deep(.quiz-question) { border-top: 1px solid #cbd6d4; padding: 18px 0; }
.catalog-lesson :deep(.quiz-question input) { display: block; width: 100%; max-width: 500px; padding: 9px; margin-top: 10px; font: inherit; }
.catalog-practice { padding: 14px 18px; background: #d7e4e0; color: #244c5a; }
.catalog-error { border-left: 3px solid #f06e43; background: #fbfcf9; padding: 16px; }
.catalog-lesson :deep(.animation-panel) { box-shadow: none; margin: 24px 0; }
@media (max-width: 760px) {
  .catalog-masthead { align-items: flex-start; flex-wrap: wrap; gap: 12px; }
  .catalog-masthead > p { flex-basis: 100%; order: 2; margin: 0; }
  .catalog-layout { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  .catalog-list ul { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 12px; }
  .catalog-list small { display: none; }
}
</style>

<style scoped>
.catalog-lesson :deep([data-testid="explanation-tab"] p) { white-space: pre-wrap; }
</style>
