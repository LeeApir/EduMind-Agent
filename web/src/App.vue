<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { NButton, NInput, NTag } from "naive-ui";

import { LearningRequestError, errorFromPayload, startLearningSession, type GoalCandidate, type LearningEvent } from "./api/learningSessions";
import { readHybridOperation, watchHybridOperation } from "./api/hybridReview";
import TeachingNodeSummary from "./components/TeachingNodeSummary.vue";
import type { TeachingBindingStatus, TeachingContext, TeachingMode } from "./api/teachingContext";
import { ensureProfileSession } from "./api/profile";
import LearningProgressPanel, {
  type PublishedResource,
  type ReviewState,
} from "./components/LearningProgressPanel.vue";
import ProfileCard from "./components/ProfileCard.vue";
import PublishedLearningWorkspace from "./components/PublishedLearningWorkspace.vue";
import LearningPathPanel from "./components/LearningPathPanel.vue";
import KnowledgeExplorer from "./components/KnowledgeExplorer.vue";
import AnimationPanel from "./components/AnimationPanel.vue";
import ClassroomPanel from "./components/ClassroomPanel.vue";
import DebatePanel from "./components/DebatePanel.vue";
import LearningControlsPanel from "./components/LearningControlsPanel.vue";
import NotesDownload from "./components/NotesDownload.vue";
import { ClassroomSpeechError, controlClassroom, loadClassroom, type LearningResourceType } from "./api/classroom";

type StartLearningRequest = (goal: string) => Promise<void>;

interface Resource extends PublishedResource {
  content: Record<string, unknown>;
  review_status: "passed";
}

interface LearningUnitPayload {
  teaching_context?: TeachingContext | null;
  binding_status?: TeachingBindingStatus;
  publication_version?: number;
  approval_source?: string;
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

const props = defineProps<{ startLearningRequest?: StartLearningRequest }>();
const goal = ref("");
const submittedGoal = ref("");
const teachingMode = ref<TeachingMode>("target");
const submittedTeachingMode = ref<TeachingMode>("target");
const teachingContext = ref<TeachingContext | null>(null);
const publishedTeachingContext = ref<TeachingContext | null>(null);
const bindingStatus = ref<TeachingBindingStatus>(null);
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
const generationPhase = ref("");
const goalCandidates = ref<GoalCandidate[]>([]);
const clarificationReason = ref("");
const approvalSource = ref("");
const publicationVersion = ref<number | undefined>();
let readyPublicationVersion: number | undefined;
let generationController: AbortController | undefined;
let stopReviewWatch: (() => void) | undefined;
const phaseLabel = computed(() => ({ planning: "正在准备教学计划", generating: "正在生成场景内容",
  reviewing: "正在审核内容", consistency_check: "正在核对整堂课", awaiting_human: "等待人工复核",
  publishing: "正在发布正式课程" })[generationPhase.value] ?? "");
onBeforeUnmount(() => { stopReviewWatch?.(); generationController?.abort(); learningGeneration += 1; });
let learningGeneration = 0;
let pendingResourceSelection: {
  signature: string;
  key: string;
  revision: number;
} | null = null;
const canSubmit = computed(() => Boolean(goal.value.trim())
  && (requestState.value !== "loading" || goal.value.trim() !== submittedGoal.value));
const selectedScene = computed(() => scenes.value.find((scene) => scene.id === selectedSceneId.value));
const resources = computed<Resource[]>(() => publicationVersion.value
  ? scenes.value.flatMap((scene) => scene.resources) : selectedScene.value?.resources ?? []);
const animationSceneVersion = computed(() => selectedScene.value?.version ?? 0);
const classroomSceneVersion = computed(() => scenes.value.find((scene) => scene.isCurrent && ["intro", "explanation"].includes(scene.sceneKey))?.version ?? animationSceneVersion.value);
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
  submittedTeachingMode.value = teachingMode.value;
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
  submittedTeachingMode.value = teachingMode.value;
  resetAttempt();
  await submitLearningRequest();
}

