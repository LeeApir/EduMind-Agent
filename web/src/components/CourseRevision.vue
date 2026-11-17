<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref,toRef,watch } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { revisionImpact } from '../api/courseChanges';
import { cancelOperation,readStored,submitOperation,terminalOperation,writeStored,type Impact } from '../api/freeCourses';
import { useCourseFeed } from '../composables/useCourseFeed';
const props=withDefaults(defineProps<{courseId:string;courseVersion:number;sceneId:string;sceneVersionId:string;headVersion:number|null;mode:'catalog_only'|'dynamic';generationActive:boolean;sceneTitles:Record<string,string>;blockedContent?:boolean}>(),{blockedContent:false});
const emit=defineEmits<{operation:[id:string];adopt:[];outline:[]}>();
const owner=ref('');const editing=ref(false);const instruction=ref('');const confirmed=ref(false);const impact=ref<Impact>();const busy=ref(false);const error=ref('');const receipt=ref('');const lastState=ref('');let alive=true;const controller=new AbortController();
interface Pending {key:string;body:{kind:'revise_scene';expected_head_version:number;scene_id:string;instruction:string;impact_digest:string};operation?:string}
const pending=ref<Pending>();
const observing=computed(()=>Boolean(receipt.value));const {operation,error:feedError,reload}=useCourseFeed(toRef(props,'courseId'),receipt,observing);
const active=computed(()=>Boolean(receipt.value)&&(!operation.value||!terminalOperation(operation.value.state)));
const unknown=computed(()=>Boolean(operation.value?.budget?.usage_unknown||operation.value?.reason_code?.includes('UNKNOWN')));
const stale=computed(()=>props.headVersion!==props.courseVersion);
const key=()=>`edumind:free:revision:${owner.value}:${props.courseId}:${props.courseVersion}:${props.sceneVersionId}`;
function persist():void{if(owner.value)writeStored(key(),{editing:editing.value,instruction:instruction.value,pending:pending.value,receipt:receipt.value});}
watch([editing,instruction],persist);
watch(()=>operation.value?.state,state=>{if(state)lastState.value=state;});
async function inspect():Promise<void>{editing.value=true;confirmed.value=false;error.value='';busy.value=true;try{const value=await revisionImpact(props.courseId,props.courseVersion,props.sceneId,controller.signal);if(alive)impact.value=value;}catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'影响范围读取失败。';}finally{if(alive)busy.value=false;}}
async function submit():Promise<void>{if(!owner.value||!impact.value||!confirmed.value||!instruction.value.trim()||busy.value||stale.value||props.mode!=='dynamic'||props.generationActive||active.value||unknown.value||impact.value.requires_outline_adjustment)return;pending.value={key:crypto.randomUUID(),body:{kind:'revise_scene',expected_head_version:props.courseVersion,scene_id:props.sceneId,instruction:instruction.value.trim(),impact_digest:impact.value.impact_digest}};persist();await retry();}
async function retry():Promise<void>{if(!pending.value||busy.value||props.mode!=='dynamic')return;busy.value=true;error.value='';const request=pending.value;try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value)throw new Error('学习身份已变化，请重新打开修订。');const id=request.operation??(await submitOperation(props.courseId,request.body,session.csrf,request.key)).operation_id;if(!alive)return;request.operation=id;receipt.value=id;pending.value=undefined;confirmed.value=false;persist();writeStored(`edumind:free:operation:${owner.value}:${props.courseId}`,id);emit('operation',id);}catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'修订结果未确认，原请求保留。';}finally{if(alive)busy.value=false;}}
async function cancel():Promise<void>{if(!receipt.value||busy.value)return;busy.value=true;error.value='';try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value)throw new Error('学习身份已变化。');const storage=`edumind:free:revision-cancel:${owner.value}:${receipt.value}`;const id=readStored<string>(storage)??crypto.randomUUID();writeStored(storage,id);await cancelOperation(props.courseId,receipt.value,session.csrf,id);if(alive)await reload();}catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'停止请求未确认。';}finally{if(alive)busy.value=false;}}
function newRevision():void{if(active.value||unknown.value||pending.value)return;receipt.value='';impact.value=undefined;confirmed.value=false;lastState.value='';persist();void inspect();}
onMounted(async()=>{try{const session=await ensureCatalogSession();if(!alive)return;owner.value=session.owner;const saved=readStored<{editing:boolean;instruction:string;pending?:Pending;receipt:string}>(key());if(saved){editing.value=saved.editing===true;instruction.value=typeof saved.instruction==='string'?saved.instruction:'';pending.value=saved.pending;receipt.value=typeof saved.receipt==='string'?saved.receipt:'';}}catch{if(alive)error.value='当前学习身份未能读取。';}});
onBeforeUnmount(()=>{alive=false;controller.abort();persist();});
const labels:Record<string,string>={queued:'修订排队中，保留旧版本',running:'正在准备完整替换集合，下游场景就绪前不切换',cancel_requested:'正在停止修订，等待可靠收尾',succeeded:'完整修订集合已就绪',partially_succeeded:'修订未完整提交，保留原版本',failed:'修订失败，保留原版本',cancelled:'修订已停止，保留原版本',timed_out:'修订超时，保留原版本'};
</script>
<template>
  <section
    class="course-revision"
    aria-label="局部修订"
  >
    <h3>调整当前场景</h3><p>重新解释、调整深浅或换例子会创建修订操作；先核对影响范围，再确认。不会把旧作答交给新题答案评分。</p><button
      v-if="!editing"
      class="secondary"
      type="button"
      @click="inspect"
    >
      准备局部修订
    </button>
    <form
      v-if="editing"
      @submit.prevent="submit"
    >
      <p v-if="blockedContent">
        相关旧内容当前不可用，保持暂停；完整修订就绪后才能确认读取新版本。
      </p><p v-if="generationActive && !active">
        仍有生成活动，请先在大纲页主动停止并等待收尾。
      </p><button
        v-if="generationActive && !active || impact?.requires_outline_adjustment"
        class="secondary"
        type="button"
        @click="$emit('outline')"
      >
        查看大纲与当前操作
      </button><p v-if="stale">
        当前是历史版本，不能据此创建新修订；请明确读取最新版本后重新核对影响。
      </p><p v-if="mode==='catalog_only'">
        当前仅开放签核课程，不能新发修订操作；已有操作可只读恢复或停止。
      </p>
      <label for="scene-revision-instruction">希望怎样修改这个场景？</label><textarea
        id="scene-revision-instruction"
        v-model="instruction"
        rows="3"
        maxlength="4000"
        :readonly="busy || Boolean(pending) || active"
      />
      <div
        v-if="impact"
        class="revision-impact"
      >
        <h4>本次影响范围</h4><ul>
          <li
            v-for="id in impact.affected_scene_ids"
            :key="id"
          >
            {{ sceneTitles[id]??id }}
          </li>
        </ul><p>最多 {{ impact.max_attempts }} 次任务尝试、{{ impact.max_seconds }} 秒，仍受课程累计预算约束。</p><p>无关内容尽可能保留。受影响的题组评分与学习证据按规则撤销；历史作答原文和旧版本保留。整套替换就绪前不切换正文。</p><p v-if="impact.requires_outline_adjustment">
          此调整需要重新规划大纲，请在大纲页核对全课影响。
        </p><label><input
          v-model="confirmed"
          type="checkbox"
          :disabled="active || busy || Boolean(pending)"
        >确认受影响场景、证据撤销与新操作预算</label>
      </div><button
        v-else
        class="secondary"
        type="button"
        :disabled="busy"
        @click="inspect"
      >
        读取影响范围
      </button>
      <div class="action-row">
        <button
          class="primary"
          type="submit"
          :disabled="!owner || busy || !impact || !confirmed || !instruction.trim() || active || generationActive || stale || mode!=='dynamic' || unknown || impact.requires_outline_adjustment || Boolean(pending)"
        >
          确认开始局部修订
        </button><button
          v-if="pending"
          class="secondary"
          type="button"
          :disabled="busy || mode!=='dynamic'"
          @click="retry"
        >
          确认原修订请求
        </button><button
          v-if="receipt"
          class="secondary"
          type="button"
          :disabled="busy"
          @click="reload"
        >
          读取修订进度
        </button><button
          v-if="active"
          class="secondary"
          type="button"
          :disabled="busy || operation?.state==='cancel_requested'"
          @click="cancel"
        >
          停止这次修订
        </button><button
          v-if="receipt && !active && !unknown"
          class="secondary"
          type="button"
          :disabled="busy"
          @click="newRevision"
        >
          重新核对修订影响
        </button>
      </div>
    </form>
    <p
      v-if="error || feedError"
      role="alert"
    >
      {{ error || feedError }}
    </p><p
      v-if="unknown"
      role="alert"
    >
      发送结果或用量待可靠确认，不自动重试，也不开始新的修订。
    </p><p
      v-if="lastState"
      role="status"
    >
      {{ labels[lastState]??'原操作状态待核对' }}
    </p><button
      v-if="operation?.state==='succeeded' && headVersion!==courseVersion"
      class="primary"
      type="button"
      @click="$emit('adopt')"
    >
      确认读取当前最新版本 v{{ headVersion }}
    </button>
  </section>
</template>
