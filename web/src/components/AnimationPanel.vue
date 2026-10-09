<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { NButton, NTag } from "naive-ui";

import {
  AnimationApiError, cancelAnimationJob, loadAnimationJob, mediaUrl, requestAnimation, retryAnimationJob,
  type AnimationJob, type AnimationRequest, type AnimationStatus, type AnimationTemplateId,
} from "../api/animationJobs";
import { cancelPreparation, generateAnimation, loadPreparation, type AnimationPreparation, type AnimationSource, type GenerationRequest } from "../api/animationGeneration";
import { DownloadError, downloadFile } from "../api/downloads";

interface StoredRequest {
  nodeId?: string;
  operationId?: string;
  generatedRequest?: GenerationRequest;
  source?: AnimationSource;
  failureCode?: string;
  sceneId?: string;
  requestKey: string;
  request?: AnimationRequest;
  jobId?: string;
  cancelKey?: string;
  retryKey?: string;
  retryOf?: string;
}

const props = defineProps<{
  unitId: string;
  nodeId: string;
  sceneVersion: number;
  sceneId?: string;
  sceneKey?: string;
  csrfToken: string;
  dynamicEnabled?: boolean;
}>();

const preparation = ref<AnimationPreparation | null>(null);
const allowFallback = ref(false);
let controller: AbortController | null = null;
const job = ref<AnimationJob | null>(null);
const phase = ref<"idle" | "requesting" | "recovering" | "acting" | "reconnecting">("idle");
const error = ref("");
const subtitleError = ref("");
const subtitleUrl = ref("");
const downloadError = ref("");
const downloading = ref<"mp4" | "srt" | "">("");
const missingMedia = ref<"mp4" | "srt" | "">("");
let active: StoredRequest | null = null;
let source: EventSource | null = null;
let generation = 0;
let snapshotRead = 0;

const templateSupported = computed(() => ["linked-list-insertion", "linked-list-deletion"].includes(props.nodeId));
const dynamicSupported = computed(() => Boolean(props.dynamicEnabled && props.sceneId) && ["array", "single-linked-list", "linked-list-concept", "linked-list-traversal", "linked-list-insertion", "linked-list-deletion"].includes(props.nodeId));
const supported = computed(() => templateSupported.value || dynamicSupported.value);
const preparing = computed(() => preparation.value && !["handed_off", "failed", "cancelled"].includes(preparation.value.stage));
const preparationText = computed(() => preparation.value ? ({reserved: "准备中", generating: "生成分镜中", reviewing: "审核动画中", compiled: "审核通过，等待渲染", handed_off: "已交付渲染", failed: "动画准备失败", cancelled: "已取消"})[preparation.value.stage] : "");
const sourceText = computed(() => active?.source === "template_fallback" || job.value?.fallback_of ? "生成动画失败，已改用审核模板"
  : job.value?.render_kind === "dsl" ? (active?.source === "reviewed_dsl_cache" ? "已审核生成动画 · 缓存复用" : "已审核生成动画") : "已审核模板动画");
const busy = computed(() => ["requesting", "recovering", "acting"].includes(phase.value));
const videoUrl = computed(() => job.value?.status === "succeeded" && job.value.media_id
  ? mediaUrl(job.value.media_id, "mp4") : "");
const progressPercent = computed(() => Math.round((job.value?.progress ?? 0) * 100));
const statusText = computed(() => ({
  queued: "排队中", running: "正在制作", succeeded: "动画已就绪",
  failed: "动画暂不可用", cancelled: "已取消",
})[job.value?.status ?? "queued"]);
const exampleLabel = computed(() => props.nodeId === "linked-list-insertion"
  ? "在 [1, 3, 5] 的第 1 位插入 4"
  : "删除 [1, 3, 5] 的第 1 位元素");