function resetAttempt(): void {
  teachingContext.value = null;
  bindingStatus.value = null;
  generationController?.abort();
  stopReviewWatch?.();
  readyPublicationVersion = undefined;
  generationPhase.value = "";
  goalCandidates.value = [];
  clarificationReason.value = "";
  learningGeneration += 1;
  restoringUnit.value = false;
  restoreUnitError.value = "";
  requestError.value = "";
  temporaryText.value = "";
  reviewState.value = "idle";
  pendingResourceSelection = null;
  classroomRefreshToken.value += 1;
  operationId.value = "";
  try { sessionStorage.removeItem("edumind:last-learning-operation"); } catch { /* Optional. */ }
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
    generationController = new AbortController();
    await startLearningSession({
      signal: generationController.signal,
      goal: requestGoal,
      teachingMode: submittedTeachingMode.value,
      csrfToken: csrf,
      idempotencyKey: requestKey,
      onEvent: (event) => {
        if (generation !== learningGeneration) return;
        readyUnitId = applyLearningEvent(event) || readyUnitId;
      },
    });
    if (generation !== learningGeneration) return;
    if (readyUnitId) {
      await loadPublishedUnit(readyUnitId, generation, undefined, readyPublicationVersion);
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
    if (operationId.value && !recoveryAttempted
      && !(error instanceof LearningRequestError && !error.retryable)) {
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
    generationPhase.value = "";
    if (failure instanceof LearningRequestError && !failure.retryable) temporaryText.value = "";
    if (failure instanceof LearningRequestError && failure.code === "GOAL_CLARIFICATION_REQUIRED") {
      goalCandidates.value = failure.candidates;
      clarificationReason.value = failure.reason ?? "unknown";
    }
    requestState.value = "error";
  }
}

function applyLearningEvent(event: LearningEvent): string {
  const eventOperationId = stringValue(event.data.operation_id);
  if (eventOperationId) {
    operationId.value = eventOperationId;
    if (event.type === "agent_start") {
      try { sessionStorage.setItem("edumind:last-learning-operation", eventOperationId); } catch { /* Optional. */ }
    }
  }
  if (event.type === "stage_changed" || event.type === "agent_start") generationPhase.value = stringValue(event.data.phase || event.data.stage);
  if (event.type === "teaching_selected") {
    teachingContext.value = event.data.teaching_context as TeachingContext;
    bindingStatus.value = "bound";
  }
  if (event.type === "review_required") {
    reviewState.value = "awaiting_human";
    temporaryText.value = "";
  }
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
    readyPublicationVersion = typeof event.data.publication_version === "number" ? event.data.publication_version : undefined;
    return stringValue(event.data.learning_unit_id);
  }
  return "";
}

async function ensureSession(): Promise<string> {
  if (csrfToken.value) return csrfToken.value;
  csrfToken.value = await ensureProfileSession();
  return csrfToken.value;
}

