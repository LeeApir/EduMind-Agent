<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NInput, NTag } from "naive-ui";

import { LearningRequestError, startLearningSession, type LearningEvent } from "./api/learningSessions";
import LearningProgressPanel, {
  type PublishedResource,
  type ReviewState,
} from "./components/LearningProgressPanel.vue";
import ProfileCard from "./components/ProfileCard.vue";
import PublishedLearningWorkspace from "./components/PublishedLearningWorkspace.vue";

type StartLearningRequest = (goal: string) => Promise<void>;

interface Resource extends PublishedResource {
  content: Record<string, unknown>;
  review_status: "passed";
}

interface LearningUnitPayload {
  scenes: Array<{ resources: Resource[] }>;
}

interface SessionPayload {
  csrf_token: string;
}

const props = defineProps<{ startLearningRequest?: StartLearningRequest }>();
const goal = ref("");
const submittedGoal = ref("");
const requestState = ref<"idle" | "loading" | "error">("idle");
const requestError = ref("");
const temporaryText = ref("");
const reviewState = ref<ReviewState>("idle");
const resources = ref<Resource[]>([]);
const learningUnitId = ref("");
const operationId = ref("");
const idempotencyKey = ref("");
const csrfToken = ref("");
const canSubmit = computed(() => Boolean(goal.value.trim()) && requestState.value !== "loading");
const publishedResources = computed<PublishedResource[]>(() =>
  resources.value.map(({ id, type, version }) => ({ id, type, version })),
);

async function startLearning(): Promise<void> {
  submittedGoal.value = goal.value.trim();
  resetAttempt();
  await submitLearningRequest();
}

async function retryLearning(): Promise<void> {
  resetAttempt();
  await submitLearningRequest();
}

function resetAttempt(): void {
  requestError.value = "";
  temporaryText.value = "";
  reviewState.value = "idle";
  resources.value = [];
  learningUnitId.value = "";
  operationId.value = "";
  idempotencyKey.value = crypto.randomUUID();
}

async function submitLearningRequest(): Promise<void> {
  requestState.value = "loading";
  try {
    if (props.startLearningRequest) {
      await props.startLearningRequest(submittedGoal.value);
      requestState.value = "idle";
      return;
    }
    const csrf = await ensureSession();
    let readyUnitId = "";
    await startLearningSession({
      goal: submittedGoal.value,
      csrfToken: csrf,
      idempotencyKey: idempotencyKey.value,
      onEvent: (event) => {
        readyUnitId = applyLearningEvent(event) || readyUnitId;
      },
    });
    if (readyUnitId) {
      await loadPublishedUnit(readyUnitId);
    }
    requestState.value = "idle";
  } catch (error: unknown) {
    if (await recoverPublishedOperation()) {
      requestState.value = "idle";
      return;
    }
    requestError.value = error instanceof Error && error.message
      ? error.message
      : "暂时无法开始学习，请检查网络后重试。";
    requestState.value = "error";
  }
}

function applyLearningEvent(event: LearningEvent): string {
  const eventOperationId = stringValue(event.data.operation_id);
  if (eventOperationId) operationId.value = eventOperationId;
  if (event.type === "token" && event.data.temporary === true) {
    temporaryText.value += stringValue(event.data.delta);
  } else if (event.type === "stage_changed" && event.data.stage === "reviewing") {
    reviewState.value = "reviewing";
  } else if (event.type === "review_reject") {
    reviewState.value = "rejected";
  } else if (event.type === "scene_ready") {
    reviewState.value = "published";
    return stringValue(event.data.learning_unit_id);
  }
  return "";
}