function failureReason(code: string): string {
  const labels: Record<string, string> = {
    DSL_RENDER_FAILED: "生成动画渲染失败", DSL_REVIEW_FAILED: "动画审核未通过",
    DSL_REVIEW_UNAVAILABLE: "动画审核暂不可用", DSL_GENERATION_UNAVAILABLE: "动画生成暂不可用",
    DSL_COMPILE_REJECTED: "动画步骤未通过安全校验", ANIMATION_UNAVAILABLE: "动画暂不可制作",
    ANIMATION_PREPARATION_EXPIRED: "制作操作已超时", ANIMATION_TARGET_UNAVAILABLE: "当前课程或动画版本已失效",
  };
  return `${labels[code] ?? "动画暂不可用"}（${code}）`;
}

function storageKey(unitId: string, sceneId = props.sceneId): string {
  return `edumind:animation:${unitId}${sceneId ? `:${sceneId}` : ""}`;
}

function save(unitId: string, value: StoredRequest): void {
  try { sessionStorage.setItem(storageKey(unitId, value.sceneId), JSON.stringify(value)); } catch { /* Optional browser storage. */ }
}

function restore(unitId: string): StoredRequest | null {
  try {
    const currentKey = storageKey(unitId);
    const legacyKey = storageKey(unitId, "");
    const raw = sessionStorage.getItem(currentKey)
      ?? (props.sceneKey === "intro" ? sessionStorage.getItem(legacyKey) : null);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredRequest>;
    if (typeof value.requestKey !== "string") return null;
    if (value.operationId) {
      if (typeof value.operationId !== "string" || !value.generatedRequest || value.nodeId !== props.nodeId
        || value.generatedRequest.scene_id !== props.sceneId || value.generatedRequest.scene_version !== props.sceneVersion
        || !props.dynamicEnabled) return null;
    } else {
      if (!value.request || (value.request.template_id !== "linked-list-insertion" && value.request.template_id !== "linked-list-deletion")) return null;
      if (value.request.scene_version !== props.sceneVersion || value.request.template_id !== props.nodeId) return null;
    }
    if (value.sceneId && value.sceneId !== props.sceneId) return null;
    if (typeof value.jobId !== "undefined" && typeof value.jobId !== "string") return null;
    if (props.sceneId && !value.sceneId) {
      value.sceneId = props.sceneId;
      sessionStorage.setItem(currentKey, JSON.stringify(value));
      sessionStorage.removeItem(legacyKey);
    }
    return value as StoredRequest;
  } catch { return null; }
}

function requestForScene(): AnimationRequest {
  const templateId = props.nodeId as AnimationTemplateId;
  return {
    template_id: templateId, template_version: "1.0.0", scene_version: props.sceneVersion,
    parameters: templateId === "linked-list-insertion"
      ? { values: [1, 3, 5], index: 1, value: 4 }
      : { values: [1, 3, 5], index: 1 },
  };
}

function invalidateMedia(): void { job.value = null; clearSubtitle(); closeSource(); error.value = "动画文件已失效，请重新读取状态。"; }

function closeSource(): void { source?.close(); source = null; }

function clearSubtitle(): void {
  if (subtitleUrl.value) URL.revokeObjectURL(subtitleUrl.value);
  subtitleUrl.value = "";
  subtitleError.value = "";
}

async function downloadMedia(extension: "mp4" | "srt"): Promise<void> {
  const mediaId = job.value?.media_id;
  if (job.value?.status !== "succeeded" || !mediaId || downloading.value) return;
  const token = generation;
  downloading.value = extension;
  downloadError.value = "";
  try {
    await downloadFile(mediaUrl(mediaId, extension, true), `animation-${mediaId}.${extension}`,
      () => token === generation && job.value?.media_id === mediaId);
    if (token === generation && missingMedia.value === extension) missingMedia.value = "";
  } catch (failure) {
    if (token === generation && job.value?.media_id === mediaId) {
      downloadError.value = failure instanceof DownloadError && failure.code === "unavailable"
        ? `${extension.toUpperCase()} 文件缺失，请重新请求动画。`
        : `${extension.toUpperCase()} 下载失败，请重试下载。`;
      if (failure instanceof DownloadError && failure.code === "unavailable") {
        missingMedia.value = extension;
        clearSubtitle();
      }
    }
  } finally {
    if (token === generation) downloading.value = "";
  }
}

