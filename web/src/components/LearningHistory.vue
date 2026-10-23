<script setup lang="ts">
import { onBeforeUnmount,onMounted,ref } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { listCourses,listVersions,readCourse,readManifest,readOperation,readStored,writeStored,type CourseSummary,type Course,type Manifest,type Operation } from '../api/freeCourses';
import { listCourseRecords,type RecordKind,type RecordRef } from '../api/courseRecords';
import { readAttempt,type Attempt } from '../api/courseExercises';
import { readFeedback,type Feedback } from '../api/courseChanges';
import { readTutorRecord,type TutorTurn } from '../api/courseTutor';
import LegacyRecordRead from './LegacyRecordRead.vue';
import WorkspaceState from './WorkspaceState.vue';
const emit=defineEmits<{restore:[course:string,version:number,scene:string,operation:string];manage:[course:string,operation:string];catalog:[]}>();
const owner=ref('');const courses=ref<CourseSummary[]>([]);const courseCursor=ref<string|null>(null);const loading=ref(true);const listError=ref('');const course=ref<Course>();const courseId=ref('');const detailLoading=ref(false);const detailError=ref('');const kind=ref<RecordKind>('attempt');const refs=ref<RecordRef[]>([]);const recordCursor=ref<string|null>(null);const recordsLoading=ref(false);const recordsError=ref('');const versions=ref<{version:number;created_at:string}[]>([]);const versionCursor=ref<string|null>(null);const version=ref(0);const manifest=ref<Manifest>();const versionError=ref('');const versionListError=ref('');const versionsLoading=ref(false);const operation=ref<Operation>();const operationError=ref('');const savedPosition=ref<{version:number;scene:string;visited?:string[]}>();const restoring=ref(false);
type Detail={kind:'attempt';value:Attempt}|{kind:'operation';value:Operation}|{kind:'feedback';value:Feedback}|{kind:'tutor';value:TutorTurn};
const detail=ref<Detail>();const recordId=ref('');const readLoading=ref(false);const readError=ref('');let alive=true;let listEpoch=0;let courseEpoch=0;let recordEpoch=0;let readEpoch=0;let controller:AbortController|undefined;let recordsController:AbortController|undefined;let readController:AbortController|undefined;const listController=new AbortController();
const kinds:RecordKind[]=['attempt','operation','feedback','tutor'];const kindLabels:Record<RecordKind,string>={attempt:'练习作答',operation:'生成与修订操作',feedback:'内容问题反馈',tutor:'导师提问'};const labels:Record<string,string>={queued:'排队中',running:'进行中',cancel_requested:'正在停止',succeeded:'操作成功',partially_succeeded:'部分完成',awaiting_clarification:'待澄清',failed:'失败',cancelled:'已停止',timed_out:'超时'};
const stepLabels:Record<string,string>={pending:'等待生成',blocked_dependency:'等待前置场景',running:'正在生成',ready:'已就绪',failed:'失败',invalidated:'已失效',cancelled:'已停止'};
const tutorLabels:Record<string,string>={queued:'排队中',running:'进行中',ready:'有效回复可读',failed:'失败',cancelled:'已停止',timed_out:'超时',invalidated:'回复已失效'};
const key=()=>`edumind:history:${owner.value}`;
function persist():void{if(owner.value)writeStored(key(),{course:courseId.value,kind:kind.value,version:version.value});}
async function initialize(more=false):Promise<void>{if(more&&(!courseCursor.value||loading.value))return;const token=++listEpoch;loading.value=true;listError.value='';try{const session=await ensureCatalogSession();if(!alive||token!==listEpoch)return;if(owner.value!==session.owner){courseEpoch+=1;recordEpoch+=1;readEpoch+=1;controller?.abort();recordsController?.abort();readController?.abort();courseId.value='';version.value=0;versions.value=[];courseCursor.value=null;recordCursor.value=null;versionCursor.value=null;savedPosition.value=undefined;operation.value=undefined;detailLoading.value=false;recordsLoading.value=false;readLoading.value=false;courses.value=[];course.value=undefined;manifest.value=undefined;detail.value=undefined;refs.value=[];owner.value=session.owner;}const result=await listCourses(more?courseCursor.value??'':'',listController.signal);if(!alive||token!==listEpoch)return;courses.value=more?[...courses.value,...result.items.filter(c=>!courses.value.some(old=>old.course_id===c.course_id))]:result.items;courseCursor.value=result.next_cursor;if(!more){const saved=readStored<{course:string;kind:RecordKind;version:number}>(key());if(saved?.kind&&kinds.includes(saved.kind))kind.value=saved.kind;if(saved?.course)await chooseCourse(saved.course,Number.isInteger(saved.version)&&saved.version>0?saved.version:undefined);}}catch{if(alive&&token===listEpoch)listError.value='课程记录未能读取，不会重新生成。';}finally{if(alive&&token===listEpoch)loading.value=false;}}
async function chooseCourse(id:string,target?:number):Promise<void>{const token=++courseEpoch;recordEpoch+=1;readEpoch+=1;controller?.abort();recordsController?.abort();readController?.abort();controller=new AbortController();courseId.value=id;course.value=undefined;manifest.value=undefined;operation.value=undefined;detail.value=undefined;refs.value=[];versions.value=[];recordCursor.value=null;versionCursor.value=null;restoring.value=false;version.value=0;versionsLoading.value=false;versionError.value='';versionListError.value='';operationError.value='';detailError.value='';readError.value='';recordsError.value='';recordId.value='';savedPosition.value=undefined;recordsLoading.value=false;readLoading.value=false;detailLoading.value=true;
 try{const results=await Promise.allSettled([readCourse(id,controller.signal),listVersions(id,'',controller.signal),listCourseRecords(id,'operation','',controller.signal)]);if(!alive||token!==courseEpoch)return;const [c,v,o]=results;if(c.status==='rejected')throw new Error('无法访问此课程记录，请重新读取。');course.value=c.value;savedPosition.value=readStored(keyForPosition(id))??undefined;if(v.status==='fulfilled'){versions.value=v.value.items;versionCursor.value=v.value.next_cursor;}else versionListError.value='版本列表未能读取；已知准确位置仍可单独读取。';if(o.status==='fulfilled'){try{for(const item of o.value.items){const op=await readOperation(id,item.record_id,controller.signal);if(!alive||token!==courseEpoch)return;if(op.kind!=='tutor_turn'){operation.value=op;break;}}if(!operation.value)operationError.value='这一页没有读到课程生成操作，可在操作列表继续查阅。';}catch{if(alive&&token===courseEpoch)operationError.value='生成操作状态未读到，不猜测完成或失败。';}}else operationError.value='生成操作状态未读到，不猜测完成或失败。';const wanted=target??c.value.head?.version;if(wanted)await loadVersion(wanted);if(!alive||token!==courseEpoch)return;persist();await loadRecords();}
 catch(failure){if(alive&&token===courseEpoch)detailError.value=failure instanceof Error?failure.message:'课程记录读取失败。';}finally{if(alive&&token===courseEpoch)detailLoading.value=false;}}
