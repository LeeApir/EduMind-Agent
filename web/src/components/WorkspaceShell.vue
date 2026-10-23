<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
const props = defineProps<{ page: string; dynamic?: boolean }>();
const emit = defineEmits<{ navigate: [page: string] }>();
const open = ref(false);
const menuButton = ref<HTMLButtonElement>();
const navigation = ref<HTMLElement>();
const content = ref<HTMLElement>();
function close(): void { open.value = false; void nextTick(() => menuButton.value?.focus()); }
function trap(event: KeyboardEvent): void {
  if (!open.value) return;
  if (event.key === 'Escape') { event.preventDefault(); close(); }
  if (event.key !== 'Tab') return;
  const targets = navigation.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
  if (!targets?.length) return;
  if (event.shiftKey && document.activeElement === targets[0]) { event.preventDefault(); targets[targets.length - 1]?.focus(); }
  else if (!event.shiftKey && document.activeElement === targets[targets.length - 1]) { event.preventDefault(); targets[0]?.focus(); }
}
async function toggle(): Promise<void> { open.value = !open.value; if (open.value) { await nextTick(); navigation.value?.querySelector('button')?.focus(); } }
watch(() => props.page, async () => { open.value = false; await nextTick(); const heading = content.value?.querySelector<HTMLElement>('section:not([style*="display: none"]) h1, h1'); if (heading) { heading.tabIndex = -1; heading.focus(); } else content.value?.focus(); });
const links = [{ id: 'learning', label: '学习' }, { id: 'catalog', label: '签核课程目录' }, { id: 'legacy', label: '原学习入口' }, { id: 'connections', label: '模型设置' }, { id: 'preferences', label: '档位与数据去向' }];
</script>
<template>
  <div class="workspace-shell">
    <a
      class="skip-link"
      href="#workspace-main"
    >跳到主要内容</a>
    <button
      ref="menuButton"
      class="mobile-menu secondary"
      type="button"
      aria-controls="workspace-navigation"
      :aria-expanded="open"
      @click="toggle"
    >
      {{ open ? '关闭导航' : '打开导航' }}
    </button>
    <aside
      id="workspace-navigation"
      ref="navigation"
      class="workspace-sidebar"
      :class="{ 'is-open': open }"

      @keydown="trap"
    >
      <div class="workspace-brand">
        <span aria-hidden="true">启</span><div>启智学伴<small>EDUMIND · 学习空间</small></div>
      </div>
      <p class="workspace-caption">
        我的学习空间
      </p>
      <nav aria-label="主导航">
        <template
          v-for="link in links"
          :key="link.id"
        >
          <button
            v-if="link.id !== 'legacy' || dynamic"
            type="button"
            :aria-current="page === link.id ? 'page' : undefined"
            @click="emit('navigate', link.id)"
          >
            {{ link.label }}
          </button>
        </template>
      </nav>
      <p class="workspace-sidebar-note">
        围绕一个目标，循序理解。<br>课程类型与内容状态分别标注。
      </p>
    </aside>
    <div class="workspace-body">
      <header class="workspace-topline">
        学习空间 <span>数据结构 · Web</span>
      </header>
      <div
        id="workspace-main"
        ref="content"
        tabindex="-1"
        class="workspace-content"
      >
        <slot />
      </div>
    </div>
  </div>
</template>
