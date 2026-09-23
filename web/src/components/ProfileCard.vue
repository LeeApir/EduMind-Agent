<script setup lang="ts">
import { onMounted, ref } from "vue";
import { NButton, NInput, NTag } from "naive-ui";

import {
  EVIDENCE_SOURCE_LABELS,
  PROFILE_FIELDS,
  PROFILE_FIELD_LABELS,
  PROFILE_FIELD_STATUS_LABELS,
  ProfileRequestError,
  type CorrectProfileOptions,
  type EditableProfileField,
  type EvidenceSource,
  type Profile,
  type ProfileField,
  type ProfileFieldStatus,
  correctProfile as requestCorrection,
  ensureProfileSession,
  fetchProfile as requestProfile,
  isEditableProfileField,
  profileFieldStatus,
  strongestEvidenceSource,
} from "../api/profile";

const props = withDefaults(defineProps<{
  fetchProfile?: () => Promise<Profile>;
  correctProfile?: (options: CorrectProfileOptions) => Promise<Profile>;
  ensureSession?: () => Promise<string>;
}>(), {
  fetchProfile: () => requestProfile(),
  correctProfile: (options: CorrectProfileOptions) => requestCorrection(options),
  ensureSession: () => ensureProfileSession(),
});

const profile = ref<Profile | null>(null);
const loadState = ref<"loading" | "ready" | "empty" | "error">("loading");
const loadError = ref("");
const saveState = ref<"idle" | "loading" | "error" | "conflict">("idle");
const saveError = ref("");
const editingField = ref<EditableProfileField | null>(null);
const draft = ref("");
const saveIdempotencyKey = ref("");

const fields = PROFILE_FIELDS;

const STATUS_TAG_TYPES: Record<ProfileFieldStatus, "default" | "success" | "info" | "warning"> = {
  unknown: "default",
  known: "success",
  inferred: "info",
  corrected: "warning",
};

onMounted(loadProfile);

async function loadProfile(): Promise<void> {
  loadState.value = "loading";
  loadError.value = "";
  try {
    await props.ensureSession();
    profile.value = await props.fetchProfile();
    loadState.value = "ready";
  } catch (error: unknown) {
    if (error instanceof ProfileRequestError && error.code === "NOT_FOUND") {
      profile.value = null;
      loadState.value = "empty";
      return;
    }
    loadState.value = "error";
    loadError.value = error instanceof Error && error.message
      ? error.message
      : "画像读取失败，请重试。";
  }
}

function statusOf(field: ProfileField): ProfileFieldStatus {
  return profile.value ? profileFieldStatus(field, profile.value) : "unknown";
}

function statusTagType(field: ProfileField): "default" | "success" | "info" | "warning" {
  return STATUS_TAG_TYPES[statusOf(field)];
}

function sourceOf(field: ProfileField): EvidenceSource | null {
  return profile.value ? strongestEvidenceSource(field, profile.value) : null;
}

function sourceLabel(field: ProfileField): string {
  if (statusOf(field) === "corrected" || statusOf(field) === "unknown") {
    return "";
  }
  const source = sourceOf(field);
  return source ? `来源：${EVIDENCE_SOURCE_LABELS[source]}` : "";
}