function keyForPosition(id:string):string{return `edumind:free:reading:${owner.value}:${id}`;}
async function loadVersion(target:number):Promise<void>{const token=courseEpoch;const id=courseId.value;version.value=target;manifest.value=undefined;versionError.value='';persist();try{const value=await readManifest(id,target,controller?.signal);if(alive&&token===courseEpoch&&target===version.value)manifest.value=value;}catch{if(alive&&token===courseEpoch&&target===version.value)versionError.value=`版本 v${target} 不可读取，不替换为最新版本。`;}}
async function moreVersions(more=true):Promise<void>{if(versionsLoading.value||detailLoading.value||more&&!versionCursor.value)return;const token=courseEpoch;versionsLoading.value=true;versionListError.value='';try{const result=await listVersions(courseId.value,more?versionCursor.value??'':'',controller?.signal);if(!alive||token!==courseEpoch)return;versions.value=more?[...versions.value,...result.items.filter(v=>!versions.value.some(old=>old.version===v.version))]:result.items;versionCursor.value=result.next_cursor;}catch{if(alive&&token===courseEpoch)versionListError.value='版本列表未能读取；已知准确位置仍可单独读取。';}finally{if(alive&&token===courseEpoch)versionsLoading.value=false;}}

async function loadRecords(more=false):Promise<void>{if(recordsLoading.value||!course.value||more&&!recordCursor.value)return;const token=++recordEpoch;recordsController?.abort();recordsController=new AbortController();const id=courseId.value;const type=kind.value;recordsLoading.value=true;recordsError.value='';if(!more){refs.value=[];recordCursor.value=null;detail.value=undefined;readEpoch+=1;readController?.abort();readLoading.value=false;recordId.value='';}persist();try{const value=await listCourseRecords(id,type,more?recordCursor.value??'':'',recordsController.signal);if(!alive||token!==recordEpoch)return;refs.value=more?[...refs.value,...value.items.filter(r=>!refs.value.some(old=>old.record_id===r.record_id))]:value.items;recordCursor.value=value.next_before_id;}catch{if(alive&&token===recordEpoch)recordsError.value='原记录列表未读到，不以空记录代替读取失败。';}finally{if(alive&&token===recordEpoch)recordsLoading.value=false;}}
async function filter():Promise<void>{recordsController?.abort();recordsLoading.value=false;recordEpoch+=1;await loadRecords();}
async function readRecord(id:string):Promise<void>{const token=++readEpoch;readController?.abort();readController=new AbortController();const cid=courseId.value;const type=kind.value;readLoading.value=true;readError.value='';detail.value=undefined;recordId.value=id;try{let result:Detail;if(type==='attempt')result={kind:type,value:await readAttempt(cid,id,readController.signal)};else if(type==='operation')result={kind:type,value:await readOperation(cid,id,readController.signal)};else if(type==='feedback')result={kind:type,value:await readFeedback(cid,id,readController.signal)};else result={kind:type,value:await readTutorRecord(cid,id,readController.signal)};if(alive&&token===readEpoch)detail.value=result;}catch{if(alive&&token===readEpoch)readError.value='无法读取这条原记录；不借用其他课程或最新版本内容。';}finally{if(alive&&token===readEpoch)readLoading.value=false;}}
async function restore(target:number,scene:string):Promise<void>{if(restoring.value||!scene)return;const token=courseEpoch;const cid=courseId.value;restoring.value=true;versionError.value='';try{const value=await readManifest(cid,target,controller?.signal);if(!alive||token!==courseEpoch)return;if(!value.scenes.some(s=>s.scene_id===scene))throw new Error('missing');emit('restore',cid,target,scene,operation.value?.operation_id??'');}catch{if(alive&&token===courseEpoch)versionError.value='原阅读位置或版本已不可访问；不跳到最新场景，也不补生成。';}finally{if(alive&&token===courseEpoch)restoring.value=false;}}
onMounted(()=>initialize());onBeforeUnmount(()=>{alive=false;listEpoch+=1;courseEpoch+=1;recordEpoch+=1;readEpoch+=1;listController.abort();controller?.abort();recordsController?.abort();readController?.abort();persist();});
</script>
<template>
  <main class="page-view learning-history">
    <p class="page-eyebrow">
      回到上次理解的地方
    </p><h1>学习记录</h1><p class="page-lead">
      课程、原始作答和内容更新各自保留版本。这里读取已有记录，不自动继续生成。
    </p><div class="action-row">
      <button
        class="secondary"
        type="button"
        :disabled="loading"
        @click="initialize()"
      >
        重新读取课程列表
      </button><button
        class="secondary"
        type="button"
        @click="emit('catalog')"
      >
        签核课程目录
      </button>
    </div><WorkspaceState
      v-if="loading"
      kind="loading"
      detail="正在读取已有记录，没有重新生成。"
    /><p
      v-if="listError"
      role="alert"
    >
      {{ listError }}
    </p><p v-if="!loading && !listError && !courses.length">
      尚无自由课程记录。原入口资源仍按原协议读取。
    </p>
    <div class="history-grid">
      <section
        class="surface history-section"
        aria-label="课程记录列表"
      >
        <h2>自由课程</h2><ul class="history-course-list">
          <li
            v-for="item in courses"
            :key="item.course_id"
          >
            <button
              class="secondary"
              type="button"
              :aria-pressed="courseId===item.course_id"
              @click="chooseCourse(item.course_id)"
            >
              {{ item.original_goal }}
            </button><p>AI 生成草稿 · 未签核 · {{ item.head_version?`最新清单 v${item.head_version}`:'尚无可读清单' }}</p><small>{{ item.created_at }}</small>
          </li>
        </ul><button
          v-if="courseCursor"
          class="secondary"
          type="button"
          :disabled="loading"
          @click="initialize(true)"
        >
          读取更多课程
        </button>
      </section>
      <section
        class="surface history-section"
        aria-label="当前课程记录"
      >
        <p
          v-if="detailLoading"
          role="status"
        >
          正在读取准确课程与操作记录。
        </p><p
          v-if="detailError"
          role="alert"
        >
          {{ detailError }}
        </p><p v-if="!course && !detailLoading && !detailError">
          请选择课程，再按类型查看原记录。
        </p><template v-if="course">
          <h2>{{ course.original_goal }}</h2><p>AI 生成草稿 · 未签核，内容可能有误</p><p v-if="operation">
            课程操作：{{ labels[operation.state]??'状态待核对' }}。操作成功不等于完成阅读或掌握。
          </p><p
            v-if="operationError"
            role="status"
          >
            {{ operationError }}
          </p><p v-if="manifest">
            读取清单 v{{ manifest.version }} · {{ manifest.scenes.filter(s=>s.scene_version_id).length }}/{{ manifest.scenes.length }} 场景已生成 · {{ manifest.complete?'清单生成完整':'清单部分生成' }}。内容是否仍可用须按准确场景读取。
          </p><p v-if="savedPosition">
            本机阅读位置 v{{ savedPosition.version }} · 查看过 {{ savedPosition.visited?.length??0 }} 个场景；查看不等于学习测评完成。
          </p><p v-else>
            本机没有保存阅读位置，不推测已经学完。
          </p><div class="action-row">
            <button
              v-if="savedPosition?.scene"
              class="primary"
              type="button"
              :disabled="restoring"
              @click="restore(savedPosition.version,savedPosition.scene)"
            >
              恢复准确阅读位置
            </button><button
              v-if="operation"
              class="secondary"
              type="button"
              @click="emit('manage',courseId,operation.operation_id)"
            >
              查看生成进度与继续选项
            </button>
          </div><p>继续生成需在大纲页另行确认新操作与预算；进入此处不发起生成。</p>
          <h3>课程版本</h3><p
            v-if="versionListError"
            role="alert"
          >
            {{ versionListError }}
          </p><button
            v-if="versionListError"
            class="secondary"
            type="button"
            :disabled="versionsLoading || detailLoading"
            @click="moreVersions(false)"
          >
            重新读取版本列表
          </button><div class="action-row">
            <button
              v-for="item in versions"
              :key="item.version"
              class="secondary"
              type="button"
              :aria-pressed="version===item.version"
              @click="loadVersion(item.version)"
            >
              读取清单 v{{ item.version }}
            </button><button
              v-if="versionCursor"
              class="secondary"
              type="button"
              @click="moreVersions(true)"
            >
              读取更多版本
            </button>
          </div><p
            v-if="versionError"
            role="alert"
          >
            {{ versionError }}
          </p><ul
            v-if="manifest"
            class="history-scene-list"
          >
            <li
              v-for="scene in manifest.scenes"
              :key="scene.scene_id"
            >
              <span>{{ scene.title }} · {{ scene.scene_version_id?'已生成；可用性待读取':'尚未生成' }}</span><button
                class="secondary"
                type="button"
                :disabled="restoring"
                @click="restore(manifest.version,scene.scene_id)"
              >
                读取此版本的{{ scene.title }}
              </button>
            </li>
          </ul>
          <label for="history-kind">记录类型<select
            id="history-kind"
            v-model="kind"
            @change="filter"
          ><option
            v-for="type in kinds"
            :key="type"
            :value="type"
          >{{ kindLabels[type] }}</option></select></label><p
            v-if="recordsLoading"
            role="status"
          >
            正在读取原记录索引。
          </p><p
            v-if="recordsError"
            role="alert"
          >
            {{ recordsError }}
          </p><button
            v-if="recordsError"
            class="secondary"
            type="button"
            @click="loadRecords()"
          >
            重新读取原索引
          </button><p v-if="!detailLoading && !recordsLoading && !recordsError && !refs.length">
            此课程暂无这类记录。
          </p><ul class="history-ref-list">
            <li
              v-for="item in refs"
              :key="item.record_id"
            >
              <button
                class="secondary"
                type="button"
                @click="readRecord(item.record_id)"
              >
                读取{{ kindLabels[kind] }} · {{ item.created_at }}
              </button>
            </li>
          </ul><button
            v-if="recordCursor"
            class="secondary"
            type="button"
            :disabled="recordsLoading"
            @click="loadRecords(true)"
          >
            读取更多原记录
          </button>
          <p
            v-if="readLoading"
            role="status"
          >
            正在读取该原记录。
          </p><p
            v-if="readError"
            role="alert"
          >
            {{ readError }}
          </p><button
            v-if="recordId"
            class="secondary"
            type="button"
            :disabled="readLoading"
            @click="readRecord(recordId)"
          >
            重新读取此原记录
          </button>
          <section
            v-if="detail?.kind==='attempt'"
            aria-label="原始作答记录"
          >
            <h3>原始作答 · 课程 v{{ detail.value.binding.course_version }}</h3><p>题组 {{ detail.value.exercise_version_id }} · {{ detail.value.completeness==='complete'?'整组完整作答':'部分作答' }} · {{ detail.value.reliability==='withdrawn'?'比较反馈已撤回':detail.value.reliability==='verified'?'可靠核定':detail.value.reliability==='provisional'?'暂定比较':'反馈不可用' }}</p><p>{{ detail.value.mastery_effect==='revoked'?'原贡献已撤销':detail.value.mastery_effect==='admitted'?'已准入正式证据':'仅课程表现，未计入正式掌握度' }}</p><blockquote
              v-for="answer in detail.value.answers"
              :key="answer.question_id"
            >
              {{ answer.question_id }}：{{ answer.answer }}
            </blockquote><template v-if="detail.value.comparison_score!==null">
              <p>原题组比较 {{ Math.round(detail.value.comparison_score*100) }}%，不是节点掌握度。</p><p
                v-for="item in detail.value.question_results"
                :key="item.question_id"
              >
                {{ item.question_id }} · {{ item.matches_reference?'与原参考一致':'与原参考不一致' }}：{{ item.explanation }}
              </p>
            </template><p v-else>
              原始输入保留；当前不展示参考答案或比较解释。
            </p><button
              class="secondary"
              type="button"
              :disabled="restoring"
              @click="restore(detail.value.binding.course_version,detail.value.binding.scene_id)"
            >
              读取作答对应原场景
            </button>
          </section>
          <section
            v-else-if="detail?.kind==='operation'"
            aria-label="原操作记录"
          >
            <h3>{{ detail.value.kind==='revise_scene'?'局部修订':detail.value.kind==='adjust_outline'?'大纲调整':detail.value.kind==='tutor_turn'?'导师操作':'课程生成操作' }} · {{ labels[detail.value.state]??'状态待核对' }}</h3><p>原基线 {{ detail.value.base_head_version===null?'无':`v${detail.value.base_head_version}` }}；当前 head {{ detail.value.head_version===null?'无':`v${detail.value.head_version}` }}。当前 head 不作为本次操作发布版本。</p><p v-if="detail.value.budget.usage_unknown">
              用量或发送结果待可靠确认，不自动补发。
            </p><ul>
              <li
                v-for="step in detail.value.steps"
                :key="step.step_key"
              >
                {{ step.scene_id??step.step_key }} · {{ stepLabels[step.state]??'状态待核对' }}
              </li>
            </ul><button
              v-if="detail.value.kind!=='tutor_turn'"
              class="secondary"
              type="button"
              @click="emit('manage',courseId,detail.value.operation_id)"
            >
              查看此操作与恢复条件
            </button>
          </section>
          <section
            v-else-if="detail?.kind==='feedback'"
            aria-label="原问题反馈"
          >
            <h3>{{ ({pending:'待核对',confirmed:'已确认处置',not_confirmed:'本次未确认',corrected:'处置已更正'} as Record<string,string>)[detail.value.status] }}</h3><p>课程 v{{ detail.value.binding.course_version }} · {{ detail.value.anchor_id }}</p><p>{{ detail.value.description }}</p>
          </section>
          <section
            v-else-if="detail?.kind==='tutor'"
            aria-label="原导师提问"
          >
            <h3>导师提问 · 课程 v{{ detail.value.binding.course_version }}</h3><p>{{ detail.value.message }}</p><p>{{ tutorLabels[detail.value.status]??'状态待核对' }}</p><p v-if="detail.value.status==='ready'">
              AI 补充解释 · 未签核：{{ detail.value.markdown }}
            </p><p v-else>
              只有仍有效的回复才展示正文，不借用新版本上下文。
            </p>
          </section>
        </template>
      </section>
    </div><LegacyRecordRead :key="owner" />
  </main>
</template>