async function loadSubtitle(mediaId: string, token: number): Promise<void> {
  clearSubtitle();
  try {
    const response = await fetch(mediaUrl(mediaId, "srt"), { credentials: "same-origin" });
    if (!response.ok) throw new Error("subtitle unavailable");
    const srt = await response.text();
    if (token !== generation || job.value?.media_id !== mediaId) return;
    const vtt = `WEBVTT\n\n${srt.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, "$1.$2")}`;
    subtitleUrl.value = URL.createObjectURL(new Blob([vtt], { type: "text/vtt" }));
  } catch {
    if (token === generation) subtitleError.value = "字幕暂不可用，视频仍可播放。";
  }
}

function applyJob(next: AnimationJob, token: number): void {
  if (token !== generation || next.learning_unit_id !== props.unitId || (active?.operationId && next.generation_id !== active.operationId)) return;
  if (job.value?.id === next.id && next.last_event_id < job.value.last_event_id) return;
  closeSource();
  const oldMediaId = job.value?.media_id;
  job.value = next;
  if (next.media_id !== oldMediaId || next.status !== "succeeded") {
    downloadError.value = "";
    missingMedia.value = "";
  }
  phase.value = "idle";
  error.value = "";
  if (next.status === "succeeded" && next.media_id && next.media_id !== oldMediaId) {
    void loadSubtitle(next.media_id, token);
  }
  if (next.status === "failed" && next.render_kind === "dsl") {
    // The fallback reference is carried by the final event, not by the Job snapshot.
    subscribe({...next, last_event_id: Math.max(0, next.last_event_id - 1)}, token);
  } else if (["succeeded", "failed", "cancelled"].includes(next.status)) closeSource();
  else subscribe(next, token);
}

function applyEvent(type: AnimationStatus | "progress" | "recovered", event: MessageEvent, token: number): void {
  if (token !== generation || !job.value) return;
  const id = Number(event.lastEventId);
  if (!Number.isInteger(id) || id < job.value.last_event_id) return;
  const oldMediaId = job.value.media_id;
  let data: Record<string, unknown>;
  try { data = JSON.parse(event.data) as Record<string, unknown>; } catch { return; }
  if (data.job_id !== job.value.id) return;
  if (type === "failed" && typeof data.fallback_job_id === "string" && data.fallback_source === "template_fallback") {
    job.value = {...job.value, status: "failed", last_event_id: id};
    void followFallback(data.fallback_job_id, token); return;
  }
  if (id === job.value.last_event_id) { if (type === "failed") closeSource(); return; }
  const status = type === "recovered" ? "queued" : type === "progress" ? job.value.status : type;
  const updated: AnimationJob = {
    ...job.value, status, last_event_id: id,
    progress: typeof data.progress === "number" ? data.progress : job.value.progress,
    attempt: typeof data.attempt === "number" ? data.attempt : job.value.attempt,
  };
  if (typeof data.media_id === "string") updated.media_id = data.media_id;
  if (typeof data.code === "string") {
    updated.error = { code: data.code, message: "动画暂不可用。", retryable: true };
  }
  job.value = updated;
  if (updated.media_id !== oldMediaId || updated.status !== "succeeded") {
    downloadError.value = "";
    missingMedia.value = "";
  }
  if (type === "succeeded" && updated.media_id && updated.media_id !== oldMediaId) {
    void loadSubtitle(updated.media_id, token);
  }
  if (type === "succeeded" || type === "failed" || type === "cancelled") {
    closeSource();
    void refreshSnapshot(token);
  } else {
    phase.value = "idle";
    error.value = "";
  }
}

function subscribe(snapshot: AnimationJob, token: number): void {
  if (source || token !== generation || typeof EventSource === "undefined") return;
  const url = `/api/animation-jobs/${encodeURIComponent(snapshot.id)}/events?after=${snapshot.last_event_id}`;
  const connection = new EventSource(url, { withCredentials: true });
  source = connection;
  for (const type of ["queued", "running", "progress", "recovered", "succeeded", "failed", "cancelled"] as const) {
    connection.addEventListener(type, (event) => applyEvent(type, event as MessageEvent, token));
  }
  connection.onerror = () => {
    if (token !== generation || source !== connection) return;
    phase.value = "reconnecting";
    error.value = "连接中断，正在读取任务状态。";
    closeSource();
    void refreshSnapshot(token);
  };
}

