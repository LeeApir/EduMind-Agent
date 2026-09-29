<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { NButton } from "naive-ui";

import {
  ClassroomSpeechError, createClassroom, exitDebate, loadClassroom,
  loadClassroomOperation, loadDebateResult, streamDebate, submitPerspectiveFeedback,
  type ClassroomOperation, type ClassroomSnapshot, type ClassroomSpeechEvent,
  type DebatePerspective, type DebateResult, type PerspectiveReceipt,
  type StreamDebateOptions,
} from "../api/classroom";

interface PendingDebate { key: string; question: string; revision: number; operationId?: string }
interface PendingExit { key: string; resultId: string; revision: number }

const props = withDefaults(defineProps<{
  unitId: string;
  csrfToken: string;
  refreshToken?: number;
  loadSnapshot?: (unitId: string) => Promise<ClassroomSnapshot>;
  create?: (unitId: string, csrf: string, key: string) => Promise<ClassroomSnapshot>;
  loadOperation?: (id: string) => Promise<ClassroomOperation>;
  loadResult?: (unitId: string, resultId: string) => Promise<DebateResult>;
  start?: (options: StreamDebateOptions) => Promise<void>;
  exit?: (unitId: string, resultId: string, revision: number, csrf: string, key: string) => Promise<ClassroomSnapshot>;
  feedback?: (unitId: string, resultId: string, perspective: DebatePerspective,
    csrf: string, key: string) => Promise<PerspectiveReceipt>;
}>(), {
  refreshToken: 0,
  loadSnapshot: loadClassroom,
  create: createClassroom,
  loadOperation: loadClassroomOperation,
  loadResult: loadDebateResult,
  start: streamDebate,
  exit: exitDebate,
  feedback: submitPerspectiveFeedback,
});
const emit = defineEmits<{ active: [value: boolean]; changed: []; profileChanged: [] }>();
const snapshot = ref<ClassroomSnapshot | null>(null);
const result = ref<DebateResult | null>(null);
const question = ref("");
const busy = ref(false);
const stage = ref("");
const error = ref("");
const notice = ref("");
const pending = ref<PendingDebate | null>(null);
const feedbackBusy = ref<DebatePerspective | null>(null);
const feedbackNotice = ref("");
let generation = 0;

const active = computed(() => result.value !== null && snapshot.value?.detour?.kind === "debate");
const canStart = computed(() => Boolean(question.value.trim()) && !busy.value && !pending.value
  && !active.value && Boolean(snapshot.value) && Boolean(props.csrfToken));
function key(kind: string): string { return `edumind:debate:${props.unitId}:${kind}`; }
function readStored<T>(kind: string): T | null {
  try { return JSON.parse(sessionStorage.getItem(key(kind)) || "null") as T | null; }
  catch { return null; }
}
function save(kind: string, value: object | null): void {
  try {
    if (value) sessionStorage.setItem(key(kind), JSON.stringify(value));
    else sessionStorage.removeItem(key(kind));
  } catch { /* Optional browser storage. */ }
}
function createKey(): string {
  const storageKey = `edumind:classroom:${props.unitId}:create`;
  try {
    const existing = sessionStorage.getItem(storageKey);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    sessionStorage.setItem(storageKey, fresh);
    return fresh;
  } catch { return crypto.randomUUID(); }
}
function explain(errorValue: unknown): string {
  if (errorValue instanceof ClassroomSpeechError) {
    if (errorValue.code === "REVIEW_REJECTED") return "多视角内容未通过审核，原课堂没有改变。请调整问题后重试。";
    if (errorValue.code === "REVIEW_UNAVAILABLE") return "审核暂时不可用，原课堂没有改变。";
    if (errorValue.code === "PROVIDER_UNAVAILABLE") return "生成服务暂时不可用，原课堂没有改变。";
    if (errorValue.code === "CLASSROOM_VERSION_CONFLICT") return "课堂已变化，请刷新状态后再试。";
  }
  return errorValue instanceof Error ? errorValue.message : "演示暂时无法完成，请重试。";
}
function clearPending(): void { pending.value = null; save("pending", null); }

