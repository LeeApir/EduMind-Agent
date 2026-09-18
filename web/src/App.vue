<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NInput, NTag } from "naive-ui";

type StartLearningRequest = (goal: string) => Promise<void>;

const props = defineProps<{
  startLearningRequest?: StartLearningRequest;
}>();

const goal = ref("");
const submittedGoal = ref("");
const requestState = ref<"idle" | "loading" | "error">("idle");
const requestError = ref("");
const canSubmit = computed(() => Boolean(goal.value.trim()) && requestState.value !== "loading");

async function startLearning(): Promise<void> {
  submittedGoal.value = goal.value.trim();
  await submitLearningRequest();
}

async function retryLearning(): Promise<void> {
  await submitLearningRequest();
}

async function submitLearningRequest(): Promise<void> {
  requestError.value = "";
  requestState.value = "loading";

  if (!props.startLearningRequest) {
    return;
  }

  try {
    await props.startLearningRequest(submittedGoal.value);
  } catch (error: unknown) {
    requestError.value = error instanceof Error && error.message
      ? error.message
      : "暂时无法开始学习，请检查网络后重试。";
    requestState.value = "error";
  }
}
</script>

<template>
  <main class="learning-desk">
    <header class="masthead">
      <p class="eyebrow">EDUMIND / 数据结构</p>
      <span class="session-mark">从一句话开始</span>
    </header>

    <section class="lesson-prompt" aria-labelledby="page-title">
      <div class="node-orbit" aria-hidden="true">
        <i></i><i></i><i></i><i></i>
      </div>
      <p class="chapter">学习入口</p>
      <h1 id="page-title">你现在想<br /><em>弄懂什么？</em></h1>
      <p class="lead">说出卡住的知识点、考试目标，或想先看的代码。启智会从第一段讲起。</p>

      <form class="goal-form" @submit.prevent="startLearning">
        <label for="learning-goal">学习目标</label>
        <NInput
          id="learning-goal"
          v-model:value="goal"
          type="textarea"
          placeholder="例如：链表插入的指针总是搞混，想先看 C 代码"
          :autosize="{ minRows: 3, maxRows: 5 }"
        />
        <div class="form-footer">
          <span>不需要先填写画像</span>
          <NButton type="primary" attr-type="submit" :disabled="!canSubmit">开始学习 →</NButton>
        </div>
      </form>
    </section>

    <section class="cue-strip" aria-label="可直接使用的学习方式">
      <NTag round :bordered="false">先看代码</NTag>
      <NTag round :bordered="false">换个例子</NTag>
      <NTag round :bordered="false">补 C 指针</NTag>
    </section>

    <aside v-if="requestState === 'loading'" class="next-state" aria-live="polite" data-testid="loading-state">
      正在为“{{ submittedGoal }}”准备第一段讲解。无需先填写画像。
    </aside>
    <aside v-else-if="requestState === 'error'" class="next-state error-state" aria-live="assertive">
      {{ requestError }}
      <NButton size="small" @click="retryLearning">重试</NButton>
    </aside>
  </main>
</template>
