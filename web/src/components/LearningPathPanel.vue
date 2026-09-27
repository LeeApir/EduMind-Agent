<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { NButton } from "naive-ui";
import { loadCurrentPath, loadGraph, loadMastery, PathRequestError, replanPath,
  type GraphSnapshot, type LearningPath, type MasterySnapshot, type ReplanOptions } from "../api/paths";
import type { MasteryStatus } from "../api/quiz";

const props = withDefaults(defineProps<{
  targetNodeId: string;
  csrfToken: string;
  refreshToken?: number;
  readPath?: (targetNodeId: string) => Promise<LearningPath | null>;
  readGraph?: () => Promise<GraphSnapshot>;
  readMastery?: () => Promise<MasterySnapshot>;
  replan?: (options: ReplanOptions) => Promise<LearningPath>;
}>(), { refreshToken: 0, readPath: loadCurrentPath, readGraph: loadGraph, readMastery: loadMastery, replan: replanPath });
interface ViewNode { id: string; name: string; status: MasteryStatus; score: number; role: string; reasons: string[]; evidence: string[]; resource: string; minutes: number | null; }
const path = shallowRef<LearningPath | null>(null);
const nodes = shallowRef<ViewNode[]>([]);
const selectedId = ref("");
const changedIds = ref<string[]>([]);
const loading = ref(false);
const error = ref("");
const empty = ref(false);
let graph: GraphSnapshot | null = null;
let generation = 0;
let pending: ReplanOptions | null = null;
const labels: Record<MasteryStatus, string> = { unseen: "未学习", learning: "学习中", weak: "需要巩固", mastered: "已掌握" };
const resources = { explanation: "讲解", code: "代码", exercise: "练习", review: "复习" };
const selected = computed(() => nodes.value.find((node) => node.id === selectedId.value));
onBeforeUnmount(() => { generation += 1; });

