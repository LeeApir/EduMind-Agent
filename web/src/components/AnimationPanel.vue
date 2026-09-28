<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { NButton, NTag } from "naive-ui";

import {
  cancelAnimationJob, loadAnimationJob, mediaUrl, requestAnimation, retryAnimationJob,
  type AnimationJob, type AnimationRequest, type AnimationStatus, type AnimationTemplateId,
} from "../api/animationJobs";

interface StoredRequest {
  requestKey: string;
  request: AnimationRequest;
  jobId?: string;
  cancelKey?: string;
  retryKey?: string;
  retryOf?: string;
}

const props = defineProps<{
  unitId: string;
  nodeId: string;
  sceneVersion: number;
  csrfToken: string;
}>();

const job = ref<AnimationJob | null>(null);
const phase = ref<"idle" | "requesting" | "recovering" | "acting" | "reconnecting">("idle");
const error = ref("");
const subtitleError = ref("");
const subtitleUrl = ref("");
let active: StoredRequest | null = null;
let source: EventSource | null = null;
let generation = 0;

const supported = computed(() => props.nodeId === "linked-list-insertion" || props.nodeId === "linked-list-deletion");
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

function storageKey(unitId: string): string { return `edumind:animation:${unitId}`; }

function save(unitId: string, value: StoredRequest): void {
  try { sessionStorage.setItem(storageKey(unitId), JSON.stringify(value)); } catch { /* Optional browser storage. */ }
}

function restore(unitId: string): StoredRequest | null {
  try {
    const raw = sessionStorage.getItem(storageKey(unitId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredRequest>;
    if (typeof value.requestKey !== "string" || !value.request || typeof value.request !== "object") return null;
    if (value.request.template_id !== "linked-list-insertion" && value.request.template_id !== "linked-list-deletion") return null;
    if (value.request.scene_version !== props.sceneVersion || value.request.template_id !== props.nodeId) return null;
    if (typeof value.jobId !== "undefined" && typeof value.jobId !== "string") return null;
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

function closeSource(): void { source?.close(); source = null; }

function clearSubtitle(): void {
  if (subtitleUrl.value) URL.revokeObjectURL(subtitleUrl.value);
  subtitleUrl.value = "";
  subtitleError.value = "";
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
  if (token !== generation || next.learning_unit_id !== props.unitId) return;
  const oldMediaId = job.value?.media_id;
  job.value = next;
  phase.value = "idle";
  error.value = "";
  if (next.status === "succeeded" && next.media_id && next.media_id !== oldMediaId) {
    void loadSubtitle(next.media_id, token);
  }
  if (["succeeded", "failed", "cancelled"].includes(next.status)) closeSource();
  else subscribe(next, token);
}

function applyEvent(type: AnimationStatus | "progress" | "recovered", event: MessageEvent, token: number): void {
  if (token !== generation || !job.value) return;
  const id = Number(event.lastEventId);
  if (!Number.isInteger(id) || id <= job.value.last_event_id) return;
  const oldMediaId = job.value.media_id;
  let data: Record<string, unknown>;
  try { data = JSON.parse(event.data) as Record<string, unknown>; } catch { return; }
  if (data.job_id !== job.value.id) return;
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
    void refreshSnapshot(token, false);
  };
}

async function refreshSnapshot(token = generation, attach = true): Promise<void> {
  const jobId = active?.jobId;
  if (!jobId) return;
  try {
    const snapshot = await loadAnimationJob(jobId);
    if (token !== generation || active?.jobId !== jobId) return;
    if (attach) applyJob(snapshot, token);
    else {
      job.value = snapshot;
      if (["succeeded", "failed", "cancelled"].includes(snapshot.status)) applyJob(snapshot, token);
      else { phase.value = "idle"; error.value = ""; }
    }
  } catch {
    if (token === generation) {
      phase.value = "reconnecting";
      error.value = "暂时无法读取动画状态。讲解、代码和练习可继续使用。";
    }
  }
}

async function sendInitial(record: StoredRequest, unitId: string, token: number): Promise<void> {
  try {
    const next = await requestAnimation(unitId, record.request, props.csrfToken, record.requestKey);
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

function openAnimation(): void {
  if (!supported.value || !props.csrfToken || busy.value || job.value) return;
  const record: StoredRequest = { requestKey: crypto.randomUUID(), request: requestForScene() };
  active = record;
  save(props.unitId, record);
  phase.value = "requesting";
  error.value = "";
  void sendInitial(record, props.unitId, generation);
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
  try {
    const next = await retryAnimationJob(current.id, props.csrfToken, record.retryKey!);
    record.jobId = next.id;
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
  else if (props.csrfToken) await sendInitial(stored, unitId, token);
}

watch(() => [props.unitId, props.nodeId, props.sceneVersion], () => {
  generation += 1;
  closeSource();
  clearSubtitle();
  active = null;
  job.value = null;
  phase.value = "idle";
  error.value = "";
  if (supported.value && props.unitId && props.sceneVersion >= 1) {
    void restoreCurrent(props.unitId, generation);
  }
}, { immediate: true });

function handleOnline(): void {
  if (active?.jobId && job.value?.status !== "succeeded") void refreshSnapshot();
}

onMounted(() => window.addEventListener("online", handleOnline));
onBeforeUnmount(() => {
  window.removeEventListener("online", handleOnline);
  generation += 1;
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
        <h2>把链表操作看清楚</h2>
        <p>{{ exampleLabel }}</p>
      </div>
      <NTag
        size="small"
        :type="job?.status === 'succeeded' ? 'success' : 'info'"
      >
        {{ job ? statusText : '点击后生成' }}
      </NTag>
    </div>
    <NButton
      v-if="!job && !active"
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
      v-else-if="!job && active"
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
        :key="job?.media_id"
        controls
        preload="metadata"
        data-testid="animation-video"
      >
        <source
          :src="videoUrl"
          type="video/mp4"
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
    </div>
    <p class="animation-hint">
      动画是可选补充。讲解、代码和练习始终可以继续。
    </p>
  </section>
</template>
