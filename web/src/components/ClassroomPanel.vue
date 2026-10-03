<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { NButton, NTag } from "naive-ui";

import {
  ClassroomSpeechError,
  createClassroom,
  loadClassroom,
  loadClassroomMessages,
  loadClassroomOperation,
  setClassroomMode,
  streamClassroomSpeech,
  type ClassroomMessage,
  type ClassroomMessageRole,
  type ClassroomMode,
  type ClassroomOperation,
  type ClassroomSnapshot,
  type ClassroomSpeechEvent,
  type CompanionRole,
  type SetClassroomModeOptions,
  type StreamClassroomSpeechOptions,
} from "../api/classroom";

interface PendingSpeech {
  key: string;
  text: string;
  operationId: string;
  terminal: boolean;
}

interface StoredPending {
  key: string;
  text: string;
  operationId: string;
}

const props = withDefaults(defineProps<{
  unitId: string;
  csrfToken?: string;
  sceneVersion?: number;
  refreshToken?: number;
  loadSnapshot?: (unitId: string) => Promise<ClassroomSnapshot>;
  create?: (unitId: string, csrfToken: string, idempotencyKey: string) => Promise<ClassroomSnapshot>;
  setMode?: (unitId: string, options: SetClassroomModeOptions) => Promise<ClassroomSnapshot>;
  loadMessages?: (unitId: string, after: number) => Promise<{ messages: ClassroomMessage[]; last_message_cursor: number }>;
  loadOperation?: (operationId: string) => Promise<ClassroomOperation>;
  streamSpeech?: (options: StreamClassroomSpeechOptions) => Promise<void>;
}>(), {
  csrfToken: "",
  sceneVersion: 0,
  refreshToken: 0,
  loadSnapshot: (unitId: string) => loadClassroom(unitId),
  create: (unitId: string, csrfToken: string, idempotencyKey: string) => createClassroom(unitId, csrfToken, idempotencyKey),
  setMode: (unitId: string, options: SetClassroomModeOptions) => setClassroomMode(unitId, options),
  loadMessages: (unitId: string, after: number) => loadClassroomMessages(unitId, after),
  loadOperation: (operationId: string) => loadClassroomOperation(operationId),
  streamSpeech: (options: StreamClassroomSpeechOptions) => streamClassroomSpeech(options),
});

const ROLE_LABELS: Record<ClassroomMessageRole, string> = {
  student: "我", tutor: "启智导师", beginner: "初学同学", advanced: "进阶同学",
  system: "系统", performance: "性能视角", engineering: "工程视角",
  academic: "学术视角", moderator: "主持人",
};
const CLASSROOM_ROLES: ClassroomMessageRole[] = [
  "student", "tutor", "beginner", "advanced", "system",
  "performance", "engineering", "academic", "moderator",
];
const companions: Array<{ role: CompanionRole; label: string }> = [
  { role: "beginner", label: "初学同学" },
  { role: "advanced", label: "进阶同学" },
];
const CONNECTION_CODES = new Set(["CONNECTION_FAILED", "CONNECTION_INTERRUPTED", "EMPTY_STREAM"]);

const phase = ref<"loading" | "ready" | "error">("loading");
const setupError = ref("");
const snapshot = ref<ClassroomSnapshot | null>(null);
const messages = ref<ClassroomMessage[]>([]);
const lastCursor = ref(0);
const modeBusy = ref(false);
const modeError = ref("");
const draft = ref("");
const streaming = ref(false);
const streamingRole = ref<ClassroomMessageRole>("tutor");
const streamingText = ref("");
const streamNotice = ref("");
const streamError = ref("");
const retracted = ref(false);
const pendingSpeech = ref<PendingSpeech | null>(null);
let generation = 0;

const interactive = computed(() => snapshot.value?.mode === "interactive");
const canSend = computed(() => Boolean(draft.value.trim()) && !streaming.value
  && Boolean(props.csrfToken) && phase.value === "ready" && Boolean(snapshot.value));

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}
function isClassroomRole(value: string): value is ClassroomMessageRole {
  return CLASSROOM_ROLES.includes(value as ClassroomMessageRole);
}
function roleOf(value: unknown): ClassroomMessageRole {
  return typeof value === "string" && isClassroomRole(value) ? value : "tutor";
}
function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "课堂暂时无法使用，请重试。";
}
function isRoleEnabled(role: CompanionRole): boolean {
  return snapshot.value?.enabled_roles.includes(role) ?? false;
}

