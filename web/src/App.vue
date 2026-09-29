<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { NButton, NInput, NTag } from "naive-ui";

import { LearningRequestError, startLearningSession, type LearningEvent } from "./api/learningSessions";
import LearningProgressPanel, {
  type PublishedResource,
  type ReviewState,
} from "./components/LearningProgressPanel.vue";
import ProfileCard from "./components/ProfileCard.vue";
import PublishedLearningWorkspace from "./components/PublishedLearningWorkspace.vue";
import LearningPathPanel from "./components/LearningPathPanel.vue";
import AnimationPanel from "./components/AnimationPanel.vue";
import ClassroomPanel from "./components/ClassroomPanel.vue";
import DebatePanel from "./components/DebatePanel.vue";
import LearningControlsPanel from "./components/LearningControlsPanel.vue";
import { ClassroomSpeechError, controlClassroom, loadClassroom, type LearningResourceType } from "./api/classroom";

type StartLearningRequest = (goal: string) => Promise<void>;

interface Resource extends PublishedResource {
  content: Record<string, unknown>;
  review_status: "passed";
}

interface LearningUnitPayload {
  scenes: Array<{
    id?: string;
    scene_key?: string;
    version?: number;
    is_current?: boolean;
    resources: Resource[];
  }>;
  knowledge_node_id?: string | null;
  path_target_node_id?: string | null;
}

