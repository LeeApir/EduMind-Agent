<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { NButton, NTag } from "naive-ui";

import {
  ClassroomSpeechError,
  controlClassroom,
  createClassroom,
  loadClassroom,
  loadClassroomOperation,
  streamReexplanation,
  type ClassroomOperation,
  type ClassroomSnapshot,
  type ControlClassroomOptions,
  type LearningControlAction,
  type StreamReexplanationOptions,
} from "../api/classroom";

type ReexplanationAction = StreamReexplanationOptions["action"];
interface SceneItem { id: string; sceneKey: string; version: number; isCurrent: boolean; }
interface PendingControl {
  action: LearningControlAction;
  key: string;
  revision: number;
  startedSelectionId: string;
}
interface PendingReexplanation {
  key: string;
  action: ReexplanationAction;
  sceneKey: string;
  baseVersion: number;
  revision: number;
  startedSelectionId: string;
  operationId: string;
}

const props = withDefaults(defineProps<{
  unitId: string;
  csrfToken: string;
  scenes: SceneItem[];
  selectedSceneId: string;
  loadSnapshot?: (unitId: string) => Promise<ClassroomSnapshot>;
  create?: (unitId: string, csrf: string, key: string) => Promise<ClassroomSnapshot>;
  control?: (options: ControlClassroomOptions) => Promise<ClassroomSnapshot>;
  loadOperation?: (id: string) => Promise<ClassroomOperation>;
  stream?: (options: StreamReexplanationOptions) => Promise<void>;
}>(), {
  loadSnapshot: (unitId: string) => loadClassroom(unitId),
  create: (unitId: string, csrf: string, key: string) => createClassroom(unitId, csrf, key),
  control: (options: ControlClassroomOptions) => controlClassroom(options),
  loadOperation: (id: string) => loadClassroomOperation(id),
  stream: (options: StreamReexplanationOptions) => streamReexplanation(options),
});
const emit = defineEmits<{
  "select-scene": [sceneId: string];
  "scene-changed": [startedSelectionId: string, sceneKey: string, sceneVersion: number];
  "classroom-changed": [];
}>();

const snapshot = ref<ClassroomSnapshot | null>(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const temporary = ref("");
const generationStage = ref<"idle" | "generating" | "reviewing" | "failed">("idle");
const pendingControl = ref<PendingControl | null>(null);
const pendingReexplanation = ref<PendingReexplanation | null>(null);
let generation = 0;

const selectedScene = computed(() => props.scenes.find((scene) => scene.id === props.selectedSceneId));
const orderedScenes = computed(() => [...props.scenes].sort((a, b) =>
  a.sceneKey.localeCompare(b.sceneKey) || b.version - a.version));
const canActOnScene = computed(() => Boolean(snapshot.value && selectedScene.value?.isCurrent
  && selectedScene.value.sceneKey === snapshot.value.scene_key
  && selectedScene.value.version === snapshot.value.scene_version));
const hasPending = computed(() => Boolean(pendingControl.value || pendingReexplanation.value));

function createStorageKey(): string { return `edumind:classroom:${props.unitId}:create`; }
function pendingStorageKey(): string { return `edumind:reexplanation:${props.unitId}:pending`; }
function controlStorageKey(): string { return `edumind:control:${props.unitId}:pending`; }
function readStored<T>(key: string): T | null {
  try {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) as T : null;
  } catch { return null; }
}
function saveStored(key: string, value: object | null): void {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value));
    else sessionStorage.removeItem(key);
  } catch { /* Optional browser storage. */ }
}
function createKey(): string {
  try {
    const existing = sessionStorage.getItem(createStorageKey());
    if (existing) return existing;
    const key = crypto.randomUUID();
    sessionStorage.setItem(createStorageKey(), key);
    return key;
  } catch { return crypto.randomUUID(); }
}
function message(errorValue: unknown): string {
  return errorValue instanceof Error && errorValue.message
    ? errorValue.message : "学习控制暂时不可用，请重试。";
}
function terminal(status: string): boolean {
  return ["published", "failed", "cancelled", "superseded"].includes(status);
}