function valueOf(field: ProfileField): string {
  const value = profile.value?.[field];
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function isEditing(field: ProfileField): boolean {
  return editingField.value === field;
}

function startEdit(field: ProfileField): void {
  if (!isEditableProfileField(field)) {
    return;
  }
  editingField.value = field;
  draft.value = valueOf(field);
  saveIdempotencyKey.value = crypto.randomUUID();
  saveState.value = "idle";
  saveError.value = "";
}

function cancelEdit(): void {
  editingField.value = null;
  draft.value = "";
  saveIdempotencyKey.value = "";
  saveState.value = "idle";
  saveError.value = "";
}

async function saveEdit(): Promise<void> {
  const field = editingField.value;
  if (!field || !profile.value) {
    return;
  }
  const parsed = parseDraft(field, draft.value);
  if (parsed.error) {
    saveState.value = "error";
    saveError.value = parsed.error;
    return;
  }
  saveState.value = "loading";
  saveError.value = "";
  try {
    const csrfToken = await props.ensureSession();
    const updated = await props.correctProfile({
      corrections: { [field]: parsed.value },
      expectedVersion: profile.value.version,
      csrfToken,
      idempotencyKey: saveIdempotencyKey.value,
    });
    profile.value = updated;
    cancelEdit();
  } catch (error: unknown) {
    if (error instanceof ProfileRequestError && error.code === "PROFILE_VERSION_CONFLICT") {
      saveState.value = "conflict";
      saveError.value = "画像已更新到新版本，请重新加载后再修改。";
    } else {
      saveState.value = "error";
      saveError.value = error instanceof Error && error.message
        ? error.message
        : "画像修正失败，请重试。";
    }
  }
}

async function reloadAfterConflict(): Promise<void> {
  cancelEdit();
  await loadProfile();
}

function parseDraft(field: EditableProfileField, text: string): { value?: unknown; error?: string } {
  const trimmed = text.trim();
  if (!trimmed) {
    return { error: "请输入要保存的内容。" };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { error: "请输入有效的 JSON。" };
  }
  if (field === "error_preferences") {
    if (!Array.isArray(parsed)) {
      return { error: "易错偏好需要是 JSON 数组，例如 [\"容易漏掉边界条件\"]。" };
    }
  } else if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { error: "该字段需要是 JSON 对象，例如 { \"major\": \"计算机\" }。" };
  }
  return { value: parsed };
}
</script>

<template>
  <section class="profile-card" data-testid="profile-card" aria-label="学习画像">
    <header class="profile-head">
      <h2>学习画像</h2>
      <NTag v-if="profile" type="info" size="small">版本 v{{ profile.version }}</NTag>
    </header>

    <p v-if="loadState === 'loading'" class="profile-hint" data-testid="profile-loading">
      正在读取学习画像…
    </p>

    <aside
      v-else-if="loadState === 'error'"
      class="profile-hint error"
      data-testid="profile-load-error"
      role="alert"
    >
      {{ loadError }}
      <NButton size="small" @click="loadProfile">重试</NButton>
    </aside>

    <aside
      v-else-if="loadState === 'empty'"
      class="profile-hint"
      data-testid="profile-empty"
    >
      还没有生成画像。开始一次学习后，启智会从你的目标建立画像。
      <NButton size="small" @click="loadProfile">重新检查</NButton>
    </aside>

    <template v-else-if="profile">
      <p class="initial-query" data-testid="profile-initial-query">
        最初目标：{{ profile.initial_query }}
      </p>
      <ul class="profile-fields" aria-label="画像字段">
        <li
          v-for="field in fields"
          :key="field"
          class="profile-field"
          :data-testid="`profile-field-${field}`"
        >
          <div class="field-head">
            <span class="field-name">{{ PROFILE_FIELD_LABELS[field] }}</span>
            <span class="field-meta">
              <NTag :type="statusTagType(field)" size="small">
                {{ PROFILE_FIELD_STATUS_LABELS[statusOf(field)] }}
              </NTag>
              <em v-if="sourceLabel(field)">{{ sourceLabel(field) }}</em>
            </span>
          </div>

          <div
            v-if="isEditing(field)"
            class="field-editor"
            :data-testid="`profile-editor-${field}`"
          >
            <NInput
              v-model:value="draft"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              :input-props="{ id: `profile-draft-${field}` }"
            />
            <p v-if="saveState === 'error'" class="save-hint error" role="alert">
              {{ saveError }}
            </p>
            <p v-else-if="saveState === 'conflict'" class="save-hint conflict" role="alert">
              {{ saveError }}
              <NButton size="tiny" @click="reloadAfterConflict">加载最新版本</NButton>
            </p>
            <div class="editor-actions">
              <NButton
                size="small"
                type="primary"
                :loading="saveState === 'loading'"
                @click="saveEdit"
              >
                保存
              </NButton>
              <NButton size="small" @click="cancelEdit">取消</NButton>
            </div>
          </div>

          <template v-else>
            <pre v-if="valueOf(field)" class="field-value"><code>{{ valueOf(field) }}</code></pre>
            <p v-else class="field-empty">尚未了解</p>
            <div v-if="isEditableProfileField(field)" class="field-actions">
              <NButton size="small" @click="startEdit(field)">编辑</NButton>
            </div>
          </template>
        </li>
      </ul>
    </template>
  </section>
</template>
