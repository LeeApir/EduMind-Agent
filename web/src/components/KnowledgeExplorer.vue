<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { loadCatalog, type CatalogListing } from "../api/catalog";
import { loadGraph, loadMastery, planPath, type GraphSnapshot, type LearningPath, type MasterySnapshot } from "../api/paths";
import LearningPathPanel from "./LearningPathPanel.vue";

const props = withDefaults(defineProps<{
  csrfToken: string; catalog?: CatalogListing | null; catalogReady?: boolean;
  canPlan?: boolean; canEnroll?: boolean; currentNodeId?: string; fixedCompletedNodeId?: string; refreshToken?: number;
  readGraph?: () => Promise<GraphSnapshot>; readMastery?: () => Promise<MasterySnapshot>;
  readCatalog?: () => Promise<CatalogListing>;
  plan?: (target: string, csrf: string, key: string) => Promise<LearningPath>;
}>(), { catalog: undefined, catalogReady: true, canPlan: false, canEnroll: false, currentNodeId: "", fixedCompletedNodeId: "", refreshToken: 0,
  readGraph: loadGraph, readMastery: loadMastery, readCatalog: loadCatalog, plan: planPath });
const emit = defineEmits<{ learn: [releaseId: string, nodeId: string] }>();
const graph = shallowRef<GraphSnapshot | null>(null);
const mastery = shallowRef<MasterySnapshot | null>(null);
const listing = shallowRef<CatalogListing | null>(null);
const selectedId = ref("");
const targetId = ref("");
const loading = ref(false);
const planning = ref(false);
const error = ref("");
const planError = ref("");
let generation = 0;
let planGeneration = 0;
let pending: { target: string; key: string } | null = null;
const selected = computed(() => graph.value?.nodes.find(node => node.id === selectedId.value));
const states = computed(() => new Map(mastery.value?.items.map(item => [item.knowledge_node_id, item])));
const activeCatalog = computed(() => props.catalog ?? listing.value);
const course = computed(() => activeCatalog.value?.releases.find(release => release.nodes.some(node => node.id === selectedId.value)));
const ready = computed(() => props.catalogReady && !loading.value && !error.value);
function name(id: string): string { return graph.value?.nodes.find(node => node.id === id)?.name ?? id; }
function stateLabel(id: string): string {
  const state = states.value.get(id);
  if (!state) return "掌握度未知";
  return { unseen: "掌握度未知", learning: "学习中", weak: "需要巩固", mastered: "已掌握" }[state.status];
}
function selectNode(id: string): void {
  selectedId.value = id; planGeneration += 1; planning.value = false; planError.value = ""; pending = null;
}
async function refresh(): Promise<void> {
  const token = ++generation;
  loading.value = true; error.value = "";
  try {
    const [structure, records, courses] = await Promise.all([props.readGraph(),
      props.csrfToken ? props.readMastery() : Promise.resolve(null),
      props.catalog !== undefined ? Promise.resolve(props.catalog) : props.readCatalog()]);
    if (token !== generation) return;
    if (records && records.graph_version !== structure.graph_version) throw new Error("知识结构已变化，请刷新后查看。");
    graph.value = structure; mastery.value = records; listing.value = courses;
    if (!structure.nodes.some(node => node.id === selectedId.value)) selectNode(structure.nodes[0]?.id ?? "");
  } catch (cause) { if (token === generation) error.value = cause instanceof Error ? cause.message : "知识结构读取失败，请重试。"; }
  finally { if (token === generation) loading.value = false; }
}
async function chooseTarget(): Promise<void> {
  if (!selected.value || !ready.value || planning.value || !props.canPlan || !props.csrfToken) return;
  const target = selected.value.id;
  const token = ++planGeneration;
  planning.value = true; planError.value = "";
  if (pending?.target !== target) pending = { target, key: crypto.randomUUID() };
  try {
    const result = await props.plan(target, props.csrfToken, pending.key);
    if (token !== planGeneration) return;
    if (result.target_node_id !== target) throw new Error("路径目标不一致，请重新读取。");
    pending = null; targetId.value = target;
  } catch (cause) { if (token === planGeneration) planError.value = cause instanceof Error ? cause.message : "路径规划失败，请重试。"; }
  finally { if (token === planGeneration) planning.value = false; }
}
function learn(): void {
  if (props.canEnroll && ready.value && course.value && selected.value) emit("learn", course.value.id, selected.value.id);
}
watch(() => [props.csrfToken, props.refreshToken], (next, previous) => {
  if (next[0] !== previous?.[0]) {
    mastery.value = null; targetId.value = ""; pending = null; planGeneration += 1; planning.value = false;
  }
  void refresh();
}, { immediate: true });
onBeforeUnmount(() => { generation += 1; planGeneration += 1; });
</script>

