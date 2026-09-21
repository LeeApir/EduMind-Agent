<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton } from "naive-ui";

type ResourceType = "explanation" | "code" | "exercise";
interface Resource { type: ResourceType; content: Record<string, unknown>; }
interface Exercise { id: string; question: string; answer: string; explanation: string; }

const props = defineProps<{ resources: Resource[] }>();
const activeTab = ref<ResourceType>("explanation");
const answers = ref<Record<string, string>>({});
const feedback = ref<Record<string, boolean>>({});
const byType = computed(() => new Map(props.resources.map((resource) => [resource.type, resource])));
const explanation = computed(() => stringField(byType.value.get("explanation")?.content, "markdown"));
const code = computed(() => stringField(byType.value.get("code")?.content, "source"));
const exercises = computed<Exercise[]>(() => {
  const items = byType.value.get("exercise")?.content.items;
  return Array.isArray(items) ? items.filter(isExercise) : [];
});

function stringField(content: Record<string, unknown> | undefined, key: string): string {
  return typeof content?.[key] === "string" ? content[key] : "";
}
function isExercise(value: unknown): value is Exercise {
  return Boolean(value) && typeof value === "object" && ["id", "question", "answer", "explanation"].every((key) => typeof (value as Record<string, unknown>)[key] === "string");
}
function checkAnswer(exercise: Exercise): void {
  feedback.value = { ...feedback.value, [exercise.id]: answers.value[exercise.id]?.trim() === exercise.answer.trim() };
}
</script>

<template>
  <section class="published-workspace" aria-label="已审核学习资源">
    <nav aria-label="学习资源切换">
      <NButton v-for="tab in ['explanation', 'code', 'exercise'] as ResourceType[]" :key="tab" :type="activeTab === tab ? 'primary' : 'default'" @click="activeTab = tab">
        {{ ({ explanation: '讲解', code: '代码', exercise: '练习' })[tab] }}
      </NButton>
    </nav>
    <article v-if="activeTab === 'explanation'" data-testid="explanation-tab"><p v-if="explanation">{{ explanation }}</p><p v-else>正式讲解正在加载。</p></article>
    <article v-else-if="activeTab === 'code'" data-testid="code-tab"><pre v-if="code"><code>{{ code }}</code></pre><p v-else>正式代码正在加载。</p></article>
    <section v-else data-testid="exercise-tab">
      <p>以下作答只在当前页面提供即时反馈，不会更新掌握度或学习路径。</p>
      <article v-for="exercise in exercises" :key="exercise.id">
        <label :for="`answer-${exercise.id}`">{{ exercise.question }}</label>
        <input :id="`answer-${exercise.id}`" v-model="answers[exercise.id]" />
        <NButton @click="checkAnswer(exercise)">检查答案</NButton>
        <p v-if="feedback[exercise.id] === true" role="status">回答正确。{{ exercise.explanation }}</p>
        <p v-else-if="feedback[exercise.id] === false" role="alert">还不对。{{ exercise.explanation }}</p>
      </article>
      <p v-if="!exercises.length">正式练习正在加载。</p>
    </section>
  </section>
</template>
