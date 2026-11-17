<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { readScene, type SceneProjection } from '../api/freeCourses';
import WorkspaceState from './WorkspaceState.vue';
const props = defineProps<{courseId:string;version:number;sceneId:string}>();
const scene = ref<SceneProjection>(); const error = ref(''); let controller: AbortController | undefined; let epoch=0;
async function load(): Promise<void> { const token=++epoch; controller?.abort(); controller=new AbortController(); scene.value=undefined; error.value=''; try { const value=await readScene(props.courseId,props.version,props.sceneId,controller.signal); if(token===epoch) scene.value=value; } catch(failure) { if(token===epoch) error.value=failure instanceof Error ? failure.message:'场景未能读取。'; } }
watch(()=>[props.courseId,props.version,props.sceneId],load,{immediate:true}); onBeforeUnmount(()=>{epoch+=1;controller?.abort();});
</script>
<template>
  <section class="page-view">
    <h1>课程学习</h1><span class="badge warning">AI 生成草稿 · v{{ version }} · 内容可能有误</span><WorkspaceState
      v-if="error"
      kind="error"
      :detail="error"
      retry
      @retry="load"
    /><WorkspaceState
      v-else-if="!scene"
      kind="loading"
      detail="正在读取已就绪场景。"
    /><template
      v-for="block in scene?.blocks"
      :key="block.anchor_id"
    >
      <p
        v-if="block.kind==='text'"
        class="scene-prose"
      >
        {{ block.markdown }}
      </p><pre v-else-if="block.kind==='code'"><code>{{ block.source }}</code></pre><p v-else-if="block.kind==='visualization'">
        {{ block.text_alternative }}
      </p><p v-else-if="block.kind==='exercise'">
        {{ block.question }}
      </p><p v-else>
        题组已停用。
      </p>
    </template>
  </section>
</template>