function project(next: LearningPath, mastery: MasterySnapshot, structure: GraphSnapshot): ViewNode[] {
  if (structure.graph_version !== next.graph_version || mastery.graph_version !== next.graph_version) {
    throw new PathRequestError("知识结构版本已变化，请重新读取推荐。", "GRAPH_VERSION_CHANGED");
  }
  if (mastery.items.reduce((total, item) => total + item.revision, 0) !== next.mastery_revision_watermark) {
    throw new PathRequestError("掌握度已变化，请重新读取最新推荐。", "MASTERY_VERSION_CHANGED");
  }
  const graphNodes = new Map(structure.nodes.map((node) => [node.id, node]));
  const closure: string[] = [];
  const visiting = new Set<string>();
  const seen = new Set<string>();
  function visit(id: string): void {
    if (visiting.has(id)) throw new PathRequestError("知识结构依赖无效。", "INVALID_RESPONSE");
    if (seen.has(id)) return;
    const node = graphNodes.get(id);
    if (!node) throw new PathRequestError("推荐节点不在当前知识结构中。", "INVALID_RESPONSE");
    visiting.add(id);
    node.prerequisites.forEach(visit);
    visiting.delete(id); seen.add(id); closure.push(id);
  }
  visit(next.target_node_id);
  if (next.nodes.some((id) => !seen.has(id))) throw new PathRequestError("推荐与目标依赖不一致。", "INVALID_RESPONSE");
  const currentStates = new Map(mastery.items.map((item) => [item.knowledge_node_id, item]));
  const details = new Map(next.node_details.map((item) => [item.node_id, item]));
  const ordered = [...closure.filter((id) => !next.nodes.includes(id)), ...next.nodes];
  return ordered.map((id) => {
    const node = graphNodes.get(id)!;
    const state = currentStates.get(id);
    const detail = details.get(id);
    // Unseen defaults mean absence of evidence, never inferred mastery.
    const status = state?.status ?? detail?.status ?? "unseen";
    const role = id === next.current_node_id ? "当前推荐" : next.prerequisite_node_ids.includes(id) ? "当前前置"
      : id === next.next_node_id ? "下一步" : id === next.target_node_id ? "目标" : "目标前置";
    const reasons = next.reasons.filter((reason) => reason.knowledge_node_id === id).map((reason) => reason.summary);
    if (!reasons.length && id !== next.target_node_id) {
      const dependent = structure.nodes.filter((item) => seen.has(item.id) && item.prerequisites.includes(id)).map((item) => item.name);
      if (dependent.length) reasons.push(`${node.name}是${dependent.join("、")}的前置知识。`);
    }
    if (!reasons.length) reasons.push(...next.reasons.filter((reason) => !reason.knowledge_node_id).map((reason) => reason.summary));
    return { id, name: node.name, status, score: state?.score ?? detail?.score ?? 0, role, reasons,
      evidence: state?.evidence_summary ?? [], resource: detail ? resources[detail.recommended_resource] : "",
      minutes: detail?.estimated_minutes ?? null };
  });
}
function applySnapshot(next: LearningPath, mastery: MasterySnapshot, structure: GraphSnapshot): void {
  const previous = new Map(nodes.value.map((node) => [node.id, node]));
  const projected = project(next, mastery, structure);
  const changes: string[] = [];
  nodes.value = projected.map((node) => {
    const old = previous.get(node.id);
    if (old && JSON.stringify(old) === JSON.stringify(node)) return old;
    if (path.value) changes.push(node.id);
    return node;
  });
  changedIds.value = changes;
  path.value = next;
  if (!nodes.value.some((node) => node.id === selectedId.value)) selectedId.value = next.current_node_id ?? nodes.value[0]?.id ?? "";
}
async function refresh(): Promise<void> {
  const token = ++generation;
  const target = props.targetNodeId;
  if (!target) return;
  loading.value = true; error.value = "";
  try {
    let next = await props.readPath(target);
    if (token !== generation) return;
    if (!next) { path.value = null; nodes.value = []; empty.value = true; return; }
    empty.value = false;
    if (next.is_stale) {
      if (!props.csrfToken) throw new PathRequestError("学习会话暂未就绪，请重新读取。", "SESSION_REQUIRED");
      // Retain a failed command verbatim until its durable receipt is recovered.
      if (!pending) pending = { targetNodeId: target, expectedVersion: next.version, csrfToken: props.csrfToken,
        idempotencyKey: crypto.randomUUID(), reason: props.refreshToken ? "mastery_changed" : "learner_request" };
      next = await props.replan(pending);
      if (token !== generation) return;
      pending = null;
      if (next.is_stale) throw new PathRequestError("推荐已再次变化，请重新读取最新版本。", "PATH_STALE");
    } else pending = null;
    const [mastery, structure] = await Promise.all([props.readMastery(), graph?.graph_version === next.graph_version ? Promise.resolve(graph) : props.readGraph()]);
    if (token !== generation) return;
    applySnapshot(next, mastery, structure);
    graph = structure;
  } catch (cause) {
    if (token !== generation) return;
    if (cause instanceof PathRequestError && cause.code === "PATH_VERSION_CONFLICT") pending = null;
    error.value = cause instanceof Error ? cause.message : "推荐暂时无法读取，请重试。";
  } finally { if (token === generation) loading.value = false; }
}
watch(() => props.targetNodeId, () => {
  generation += 1; pending = null; path.value = null; nodes.value = []; selectedId.value = ""; changedIds.value = []; empty.value = false;
  void refresh();
}, { immediate: true });
watch(() => props.refreshToken, () => { void refresh(); });
</script>