async function loadCurrent(token: number): Promise<void> {
  let next: ClassroomSnapshot;
  try { next = await props.loadSnapshot(props.unitId); }
  catch (failure) {
    if (!(failure instanceof ClassroomSpeechError) || failure.code !== "NOT_FOUND") throw failure;
    next = await props.create(props.unitId, props.csrfToken, createKey());
  }
  if (token !== generation) return;
  snapshot.value = next;
  const resultId = next.detour?.kind === "debate" ? next.detour.result_id : undefined;
  const published = resultId ? await props.loadResult(props.unitId, resultId) : null;
  if (token !== generation) return;
  result.value = published?.status === "published" ? published : null;
  emit("active", Boolean(result.value));
}

async function recover(token: number): Promise<void> {
  const exitRequest = readStored<PendingExit>("exit");
  if (exitRequest) {
    try {
      const next = await props.exit(props.unitId, exitRequest.resultId, exitRequest.revision,
        props.csrfToken, exitRequest.key);
      if (token !== generation) return;
      save("exit", null);
      snapshot.value = next;
      result.value = null;
      emit("active", false);
      emit("changed");
      if (next.version_changed) notice.value = "原场景已有新版内容，已返回最新审核版本。";
    } catch (failure) {
      if (token !== generation) return;
      error.value = explain(failure);
      return;
    }
  }
  const stored = readStored<PendingDebate>("pending");
  if (!stored || typeof stored.key !== "string" || typeof stored.question !== "string"
    || typeof stored.revision !== "number") return;
  pending.value = stored;
  if (result.value) { clearPending(); return; }
  if (!stored.operationId) {
    stage.value = "上次请求尚未确认，可恢复原请求。";
    return;
  }
  try {
    const operation = await props.loadOperation(stored.operationId);
    if (token !== generation) return;
    if (operation.status === "published") {
      await loadCurrent(token);
      if (token !== generation) return;
      clearPending();
      emit("changed");
    } else if (["failed", "cancelled", "superseded"].includes(operation.status)) {
      clearPending();
      error.value = "上次演示未发布，原课堂没有改变。可重新发起。";
    } else {
      stage.value = "演示仍在生成或审核，稍后检查状态。";
    }
  } catch { stage.value = "暂时无法确认上次操作，请恢复原请求。"; }
}

async function refresh(): Promise<void> {
  const token = ++generation;
  error.value = "";
  try { await loadCurrent(token); if (token === generation) await recover(token); }
  catch (failure) { if (token === generation) error.value = explain(failure); }
}

async function run(request: PendingDebate): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  stage.value = "正在生成并审核完整演示…";
  const token = generation;
  try {
    await props.start({
      unitId: props.unitId, question: request.question, revision: request.revision,
      csrfToken: props.csrfToken, idempotencyKey: request.key,
      onEvent: (event: ClassroomSpeechEvent) => {
        if (token !== generation) return;
        if (event.type === "agent_start" && typeof event.data.operation_id === "string") {
          request.operationId = event.data.operation_id;
          save("pending", request);
        }
        if (event.type === "stage_changed") stage.value = "正在独立审核事实与结论…";
      },
    });
    if (token !== generation) return;
    await loadCurrent(token);
    if (token !== generation) return;
    if (result.value) {
      clearPending();
      stage.value = "";
      emit("changed");
    } else {
      await recover(token);
    }
  } catch (failure) {
    if (token !== generation) return;
    const code = failure instanceof ClassroomSpeechError ? failure.code : "";
    if (!new Set(["CONNECTION_FAILED", "CONNECTION_INTERRUPTED", "EMPTY_STREAM"]).has(code)) {
      clearPending();
    }
    error.value = explain(failure);
    await loadCurrent(token).catch(() => undefined);
  } finally { if (token === generation) busy.value = false; }
}

