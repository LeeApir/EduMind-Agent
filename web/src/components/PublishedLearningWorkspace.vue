<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { NButton } from "naive-ui";
import { loadLatestQuizResult, submitQuizAttempt, type QuizResourceRef, type QuizSubmissionResult, type SubmitQuizOptions } from "../api/quiz";

type ResourceType = "explanation" | "code" | "exercise";
interface Resource { id: string; version: number; type: ResourceType; content: Record<string, unknown>; }
interface Exercise { id: string; question: string; }

const props = withDefaults(defineProps<{
  resources: Resource[];
  csrfToken?: string;
  submitQuiz?: (options: SubmitQuizOptions) => Promise<QuizSubmissionResult>;
  loadQuizResult?: (options: QuizResourceRef) => Promise<QuizSubmissionResult | null>;
  selectResource?: (type: ResourceType) => Promise<void>;
  selectedResource?: ResourceType;
}>(), {
  csrfToken: "",
  submitQuiz: (options: SubmitQuizOptions) => submitQuizAttempt(options),
  loadQuizResult: (options: QuizResourceRef) => loadLatestQuizResult(options),
  selectResource: undefined,
  selectedResource: undefined,
});
const emit = defineEmits<{
  "quiz-submitted": [result: QuizSubmissionResult];
  "quiz-restored": [result: QuizSubmissionResult];
  "resource-selected": [type: ResourceType];
}>();
const activeTab = ref<ResourceType>("explanation");
watch(() => props.selectedResource, (value) => { if (value) activeTab.value = value; }, { immediate: true });
const answers = ref<Record<string, string>>({});
const result = ref<QuizSubmissionResult | null>(null);
const restoring = ref(false);
const restoreError = ref("");
const submitting = ref(false);
const requestError = ref("");
const selectionError = ref("");
const selecting = ref(false);
let generation = 0;
let pending: { signature: string; key: string; answers: SubmitQuizOptions["answers"] } | null = null;
onBeforeUnmount(() => { generation += 1; });
const byType = computed(() => new Map(props.resources.map((resource) => [resource.type, resource])));
const exerciseResource = computed(() => byType.value.get("exercise"));
const explanation = computed(() => stringField(byType.value.get("explanation")?.content, "markdown"));
const code = computed(() => stringField(byType.value.get("code")?.content, "source"));
const exercises = computed<Exercise[]>(() => {
  const items = exerciseResource.value?.content.items;
  return Array.isArray(items) ? items.filter(isExercise) : [];
});
const feedback = computed(() => new Map(result.value?.question_results.map((item) => [item.question_id, item]) ?? []));
const canSubmit = computed(() => Boolean(props.csrfToken) && exercises.value.some((item) => answers.value[item.id]?.trim())
  && !restoring.value && !restoreError.value && !submitting.value && !result.value);
const statusLabels = { unseen: "未学习", learning: "学习中", weak: "需要巩固", mastered: "已掌握" };