async function ensureSnapshot(token: number): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    let current: ClassroomSnapshot;
    try {
      current = await props.loadSnapshot(props.unitId);
    } catch (failure) {
      if (!(failure instanceof ClassroomSpeechError) || failure.code !== "NOT_FOUND") throw failure;
      current = await props.create(props.unitId, props.csrfToken, createKey());
    }
    if (token !== generation) return;
    snapshot.value = current;
    pendingControl.value = readStored<PendingControl>(controlStorageKey());
    pendingReexplanation.value = readStored<PendingReexplanation>(pendingStorageKey());
    if (pendingControl.value || pendingReexplanation.value) {
      notice.value = "检测到上次未确认的操作，请恢复原请求。";
    }
    if (pendingReexplanation.value?.operationId) void recoverReexplanation(token);
  } catch (failure) {
    if (token === generation) error.value = message(failure);
  } finally {
    if (token === generation) loading.value = false;
  }
}

watch(() => props.unitId, () => {
  const token = ++generation;
  snapshot.value = null;
  pendingControl.value = null;
  pendingReexplanation.value = null;
  temporary.value = "";
  notice.value = "";
  generationStage.value = "idle";
  if (props.unitId) void ensureSnapshot(token);
}, { immediate: true });
onBeforeUnmount(() => { generation += 1; });

async function refreshSnapshot(): Promise<void> {
  const token = generation;
  const current = await props.loadSnapshot(props.unitId);
  if (token === generation) snapshot.value = current;
}

async function runControl(action: LearningControlAction): Promise<void> {
  if (busy.value || !snapshot.value) return;
  if (pendingReexplanation.value || (pendingControl.value && pendingControl.value.action !== action)) {
    error.value = "请先恢复上次未确认的操作。";
    return;
  }
  const token = generation;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    let pending = pendingControl.value;
    if (!pending || pending.action !== action) {
      const latest = await props.loadSnapshot(props.unitId);
      if (token !== generation) return;
      snapshot.value = latest;
      pending = {
        action, key: crypto.randomUUID(), revision: latest.revision,
        startedSelectionId: props.selectedSceneId,
      };
      pendingControl.value = pending;
      saveStored(controlStorageKey(), pending);
    }
    const result = await props.control({
      unitId: props.unitId, action, revision: pending.revision,
      csrfToken: props.csrfToken, idempotencyKey: pending.key,
    });
    if (token !== generation) return;
    snapshot.value = result;
    pendingControl.value = null;
    saveStored(controlStorageKey(), null);
    emit("classroom-changed");
    if (action === "skip") {
      emit("scene-changed", pending.startedSelectionId, result.scene_key, result.scene_version);
    }
    notice.value = action === "skip" ? "已跳过当前场景。" : result.paused ? "已暂停。" : "已继续。";
  } catch (failure) {
    if (token !== generation) return;
    error.value = message(failure);
    if (failure instanceof ClassroomSpeechError && !failure.retryable) {
      pendingControl.value = null;
      saveStored(controlStorageKey(), null);
    }
    try { await refreshSnapshot(); } catch { /* Preserve original error. */ }
  } finally {
    if (token === generation) busy.value = false;
  }
}

async function recoverReexplanation(token = generation): Promise<void> {
  const pending = pendingReexplanation.value;
  if (!pending?.operationId) return;
  try {
    const operation = await props.loadOperation(pending.operationId);
    if (token !== generation) return;
    if (operation.status === "published") {
      await refreshSnapshot();
      if (token !== generation || !snapshot.value) return;
      emit("scene-changed", pending.startedSelectionId,
        snapshot.value.scene_key, snapshot.value.scene_version);
      emit("classroom-changed");
      notice.value = "已恢复审核通过的正式新版本。";
      temporary.value = "";
    } else if (operation.status === "accepted" || operation.status === "running") {
      notice.value = "原请求仍在处理；不会重复生成。";
      return;
    } else {
      generationStage.value = "failed";
      temporary.value = "";
      error.value = "上次重解释未发布，原正式版本仍可学习。";
    }
    if (terminal(operation.status)) {
      pendingReexplanation.value = null;
      saveStored(pendingStorageKey(), null);
    }
  } catch (failure) {
    if (token === generation) error.value = message(failure);
  }
}