function beginDebate(): void {
  if (!canStart.value || !snapshot.value) return;
  const request: PendingDebate = {
    key: crypto.randomUUID(), question: question.value.trim(), revision: snapshot.value.revision,
  };
  pending.value = request;
  save("pending", request);
  void run(request);
}
function retry(): void {
  if (!pending.value || busy.value) return;
  void run(pending.value);
}
async function leave(): Promise<void> {
  if (!snapshot.value || !result.value || busy.value) return;
  const request: PendingExit = readStored<PendingExit>("exit") ?? {
    key: crypto.randomUUID(), resultId: result.value.id, revision: snapshot.value.revision,
  };
  save("exit", request);
  busy.value = true;
  error.value = "";
  try {
    const next = await props.exit(props.unitId, request.resultId, request.revision,
      props.csrfToken, request.key);
    save("exit", null);
    snapshot.value = next;
    result.value = null;
    emit("active", false);
    emit("changed");
    if (next.version_changed) notice.value = "原场景已有新版内容，已返回最新审核版本。";
  } catch (failure) { error.value = explain(failure); }
  finally { busy.value = false; }
}

async function markHelpful(perspective: DebatePerspective): Promise<void> {
  if (!result.value || feedbackBusy.value) return;
  feedbackBusy.value = perspective;
  feedbackNotice.value = "";
  const resultId = result.value.id;
  const keyName = `feedback:${resultId}:${perspective}`;
  const stored = readStored<{ key: string }>(keyName);
  const requestKey = stored?.key ?? crypto.randomUUID();
  save(keyName, { key: requestKey });
  try {
    const receipt = await props.feedback(props.unitId, resultId, perspective,
      props.csrfToken, requestKey);
    save(keyName, null);
    feedbackNotice.value = receipt.update_status === "pending"
      ? "反馈已记录，画像更新待处理。"
      : receipt.update_status === "failed"
        ? "反馈已记录，画像更新暂未完成。"
        : "反馈已记录，后续讲解会参考这个视角。";
    if (receipt.update_status === "updated" || receipt.update_status === "unchanged") {
      emit("profileChanged");
    }
  } catch (failure) { feedbackNotice.value = explain(failure); }
  finally { feedbackBusy.value = null; }
}

watch(() => props.unitId, () => {
  snapshot.value = null; result.value = null; pending.value = null;
  question.value = ""; stage.value = ""; notice.value = ""; error.value = "";
  feedbackNotice.value = "";
  emit("active", false);
  if (props.unitId) void refresh();
}, { immediate: true });
watch(() => props.refreshToken, () => { if (props.unitId && !busy.value) void refresh(); });
onBeforeUnmount(() => { generation += 1; emit("active", false); });
</script>