<template>
  <section
    class="learning-path"
    aria-label="学习路径"
    :aria-busy="loading"
  >
    <header>
      <h2>你的下一步</h2>
      <span v-if="path">路径 v{{ path.version }}</span>
    </header>
    <p
      v-if="loading"
      role="status"
    >
      正在更新推荐，已有节点保持可见…
    </p>
    <div
      v-if="error"
      role="alert"
    >
      <p>{{ error }}<span v-if="path">下面保留的是上次读取的推荐。</span></p>
      <NButton
        :disabled="loading"
        @click="refresh"
      >
        重新读取推荐
      </NButton>
    </div>
    <p v-if="empty && !loading">
      该目标暂无已保存路径。请重新输入学习目标，建立学习推荐。
    </p>
    <template v-if="path">
      <p v-if="path.current_node_id === null">
        这条目标路径已完成。已掌握状态来自服务端学习证据。
      </p>
      <p
        v-else
        class="path-direction"
      >
        当前：{{ nodes.find(node => node.id === path?.current_node_id)?.name }} · 下一步：{{ nodes.find(node => node.id === path?.next_node_id)?.name ?? '完成当前目标' }}
      </p>
      <ul
        class="path-legend"
        aria-label="节点状态说明"
      >
        <li
          v-for="(label, state) in labels"
          :key="state"
          :class="`state-${state}`"
        >
          {{ label }}
        </li>
      </ul>
      <ol
        class="path-nodes"
        aria-label="推荐学习顺序"
      >
        <li
          v-for="node in nodes"
          :key="node.id"
          :data-node-id="node.id"
          :data-changed="changedIds.includes(node.id)"
        >
          <button
            type="button"
            :aria-pressed="selectedId === node.id"
            :class="`state-${node.status}`"
            @click="selectedId = node.id"
          >
            <span class="node-role">{{ node.role }}</span>
            <strong>{{ node.name }}</strong>
            <span>{{ labels[node.status] }} · {{ Math.round(node.score * 100) }}%</span>
            <span
              v-if="changedIds.includes(node.id)"
              class="node-updated"
            >已更新</span>
          </button>
        </li>
      </ol>
      <section
        v-if="selected"
        class="node-detail"
        aria-label="节点推荐依据"
      >
        <h3>{{ selected.name }} · 推荐依据</h3>
        <ul>
          <li
            v-for="reason in selected.reasons"
            :key="reason"
          >
            {{ reason }}
          </li>
        </ul>
        <p v-if="selected.resource">
          建议先看{{ selected.resource }} · 预计 {{ selected.minutes }} 分钟
        </p>
        <h4>学习证据摘要</h4>
        <ul v-if="selected.evidence.length">
          <li
            v-for="item in selected.evidence"
            :key="item"
          >
            {{ item }}
          </li>
        </ul>
        <p v-else>
          尚无已记录的学习证据。未学习不等于已掌握。
        </p>
      </section>
      <NButton
        :disabled="loading"
        @click="refresh"
      >
        刷新推荐
      </NButton>
    </template>
  </section>
</template>

<style scoped>
.learning-path { margin: 32px auto; max-width: 760px; color: #17253a; }
header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
header span, .node-role { font-size: 12px; color: #35656d; }
.path-legend { display: flex; flex-wrap: wrap; gap: 16px; list-style: none; padding: 0; font-size: 12px; }
.path-legend li::before { content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 6px; background: var(--state-color); }
.state-unseen { --state-color: #657580; }
.state-learning { --state-color: #a3631b; }
.state-weak { --state-color: #a13d36; }
.state-mastered { --state-color: #28734d; }
.path-nodes { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); list-style: none; gap: 12px; padding: 0; }
.path-nodes button { background: #fbfcf9; border: 1px solid #cbd6d4; border-top: 3px solid var(--state-color); color: #17253a; cursor: pointer; display: flex; flex-direction: column; gap: 8px; text-align: left; padding: 14px; width: 100%; height: 100%; font: inherit; }
.path-nodes button[aria-pressed="true"] { outline: 2px solid #35656d; outline-offset: 2px; }
.path-nodes button:focus-visible, .learning-path :deep(button:focus-visible) { outline: 3px solid #f06e43; outline-offset: 3px; }
.node-updated { color: #35656d; font-size: 12px; }
.node-detail { border-left: 3px solid #35656d; padding: 8px 20px; background: #fbfcf9; margin: 20px 0; overflow-wrap: anywhere; }
.node-detail h3 { font-size: 16px; }
.node-detail h4 { font-size: 14px; }
.learning-path :deep(.n-button) { color: #fbfcf9; }
@media (max-width: 480px) { .path-nodes { grid-template-columns: 1fr; } }
</style>
