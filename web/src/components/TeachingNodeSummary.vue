<script setup lang="ts">
import type { TeachingBindingStatus, TeachingContext } from "../api/teachingContext";
defineProps<{ context: TeachingContext | null; bindingStatus: TeachingBindingStatus }>();
const names: Record<string, string> = { "c-pointer": "C 指针", stack: "栈", array: "数组", "linked-list-insertion": "链表插入", "linked-list-concept": "链表概念" };
function label(id: string | null): string { return id ? names[id] ?? id : "无"; }
</script>

<template>
  <section
    v-if="context"
    aria-label="本节教学范围"
    data-testid="teaching-summary"
  >
    <dl>
      <dt>目标</dt><dd data-testid="target-node">
        {{ label(context.target_node_id) }}
      </dd>
      <dt>路径建议</dt><dd data-testid="recommended-node">
        {{ label(context.recommended_node_id) }}
      </dd>
      <dt>本节教学</dt><dd data-testid="teaching-node">
        {{ label(context.teaching_node_id) }}
      </dd>
    </dl>
    <p v-if="context.teaching_node_id !== context.target_node_id">
      本节先补前置知识；原目标尚未交付，也不代表已掌握。
    </p>
    <p v-else-if="context.recommended_node_id !== context.target_node_id">
      本节直接学习目标；路径建议保留供后续选择。
    </p>
  </section>
  <p
    v-else-if="bindingStatus === 'legacy_unverified'"
    data-testid="legacy-teaching"
  >
    历史课程未绑定教学范围，不能据此确认目标已完成。
  </p>
</template>

<style scoped>
section { padding: 1rem; border: 1px solid #d9e2df; border-radius: 8px; }
dl { display: grid; grid-template-columns: auto 1fr; gap: .4rem 1rem; margin: 0; }
dd { margin: 0; overflow-wrap: anywhere; }
p { margin-bottom: 0; }
</style>