function stringField(content: Record<string, unknown> | undefined, key: string): string {
  return typeof content?.[key] === "string" ? content[key] : "";
}
function isExercise(value: unknown): value is Exercise {
  return Boolean(value) && typeof value === "object" && ["id", "question"].every((key) => typeof (value as Record<string, unknown>)[key] === "string");
}
function resourceRef(): QuizResourceRef | null {
  const resource = exerciseResource.value;
  return resource?.id && resource.version >= 1 ? { resourceId: resource.id, resourceVersion: resource.version } : null;
}
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "练习请求失败，请重试。";
}
async function restoreResult(): Promise<void> {
  const current = resourceRef();
  const token = ++generation;
  result.value = null;
  answers.value = {};
  pending = null;
  requestError.value = "";
  restoreError.value = "";
  submitting.value = false;
  if (!current) { restoring.value = false; return; }
  restoring.value = true;
  try {
    const restored = await props.loadQuizResult(current);
    if (token === generation) {
      result.value = restored;
      if (restored) emit("quiz-restored", restored);
    }
  } catch (error) {
    if (token === generation) restoreError.value = errorMessage(error);
  } finally {
    if (token === generation) restoring.value = false;
  }
}
watch(exerciseResource, () => { void restoreResult(); }, { immediate: true });
async function submitAnswers(): Promise<void> {
  const current = resourceRef();
  if (!current || !canSubmit.value) return;
  const submittedAnswers = exercises.value.map((item) => ({ question_id: item.id, answer: answers.value[item.id] ?? "" }));
  const signature = JSON.stringify({ ...current, answers: submittedAnswers });
  if (!pending || pending.signature !== signature) {
    pending = { signature, key: crypto.randomUUID(), answers: submittedAnswers };
  }
  const attempt = pending;
  const token = generation;
  submitting.value = true;
  requestError.value = "";
  try {
    const receipt = await props.submitQuiz({ ...current, answers: attempt.answers, csrfToken: props.csrfToken, idempotencyKey: attempt.key });
    if (token !== generation) return;
    result.value = receipt;
    pending = null;
    emit("quiz-submitted", receipt);
  } catch (error) {
    if (token === generation) requestError.value = errorMessage(error);
  } finally {
    if (token === generation) submitting.value = false;
  }
}
function beginNewAttempt(): void {
  result.value = null;
  answers.value = {};
  pending = null;
  requestError.value = "";
}

async function switchTab(tab: ResourceType): Promise<void> {
  if (tab === activeTab.value || selecting.value) return;
  selectionError.value = "";
  if (props.selectResource) {
    selecting.value = true;
    try {
      await props.selectResource(tab);
    } catch (error) {
      selectionError.value = errorMessage(error);
      return;
    } finally {
      selecting.value = false;
    }
  }
  activeTab.value = tab;
  emit("resource-selected", tab);
}
</script>