<template>
  <section
    class="debate-panel"
    aria-label="多视角演示"
    data-testid="debate-panel"
  >
    <template v-if="active && result">
      <div class="debate-heading">
        <div>
          <p class="eyebrow">
            数组 vs 链表
          </p><h2>三种视角，一起判断</h2>
        </div>
        <NButton
          :disabled="busy"
          data-testid="exit-debate"
          @click="leave"
        >
          返回原课堂
        </NButton>
      </div>
      <p class="question">
        {{ result.question }}
      </p>
      <div class="conditions">
        <p v-if="result.question_conditions.stated.length">
          已知条件：{{ result.question_conditions.stated.join('、') }}
        </p>
        <p v-if="result.question_conditions.unknown.length">
          还需确认：{{ result.question_conditions.unknown.join('、') }}
        </p>
      </div>
      <div
        class="perspectives"
        data-testid="debate-perspectives"
      >
        <article>
          <span>01 · 性能派</span><h3>性能视角</h3><p>{{ result.perspectives.performance }}</p><NButton
            :disabled="!!feedbackBusy"
            @click="markHelpful('performance')"
          >
            这个视角有帮助
          </NButton>
        </article>
        <article>
          <span>02 · 工程派</span><h3>工程视角</h3><p>{{ result.perspectives.engineering }}</p><NButton
            :disabled="!!feedbackBusy"
            @click="markHelpful('engineering')"
          >
            这个视角有帮助
          </NButton>
        </article>
        <article>
          <span>03 · 学术派</span><h3>学术视角</h3><p>{{ result.perspectives.academic }}</p><NButton
            :disabled="!!feedbackBusy"
            @click="markHelpful('academic')"
          >
            这个视角有帮助
          </NButton>
        </article>
      </div>
      <article
        class="moderator"
        data-testid="debate-moderator"
      >
        <span>主持人 · 审核后总结</span>
        <h3>条件化结论</h3><p>{{ result.moderator.objective_conclusion }}</p>
        <h3>取舍</h3><p>{{ result.moderator.tradeoffs }}</p>
        <h3>学习建议</h3><p>{{ result.moderator.learner_advice }}</p>
      </article>
      <p
        v-if="feedbackNotice"
        role="status"
        data-testid="perspective-feedback-status"
      >
        {{ feedbackNotice }}
      </p>
    </template>
    <template v-else>
      <div class="debate-heading">
        <div>
          <p class="eyebrow">
            按需展开
          </p><h2>数组与链表，怎么选？</h2>
        </div>
      </div>
      <p>输入一个选型问题，查看性能、工程、学术三个视角及审核后的总结。</p>
      <label for="debate-question">你的问题</label>
      <textarea
        id="debate-question"
        v-model="question"
        maxlength="1000"
        rows="2"
        placeholder="例如：频繁随机访问时用数组还是链表？"
        data-testid="debate-question"
      />
      <div class="actions">
        <NButton
          type="primary"
          :loading="busy"
          :disabled="!canStart"
          data-testid="start-debate"
          @click="beginDebate"
        >
          展开多视角讨论
        </NButton>
        <NButton
          v-if="pending && !busy"
          data-testid="recover-debate"
          @click="retry"
        >
          恢复原请求
        </NButton>
        <NButton
          v-if="pending && !busy"
          data-testid="check-debate"
          @click="refresh"
        >
          检查状态
        </NButton>
      </div>
      <p
        v-if="stage"
        role="status"
        data-testid="debate-stage"
      >
        {{ stage }}
      </p>
    </template>
    <p
      v-if="notice"
      role="status"
    >
      {{ notice }}
    </p>
    <p
      v-if="error"
      role="alert"
      data-testid="debate-error"
    >
      {{ error }}
    </p>
  </section>
</template>

<style scoped>
.debate-panel { max-width: 1000px; margin: 24px auto; padding: 28px; border: 1px solid #c9d8d5; border-radius: 20px; background: #f7faf8; color: #17333b; }
.debate-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.debate-heading h2 { margin: 4px 0 14px; font-size: clamp(1.4rem, 2.5vw, 2rem); }
.eyebrow, .perspectives span, .moderator span { color: #386b69; font-size: .8rem; font-weight: 700; letter-spacing: .08em; }
.debate-panel p { line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.question { font-size: 1.2rem; font-weight: 600; }
.conditions { color: #50636a; }
.perspectives { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 22px 0; }
.perspectives article, .moderator { padding: 20px; border-radius: 14px; background: white; border: 1px solid #dce6e3; }
.perspectives h3, .moderator h3 { margin: 12px 0 4px; }
.moderator { border-left: 4px solid #417b71; }
label { display: block; font-weight: 700; margin: 18px 0 8px; }
textarea { box-sizing: border-box; width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #a9c4bd; font: inherit; resize: vertical; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
@media (max-width: 720px) { .perspectives { grid-template-columns: 1fr; } .debate-heading { flex-direction: column; } }
</style>
