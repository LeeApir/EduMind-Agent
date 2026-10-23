<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref,watch } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { readStored,writeStored,type SceneBlock } from '../api/freeCourses';
import { readFeedback,sendFeedback,type Feedback,type FeedbackRequest } from '../api/courseChanges';
const props=defineProps<{courseId:string;courseVersion:number;sceneId:string;sceneVersionId:string;blocks:SceneBlock[]}>();
const emit=defineEmits<{confirmed:[]}>();
const owner=ref('');const description=ref('');const selected=ref('');const loading=ref(true);const busy=ref(false);const error=ref('');const feedback=ref<Feedback>();const receipt=ref('');let alive=true;const controller=new AbortController();
interface Pending {key:string;body:FeedbackRequest;id?:string}
const pending=ref<Pending>();
const options=computed(()=>props.blocks.flatMap((block,index)=>{
  if(block.anchor_id.length>128)return [];
  const base={anchor:block.anchor_id,eid:block.kind==='exercise'||block.kind==='exercise_unavailable'?block.exercise_id:null,evid:block.kind==='exercise'||block.kind==='exercise_unavailable'?block.exercise_version_id:null};
  if(block.kind==='exercise')return block.items.map((q,i)=>({...base,key:JSON.stringify([block.anchor_id,q.question_id]),label:`题目 ${i+1}：${q.question}`,prefix:`题目[${q.question_id}]：`}));
  return [{...base,key:JSON.stringify([block.anchor_id]),label:`${index+1}. ${({text:'讲解',code:'代码',visualization:'状态演示',exercise_unavailable:'已停用题组'} as Record<string,string>)[block.kind]??'内容'} · ${block.anchor_id}`,prefix:''}];
}));
const location=computed(()=>options.value.find(o=>o.key===selected.value));
const storageKey=()=>`edumind:free:feedback:${owner.value}:${props.courseId}:${props.courseVersion}:${props.sceneVersionId}`;
function persist():void{if(owner.value)writeStored(storageKey(),{description:description.value,selected:selected.value,pending:pending.value,receipt:receipt.value});}
watch([description,selected],persist);
async function refresh():Promise<void>{
  if(!receipt.value||busy.value)return;busy.value=true;error.value='';
  try{const result=await readFeedback(props.courseId,receipt.value,controller.signal);if(!alive)return;if(result.binding.course_version!==props.courseVersion||result.binding.scene_id!==props.sceneId||result.binding.scene_version_id!==props.sceneVersionId)throw new Error('反馈记录与准确场景不匹配，请重新读取原版本。');feedback.value=result;if(result.status==='confirmed')emit('confirmed');}
  catch(failure){if(alive){feedback.value=undefined;error.value=failure instanceof Error?failure.message:'反馈状态未能读取。';}}
  finally{if(alive)busy.value=false;}
}
async function submit():Promise<void>{
  if(busy.value||loading.value||!location.value||!description.value.trim()||receipt.value||pending.value)return;
  const text=location.value.prefix+description.value.trim();if(text.length>2000){error.value='含题目位置的描述超过2000字符，请缩短后提交；原文字保留。';return;}
  pending.value={key:crypto.randomUUID(),body:{course_version:props.courseVersion,scene_id:props.sceneId,scene_version_id:props.sceneVersionId,anchor_id:location.value.anchor,exercise_id:location.value.eid,exercise_version_id:location.value.evid,description:text}};persist();await retry();
}
async function retry():Promise<void>{
  if(!pending.value||busy.value)return;busy.value=true;error.value='';const request=pending.value;
  try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value)throw new Error('学习身份已变化，请重新打开反馈。');const id=request.id??await sendFeedback(props.courseId,request.body,session.csrf,request.key);if(!alive)return;request.id=id;receipt.value=id;pending.value=undefined;persist();
    const key=`edumind:free:feedback-records:${owner.value}:${props.courseId}`;const records=readStored<string[]>(key)??[];if(!records.includes(id)){records.push(id);writeStored(key,records);}
  }catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'反馈结果未确认，原请求保留。';}
  finally{if(alive)busy.value=false;}if(receipt.value)await refresh();
}
function reset():void{if(pending.value||busy.value)return;receipt.value='';feedback.value=undefined;description.value='';error.value='';persist();}
onMounted(async()=>{try{const session=await ensureCatalogSession();if(!alive)return;owner.value=session.owner;const saved=readStored<{description:string;selected:string;pending?:Pending;receipt:string}>(storageKey());if(saved){description.value=typeof saved.description==='string'?saved.description:'';selected.value=saved.selected;pending.value=saved.pending;receipt.value=typeof saved.receipt==='string'?saved.receipt:'';}if(!selected.value)selected.value=options.value[0]?.key??'';if(receipt.value)await refresh();}catch{if(alive)error.value='当前学习身份未能读取。';}finally{if(alive)loading.value=false;}});
onBeforeUnmount(()=>{alive=false;controller.abort();persist();});
const labels={pending:'已提交 · 待核对',confirmed:'已确认 · 按规则处置',not_confirmed:'本次未确认',corrected:'处置已更正'};
</script>
<template>
  <section
    class="course-feedback"
    aria-label="内容问题反馈"
  >
    <h3>反馈内容问题</h3><p>反馈对应课程 v{{ courseVersion }}、当前准确场景。提交不代表错误已确认，也不会自动触发生成。</p>
    <form @submit.prevent="submit">
      <label for="feedback-location">反馈位置</label><select
        id="feedback-location"
        v-model="selected"
        :disabled="busy || Boolean(pending) || Boolean(receipt)"
      >
        <option
          v-for="option in options"
          :key="option.key"
          :value="option.key"
        >
          {{ option.label }}
        </option>
      </select><p v-if="!options.length">
        当前没有可绑定的公开段落或题目，可读取已有反馈；不会编造反馈位置。
      </p><label for="feedback-description">问题描述</label><textarea
        id="feedback-description"
        v-model="description"
        rows="3"
        maxlength="2000"
        :readonly="busy || Boolean(pending) || Boolean(receipt)"
      /><div class="action-row">
        <button
          class="secondary"
          type="submit"
          :disabled="loading || busy || !location || !description.trim() || Boolean(pending) || Boolean(receipt)"
        >
          提交问题反馈
        </button><button
          v-if="pending"
          class="secondary"
          type="button"
          :disabled="busy"
          @click="retry"
        >
          确认原反馈请求
        </button><button
          v-if="receipt"
          class="secondary"
          type="button"
          :disabled="busy"
          @click="refresh"
        >
          读取反馈处置
        </button><button
          v-if="receipt && !pending"
          class="secondary"
          type="button"
          :disabled="busy"
          @click="reset"
        >
          反馈另一个问题
        </button>
      </div>
    </form>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p><p
      v-if="receipt && !feedback"
      role="status"
    >
      反馈已提交，处置状态尚未读到。请读取原记录，不会重新提交。
    </p>
    <section
      v-if="feedback"
      class="surface"
    >
      <h4>{{ labels[feedback.status] }}</h4><p>{{ feedback.description }}</p><small>位置 {{ feedback.anchor_id }} · 课程 v{{ feedback.binding.course_version }}</small><p v-if="feedback.status==='pending'">
        等待可信核对，学生或模型意见不作为正式确认。
      </p><p v-else-if="feedback.status==='confirmed'">
        相关内容与学习证据按服务端规则处置；正在重新读取内容状态，不由前端自行判错。
      </p><p v-else-if="feedback.status==='not_confirmed'">
        本次未确认不等于证明内容一定正确。
      </p><p v-else>
        原始反馈保留，旧评分不会因处置更正而自动恢复。
      </p>
    </section>
  </section>
</template>
