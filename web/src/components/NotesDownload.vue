<script setup lang="ts">
import { ref, watch } from "vue";
import { NButton } from "naive-ui";
import { downloadFile, notesUrl } from "../api/downloads";

const props = defineProps<{ unitId: string; current: boolean }>();
const busy = ref(false);
const error = ref("");
let generation = 0;

watch(() => [props.unitId, props.current], () => { generation += 1; error.value = ""; busy.value = false; });

async function download(): Promise<void> {
  if (busy.value || !props.current) return;
  const token = generation;
  busy.value = true;
  error.value = "";
  try {
    await downloadFile(notesUrl(props.unitId), `learning-notes-${props.unitId}.md`,
      () => token === generation && props.current);
  } catch {
    if (token === generation) error.value = "笔记下载失败，请重试下载。";
  } finally {
    if (token === generation) busy.value = false;
  }
}
</script>

<template>
  <section
    class="export-panel"
    aria-label="学习笔记下载"
  >
    <div>
      <h2>学习笔记</h2>
      <p v-if="current">
        可下载本单元当前已审核版本的讲解与错题摘要。
      </p>
      <p v-else>
        当前查看的是历史场景。切回最新版本后，可下载当前已审核笔记。
      </p>
    </div>
    <NButton
      data-testid="download-notes"
      :disabled="busy || !current"
      @click="download"
    >
      {{ busy ? "正在下载…" : "下载 Markdown" }}
    </NButton>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
  </section>
</template>
