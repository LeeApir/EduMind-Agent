<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { FreeCourseError, readStored, writeStored, type SceneBlock } from '../api/freeCourses';
import { readAttempt, submitAttempt, type Attempt, type AttemptRequest } from '../api/courseExercises';
const props=withDefaults(defineProps<{courseId:string;courseVersion:number;sceneId:string;sceneVersionId:string;block:Extract<SceneBlock,{kind:'exercise'}>;headVersion:number|null;mode:'catalog_only'|'dynamic';active?:boolean}>(),{active:true});
const answers=ref<Record<string,string>>({});const owner=ref('');const busy=ref(false);const loading=ref(true);const error=ref('');const locked=ref(false);const blocked=ref(false);const attempt=ref<Attempt>();
interface Pending {key:string;body:AttemptRequest;attemptId?:string}
interface RecordRef {id:string;body:Omit<AttemptRequest,'answers'>}
const pending=ref<Pending>();const records=ref<RecordRef[]>([]);const selectedRecord=ref('');let alive=true;const controller=new AbortController();
const bindingKey=()=>`edumind:free:exercise:${owner.value}:${props.courseId}:${props.courseVersion}:${props.sceneVersionId}:${props.block.exercise_version_id}`;
const historyKey=()=>`edumind:free:attempts:${owner.value}:${props.courseId}:${props.block.exercise_id}`;
const stale=computed(()=>props.headVersion!==props.courseVersion);
const canSubmit=computed(()=>!busy.value&&!loading.value&&!locked.value&&!blocked.value&&props.active&&props.mode==='dynamic'&&!stale.value&&props.block.items.some(q=>answers.value[q.question_id]?.trim()));
function persist():void{if(owner.value)writeStored(bindingKey(),{answers:answers.value,pending:pending.value});}
function bound(a:Attempt,body:Omit<AttemptRequest,'answers'>):boolean{return a.binding.course_version===body.course_version&&a.binding.scene_id===body.scene_id&&a.binding.scene_version_id===body.scene_version_id&&a.exercise_id===body.exercise_id&&a.exercise_version_id===body.exercise_version_id;}
async function displayRecord(id:string):Promise<void>{
  const record=records.value.find(r=>r.id===id);if(!record)return;busy.value=true;error.value='';attempt.value=undefined;
  try{const value=await readAttempt(props.courseId,id,controller.signal);if(!alive)return;if(!bound(value,record.body))throw new FreeCourseError(502,'VERSION_MISMATCH');attempt.value=value;selectedRecord.value=id;}
  catch(failure){if(alive)error.value=failure instanceof Error?failure.message:'作答记录读取失败，原输入保留。';}
  finally{if(alive)busy.value=false;}
}
async function initialize():Promise<void>{
  try{
    const session=await ensureCatalogSession();if(!alive)return;owner.value=session.owner;
    const saved=readStored<{answers:Record<string,string>;pending?:Pending}>(bindingKey());
    if(saved&&saved.answers&&typeof saved.answers==='object')for(const q of props.block.items){const value=saved.answers[q.question_id];if(typeof value==='string')answers.value[q.question_id]=value.slice(0,500);}
    if(saved?.pending&&saved.pending.body?.course_version===props.courseVersion&&saved.pending.body.exercise_version_id===props.block.exercise_version_id&&saved.pending.body.scene_version_id===props.sceneVersionId&&typeof saved.pending.key==='string'){pending.value=saved.pending;locked.value=true;}
    const history=readStored<RecordRef[]>(historyKey());records.value=Array.isArray(history)?history.filter(r=>typeof r.id==='string'&&r.body?.exercise_id===props.block.exercise_id):[];
    const id=pending.value?.attemptId??records.value.at(-1)?.id;if(id)await displayRecord(id);
  }catch{if(alive)error.value='当前学习身份未能读取，请重新打开练习。';}
  finally{if(alive)loading.value=false;}
}
async function submit():Promise<void>{
  if(!canSubmit.value)return;
  pending.value={key:crypto.randomUUID(),body:{course_version:props.courseVersion,scene_id:props.sceneId,scene_version_id:props.sceneVersionId,exercise_id:props.block.exercise_id,exercise_version_id:props.block.exercise_version_id,answers:props.block.items.filter(q=>answers.value[q.question_id]?.trim()).map(q=>({question_id:q.question_id,answer:answers.value[q.question_id]!}))}};
  locked.value=true;persist();await retry();
}
async function retry():Promise<void>{
  if(busy.value||!pending.value||!props.active||props.mode!=='dynamic')return;busy.value=true;error.value='';const request=pending.value;
  try{
    const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value){attempt.value=undefined;records.value=[];blocked.value=true;throw new Error('学习身份已变化，请重新打开练习。');}
    const id=request.attemptId??await submitAttempt(props.courseId,request.body,session.csrf,request.key);if(!alive)return;request.attemptId=id;persist();
    if(!records.value.some(r=>r.id===id)){const {answers: _answers,...body}=request.body;void _answers;records.value.push({id,body});writeStored(historyKey(),records.value);}
    const value=await readAttempt(props.courseId,id,controller.signal);if(!alive)return;if(!bound(value,request.body))throw new FreeCourseError(502,'VERSION_MISMATCH');attempt.value=value;selectedRecord.value=id;pending.value=undefined;persist();
  }catch(failure){if(!alive)return;error.value=failure instanceof Error?failure.message:'提交结果未确认，原输入和幂等键已保留。';if(failure instanceof FreeCourseError&&failure.status===409){blocked.value=true;error.value='版本、题组或提交状态已变化。保留原作答，不使用新题答案评分；请重新读取课程。';}}
  finally{if(alive)busy.value=false;}
}
function newAttempt():void{if(pending.value)return;locked.value=false;attempt.value=undefined;selectedRecord.value='';}
function feedbackLabel(value:Attempt):string{return({provisional:'暂定比较 · 答案尚未可靠核定',verified:'答案已可靠核定',unavailable:'反馈暂不可用',withdrawn:'反馈已撤回'})[value.reliability];}
onMounted(initialize);onBeforeUnmount(()=>{alive=false;controller.abort();persist();});
</script>
<template>
  <section
    class="exercise-reading"
    aria-label="随堂练习"
  >
    <h3>随堂练习</h3><p>{{ block.question }}</p><p class="badge">
      题组版本 {{ block.exercise_version_id }} · 课程 v{{ courseVersion }}
    </p>
    <p v-if="mode==='catalog_only'">
      当前只开放签核课程：可以读取已有作答，暂不能提交新的草稿练习。
    </p><p v-if="stale">
      当前是历史版本，只读原题和作答。不会把原作答交给新版答案评分。
    </p><p v-if="!active">
      练习已暂停，原输入保留。
    </p>
    <form @submit.prevent="submit">
      <div
        v-for="(item,i) in block.items"
        :key="item.question_id"
        class="exercise-question"
      >
        <label :for="`answer-${block.exercise_version_id}-${i}`">{{ i+1 }}. {{ item.question }}</label><small v-if="item.input_type!=='short_text'">{{ item.input_type==='integer'?'输入一个 JSON 整数':'输入 JSON 整数数组，不附加文字' }}</small><textarea
          :id="`answer-${block.exercise_version_id}-${i}`"
          v-model="answers[item.question_id]"
          rows="2"
          maxlength="500"
          :readonly="locked || busy || blocked || stale || mode!=='dynamic' || !active"
          @input="persist"
        />
      </div><small>可先保存部分作答；全部作答后才显示比较。暂定结果不直接更新掌握度。</small><div class="action-row">
        <button
          class="primary"
          type="submit"
          :disabled="!canSubmit"
        >
          提交本次作答
        </button><button
          v-if="pending"
          class="secondary"
          type="button"
          :disabled="busy || !active || mode!=='dynamic'"
          @click="retry"
        >
          {{ pending.attemptId ? '读取原提交结果':'确认原提交' }}
        </button><button
          v-else-if="locked"
          class="secondary"
          type="button"
          :disabled="stale || mode!=='dynamic' || blocked"
          @click="newAttempt"
        >
          继续完善或新作答
        </button>
      </div>
    </form>
    <p
      v-if="loading"
      role="status"
    >
      正在读取本机作答引用与服务端记录。
    </p><p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <div
      v-if="records.length"
      class="action-row"
    >
      <label :for="`attempt-history-${block.exercise_id}`">原始作答记录</label><select
        :id="`attempt-history-${block.exercise_id}`"
        v-model="selectedRecord"
        :disabled="busy"
        @change="displayRecord(selectedRecord)"
      >
        <option value="">
          选择已有记录
        </option><option
          v-for="(record,i) in records"
          :key="record.id"
          :value="record.id"
        >
          第{{ i+1 }}次 · 课程 v{{ record.body.course_version }} · 题组 {{ record.body.exercise_version_id }}
        </option>
      </select><button
        v-if="selectedRecord"
        class="secondary"
        type="button"
        :disabled="busy"
        @click="displayRecord(selectedRecord)"
      >
        刷新这份反馈
      </button>
    </div>
    <section
      v-if="attempt"
      class="attempt-feedback"
      aria-label="本次作答反馈"
    >
      <h4>{{ feedbackLabel(attempt) }}</h4><p>作答对应课程 v{{ attempt.binding.course_version }}，场景版本 {{ attempt.binding.scene_version_id }}，题组版本 {{ attempt.exercise_version_id }}。</p><h4>你的原始作答</h4><ul>
        <li
          v-for="answer in attempt.answers"
          :key="answer.question_id"
        >
          {{ answer.question_id }}：{{ answer.answer }}
        </li>
      </ul><p v-if="attempt.completeness==='incomplete'">
        部分作答已保存；不显示参考比较或答案解释。完善后将保存为新的一次作答。
      </p><p v-if="attempt.reliability==='withdrawn'">
        原始作答保留，错误或失效的比较已隐藏。
      </p><p v-if="attempt.mastery_effect==='revoked'">
        关联评分与掌握度证据已撤销，不再计入有效掌握度。
      </p><p v-else-if="attempt.mastery_effect==='admitted'">
        服务端已将可靠证据纳入掌握度；此处不推算增长分数。
      </p><p v-else>
        仅保留课程内表现，未更新正式掌握度。
      </p><template v-if="attempt.completeness==='complete' && ['provisional','verified'].includes(attempt.reliability)">
        <p>{{ attempt.reliability==='provisional'?'与暂定参考的匹配比例':'参考匹配比例' }}：{{ Math.round((attempt.comparison_score ?? 0)*100) }}%</p><ul>
          <li
            v-for="result in attempt.question_results"
            :key="result.question_id"
          >
            {{ result.question_id }}：{{ result.matches_reference?'匹配参考':'与参考不同' }}。{{ result.explanation }}
          </li>
        </ul>
      </template>
    </section>
  </section>
</template>