interface SceneVersion {
  id: string;
  sceneKey: string;
  version: number;
  isCurrent: boolean;
  resources: Resource[];
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
const scenes = ref<SceneVersion[]>([]);
const selectedSceneId = ref("");
const learningUnitId = ref("");
const animationNodeId = ref("");
const classroomRefreshToken = ref(0);
const debateActive = ref(false);
const operationId = ref("");
const idempotencyKey = ref("");
const csrfToken = ref("");
const profileRefreshToken = ref(0);
const pathTargetNodeId = ref("");
const pathRefreshToken = ref(0);
const restoringUnit = ref(false);
const restoreUnitError = ref("");
let learningGeneration = 0;
let pendingResourceSelection: {
  signature: string;
  key: string;
  revision: number;
} | null = null;
const canSubmit = computed(() => Boolean(goal.value.trim())
  && (requestState.value !== "loading" || goal.value.trim() !== submittedGoal.value));
const selectedScene = computed(() => scenes.value.find((scene) => scene.id === selectedSceneId.value));
const resources = computed<Resource[]>(() => selectedScene.value?.resources ?? []);
const animationSceneVersion = computed(() => selectedScene.value?.version ?? 0);
const classroomSceneVersion = computed(() => scenes.value.find((scene) => scene.isCurrent && scene.sceneKey === "intro")?.version ?? animationSceneVersion.value);
const publishedResources = computed<PublishedResource[]>(() =>
  resources.value.map(({ id, type, version }) => ({ id, type, version })),
);

function selectionStorageKey(unitId: string): string { return `edumind:scene-selection:${unitId}`; }
function selectScene(sceneId: string): void {
  if (!scenes.value.some((scene) => scene.id === sceneId)) return;
  selectedSceneId.value = sceneId;
  try { sessionStorage.setItem(selectionStorageKey(learningUnitId.value), sceneId); } catch { /* Optional. */ }
}

async function startLearning(): Promise<void> {
  if (!canSubmit.value) return;
  submittedGoal.value = goal.value.trim();
  resetAttempt();
  await submitLearningRequest();
}

async function retryLearning(): Promise<void> {
  if (requestState.value === "loading") return;
  requestError.value = "";
  if (operationId.value) {
    const generation = learningGeneration;
    requestState.value = "loading";
    try {
      await recoverPublishedOperation(generation);
      if (generation === learningGeneration) requestState.value = "idle";
    } catch (error) {
      if (generation !== learningGeneration) return;
      requestError.value = error instanceof Error ? error.message : "恢复失败，请再次重试。";
      requestState.value = "error";
    }
    return;
  }
  await submitLearningRequest();
}

async function regenerateLearning(): Promise<void> {
  if (!submittedGoal.value || requestState.value === "loading") return;
  resetAttempt();
  await submitLearningRequest();
}

function resetAttempt(): void {
  learningGeneration += 1;
  restoringUnit.value = false;
  restoreUnitError.value = "";
  requestError.value = "";
  temporaryText.value = "";
  reviewState.value = "idle";
  scenes.value = [];
  selectedSceneId.value = "";
  pendingResourceSelection = null;
  pathTargetNodeId.value = "";
  learningUnitId.value = "";
  animationNodeId.value = "";
  classroomRefreshToken.value += 1;
  operationId.value = "";
  idempotencyKey.value = crypto.randomUUID();
}

async function submitLearningRequest(): Promise<void> {
  const generation = learningGeneration;
  const requestGoal = submittedGoal.value;
  const requestKey = idempotencyKey.value;
  let recoveryAttempted = false;
  requestState.value = "loading";
  try {
    if (props.startLearningRequest) {
      await props.startLearningRequest(requestGoal);
      if (generation !== learningGeneration) return;
      profileRefreshToken.value += 1;
      requestState.value = "idle";
      return;
    }
    const csrf = await ensureSession();
    if (generation !== learningGeneration) return;
    let readyUnitId = "";
    await startLearningSession({
      goal: requestGoal,
      csrfToken: csrf,
      idempotencyKey: requestKey,
      onEvent: (event) => {
        if (generation !== learningGeneration) return;
        readyUnitId = applyLearningEvent(event) || readyUnitId;
      },
    });
    if (generation !== learningGeneration) return;
    if (readyUnitId) {
      await loadPublishedUnit(readyUnitId, generation);
    } else if (operationId.value) {
      recoveryAttempted = true;
      await recoverPublishedOperation(generation);
    } else {
      throw new Error("未收到操作状态，请恢复原请求。");
    }
    if (generation === learningGeneration) requestState.value = "idle";
  } catch (error: unknown) {
    if (generation !== learningGeneration) return;
    if (error instanceof LearningRequestError && error.operationId) operationId.value = error.operationId;
    let recoveryError: unknown;
    if (operationId.value && !recoveryAttempted) {
      try {
        await recoverPublishedOperation(generation);
        if (generation === learningGeneration) requestState.value = "idle";
        return;
      } catch (failure) {
        recoveryError = failure;
      }
    }
    if (generation !== learningGeneration) return;
    const failure = recoveryError ?? error;
    requestError.value = failure instanceof Error && failure.message
      ? failure.message
      : "暂时无法开始学习，请检查网络后重试。";
    requestState.value = "error";
  }
}

function applyLearningEvent(event: LearningEvent): string {
  const eventOperationId = stringValue(event.data.operation_id);
  if (eventOperationId) operationId.value = eventOperationId;
  if (event.type === "agent_start" && event.data.stage === "preparing") {
    profileRefreshToken.value += 1;
  } else if (event.type === "token" && event.data.temporary === true) {
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

async function recoverPublishedOperation(generation: number): Promise<void> {
  const recoveringOperationId = operationId.value;
  if (!recoveringOperationId) throw new Error("缺少操作标识，请恢复原请求。");
  const response = await fetch(`/api/learning-operations/${recoveringOperationId}`, {
    credentials: "same-origin",
  });
  if (generation !== learningGeneration) return;
  if (!response.ok) throw new Error("原请求状态暂时无法读取，请再次重试恢复。");
  const payload = await response.json() as Record<string, unknown>;
  if (generation !== learningGeneration) return;
  const unitId = stringValue(payload.learning_unit_id);
  if (payload.id !== recoveringOperationId) throw new Error("原请求状态无效，请再次重试恢复。");
  if (payload.status === "published" && unitId) {
    await loadPublishedUnit(unitId, generation);
    return;
  }
  if (payload.status === "failed" || payload.status === "canceled") {
    throw new Error("原请求已失败或取消。恢复不会再次生成；需要新内容请明确选择“重新生成”。");
  }
  throw new Error("原请求尚未发布，请等待后重试恢复；不会重复生成。");
}

async function loadPublishedUnit(
  unitId = learningUnitId.value,
  expectedGeneration = learningGeneration,
  published?: { startedSelectionId: string; sceneKey: string; sceneVersion: number },
): Promise<void> {
  if (!unitId) throw new Error("正式学习资源缺少单元标识，请重新开始。");
  const response = await fetch(`/api/learning-units/${encodeURIComponent(unitId)}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new LearningRequestError({ message: "正式资源暂时无法读取，请重试。" });
  }
  const payload = await response.json() as LearningUnitPayload;
  const loaded = payload.scenes.map((scene, index): SceneVersion => ({
    id: typeof scene.id === "string" ? scene.id : `legacy-${index}`,
    sceneKey: typeof scene.scene_key === "string" ? scene.scene_key : "intro",
    version: Number.isInteger(scene.version) ? scene.version as number : 0,
    isCurrent: scene.is_current !== false,
    resources: scene.resources.filter(isPublishedResource),
  })).filter((scene) => scene.resources.length);
  if (!loaded.length) throw new Error("正式学习资源为空，请重新开始。");
  if (expectedGeneration !== learningGeneration) return;
  let priorSelection = learningUnitId.value === unitId ? selectedSceneId.value : "";
  if (!priorSelection) {
    try { priorSelection = sessionStorage.getItem(selectionStorageKey(unitId)) ?? ""; } catch { /* Optional. */ }
  }
  const current = loaded.find((scene) => scene.isCurrent && scene.sceneKey === "intro")
    ?? loaded.find((scene) => scene.isCurrent) ?? loaded[0];
  const publishedScene = published && priorSelection === published.startedSelectionId
    ? loaded.find((scene) => scene.version === published.sceneVersion && scene.sceneKey === published.sceneKey)
    : undefined;
  const selected = publishedScene ?? loaded.find((scene) => scene.id === priorSelection) ?? current;
  learningUnitId.value = unitId;
  scenes.value = loaded;
  selectedSceneId.value = selected.id;
  try { sessionStorage.setItem(selectionStorageKey(unitId), selected.id); } catch { /* Optional. */ }
  animationNodeId.value = typeof payload.knowledge_node_id === "string" ? payload.knowledge_node_id : "";
  pathTargetNodeId.value = typeof payload.path_target_node_id === "string" ? payload.path_target_node_id : "";
  reviewState.value = "published";
  try { sessionStorage.setItem("edumind:last-learning-unit", unitId); } catch { /* Storage is optional; server state remains authoritative. */ }
}

async function handleScenePublished(startedSelectionId: string, sceneKey: string, sceneVersion: number): Promise<void> {
  const generation = learningGeneration;
  const unitId = learningUnitId.value;
  await loadPublishedUnit(unitId, generation, { startedSelectionId, sceneKey, sceneVersion });
  if (generation === learningGeneration) classroomRefreshToken.value += 1;
}

async function selectResource(type: LearningResourceType): Promise<void> {
  if (!selectedScene.value?.isCurrent || !learningUnitId.value || !csrfToken.value) return;
  const signature = `${learningUnitId.value}:${selectedScene.value.id}:${type}`;
  if (!pendingResourceSelection || pendingResourceSelection.signature !== signature) {
    const snapshot = await loadClassroom(learningUnitId.value);
    if (snapshot.scene_key !== selectedScene.value.sceneKey
      || snapshot.scene_version !== selectedScene.value.version) {
      throw new Error("课堂版本已更新，请刷新后选择资源。");
    }
    pendingResourceSelection = { signature, key: crypto.randomUUID(), revision: snapshot.revision };
  }
  try {
    await controlClassroom({
      unitId: learningUnitId.value, action: "select_resource", resourceType: type,
      revision: pendingResourceSelection.revision, csrfToken: csrfToken.value,
      idempotencyKey: pendingResourceSelection.key,
    });
    pendingResourceSelection = null;
    classroomRefreshToken.value += 1;
  } catch (error) {
    if (error instanceof ClassroomSpeechError && !error.retryable) {
      pendingResourceSelection = null;
    }
    throw error;
  }
}

async function restoreRecentUnit(): Promise<void> {
  let unitId = "";
  try { unitId = sessionStorage.getItem("edumind:last-learning-unit") ?? ""; } catch { return; }
  if (!/^[A-Za-z0-9_-]{8,64}$/.test(unitId)) return;
  const token = learningGeneration;
  restoringUnit.value = true;
  restoreUnitError.value = "";
  try {
    await ensureSession();
    await loadPublishedUnit(unitId, token);
  } catch {
    if (token === learningGeneration) restoreUnitError.value = "上次学习资源暂时无法读取。可以重试读取或开始新目标。";
  } finally {
    if (token === learningGeneration) restoringUnit.value = false;
  }
}
onMounted(() => { if (!props.startLearningRequest) void restoreRecentUnit(); });

function handleQuizSubmitted(): void {
  profileRefreshToken.value += 1;
  pathRefreshToken.value += 1;
}

function isPublishedResource(value: Resource): value is Resource {
  return ["explanation", "code", "exercise"].includes(value.type)
    && typeof value.id === "string" && Number.isInteger(value.version) && value.version >= 1
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
        重试恢复原请求
      </NButton>
    </aside>
    <NButton
      v-if="submittedGoal && requestState !== 'loading'"
      size="small"
      data-testid="regenerate-learning"
      @click="regenerateLearning"
    >
      重新生成（新请求）
    </NButton>
    <LearningProgressPanel
      :temporary-text="temporaryText"
      :review-state="reviewState"
      :published-resources="publishedResources"
      :reload-published="learningUnitId ? loadPublishedUnit : undefined"
    />
    <DebatePanel
      v-if="resources.length && learningUnitId && csrfToken"
      :unit-id="learningUnitId"
      :csrf-token="csrfToken"
      :refresh-token="classroomRefreshToken"
      @active="debateActive = $event"
      @changed="classroomRefreshToken += 1"
    />
    <div v-show="!debateActive">
      <PublishedLearningWorkspace
        v-if="resources.length"
        :key="selectedSceneId"
        :resources="resources"
        :csrf-token="csrfToken"
        :select-resource="selectResource"
        @quiz-submitted="handleQuizSubmitted"
      />
      <LearningControlsPanel
        v-if="resources.length && learningUnitId && csrfToken"
        :unit-id="learningUnitId"
        :csrf-token="csrfToken"
        :scenes="scenes"
        :selected-scene-id="selectedSceneId"
        @select-scene="selectScene"
        @scene-changed="handleScenePublished"
        @classroom-changed="classroomRefreshToken += 1"
      />
      <AnimationPanel
        v-if="resources.length && learningUnitId && animationSceneVersion >= 1"
        :unit-id="learningUnitId"
        :node-id="animationNodeId"
        :scene-version="animationSceneVersion"
        :csrf-token="csrfToken"
      />
      <ClassroomPanel
        v-if="resources.length && learningUnitId && csrfToken"
        :unit-id="learningUnitId"
        :csrf-token="csrfToken"
        :scene-version="classroomSceneVersion"
        :refresh-token="classroomRefreshToken"
      />
    </div>
    <p
      v-if="restoringUnit"
      role="status"
    >
      正在恢复上次已审核的学习资源…
    </p>
    <section
      v-if="restoreUnitError"
      role="alert"
    >
      <p>{{ restoreUnitError }}</p>
      <NButton @click="restoreRecentUnit">
        重新读取上次学习
      </NButton>
    </section>
    <LearningPathPanel
      v-if="pathTargetNodeId"
      :target-node-id="pathTargetNodeId"
      :csrf-token="csrfToken"
      :refresh-token="pathRefreshToken"
    />
    <ProfileCard :refresh-token="profileRefreshToken" />
  </main>
</template>