async function recoverPublishedOperation(generation: number): Promise<void> {
  const recoveringOperationId = operationId.value;
  if (!recoveringOperationId) throw new Error("缺少操作标识，请恢复原请求。");
  const payload = await readHybridOperation(recoveringOperationId);
  if (generation !== learningGeneration) return;
  teachingContext.value = payload.teaching_context ?? null;
  bindingStatus.value = payload.binding_status ?? null;
  const unitId = stringValue(payload.learning_unit_id);
  if (payload.id !== recoveringOperationId) throw new Error("原请求状态无效，请再次重试恢复。");
  if ((payload.status === "published" || payload.status === "completed") && unitId) {
    stopReviewWatch?.();
    await loadPublishedUnit(unitId, generation, undefined, payload.publication_version ?? undefined);
    try { sessionStorage.removeItem("edumind:last-learning-operation"); } catch { /* Optional. */ }
    return;
  }
  if (payload.status === "awaiting_human") {
    reviewState.value = "awaiting_human";
    generationPhase.value = "awaiting_human";
    temporaryText.value = "";
    stopReviewWatch?.();
    stopReviewWatch = watchHybridOperation({ id: recoveringOperationId,
      onUpdate: async (state) => {
        if (generation !== learningGeneration || operationId.value !== state.id) return;
        if ((state.status === "completed" || state.status === "published") && state.learning_unit_id) {
          await loadPublishedUnit(state.learning_unit_id, generation, undefined, state.publication_version ?? undefined);
        } else if (["failed", "canceled", "rejected"].includes(state.status)) {
          generationPhase.value = "";
          reviewState.value = "rejected";
          requestError.value = "本次课程未发布，已有课程仍可学习。";
        }
      }, onError: () => { if (generation === learningGeneration) requestError.value = "状态查询已暂停，可手动刷新；不会重复生成。"; },
    });
    return;
  }
  if (payload.status === "failed" || payload.status === "canceled" || payload.status === "rejected") {
    generationPhase.value = "";
    temporaryText.value = "";
    if (payload.error?.code === "GOAL_CLARIFICATION_REQUIRED") {
      const failure = errorFromPayload(payload.error);
      goalCandidates.value = failure.candidates;
      clarificationReason.value = failure.reason ?? "unknown";
      throw failure;
    }
    if (payload.status === "rejected") {
      reviewState.value = "rejected";
      requestError.value = "本次课程未发布，已有课程仍可学习。";
      return;
    }
    throw new Error("原请求已失败或取消。恢复不会再次生成；需要新内容请明确选择“重新生成”。");
  }
  throw new Error("原请求尚未发布，请等待后重试恢复；不会重复生成。");
}