function pendingStorageKey(unitId: string): string { return `edumind:classroom:${unitId}:pending`; }
function createStorageKey(unitId: string): string { return `edumind:classroom:${unitId}:create`; }

function createIdempotencyKey(unitId: string): string {
  try {
    const existing = sessionStorage.getItem(createStorageKey(unitId));
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    sessionStorage.setItem(createStorageKey(unitId), fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

function persistPending(unitId: string, pending: PendingSpeech | null): void {
  try {
    if (pending && pending.operationId) {
      const stored: StoredPending = { key: pending.key, text: pending.text, operationId: pending.operationId };
      sessionStorage.setItem(pendingStorageKey(unitId), JSON.stringify(stored));
    } else {
      sessionStorage.removeItem(pendingStorageKey(unitId));
    }
  } catch { /* Optional browser storage. */ }
}

function readPending(unitId: string): PendingSpeech | null {
  try {
    const raw = sessionStorage.getItem(pendingStorageKey(unitId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredPending>;
    if (typeof value.key !== "string" || typeof value.text !== "string" || typeof value.operationId !== "string") return null;
    return { key: value.key, text: value.text, operationId: value.operationId, terminal: false };
  } catch {
    return null;
  }
}

function clearPending(unitId: string): void { persistPending(unitId, null); }

async function loadTranscript(token: number): Promise<void> {
  const page = await props.loadMessages(props.unitId, 0);
  if (token !== generation) return;
  messages.value = page.messages;
  lastCursor.value = page.last_message_cursor;
}

async function ensureClassroom(token: number): Promise<void> {
  phase.value = "loading";
  setupError.value = "";
  try {
    let snap: ClassroomSnapshot;
    try {
      snap = await props.loadSnapshot(props.unitId);
    } catch (error) {
      const code = error instanceof ClassroomSpeechError ? error.code : "";
      if (code === "NOT_FOUND" && props.csrfToken) {
        snap = await props.create(props.unitId, props.csrfToken, createIdempotencyKey(props.unitId));
      } else {
        throw error;
      }
    }
    if (token !== generation) return;
    snapshot.value = snap;
    lastCursor.value = snap.message_cursor;
    await loadTranscript(token);
    if (token !== generation) return;
    phase.value = "ready";
    void recoverPending(token);
  } catch (error) {
    if (token !== generation) return;
    setupError.value = messageOf(error);
    phase.value = "error";
  }
}

async function recoverPending(token: number): Promise<void> {
  const pending = readPending(props.unitId);
  if (!pending) return;
  pendingSpeech.value = pending;
  try {
    const operation = await props.loadOperation(pending.operationId);
    if (token !== generation) return;
    if (operation.status === "published") {
      await loadTranscript(token);
      clearPending(props.unitId);
      pendingSpeech.value = null;
    } else if (operation.status === "failed" || operation.status === "cancelled" || operation.status === "superseded") {
      clearPending(props.unitId);
      pendingSpeech.value = null;
      streamNotice.value = "上次课堂发言未完成，可重新发送。";
    }
    // accepted / running: keep pending so the user can retry safely.
  } catch {
    // Keep pending; the retry button recovers by idempotent replay.
  }
}

function resetState(): void {
  phase.value = "loading";
  setupError.value = "";
  snapshot.value = null;
  messages.value = [];
  lastCursor.value = 0;
  modeBusy.value = false;
  modeError.value = "";
  draft.value = "";
  streaming.value = false;
  streamingRole.value = "tutor";
  streamingText.value = "";
  streamNotice.value = "";
  streamError.value = "";
  retracted.value = false;
  pendingSpeech.value = null;
}

watch(() => props.unitId, () => {
  const token = ++generation;
  resetState();
  if (props.unitId) void ensureClassroom(token);
}, { immediate: true });

watch(() => props.refreshToken, () => {
  if (!props.unitId || phase.value !== "ready") return;
  if (streaming.value) {
    streaming.value = false;
    streamingText.value = "";
    retracted.value = true;
    if (pendingSpeech.value && !draft.value) draft.value = pendingSpeech.value.text;
    pendingSpeech.value = null;
    clearPending(props.unitId);
    streamNotice.value = "课堂进度已变化，原发言未发布。";
  }
  void refreshSnapshot();
});

async function applyEvent(event: ClassroomSpeechEvent): Promise<void> {
  switch (event.type) {
    case "agent_start": {
      const operationId = str(event.data.operation_id);
      if (operationId && pendingSpeech.value) {
        pendingSpeech.value.operationId = operationId;
        persistPending(props.unitId, pendingSpeech.value);
      }
      break;
    }
    case "token": {
      streamingRole.value = roleOf(event.data.role);
      streamingText.value += str(event.data.delta);
      break;
    }
    case "review_pass":
    case "message_ready":
      break;
    case "content_retracted":
      streamingText.value = "";
      retracted.value = true;
      streamNotice.value = "本次发言未通过安全审核，未发布。";
      break;
    case "done": {
      const status = str(event.data.status);
      streaming.value = false;
      if (status === "published") {
        clearPending(props.unitId);
        pendingSpeech.value = null;
        await loadTranscript(generation);
      } else if (status === "cancelled") {
        clearPending(props.unitId);
        pendingSpeech.value = null;
        streamNotice.value = "课堂已变化，本次发言未发布。";
        await refreshSnapshot();
      } else if (status === "failed") {
        clearPending(props.unitId);
        pendingSpeech.value = null;
        if (!retracted.value) streamNotice.value = "本次发言未能完成。";
      } else {
        // running: idempotent replay of an in-flight operation.
        streamNotice.value = "发言仍在处理，可稍后重新读取。";
      }
      break;
    }
  }
}

async function runSpeech(target: { key: string; text: string }): Promise<void> {
  if (!snapshot.value || !props.csrfToken || streaming.value) return;
  const token = ++generation;
  const revision = snapshot.value.revision;
  const sceneVersion = snapshot.value.scene_version || props.sceneVersion;
  streaming.value = true;
  streamingRole.value = "tutor";
  streamingText.value = "";
  streamNotice.value = "";
  streamError.value = "";
  retracted.value = false;
  pendingSpeech.value = { key: target.key, text: target.text, operationId: "", terminal: false };
  try {
    await props.streamSpeech({
      unitId: props.unitId,
      text: target.text,
      sceneVersion,
      csrfToken: props.csrfToken,
      idempotencyKey: target.key,
      revision,
      onEvent: (event) => { if (token === generation) void applyEvent(event); },
    });
  } catch (error) {
    if (token !== generation) return;
    streaming.value = false;
    const code = error instanceof ClassroomSpeechError ? error.code : "CONNECTION_INTERRUPTED";
    if (code === "CLASSROOM_VERSION_CONFLICT" || code === "SCENE_VERSION_CONFLICT" || code === "MESSAGE_CURSOR_INVALID") {
      clearPending(props.unitId);
      pendingSpeech.value = null;
      streamNotice.value = "课堂版本已更新，正在刷新。";
      await refreshSnapshot();
      return;
    }
    streamError.value = messageOf(error);
    if (pendingSpeech.value) {
      pendingSpeech.value.terminal = !CONNECTION_CODES.has(code);
      persistPending(props.unitId, pendingSpeech.value);
    }
  }
}

async function sendSpeech(): Promise<void> {
  const text = draft.value.trim();
  if (!text || streaming.value || !snapshot.value || !props.csrfToken) return;
  draft.value = "";
  await runSpeech({ key: crypto.randomUUID(), text });
}

async function retrySpeech(): Promise<void> {
  const pending = pendingSpeech.value;
  if (!pending || streaming.value || !snapshot.value || !props.csrfToken) return;
  const key = pending.terminal ? crypto.randomUUID() : pending.key;
  await runSpeech({ key, text: pending.text });
}

async function retrySetup(): Promise<void> {
  const token = ++generation;
  await ensureClassroom(token);
}

async function refreshSnapshot(): Promise<void> {
  const token = ++generation;
  try {
    const snap = await props.loadSnapshot(props.unitId);
    if (token !== generation) return;
    snapshot.value = snap;
    lastCursor.value = snap.message_cursor;
    await loadTranscript(token);
    if (token !== generation) return;
    phase.value = "ready";
  } catch (error) {
    if (token !== generation) return;
    setupError.value = messageOf(error);
    phase.value = "error";
  }
}

async function applyMode(mode: ClassroomMode, roles: CompanionRole[]): Promise<void> {
  if (!snapshot.value || modeBusy.value || !props.csrfToken) return;
  const token = ++generation;
  if (pendingSpeech.value) {
    const text = pendingSpeech.value.text;
    streaming.value = false;
    clearPending(props.unitId);
    pendingSpeech.value = null;
    if (!draft.value) draft.value = text;
    streamNotice.value = "已切换课堂，本次发言未发布。";
  }
  modeBusy.value = true;
  modeError.value = "";
  try {
    const snap = await props.setMode(props.unitId, {
      mode,
      enabledRoles: roles,
      revision: snapshot.value.revision,
      csrfToken: props.csrfToken,
      idempotencyKey: crypto.randomUUID(),
    });
    if (token !== generation) return;
    snapshot.value = snap;
  } catch (error) {
    if (token !== generation) return;
    const code = error instanceof ClassroomSpeechError ? error.code : "";
    if (code === "CLASSROOM_VERSION_CONFLICT") {
      void refreshSnapshot();
    } else {
      modeError.value = messageOf(error);
    }
  } finally {
    if (token === generation) modeBusy.value = false;
  }
}

async function toggleMode(): Promise<void> {
  if (!snapshot.value) return;
  const next: ClassroomMode = snapshot.value.mode === "focus" ? "interactive" : "focus";
  const roles: CompanionRole[] = next === "interactive"
    ? (snapshot.value.enabled_roles.length ? snapshot.value.enabled_roles : ["beginner", "advanced"])
    : [];
  await applyMode(next, roles);
}

async function toggleRole(role: CompanionRole): Promise<void> {
  if (!snapshot.value) return;
  const enabled = new Set(snapshot.value.enabled_roles);
  if (enabled.has(role)) enabled.delete(role); else enabled.add(role);
  await applyMode("interactive", [...enabled].sort());
}

function handleOnline(): void {
  if (phase.value === "error") {
    void retrySetup();
  } else if (pendingSpeech.value) {
    void retrySpeech();
  }
}

onMounted(() => window.addEventListener("online", handleOnline));
onBeforeUnmount(() => {
  window.removeEventListener("online", handleOnline);
  generation += 1;
});
</script>

<template>
  <section
    class="classroom-panel"
    aria-label="课堂"
    data-testid="classroom-panel"
  >
    <div class="classroom-heading">
      <div>
        <p class="eyebrow">
          课堂
        </p>
        <h2>把这一节讲透</h2>
      </div>
      <NTag
        size="small"
        :type="interactive ? 'warning' : 'info'"
        data-testid="mode-tag"
      >
        {{ interactive ? '互动模式' : '专注模式' }}
      </NTag>
    </div>

    <p
      v-if="phase === 'loading'"
      role="status"
    >
      正在进入课堂…
    </p>
    <div
      v-else-if="phase === 'error'"
      role="alert"
      data-testid="setup-error"
    >
      <p>{{ setupError }}</p>
      <NButton
        size="small"
        data-testid="retry-setup"
        @click="retrySetup"
      >
        重新进入课堂
      </NButton>
    </div>

    <template v-else>
      <div class="classroom-controls">
        <NButton
          data-testid="toggle-mode"
          :disabled="modeBusy"
          @click="toggleMode"
        >
          {{ interactive ? '关闭互动' : '开启互动' }}
        </NButton>
        <div
          v-if="interactive"
          class="role-toggles"
          data-testid="role-toggles"
        >
          <span class="role-toggle-label">参与角色</span>
          <button
            v-for="companion in companions"
            :key="companion.role"
            type="button"
            class="role-chip"
            :aria-pressed="isRoleEnabled(companion.role)"
            :data-testid="`role-${companion.role}`"
            @click="toggleRole(companion.role)"
          >
            {{ companion.label }}
          </button>
        </div>
        <p
          v-if="modeError"
          role="status"
          class="classroom-hint"
        >
          {{ modeError }}
        </p>
      </div>

      <div
        class="transcript"
        aria-label="课堂对话"
        data-testid="transcript"
      >
        <p
          v-if="!messages.length && !streaming"
          class="classroom-hint"
        >
          还没有对话，先向启智提问吧。
        </p>
        <article
          v-for="message in messages"
          :key="message.id"
          class="message"
          :class="`message-${message.role}`"
          :data-role="message.role"
        >
          <span class="message-role">{{ ROLE_LABELS[message.role] ?? message.role }}</span>
          <p class="message-text">
            {{ message.text }}
          </p>
        </article>
        <article
          v-if="streaming"
          class="message message-streaming"
          :data-role="streamingRole"
          aria-live="polite"
        >
          <span class="message-role">
            {{ ROLE_LABELS[streamingRole] ?? streamingRole }}
            <span
              v-if="interactive"
              class="speaker-mark"
            >
              当前发言者
            </span>
          </span>
          <p class="message-text">
            {{ streamingText || '正在思考…' }}
          </p>
        </article>
      </div>

      <p
        v-if="streamNotice"
        role="status"
        class="classroom-notice"
        data-testid="stream-notice"
      >
        {{ streamNotice }}
      </p>
      <div
        v-if="streamError"
        role="alert"
        data-testid="stream-error"
      >
        <p>{{ streamError }}</p>
        <NButton
          size="small"
          data-testid="retry-speech"
          @click="retrySpeech"
        >
          重试发言
        </NButton>
      </div>
      <div
        v-else-if="pendingSpeech && !streaming"
        data-testid="pending-speech"
      >
        <p class="classroom-notice">
          上一次发言尚未确认，可安全重试恢复。
        </p>
        <NButton
          size="small"
          data-testid="retry-speech"
          @click="retrySpeech"
        >
          重试恢复
        </NButton>
      </div>

      <form
        class="composer"
        @submit.prevent="sendSpeech"
      >
        <label for="classroom-speech">向启智提问</label>
        <textarea
          id="classroom-speech"
          v-model="draft"
          rows="3"
          maxlength="2000"
          :disabled="streaming || !props.csrfToken"
          placeholder="例如：插入节点时为什么要先保存后继？"
          data-testid="speech-input"
          @keydown.enter.exact.prevent="sendSpeech"
        />
        <div class="composer-footer">
          <span>Enter 发送 · Shift+Enter 换行</span>
          <NButton
            type="primary"
            attr-type="submit"
            :loading="streaming"
            :disabled="!canSend"
            data-testid="send-speech"
          >
            {{ streaming ? '正在回复' : '发送' }}
          </NButton>
        </div>
      </form>
    </template>
  </section>
</template>

<style scoped>
.classroom-panel {
  max-width: 880px;
  margin: 28px auto;
  padding: clamp(20px, 4vw, 32px);
  background: #fbfcf9;
  border: 1px solid #cbd6d4;
  box-shadow: 6px 6px 0 #c9ddd8;
}
.classroom-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}
.classroom-heading h2 {
  margin: 8px 0;
  font-family: Newsreader, serif;
  font-size: clamp(28px, 4vw, 42px);
  font-weight: 400;
}
.classroom-heading .eyebrow { margin: 0; color: #35656d; }
.classroom-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; margin-bottom: 18px; }
.role-toggles { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.role-toggle-label { font-family: "DM Mono", monospace; font-size: 12px; letter-spacing: .08em; color: #607783; }
.role-chip {
  background: #eaf0f2;
  border: 1px solid #8aafb0;
  border-radius: 999px;
  color: #244c5a;
  cursor: pointer;
  font: inherit;
  padding: 5px 14px;
}
.role-chip[aria-pressed="true"] { background: #35656d; color: #fbfcf9; }
.role-chip:focus-visible { outline: 2px solid #f06e43; outline-offset: 2px; }
.transcript { border-top: 1px solid #cbd6d4; padding-top: 14px; }
.message { margin: 14px 0; padding: 12px 16px; background: #eaf0f2; border-left: 3px solid #8aafb0; }
.message-tutor { background: #d7e4e0; border-left-color: #35656d; }
.message-student { background: #fbfcf9; border-left-color: #f06e43; }
.message-beginner, .message-advanced { background: #eef4f2; border-left-color: #6b9a92; }
.message-role { display: block; font-family: "DM Mono", monospace; font-size: 12px; letter-spacing: .08em; color: #607783; margin-bottom: 6px; }
.speaker-mark { margin-left: 8px; color: #f06e43; }
.message-text { margin: 0; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.message-streaming { background: #fbfcf9; }
.classroom-hint, .classroom-notice { color: #536876; line-height: 1.6; }
.classroom-notice { color: #a13d36; }
.composer { margin-top: 22px; }
.composer label { display: block; font-weight: 700; margin-bottom: 10px; }
.composer textarea {
  background: #fbfcf9;
  border: 1px solid #8aafb0;
  color: #17253a;
  font: inherit;
  max-width: 100%;
  padding: 10px;
  resize: vertical;
  width: 100%;
}
.composer textarea:focus-visible { outline: 2px solid #35656d; outline-offset: 3px; }
.composer-footer { align-items: center; display: flex; justify-content: space-between; margin-top: 12px; }
.composer-footer span { font-family: "DM Mono", monospace; font-size: 12px; color: #708088; }
@media (max-width: 600px) {
  .classroom-heading { flex-direction: column; gap: 8px; }
  .composer-footer { align-items: flex-start; flex-direction: column; gap: 14px; }
}
</style>
