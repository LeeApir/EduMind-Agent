<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NTag } from "naive-ui";

export type ReviewState = "idle" | "reviewing" | "published" | "rejected";

export interface PublishedResource {
  id: string;
  type: "explanation" | "code" | "exercise";
  version: number;
}

const props = defineProps<{
  temporaryText: string;
  reviewState: ReviewState;
  publishedResources?: PublishedResource[];
  reloadPublished?: () => Promise<void>;
}>();

const reloadState = ref<"idle" | "loading" | "error">("idle");
const reloadError = ref("");
const hasTemporaryText = computed(() => Boolean(props.temporaryText.trim()));

async function reload(): Promise<void> {
  if (!props.reloadPublished || reloadState.value === "loading") {
    return;
  }
  reloadState.value = "loading";
  reloadError.value = "";
  try {
    await props.reloadPublished();
    reloadState.value = "idle";
  } catch {
    reloadState.value = "error";
    reloadError.value = "正式资源暂时无法重新加载，请重试。";
  }
}
</script>

<template>
  <section class="learning-progress" aria-live="polite">
    <section v-if="hasTemporaryText" class="temporary-card" data-testid="temporary-explanation">
      <div class="resource-label"><NTag type="warning" size="small">临时流式内容</NTag><span>尚未审核，不会作为正式资源保存</span></div>
      <h2>首段讲解</h2>
      <p>{{ temporaryText }}</p>
    </section>
    <section v-else class="empty-card" data-testid="empty-state">
      <h2>首段讲解会显示在这里</h2>
      <p>输入学习目标后，启智会先流式展示一段临时讲解。</p>
    </section>

    <section v-if="reviewState === 'reviewing'" class="review-state" data-testid="reviewing-state">
      正在审核并准备正式学习资源。临时首段仍可继续阅读。
    </section>
    <section v-else-if="reviewState === 'rejected'" class="review-state rejected" data-testid="review-rejected-state">
      本次正式资源未通过审核，临时首段不会被保存。请调整学习目标后重新开始。
    </section>
    <section v-else-if="reviewState === 'published'" class="published-state" data-testid="published-state">
      <div>
        <NTag type="success" size="small">已审核正式资源</NTag>
        <p>以下资源已通过审核，可安全继续学习。</p>
      </div>
      <NButton :loading="reloadState === 'loading'" @click="reload">重新加载</NButton>
      <p v-if="reloadState === 'error'" class="reload-error" role="alert">{{ reloadError }}</p>
      <ul v-if="publishedResources?.length" aria-label="已发布资源">
        <li v-for="resource in publishedResources" :key="resource.id">{{ resource.type }} · v{{ resource.version }}</li>
      </ul>
      <p v-else>正式资源已准备好；正在读取资源清单。</p>
    </section>
  </section>
</template>