async function runReexplanation(action: ReexplanationAction, retry = false): Promise<void> {
  if (busy.value || !snapshot.value || (!retry && !canActOnScene.value) || !selectedScene.value) return;
  if (!retry && hasPending.value) {
    error.value = "请先恢复上次未确认的操作。";
    return;
  }
  const token = generation;
  const selected = selectedScene.value;
  busy.value = true;
  error.value = "";
  notice.value = "";
  temporary.value = "";
  generationStage.value = "generating";
  let readyVersion: number | null = null;
  let pending = retry ? pendingReexplanation.value : null;
  if (!pending || pending.action !== action || (!retry && pending.sceneKey !== selected.sceneKey)) {
    try {
      const latest = await props.loadSnapshot(props.unitId);
      if (token !== generation) return;
      snapshot.value = latest;
      if (latest.scene_key !== selected.sceneKey || latest.scene_version !== selected.version) {
        throw new Error("当前场景已变化，请读取新版本后重试。");
      }
      pending = {
        key: crypto.randomUUID(), action, sceneKey: selected.sceneKey,
        baseVersion: selected.version, revision: latest.revision,
        startedSelectionId: props.selectedSceneId, operationId: "",
      };
      pendingReexplanation.value = pending;
      saveStored(pendingStorageKey(), pending);
    } catch (failure) {
      if (token === generation) {
        error.value = message(failure);
        busy.value = false;
        generationStage.value = "failed";
      }
      return;
    }
  }
  try {
    await props.stream({
      unitId: props.unitId, sceneKey: pending.sceneKey,
      baseSceneVersion: pending.baseVersion, action: pending.action,
      revision: pending.revision, csrfToken: props.csrfToken,
      idempotencyKey: pending.key,
      onEvent: (event) => {
        if (token !== generation) return;
        if (event.type === "agent_start" && typeof event.data.operation_id === "string") {
          pending.operationId = event.data.operation_id;
          saveStored(pendingStorageKey(), pending);
        } else if (event.type === "token" && event.data.temporary === true) {
          temporary.value += typeof event.data.delta === "string" ? event.data.delta : "";
          generationStage.value = "reviewing";
        } else if (event.type === "content_retracted") {
          temporary.value = "";
          generationStage.value = "failed";
        } else if (event.type === "scene_ready" && typeof event.data.scene_version === "number") {
          readyVersion = event.data.scene_version;
        }
      },
    });
    if (token !== generation) return;
    if (readyVersion !== null) {
      await refreshSnapshot();
      if (token !== generation) return;
      emit("scene-changed", pending.startedSelectionId, pending.sceneKey, readyVersion);
      emit("classroom-changed");
      notice.value = "新版本已通过审核并发布。";
      generationStage.value = "idle";
      temporary.value = "";
      pendingReexplanation.value = null;
      saveStored(pendingStorageKey(), null);
    } else if (pending.operationId) {
      await recoverReexplanation(token);
    } else {
      notice.value = "请求状态尚未确认，可恢复原请求。";
    }
  } catch (failure) {
    if (token !== generation) return;
    temporary.value = "";
    generationStage.value = "failed";
    error.value = message(failure);
    if (pending.operationId) await recoverReexplanation(token);
  } finally {
    if (token === generation) busy.value = false;
  }
}

async function retryPending(): Promise<void> {
  const pending = pendingReexplanation.value;
  if (!pending) return;
  if (pending.operationId) await recoverReexplanation();
  else await runReexplanation(pending.action, true);
}
</script>

