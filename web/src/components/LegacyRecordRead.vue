<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { readStored,writeStored } from '../api/freeCourses';
import PublishedLearningWorkspace from './PublishedLearningWorkspace.vue';
interface Scene {id:string;version:number;scene_key:string;resources:{id:string;version:number;type:'explanation'|'code'|'exercise';content:Record<string,unknown>}[]}
const initializing=ref(true);const owner=ref('');const reference=ref<{id:string;version?:number}>();const busy=ref(false);const error=ref('');const scenes=ref<Scene[]>([]);const selected=ref('');const kind=ref('');const actualVersion=ref<number>();let alive=true;const controller=new AbortController();
const scene=computed(()=>scenes.value.find(s=>s.id===selected.value));
onMounted(async()=>{try{const session=await ensureCatalogSession();if(!alive)return;owner.value=session.owner;const saved=readStored<{id:string;version?:number}>(`edumind:history:old:${session.owner}`);let id=saved?.id;let version=saved?.version;try{if(!id)id=sessionStorage.getItem(`edumind:catalog:last:${session.owner}`)??sessionStorage.getItem('edumind:last-learning-unit')??'';if(!version){const v=Number(sessionStorage.getItem(`edumind:publication:${id}`));if(Number.isInteger(v)&&v>0)version=v;}}catch{/* Optional local reference. */}if(typeof id==='string'&&/^[A-Za-z0-9_-]{8,64}$/.test(id))reference.value={id,version};}catch{if(alive)error.value='原入口引用的学习身份未能读取。';}finally{if(alive)initializing.value=false;}});
async function read():Promise<void>{if(!reference.value||busy.value)return;busy.value=true;error.value='';scenes.value=[];try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value)throw new Error('学习身份已变化，请重新打开记录。');const ref=reference.value;const response=await fetch(`/api/learning-units/${encodeURIComponent(ref.id)}${ref.version?`?publication_version=${ref.version}`:''}`,{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error('无法按原权限/版本读取原入口资源；不回退最新，也不重新生成。');const value=await response.json();if(!alive)return;if(value.id!==ref.id||!Array.isArray(value.scenes)||ref.version&&value.publication_version!==ref.version||!value.scenes.every((s:Scene)=>typeof s.id==='string'&&Number.isInteger(s.version)&&Array.isArray(s.resources)&&s.resources.every(r=>typeof r.id==='string'&&Number.isInteger(r.version)&&['explanation','code','exercise'].includes(r.type)&&r.content&&typeof r.content==='object')))throw new Error('原资源响应与记录不一致。');scenes.value=value.scenes;selected.value=value.scenes[0]?.id??'';kind.value=value.origin_type==='curated'?'签核课程 · 原协议':'原入口资源 · 按原权限可读';actualVersion.value=value.publication_version;writeStored(`edumind:history:old:${owner.value}`,ref);}catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'原资源读取失败。';}finally{if(alive)busy.value=false;}}
onBeforeUnmount(()=>{alive=false;controller.abort();});
</script>
<template>
  <section
    class="surface history-section"
    aria-label="原入口记录引用"
  >
    <h2>原入口记录</h2><p>新自由课程账本与旧协议分别保留。旧接口没有完整记录列表；这里仅核对本机已有引用，不将其包装成全部历史。</p><p
      v-if="initializing"
      role="status"
    >
      正在核对本机已有引用。
    </p><p v-if="!initializing && !reference && !error">
      本机没有保留原入口引用。签核课程仍可从课程目录查看。
    </p><template v-if="reference">
      <p>{{ reference.version?`已保留发布版本 ${reference.version}，只读取这一版。`:'本机未保存发布版本；点击后明确读取原协议当前可见资源，不声称恢复历史版本。' }}</p><button
        class="secondary"
        type="button"
        :disabled="busy"
        @click="read"
      >
        读取原入口引用
      </button>
    </template><p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p><template v-if="scenes.length">
      <h3>{{ kind }}</h3><p v-if="actualVersion">
        发布版本 {{ actualVersion }}
      </p><label for="old-record-scene">原场景<select
        id="old-record-scene"
        v-model="selected"
      ><option
        v-for="item in scenes"
        :key="item.id"
        :value="item.id"
      >{{ item.scene_key }} · v{{ item.version }}</option></select></label><PublishedLearningWorkspace
        v-if="scene"
        :key="scene.id"
        :resources="scene.resources"
      />
    </template>
  </section>
</template>