async function refreshSnapshot(token = generation): Promise<void> {
  const jobId = active?.jobId;
  if (!jobId) return;
  const read = ++snapshotRead;
  try {
    const snapshot = await loadAnimationJob(jobId);
    if (token !== generation || active?.jobId !== jobId || read !== snapshotRead) return;
    if (snapshot.learning_unit_id !== props.unitId || (active?.operationId && snapshot.generation_id !== active.operationId)) throw new Error("target mismatch");
    applyJob(snapshot, token);
  } catch {
    if (token === generation && read === snapshotRead) {
      job.value = null; clearSubtitle(); closeSource();
      phase.value = "reconnecting";
      error.value = "暂时无法读取动画状态。讲解、代码和练习可继续使用。";
    }
  }
}

async function sendInitial(record: StoredRequest, unitId: string, token: number): Promise<void> {
  try {
    const next = await requestAnimation(unitId, record.request!, props.csrfToken, record.requestKey);
    if (token !== generation) return;
    record.jobId = next.id;
    save(unitId, record);
    if (token === generation && props.unitId === unitId) applyJob(next, token);
  } catch {
    if (token === generation) {
      phase.value = "idle";
      error.value = "动画请求暂时未确认。可用相同请求键恢复，其他学习内容不受影响。";
    }
  }
}

function openTemplate(): void {
  if (preparing.value || busy.value || (job.value && ["queued", "running"].includes(job.value.status))) return;
  controller?.abort(); preparation.value = null; job.value = null; active = null;
  clearSubtitle(); openAnimation();
}

function openAnimation(): void {
  if (!templateSupported.value || !props.csrfToken || busy.value || job.value) return;
  const record: StoredRequest = { sceneId: props.sceneId, requestKey: crypto.randomUUID(), request: requestForScene() };
  active = record;
  save(props.unitId, record);
  phase.value = "requesting";
  error.value = "";
  void sendInitial(record, props.unitId, generation);
}

function requestMissingMedia(): void {
  if (!missingMedia.value || !props.csrfToken || busy.value) return;
  const wasGenerated = Boolean(active?.operationId);
  closeSource();
  job.value = null;
  active = null;
  missingMedia.value = "";
  downloadError.value = "";
  if (wasGenerated) startGenerated(); else openAnimation();
}

function recoverRequest(): void {
  if (!active || active.jobId || !props.csrfToken || busy.value) return;
  phase.value = "requesting";
  void sendInitial(active, props.unitId, generation);
}

async function cancel(): Promise<void> {
  const current = job.value;
  if (!current || !active || !props.csrfToken || busy.value || !["queued", "running"].includes(current.status)) return;
  const token = generation;
  const record = active;
  record.cancelKey ||= crypto.randomUUID();
  save(props.unitId, record);
  phase.value = "acting";
  try {
    const result = await cancelAnimationJob(current.id, props.csrfToken, record.cancelKey);
    if (token === generation) applyJob(result, token);
  } catch {
    if (token === generation) {
      phase.value = "idle";
      error.value = "取消结果暂时无法确认，请读取任务状态或重试取消。";
    }
  }
}

async function retry(): Promise<void> {
  const current = job.value;
  if (!current || !active || !props.csrfToken || busy.value || !["failed", "cancelled"].includes(current.status)) return;
  const token = generation;
  const record = active;
  const unitId = props.unitId;
  if (record.retryOf !== current.id) {
    record.retryOf = current.id;
    record.retryKey = crypto.randomUUID();
  }
  save(unitId, record);
  phase.value = "acting";
  closeSource();
  try {
    const next = await retryAnimationJob(current.id, props.csrfToken, record.retryKey!);
    if (token !== generation) return;
    record.jobId = next.id;
    if (record.operationId && next.render_kind !== "dsl" && !next.generation_id) {
      // Legacy template retries are independent receipts without preparation metadata.
      record.operationId = undefined; record.generatedRequest = undefined;
      record.request = requestForScene(); preparation.value = null;
    }
    record.retryKey = undefined;
    record.retryOf = undefined;
    record.cancelKey = undefined;
    save(unitId, record);
    if (token === generation) applyJob(next, token);
  } catch {
    if (token === generation) {
      phase.value = "idle";
      error.value = "重试结果暂时无法确认，可用同一请求键继续恢复。";
    }
  }
}