async function ensureSession(): Promise<string> {
  if (csrfToken.value) return csrfToken.value;
  let response = await fetch("/api/auth/session", { credentials: "same-origin" });
  if (response.status === 401) {
    response = await fetch("/api/auth/guest", {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  }
  if (!response.ok) throw new Error("无法建立安全学习会话，请刷新页面后重试。");
  const payload = await response.json() as Partial<SessionPayload>;
  if (typeof payload.csrf_token !== "string") {
    throw new Error("学习会话响应无效，请刷新页面后重试。");
  }
  csrfToken.value = payload.csrf_token;
  return csrfToken.value;
}

async function recoverPublishedOperation(): Promise<boolean> {
  if (!operationId.value) return false;
  try {
    const response = await fetch(`/api/learning-operations/${operationId.value}`, {
      credentials: "same-origin",
    });
    if (!response.ok) return false;
    const payload = await response.json() as Record<string, unknown>;
    const unitId = stringValue(payload.learning_unit_id);
    if (payload.status !== "published" || !unitId) return false;
    await loadPublishedUnit(unitId);
    return true;
  } catch {
    return false;
  }
}

async function loadPublishedUnit(unitId = learningUnitId.value): Promise<void> {
  if (!unitId) throw new Error("正式学习资源缺少单元标识，请重新开始。");
  const response = await fetch(`/api/learning-units/${unitId}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new LearningRequestError({ message: "正式资源暂时无法读取，请重试。" });
  }
  const payload = await response.json() as LearningUnitPayload;
  const loaded = payload.scenes.flatMap((scene) => scene.resources).filter(isPublishedResource);
  if (!loaded.length) throw new Error("正式学习资源为空，请重新开始。");
  learningUnitId.value = unitId;
  resources.value = loaded;
  reviewState.value = "published";
}

function isPublishedResource(value: Resource): value is Resource {
  return ["explanation", "code", "exercise"].includes(value.type)
    && value.review_status === "passed"
    && Boolean(value.content)
    && typeof value.content === "object";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
</script>

<template>
  <main class="learning-desk">
    <header class="masthead">
      <p class="eyebrow">
        EDUMIND / 数据结构
      </p>
      <span class="session-mark">从一句话开始</span>
    </header>
    <section
      class="lesson-prompt"
      aria-labelledby="page-title"
    >
      <div
        class="node-orbit"
        aria-hidden="true"
      >
        <i /><i /><i /><i />
      </div>
      <p class="chapter">
        学习入口
      </p>
      <h1 id="page-title">
        你现在想<br><em>弄懂什么？</em>
      </h1>
      <p class="lead">
        说出卡住的知识点、考试目标，或想先看的代码。启智会从第一段讲起。
      </p>
      <form
        class="goal-form"
        @submit.prevent="startLearning"
      >
        <label for="learning-goal">学习目标</label>
        <NInput
          v-model:value="goal"
          type="textarea"
          placeholder="例如：链表插入的指针总是搞混，想先看 C 代码"
          :autosize="{ minRows: 3, maxRows: 5 }"
          :input-props="{ id: 'learning-goal' }"
        />
        <div class="form-footer">
          <span>不需要先填写画像</span>
          <NButton
            type="primary"
            attr-type="submit"
            :disabled="!canSubmit"
          >
            开始学习 →
          </NButton>
        </div>
      </form>
    </section>
    <section
      class="cue-strip"
      aria-label="可直接使用的学习方式"
    >
      <NTag
        round
        :bordered="false"
      >
        先看代码
      </NTag>
      <NTag
        round
        :bordered="false"
      >
        换个例子
      </NTag>
      <NTag
        round
        :bordered="false"
      >
        补 C 指针
      </NTag>
    </section>
    <aside
      v-if="requestState === 'loading'"
      class="next-state"
      aria-live="polite"
      data-testid="loading-state"
    >
      正在为“{{ submittedGoal }}”准备第一段讲解。无需先填写画像。
    </aside>
    <aside
      v-else-if="requestState === 'error'"
      class="next-state error-state"
      aria-live="assertive"
    >
      {{ requestError }}
      <NButton
        size="small"
        @click="retryLearning"
      >
        重试
      </NButton>
    </aside>
    <LearningProgressPanel
      :temporary-text="temporaryText"
      :review-state="reviewState"
      :published-resources="publishedResources"
      :reload-published="learningUnitId ? loadPublishedUnit : undefined"
    />
    <PublishedLearningWorkspace
      v-if="resources.length"
      :resources="resources"
    />
    <ProfileCard />
  </main>
</template>
