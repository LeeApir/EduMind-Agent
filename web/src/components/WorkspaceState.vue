<script setup lang="ts">
withDefaults(defineProps<{ kind: 'loading' | 'empty' | 'unknown' | 'forbidden' | 'error' | 'invalid'; detail?: string; retry?: boolean }>(), { detail: '', retry: false });
defineEmits<{ retry: [] }>();
const titles = { loading: '正在读取', empty: '还没有记录', unknown: '暂时未知', forbidden: '无法访问此内容', error: '读取失败', invalid: '此版本已不可用' };
</script>
<template>
  <section
    class="workspace-state"
    :role="kind === 'error' || kind === 'forbidden' ? 'alert' : 'status'"
    :aria-busy="kind === 'loading'"
  >
    <h2>{{ titles[kind] }}</h2>
    <p>{{ detail || '已有内容会保留，重新读取不会启动生成。' }}</p>
    <button
      v-if="retry"
      type="button"
      class="secondary"
      @click="$emit('retry')"
    >
      重新读取
    </button>
  </section>
</template>