async function restoreCurrent(unitId: string, token: number): Promise<void> {
  const stored = restore(unitId);
  if (!stored) return;
  active = stored;
  phase.value = "recovering";
  if (stored.jobId) await refreshSnapshot(token);
  else if (stored.operationId) await recoverPreparation(token);
  else if (props.csrfToken) await sendInitial(stored, unitId, token);
}

watch(() => [props.unitId, props.nodeId, props.sceneVersion, props.sceneId, props.dynamicEnabled], () => {
  generation += 1;
  controller?.abort(); controller = null; preparation.value = null;
  closeSource();
  clearSubtitle();
  downloadError.value = "";
  downloading.value = "";
  missingMedia.value = "";
  active = null;
  job.value = null;
  phase.value = "idle";
  error.value = "";
  if (supported.value && props.unitId && props.sceneVersion >= 1) {
    void restoreCurrent(props.unitId, generation);
  }
}, { immediate: true });

async function followFallback(id: string, token: number): Promise<void> {
  const original = job.value?.id;
  const record = active;
  closeSource();
  try {
    const next = await loadAnimationJob(id);
    if (token !== generation || !active || active !== record || job.value?.id !== original) return;
    if (next.learning_unit_id !== props.unitId || next.fallback_of !== original || next.render_kind !== "template" || (active.operationId && next.generation_id !== active.operationId)) throw new Error("fallback mismatch");
    active.failureCode = "DSL_RENDER_FAILED"; active.source = "template_fallback"; active.jobId = id;
    save(props.unitId, active); applyJob(next, token);
  } catch { if (token === generation) error.value = "生成动画失败，模板替代状态暂不可用，请重新读取状态。"; }
}
async function applyPreparation(next: AnimationPreparation, token: number): Promise<void> {
  if (token !== generation || next.id !== active?.operationId) return;
  if (preparation.value && ["handed_off", "failed", "cancelled"].includes(preparation.value.stage)
    && !["handed_off", "failed", "cancelled"].includes(next.stage)) return;
  preparation.value = next; phase.value = "idle";
  active.source = next.source; active.failureCode = next.error_code;
  if (next.job_id) active.jobId = next.job_id;
  save(props.unitId, active);
  if (next.job_id) await refreshSnapshot(token);
}
async function recoverPreparation(token = generation): Promise<void> {
  const id = active?.operationId;
  if (!id) return;
  phase.value = "recovering";
  try { await applyPreparation(await loadPreparation(id), token); }
  catch { if (token === generation) { phase.value = "idle"; error.value = "暂时无法读取动画准备状态。讲解和练习可继续。"; } }
}
function startGenerated(): void {
  if (!dynamicSupported.value || busy.value || preparing.value || !props.csrfToken) return;
  if (job.value && ["queued", "running"].includes(job.value.status)) return;
  controller?.abort(); closeSource(); clearSubtitle(); job.value = null; error.value = "";
  downloading.value = ""; downloadError.value = ""; missingMedia.value = "";
  generation += 1;
  const token = generation;
  const id = crypto.randomUUID();
  const goal = props.nodeId === "linked-list-insertion" ? "trace_insert" : props.nodeId === "linked-list-deletion" ? "trace_delete" : "traverse";
  const parameters = goal === "trace_insert" ? {values: [1, 3, 5], index: 1, value: 4} : goal === "trace_delete" ? {values: [1, 3, 5], index: 1} : {values: [1, 3, 5]};
  const request: GenerationRequest = {scene_id: props.sceneId!, scene_version: props.sceneVersion, goal_kind: goal, parameters};
  const record: StoredRequest = {nodeId: props.nodeId, sceneId: props.sceneId, requestKey: crypto.randomUUID(), operationId: id, generatedRequest: request};
  active = record; save(props.unitId, record);
  preparation.value = {id, stage: "reserved", deadline: new Date(Date.now() + 180000).toISOString()};
  const requestController = new AbortController();
  controller = requestController;
  void generateAnimation(props.unitId, request, props.csrfToken, record.requestKey, id, allowFallback.value, requestController.signal,
    (next) => { void applyPreparation(next, token); }).catch((failure) => {
      if (token === generation && !requestController.signal.aborted) { phase.value = "idle"; error.value = `动画准备连接中断或不可用（${failure instanceof AnimationApiError ? failure.code : "CONNECTION_INTERRUPTED"}），请读取状态。不会自动重新生成。`; }
    });
}
async function cancelPreparing(): Promise<void> {
  const record = active; const token = generation;
  if (!record?.operationId || busy.value) return;
  record.cancelKey ||= crypto.randomUUID(); save(props.unitId, record); phase.value = "acting";
  try {
    const next = await cancelPreparation(record.operationId, props.csrfToken, record.cancelKey);
    if (token !== generation) return;
    controller?.abort(); controller = null;
    await applyPreparation(next, token);
    if (next.stage === "handed_off" && job.value && ["queued", "running"].includes(job.value.status)) await cancel();
  } catch { if (token === generation) { phase.value = "idle"; error.value = "取消结果未确认，请读取状态。"; } }
}
function handleOnline(): void {
  if (active?.operationId && !active.jobId) void recoverPreparation();
  if (active?.jobId) void refreshSnapshot();
}