<template>
  <section
    class="published-workspace"
    aria-label="已审核学习资源"
  >
    <nav aria-label="学习资源切换">
      <NButton
        v-for="tab in ['explanation', 'code', 'exercise'] as ResourceType[]"
        :key="tab"
        :type="activeTab === tab ? 'primary' : 'default'"
        :aria-pressed="activeTab === tab"
        :disabled="selecting"
        @click="switchTab(tab)"
      >
        {{ ({ explanation: '讲解', code: '代码', exercise: '练习' })[tab] }}
      </NButton>
    </nav>
    <p
      v-if="selectionError"
      role="alert"
    >
      {{ selectionError }}
    </p>
    <article
      v-if="activeTab === 'explanation'"
      data-testid="explanation-tab"
    >
      <p v-if="explanation">
        {{ explanation }}
      </p><p v-else>
        正式讲解正在加载。
      </p>
    </article>
    <article
      v-else-if="activeTab === 'code'"
      data-testid="code-tab"
    >
      <pre v-if="code"><code>{{ code }}</code></pre><p v-else>
        正式代码正在加载。
      </p>
      <template v-if="code">
        <h3>预期输出</h3><pre>{{ stringField(byType.get('code')?.content, 'expected_output') }}</pre>
        <h3>关键步骤</h3><ul>
          <li
            v-for="(step, index) in byType.get('code')?.content.key_steps as string[]"
            :key="index"
          >
            {{ step }}
          </li>
        </ul>
      </template>
    </article>
    <section
      v-else
      data-testid="exercise-tab"
      :aria-busy="restoring || submitting"
    >
      <p>提交后由服务端评分并记录学习证据；未作答的题目计为跳过。</p>
      <p
        v-if="restoring"
        role="status"
      >
        正在读取最近一次提交结果…
      </p>
      <div
        v-if="restoreError"
        role="alert"
      >
        <p>{{ restoreError }}</p><NButton @click="restoreResult">
          重新读取结果
        </NButton>
      </div>
      <form @submit.prevent="submitAnswers">
        <article
          v-for="exercise in exercises"
          :key="exercise.id"
          class="quiz-question"
        >
          <label
            v-if="!result || answers[exercise.id] !== undefined"
            :for="`answer-${exercise.id}`"
          >{{ exercise.question }}</label>
          <p
            v-else
            class="quiz-question-title"
          >
            {{ exercise.question }}
          </p>
          <input
            v-if="!result || answers[exercise.id] !== undefined"
            :id="`answer-${exercise.id}`"
            v-model="answers[exercise.id]"
            maxlength="500"
            :disabled="restoring || Boolean(restoreError) || submitting || Boolean(result)"
          >
          <p
            v-if="feedback.has(exercise.id)"
            role="status"
            :class="{ 'quiz-needs-work': !feedback.get(exercise.id)?.correct }"
          >
            {{ feedback.get(exercise.id)?.correct ? '回答正确。' : '这题需要再想一想。' }}{{ feedback.get(exercise.id)?.explanation }}
          </p>
        </article>
        <p v-if="!exercises.length">
          正式练习正在加载。
        </p>
        <p
          v-if="requestError"
          role="alert"
        >
          {{ requestError }}
        </p>
        <NButton
          v-if="!result"
          attr-type="submit"
          :loading="submitting"
          :disabled="!canSubmit"
        >
          {{ requestError ? '重试本次提交' : '提交练习' }}
        </NButton>
      </form>
      <section
        v-if="result"
        class="quiz-receipt"
        aria-label="最近一次练习提交回执"
        aria-live="polite"
      >
        <p class="receipt-label">
          最近一次提交 · 服务端已记录
        </p>
        <p>这里展示服务端回执，原始作答不保存在浏览器。点击“再做一次”可填写新答案。</p>
        <p>{{ result.correct_count }} / {{ result.question_count }} 题正确</p>
        <p v-if="result.catalog_assessment">
          {{ result.catalog_assessment.eligible_for_mastery
            ? '首次完整作答已计入学习证据；完成练习与已掌握分别记录。'
            : '本次为练习记录，保留评分与反馈，不重复计入掌握度。' }}
        </p>
        <div
          v-for="change in result.mastery_changes"
          :key="change.knowledge_node_id"
          class="mastery-receipt"
        >
          <span>本次掌握度变化</span>
          <output>{{ Math.round(change.previous_score * 100) }}% → {{ Math.round(change.score * 100) }}%</output>
          <span>{{ statusLabels[change.status] }}</span>
        </div>
        <p v-if="result.path_replan_required">
          下一步推荐需要根据本次学习结果更新。
        </p>
        <NButton @click="beginNewAttempt">
          再做一次
        </NButton>
      </section>
    </section>
  </section>
</template>

<style scoped>
.published-workspace { margin: 32px auto; max-width: 760px; }
.published-workspace :deep(.n-button) { color: #fbfcf9; }
.published-workspace nav :deep(.n-button) { background: transparent !important; color: #244c5a; }
.published-workspace nav :deep(.n-button[aria-pressed="true"]) { background: #35656d !important; color: #fbfcf9; }
.published-workspace :deep(button:focus-visible) { outline: 2px solid #f06e43; outline-offset: 3px; }
.quiz-question { border-bottom: 1px solid #cbd6d4; padding: 18px 0; }
.quiz-question label, .quiz-question-title { display: block; font-weight: 500; margin-bottom: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
.quiz-question input { background: #fbfcf9; border: 1px solid #8aafb0; color: #17253a; font: inherit; max-width: 100%; padding: 10px; width: 100%; }
.quiz-question input:focus-visible { outline: 2px solid #35656d; outline-offset: 3px; }
.quiz-needs-work { color: #a13d36; }
.quiz-receipt { background: #fbfcf9; border-left: 3px solid #35656d; margin-top: 20px; padding: 16px 20px; }
.receipt-label { color: #35656d; font-size: 12px; margin: 0; }
.mastery-receipt { align-items: baseline; display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.mastery-receipt output { font-family: "DM Mono", monospace; font-size: 20px; }
</style>