async function loadPublishedUnit(
  unitId = learningUnitId.value,
  expectedGeneration = learningGeneration,
  published?: { startedSelectionId: string; sceneKey: string; sceneVersion: number; publicationVersion?: number },
  exactPublicationVersion?: number,
): Promise<void> {
  if (!unitId) throw new Error("正式学习资源缺少单元标识，请重新开始。");
  const exactVersion = exactPublicationVersion ?? published?.publicationVersion;
  const response = await fetch(`/api/learning-units/${encodeURIComponent(unitId)}${exactVersion ? `?publication_version=${exactVersion}` : ""}`, {
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
  const current = loaded.find((scene) => scene.isCurrent && ["intro", "explanation"].includes(scene.sceneKey))
    ?? loaded.find((scene) => scene.isCurrent) ?? loaded[0];
  const publishedScene = published && priorSelection === published.startedSelectionId
    ? loaded.find((scene) => scene.version === published.sceneVersion && scene.sceneKey === published.sceneKey)
    : undefined;
  const selected = publishedScene ?? loaded.find((scene) => scene.id === priorSelection) ?? current;
  learningUnitId.value = unitId;
  generationPhase.value = "";
  teachingContext.value = payload.teaching_context ?? null;
  bindingStatus.value = payload.binding_status ?? null;
  publishedTeachingContext.value = payload.teaching_context ?? null;
  publicationVersion.value = payload.publication_version;
  approvalSource.value = payload.approval_source ?? "";
  scenes.value = loaded;
  selectedSceneId.value = selected.id;
  try { sessionStorage.setItem(selectionStorageKey(unitId), selected.id); } catch { /* Optional. */ }
  animationNodeId.value = typeof payload.knowledge_node_id === "string" ? payload.knowledge_node_id : "";
  pathTargetNodeId.value = typeof payload.path_target_node_id === "string" ? payload.path_target_node_id : "";
  reviewState.value = "published";
  try {
    sessionStorage.setItem("edumind:last-learning-unit", unitId);
    if (payload.publication_version) sessionStorage.setItem(`edumind:publication:${unitId}`, String(payload.publication_version));
    else sessionStorage.removeItem(`edumind:publication:${unitId}`);
  } catch { /* Storage is optional; server state remains authoritative. */ }
}

async function handleScenePublished(startedSelectionId: string, sceneKey: string, sceneVersion: number, publishedVersion?: number): Promise<void> {
  const generation = learningGeneration;
  const unitId = learningUnitId.value;
  await loadPublishedUnit(unitId, generation, { startedSelectionId, sceneKey, sceneVersion, publicationVersion: publishedVersion });
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
    const savedVersion = Number(sessionStorage.getItem(`edumind:publication:${unitId}`));
    await loadPublishedUnit(unitId, token, undefined, Number.isSafeInteger(savedVersion) && savedVersion > 0 ? savedVersion : undefined);
  } catch {
    if (token === learningGeneration) restoreUnitError.value = "上次学习资源暂时无法读取。可以重试读取或开始新目标。";
  } finally {
    if (token === learningGeneration) restoringUnit.value = false;
  }
}
onMounted(async () => {
  if (props.startLearningRequest) return;
  await restoreRecentUnit();
  let saved = "";
  try { saved = sessionStorage.getItem("edumind:last-learning-operation") ?? ""; } catch { /* Optional. */ }
  if (!/^[A-Za-z0-9_-]{4,128}$/.test(saved)) return;
  operationId.value = saved;
  try { await recoverPublishedOperation(learningGeneration); } catch { /* Explicit recovery stays available. */ }
});

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
        <label for="teaching-mode">本节安排</label>
        <select
          id="teaching-mode"
          v-model="teachingMode"
          :disabled="requestState === 'loading'"
        >
          <option value="target">
            直接学习目标
          </option>
          <option value="recommended">
            先按路径建议补前置
          </option>
        </select>
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
    <TeachingNodeSummary
      :context="teachingContext"
      :binding-status="bindingStatus"
    />
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
      <div
        v-if="clarificationReason"
        data-testid="goal-clarification"
      >
        <p>请选择本次主要目标，或编辑原文说明主次后重新提交。</p>
        <ul>
          <li
            v-for="candidate in goalCandidates"
            :key="candidate.id"
          >
            {{ candidate.name }}
          </li>
        </ul>
      </div>
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
      :phase-label="phaseLabel"
      :approval-source="approvalSource"
      :temporary-text="temporaryText"
      :review-state="reviewState"
      :published-resources="publishedResources"
      :reload-published="reviewState === 'awaiting_human' ? () => recoverPublishedOperation(learningGeneration) : learningUnitId ? loadPublishedUnit : undefined"
    />
    <DebatePanel
      v-if="resources.length && learningUnitId && csrfToken"
      :unit-id="learningUnitId"
      :csrf-token="csrfToken"
      :refresh-token="classroomRefreshToken"
      @active="debateActive = $event"
      @changed="classroomRefreshToken += 1"
      @profile-changed="profileRefreshToken += 1"
    />
    <div v-show="!debateActive">
      <aside
        v-if="resources.length && publishedTeachingContext && publishedTeachingContext !== teachingContext"
        data-testid="previous-teaching-scope"
      >
        <p>下方仍为此前已发布课程：{{ publishedTeachingContext.segment_goal }}。本次请求发布前保留该版本。</p>
      </aside>
      <PublishedLearningWorkspace
        v-if="resources.length"
        :key="selectedSceneId"
        :resources="resources"
        :csrf-token="csrfToken"
        :select-resource="selectResource"
        @quiz-submitted="handleQuizSubmitted"
      />
      <NotesDownload
        v-if="resources.length && learningUnitId"
        :unit-id="learningUnitId"
        :current="Boolean(selectedScene?.isCurrent)"
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
        :dynamic-enabled="true"
        :unit-id="learningUnitId"
        :node-id="animationNodeId"
        :scene-version="animationSceneVersion"
        :scene-id="selectedSceneId"
        :scene-key="selectedScene?.sceneKey"
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
    <KnowledgeExplorer
      v-if="csrfToken"
      :csrf-token="csrfToken"
      :can-plan="Boolean(learningUnitId)"
      :current-node-id="animationNodeId"
      :refresh-token="pathRefreshToken"
    />
    <LearningPathPanel
      v-if="pathTargetNodeId"
      :target-node-id="pathTargetNodeId"
      :csrf-token="csrfToken"
      :refresh-token="pathRefreshToken"
    />
    <ProfileCard :refresh-token="profileRefreshToken" />
  </main>
</template>