onMounted(() => { window.addEventListener("online", handleOnline); window.addEventListener("focus", handleOnline); });
onBeforeUnmount(() => {
  window.removeEventListener("online", handleOnline);
  window.removeEventListener("focus", handleOnline);
  generation += 1;
  controller?.abort(); controller = null; preparation.value = null;
  closeSource();
  clearSubtitle();
});
</script>

<template>
  <section
    v-if="supported"
    class="animation-panel"
    aria-label="按需动画"
    data-testid="animation-panel"
  >
    <div class="animation-heading">
      <div>
        <p class="eyebrow">
          按需动画
        </p>
        <h2>把操作过程看清楚</h2>
        <p>{{ templateSupported ? exampleLabel : '遍历 [1, 3, 5]，观察操作步骤' }}</p>
      </div>
      <NTag
        size="small"
        :type="job?.status === 'succeeded' ? 'success' : 'info'"
      >
        {{ job ? statusText : '点击后生成' }}
      </NTag>
    </div>
    <div
      v-if="dynamicSupported"
      class="generation-controls"
      data-testid="generated-animation-controls"
    >
      <label><input
        v-model="allowFallback"
        type="checkbox"
        :disabled="Boolean(preparing) || busy"
      >生成失败时允许使用同目标审核模板</label>
      <NButton
        data-testid="generate-animation"
        :disabled="Boolean(preparing) || busy || !csrfToken || Boolean(job && ['queued', 'running'].includes(job.status))"
        @click="startGenerated"
      >
        制作详细动画
      </NButton>
    </div>
    <NButton
      v-if="templateSupported && active?.operationId && !preparing && !busy && (!job || ['failed', 'cancelled'].includes(job.status))"
      data-testid="use-template-animation"
      :disabled="!csrfToken"
      @click="openTemplate"
    >
      使用审核模板动画
    </NButton>
    <div
      v-if="preparation && (!job || preparation.stage !== 'handed_off')"
      aria-live="polite"
      data-testid="preparation-status"
    >
      <p>{{ preparationText }}</p>
      <p v-if="preparation.error_code">
        失败原因：{{ failureReason(preparation.error_code) }}。讲解和练习可继续。
      </p>
      <NButton
        v-if="preparing"
        data-testid="cancel-preparation"
        :disabled="busy"
        @click="cancelPreparing"
      >
        取消制作
      </NButton>
      <NButton
        v-if="!job"
        data-testid="recover-preparation"
        :disabled="busy"
        @click="recoverPreparation()"
      >
        读取制作状态
      </NButton>
    </div>
    <p
      v-if="job"
      data-testid="animation-source"
    >
      {{ sourceText }}<span v-if="active?.failureCode || job.fallback_reason_code"> · 原因：{{ failureReason((active?.failureCode || job.fallback_reason_code)!) }}</span>
    </p>
    <NButton
      v-if="!job && !active && templateSupported"
      type="primary"
      :disabled="!csrfToken || busy"
      data-testid="request-animation"
      @click="openAnimation"
    >
      打开动画
    </NButton>
    <NButton
      v-else-if="!job && active?.jobId"
      :disabled="busy"
      data-testid="recover-animation-job"
      @click="refreshSnapshot()"
    >
      重新读取动画状态
    </NButton>
    <NButton
      v-else-if="!job && active && !active.operationId"
      :disabled="busy"
      data-testid="recover-animation-request"
      @click="recoverRequest"
    >
      恢复动画请求
    </NButton>
    <div
      v-if="job"
      class="animation-status"
      aria-live="polite"
    >
      <p>{{ statusText }}<span v-if="job.status === 'running'"> · {{ progressPercent }}%</span></p>
      <p v-if="job.error">
        失败原因：{{ failureReason(job.error.code) }}
      </p>
      <NButton
        v-if="job.status === 'queued' || job.status === 'running'"
        size="small"
        :disabled="busy"
        data-testid="cancel-animation"
        @click="cancel"
      >
        取消动画
      </NButton>
      <NButton
        v-if="job.status === 'failed' || job.status === 'cancelled'"
        size="small"
        :disabled="busy"
        data-testid="retry-animation"
        @click="retry"
      >
        重试动画
      </NButton>
      <NButton
        v-if="phase === 'reconnecting'"
        size="small"
        data-testid="recover-animation-job"
        @click="refreshSnapshot()"
      >
        重新读取状态
      </NButton>
    </div>
    <p
      v-if="error"
      role="status"
      class="animation-hint"
    >
      {{ error }}
    </p>
    <div
      v-if="videoUrl"
      class="animation-player"
    >
      <video
        v-if="!missingMedia"
        :key="job?.media_id"
        controls
        preload="metadata"
        data-testid="animation-video"
        @error="invalidateMedia"
      >
        <source
          :src="videoUrl"
          type="video/mp4"
          @error="invalidateMedia"
        >
        <track
          v-if="subtitleUrl"
          kind="subtitles"
          srclang="zh"
          label="中文字幕"
          :src="subtitleUrl"
          default
        >
      </video>
      <p
        v-if="subtitleError"
        role="status"
      >
        {{ subtitleError }}
      </p>
      <div
        class="download-actions"
        aria-label="动画文件下载"
      >
        <NButton
          data-testid="download-mp4"
          :disabled="Boolean(downloading)"
          @click="downloadMedia('mp4')"
        >
          {{ downloading === 'mp4' ? '正在下载…' : '下载 MP4' }}
        </NButton>
        <NButton
          data-testid="download-srt"
          :disabled="Boolean(downloading)"
          @click="downloadMedia('srt')"
        >
          {{ downloading === 'srt' ? '正在下载…' : '下载 SRT 字幕' }}
        </NButton>
      </div>
      <p
        v-if="downloadError"
        role="alert"
      >
        {{ downloadError }}
      </p>
      <NButton
        v-if="missingMedia"
        data-testid="request-missing-animation"
        :disabled="busy"
        @click="requestMissingMedia"
      >
        重新请求动画
      </NButton>
    </div>
    <p
      v-else-if="job && job.status !== 'succeeded'"
      class="animation-hint"
    >
      {{ job.status === 'failed' ? '动画生成失败，暂无已审核文件可下载。' : '动画尚未审核完成，暂无文件可下载。' }}
    </p>
    <p class="animation-hint">
      动画是可选补充。讲解、代码和练习始终可以继续。
    </p>
  </section>
</template>

<style scoped>
.generation-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.generation-controls label { display: flex; align-items: center; gap: 6px; line-height: 1.5; }
.animation-panel :deep(.n-button) { color: #fff; }
</style>