<template>
  <section
    class="learning-controls"
    aria-label="学习控制"
    data-testid="learning-controls"
  >
    <div class="controls-heading">
      <div>
        <p class="eyebrow">
          学习控制
        </p><h2>按你的节奏继续</h2>
      </div>
      <NTag
        size="small"
        :type="snapshot?.paused ? 'warning' : 'info'"
      >
        {{ snapshot?.paused ? '已暂停' : '进行中' }}
      </NTag>
    </div>
    <p
      v-if="loading"
      role="status"
    >
      正在读取课堂进度…
    </p>
    <div
      v-else-if="!snapshot"
      role="alert"
    >
      {{ error || '课堂进度暂时不可用。' }}
      <NButton
        size="small"
        @click="ensureSnapshot(++generation)"
      >
        重试读取
      </NButton>
    </div>
    <template v-else>
      <nav
        class="version-list"
        aria-label="场景版本"
      >
        <NButton
          v-for="scene in orderedScenes"
          :key="scene.id"
          size="small"
          :type="scene.id === selectedSceneId ? 'primary' : 'default'"
          :aria-pressed="scene.id === selectedSceneId"
          @click="emit('select-scene', scene.id)"
        >
          {{ scene.sceneKey }} · 版本 {{ scene.version }}{{ scene.isCurrent ? ' · 当前' : ' · 旧版只读' }}
        </NButton>
      </nav>
      <p
        v-if="!canActOnScene"
        class="history-note"
      >
        当前查看的是历史或其他场景；切回课堂当前版本后可重新解释。
      </p>
      <div class="control-actions">
        <NButton
          size="small"
          :disabled="busy || hasPending"
          @click="runControl(snapshot.paused ? 'resume' : 'pause')"
        >
          {{ snapshot.paused ? '继续' : '暂停' }}
        </NButton>
        <NButton
          size="small"
          :disabled="busy || hasPending || !canActOnScene"
          @click="runControl('skip')"
        >
          跳过当前场景
        </NButton>
      </div>
      <div
        class="reexplanation-actions"
        aria-label="重解释当前场景"
      >
        <NButton
          size="small"
          :disabled="busy || hasPending || !canActOnScene"
          @click="runReexplanation('simpler')"
        >
          更简单
        </NButton>
        <NButton
          size="small"
          :disabled="busy || hasPending || !canActOnScene"
          @click="runReexplanation('deeper')"
        >
          更深入
        </NButton>
        <NButton
          size="small"
          :disabled="busy || hasPending || !canActOnScene"
          @click="runReexplanation('another_example')"
        >
          换个例子
        </NButton>
      </div>
      <p
        v-if="generationStage === 'generating'"
        role="status"
      >
        正在生成当前场景的新讲解…
      </p>
      <p
        v-else-if="generationStage === 'reviewing'"
        role="status"
      >
        新讲解正在审核；下方内容尚未发布。
      </p>
      <p
        v-if="temporary"
        class="temporary-text"
        aria-label="临时讲解"
      >
        {{ temporary }}
      </p>
      <p
        v-if="notice"
        role="status"
      >
        {{ notice }}
      </p>
      <p
        v-if="error"
        role="alert"
      >
        {{ error }}
      </p>
      <NButton
        v-if="pendingReexplanation && !busy"
        size="small"
        @click="retryPending"
      >
        恢复原重解释请求
      </NButton>
      <NButton
        v-else-if="pendingControl && !busy"
        size="small"
        @click="runControl(pendingControl.action)"
      >
        恢复原控制请求
      </NButton>
    </template>
  </section>
</template>

<style scoped>
.learning-controls { max-width: 760px; margin: 28px auto; padding: 22px; border: 1px solid #cbd6d4; border-radius: 16px; background: #f8faf7; }
.controls-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.controls-heading h2 { margin: 0 0 18px; color: #173747; }
.version-list, .control-actions, .reexplanation-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.history-note { color: #6a5761; }
.temporary-text { white-space: pre-wrap; overflow-wrap: anywhere; padding: 14px; border-left: 3px solid #df9e55; background: #fff8ec; }
.learning-controls :deep(.n-button--default-type) { background: #fff !important; }
.learning-controls :deep(button:focus-visible) { outline: 2px solid #f06e43; outline-offset: 3px; }
@media (max-width: 600px) { .learning-controls { padding: 16px; } .controls-heading { flex-direction: column; gap: 0; } }
</style>
