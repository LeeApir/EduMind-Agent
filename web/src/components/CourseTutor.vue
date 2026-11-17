<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref,toRef,watch } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { cancelOperation,readStored,terminalOperation,writeStored } from '../api/freeCourses';
import { createTutor,readTutor,type TutorReceipt,type TutorRequest,type TutorTurn } from '../api/courseTutor';
import { useCourseFeed } from '../composables/useCourseFeed';
const props=withDefaults(defineProps<{courseId:string;courseVersion:number;sceneId:string;sceneVersionId:string;headVersion:number|null;mode:'catalog_only'|'dynamic';generationActive:boolean;modelValue:string;active?:boolean}>(),{active:true});
const emit=defineEmits<{'update:modelValue':[value:string]}>();
const question=computed({get:()=>props.modelValue,set:value=>emit('update:modelValue',value)});
const owner=ref('');const loading=ref(true);const busy=ref(false);const error=ref('');const acknowledged=ref(false);const receipt=ref<TutorReceipt>();const turn=ref<TutorTurn>();
interface Pending {key:string;body:TutorRequest;receipt?:TutorReceipt}
const pending=ref<Pending>();const history=ref<TutorReceipt[]>([]);
const opId=computed(()=>receipt.value?.operation_id??'');const observing=computed(()=>props.active&&Boolean(receipt.value));
const {operation,error:feedError,reload,inaccessible}=useCourseFeed(toRef(props,'courseId'),opId,observing);
const opActive=computed(()=>Boolean(receipt.value)&&(!operation.value||!terminalOperation(operation.value.state)));
const unresolved=computed(()=>Boolean(operation.value?.budget?.usage_unknown||operation.value?.reason_code?.includes('UNKNOWN')));
const stale=computed(()=>props.headVersion!==props.courseVersion);
const canSend=computed(()=>!loading.value&&!busy.value&&!pending.value&&!receipt.value&&props.active&&props.mode==='dynamic'&&!props.generationActive&&!stale.value&&acknowledged.value&&question.value.trim().length>0&&question.value.trim().length<=2000);
let alive=true;let epoch=0;let controller:AbortController|undefined;
const storageKey=()=>`edumind:free:tutor:${owner.value}:${props.courseId}:${props.courseVersion}:${props.sceneVersionId}`;
function persist():void{if(owner.value)writeStored(storageKey(),{pending:pending.value,receipt:receipt.value,history:history.value});}
const labels:Record<string,string>={queued:'等待导师回复',running:'导师正在组织解释',ready:'AI 补充解释 · 未签核',failed:'本次提问未完成',cancelled:'本次提问已停止',timed_out:'本次提问已超时',invalidated:'回复来源已失效'};
async function refreshTurn():Promise<void>{
  if(!receipt.value||!props.active)return;const current=receipt.value;const token=++epoch;controller?.abort();controller=new AbortController();error.value='';
  try{const value=await readTutor(props.courseId,current,controller.signal);if(!alive||token!==epoch)return;
    if(value.binding.course_version!==props.courseVersion||value.binding.scene_id!==props.sceneId||value.binding.scene_version_id!==props.sceneVersionId)throw new Error('回复对应的场景版本已变化，请从准确旧版本读取。');
    turn.value=value;question.value=value.message;
  }catch(failure){if(alive&&token===epoch){turn.value=undefined;error.value=failure instanceof Error?failure.message:'原提问状态未能读取，问题保留。';}}
}
watch([()=>operation.value?.last_event_id,()=>operation.value?.state],()=>{void refreshTurn();});
watch(inaccessible,value=>{if(value){turn.value=undefined;error.value='学习身份已变化或无法访问，已隐藏原回复。';}});
async function initialize():Promise<void>{
  try{const session=await ensureCatalogSession();if(!alive)return;owner.value=session.owner;
    const saved=readStored<{pending?:Pending;receipt?:TutorReceipt;history?:TutorReceipt[]}>(storageKey());
    if(saved){
      if(saved.pending?.body.course_version===props.courseVersion&&saved.pending.body.scene_version_id===props.sceneVersionId&&typeof saved.pending.key==='string'){pending.value=saved.pending;question.value=saved.pending.body.message;}
      const last=saved.receipt??pending.value?.receipt;if(last&&typeof last.turn_id==='string'&&typeof last.operation_id==='string')receipt.value=last;
      history.value=Array.isArray(saved.history)?saved.history.filter(r=>typeof r.turn_id==='string'&&typeof r.operation_id==='string'):[];
      if(receipt.value)await refreshTurn();
    }
  }catch{if(alive)error.value='当前学习身份未能读取，请重新打开导师。';}
  finally{if(alive)loading.value=false;}
}
async function send():Promise<void>{
  if(!canSend.value)return;
  pending.value={key:crypto.randomUUID(),body:{course_version:props.courseVersion,scene_id:props.sceneId,scene_version_id:props.sceneVersionId,message:question.value.trim(),acknowledge_assisted_practice:true}};persist();await confirmRequest();
}
async function confirmRequest():Promise<void>{
  if(!pending.value||busy.value||props.mode!=='dynamic'||!props.active)return;busy.value=true;error.value='';const request=pending.value;
  try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value){turn.value=undefined;throw new Error('学习身份已变化，请重新打开导师。');}
    const result=request.receipt??await createTutor(props.courseId,request.body,session.csrf,request.key);if(!alive)return;
    request.receipt=result;receipt.value=result;if(!history.value.some(r=>r.turn_id===result.turn_id))history.value.push(result);pending.value=undefined;persist();acknowledged.value=false;await refreshTurn();
  }catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'提问结果未确认；保留原请求，不自动重试。';}
  finally{if(alive)busy.value=false;}
}
async function cancel():Promise<void>{
  if(!receipt.value||busy.value||!props.active)return;busy.value=true;error.value='';
  try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value)throw new Error('学习身份已变化，请重新打开导师。');
    const key=`edumind:free:tutor-cancel:${owner.value}:${receipt.value.operation_id}`;const id=readStored<string>(key)??crypto.randomUUID();writeStored(key,id);
    await cancelOperation(props.courseId,receipt.value.operation_id,session.csrf,id);if(!alive)return;await reload();await refreshTurn();
  }catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'停止请求未确认，请重新读取原提问。';}
  finally{if(alive)busy.value=false;}
}
async function readAgain():Promise<void>{await reload();await refreshTurn();}
function newQuestion():void{if(busy.value||opActive.value||pending.value||unresolved.value)return;receipt.value=undefined;turn.value=undefined;error.value='';acknowledged.value=false;question.value='';persist();}
function chooseRecord(id:string):void{const found=history.value.find(r=>r.turn_id===id);if(!found)return;receipt.value=found;pending.value=undefined;persist();void refreshTurn();}
watch(()=>props.active,value=>{if(!value){epoch+=1;controller?.abort();}});
onMounted(initialize);onBeforeUnmount(()=>{alive=false;epoch+=1;controller?.abort();persist();});
</script>
<template>
  <section
    class="course-tutor"
    aria-label="当前场景导师问答"
  >
    <p>导师只作补充解释，不修改课程，也不授予评分或签核。要修改正文需另走课程修订确认。</p>
    <p v-if="generationActive">
      当前生成仍在进行。请等待完成，或在大纲页主动停止后再提问；不会自动停止生成。
    </p><p v-if="stale">
      这是准确历史版本，只能读取原提问，不向新版本发送。
    </p><p v-if="mode==='catalog_only'">
      当前只开放签核课程，可以读取已有回复或停止原提问，暂不能发送新的草稿导师请求。
    </p>
    <form @submit.prevent="send">
      <label for="tutor-question-draft">记下问题</label><textarea
        id="tutor-question-draft"
        v-model="question"
        rows="3"
        maxlength="2000"
        :readonly="busy || Boolean(pending) || Boolean(receipt)"
      /><p
        v-if="question.length>2000"
        role="alert"
      >
        问题超过2000字符，请编辑后再发送；原文字保留。
      </p><label class="assistance-consent"><input
        v-model="acknowledged"
        type="checkbox"
        :disabled="Boolean(receipt) || Boolean(pending) || busy"
      >本次上下文涉及的练习将按辅助学习记录，包括相关场景中尚未作答的题组。</label><small>每轮最多一次发送、总90秒；仍受课程累计预算限制，不自动重试。</small><div class="action-row">
        <button
          class="primary"
          type="submit"
          :disabled="!canSend"
        >
          发送本次提问
        </button><button
          v-if="pending"
          class="secondary"
          type="button"
          :disabled="busy || mode!=='dynamic' || !active"
          @click="confirmRequest"
        >
          确认原提问请求
        </button><button
          v-if="receipt"
          class="secondary"
          type="button"
          :disabled="busy"
          @click="readAgain"
        >
          重新读取本次提问
        </button><button
          v-if="opActive"
          class="secondary"
          type="button"
          :disabled="busy || operation?.state==='cancel_requested'"
          @click="cancel"
        >
          停止本次提问
        </button><button
          v-else-if="receipt"
          class="secondary"
          type="button"
          :disabled="busy || unresolved"
          @click="newQuestion"
        >
          开始新问题
        </button>
      </div>
    </form>
    <p
      v-if="loading"
      role="status"
    >
      正在读取本机轮次引用，没有发送提问。
    </p><p
      v-if="error || feedError"
      role="alert"
    >
      {{ error || feedError }}
    </p><p
      v-if="unresolved"
      role="alert"
    >
      本次发送结果或用量尚未可靠确认，不能开始新的发送；已有内容保留。
    </p><p
      v-if="operation?.state==='cancel_requested'"
      role="status"
    >
      停止请求已记录，正在等待可靠收尾。
    </p>
    <div
      v-if="history.length"
      class="action-row"
    >
      <label for="tutor-history">本版本的提问记录</label><select
        id="tutor-history"
        :value="receipt?.turn_id??''"
        :disabled="busy || Boolean(opActive)"
        @change="chooseRecord(($event.target as HTMLSelectElement).value)"
      >
        <option value="">
          选择原提问
        </option><option
          v-for="(item,i) in history"
          :key="item.turn_id"
          :value="item.turn_id"
        >
          第{{ i+1 }}次提问
        </option>
      </select>
    </div>
    <section
      v-if="turn"
      class="tutor-answer"
      aria-label="导师本次回复"
    >
      <h4>{{ labels[turn.status] }}</h4><p>对应课程 v{{ turn.binding.course_version }} · 场景版本 {{ turn.binding.scene_version_id }}</p><blockquote>{{ turn.message }}</blockquote><div
        v-if="turn.status==='ready'"
        class="scene-prose"
      >
        {{ turn.markdown }}
      </div><p v-else-if="turn.status==='invalidated'">
        回复所依赖的内容或学情证据已失效，已隐藏旧回复。你的问题保留，不自动重发。
      </p><p v-else-if="['failed','timed_out'].includes(turn.status)">
        已有课程内容保留。可以只读刷新原请求；如需再次提问，请明确开始新问题。
      </p><p v-else-if="turn.status==='cancelled'">
        已停止本次提问，未修改课程。
      </p>
    </section>
  </section>
</template>