<template>
  <section
    class="knowledge-explorer"
    aria-label="知识结构浏览"
    :aria-busy="loading"
  >
    <header><h2>浏览知识结构</h2><span v-if="graph">{{ graph.nodes.length }} 个知识点</span></header>
    <p>先修关系帮助你选择目标；只有已审核课程可以开始学习。</p>
    <p
      v-if="loading"
      role="status"
    >
      正在读取知识结构与学习记录…
    </p>
    <div
      v-if="error"
      role="alert"
    >
      <p>{{ error }}</p><button
        type="button"
        :disabled="loading"
        @click="refresh"
      >
        重新读取知识结构
      </button>
    </div>
    <div
      v-if="graph"
      class="explorer-layout"
    >
      <ul
        class="explorer-nodes"
        aria-label="全部知识点"
      >
        <li
          v-for="node in graph.nodes"
          :key="node.id"
        >
          <button
            type="button"
            :aria-pressed="selectedId === node.id"
            :data-knowledge-id="node.id"
            @click="selectNode(node.id)"
          >
            <strong>{{ node.name }}</strong><span>{{ stateLabel(node.id) }}</span>
            <span v-if="currentNodeId === node.id">当前课程</span>
            <span v-if="fixedCompletedNodeId === node.id">已完成固定题</span>
          </button>
        </li>
      </ul>
      <section
        v-if="selected"
        class="explorer-detail"
        aria-label="知识点详情"
      >
        <h3>{{ selected.name }}</h3>
        <p>
          {{ stateLabel(selected.id) }}<template v-if="states.get(selected.id)">
            · {{ Math.round(states.get(selected.id)!.score * 100) }}%
          </template>
        </p>
        <p v-if="fixedCompletedNodeId === selected.id">
          已完成固定题；这不等于已掌握。掌握度以学习证据为准。
        </p>
        <h4>先修知识</h4>
        <ul v-if="selected.prerequisites.length">
          <li
            v-for="id in selected.prerequisites"
            :key="id"
          >
            <button
              type="button"
              @click="selectNode(id)"
            >
              {{ name(id) }}
            </button>
          </li>
        </ul>
        <p v-else>
          此节点没有列出的前置要求。
        </p>
        <p v-if="!ready">
          课程可用性尚未确认，请完成读取后再学习。
        </p>
        <template v-else-if="course">
          <p>已有已审核课程。</p><button
            v-if="canEnroll"
            type="button"
            @click="learn"
          >
            学习已审核课程
          </button>
        </template>
        <p v-else>
          该知识点暂未提供已审核课程。
        </p>
        <button
          v-if="canPlan"
          type="button"
          :disabled="!ready || planning"
          @click="chooseTarget"
        >
          {{ planning ? '正在规划…' : '查看该目标路径' }}
        </button>
        <p v-else>
          开始一节已审核课程后，可以查看目标的个性化学习路径。
        </p>
        <p
          v-if="planError"
          role="alert"
        >
          {{ planError }}
        </p>
      </section>
    </div>
    <LearningPathPanel
      v-if="targetId"
      :target-node-id="targetId"
      :csrf-token="csrfToken"
      :refresh-token="refreshToken"
    />
  </section>
</template>

<style scoped>
.knowledge-explorer { margin: 32px auto; max-width: 1100px; color: #17253a; }
header { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.explorer-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr); gap: 24px; }
.explorer-nodes { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 10px; padding: 0; list-style: none; }
button { font: inherit; cursor: pointer; color: #17253a; background: #fbfcf9; border: 1px solid #cbd6d4; padding: 10px; border-radius: 4px; }
button:disabled { cursor: default; opacity: .6; }
.explorer-nodes button { width: 100%; height: 100%; display: flex; flex-direction: column; gap: 8px; text-align: left; }
.explorer-nodes span { font-size: 12px; }
button[aria-pressed="true"] { border-color: #35656d; box-shadow: inset 0 0 0 1px #35656d; }
button:focus-visible { outline: 3px solid #f06e43; outline-offset: 3px; }
.explorer-detail { background: #fbfcf9; padding: 18px; overflow-wrap: anywhere; align-self: start; }
@media (max-width: 640px) { .explorer-layout { grid-template-columns: 1fr; } .explorer-nodes { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
