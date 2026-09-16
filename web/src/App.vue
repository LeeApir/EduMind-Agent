<script setup lang="ts">
import { ref } from "vue";
import { NButton, NInput, NTag } from "naive-ui";

const goal = ref("");
const submittedGoal = ref("");

function startLearning(): void {
  submittedGoal.value = goal.value.trim();
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
          <NButton type="primary" attr-type="submit" :disabled="!goal.trim()">开始学习 →</NButton>
        </div>
      </form>
    </section>

    <section class="cue-strip" aria-label="可直接使用的学习方式">
      <NTag round :bordered="false">先看代码</NTag>
      <NTag round :bordered="false">换个例子</NTag>
      <NTag round :bordered="false">补 C 指针</NTag>
    </section>

    <aside v-if="submittedGoal" class="next-state" aria-live="polite">
      已收到：{{ submittedGoal }}。下一步将建立临时画像并流式显示第一段讲解。
    </aside>
  </main>
</template>
