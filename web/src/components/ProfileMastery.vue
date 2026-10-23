<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { fetchProfile,correctProfile,ProfileRequestError,PROFILE_FIELDS,EDITABLE_PROFILE_FIELDS,PROFILE_FIELD_LABELS,PROFILE_FIELD_STATUS_LABELS,EVIDENCE_SOURCE_LABELS,profileFieldStatus,type Profile,type EditableProfileField } from '../api/profile';
import { loadGraph,loadMastery,type GraphSnapshot,type MasterySnapshot } from '../api/paths';
import { readCourse,readStored,writeStored } from '../api/freeCourses';
import { readAttempt,type Attempt } from '../api/courseExercises';
import { readMasteryHistory,type MasteryRevision,type FreeAttemptRef } from '../api/masteryHistory';
import ProfileValueEditor from './ProfileValueEditor.vue';
import WorkspaceState from './WorkspaceState.vue';
const props=withDefaults(defineProps<{courseId?:string}>(),{courseId:''});
const owner=ref('');const profile=ref<Profile>();const mastery=ref<MasterySnapshot>();const graph=ref<GraphSnapshot>();const goal=ref('');const loading=ref(true);const error=ref('');const profileError=ref('');const masteryError=ref('');const empty=ref(false);const busy=ref(false);const editError=ref('');const savedNotice=ref('');const editing=ref<EditableProfileField>();const draft=ref<unknown>();let alive=true;let epoch=0;let historyEpoch=0;const controller=new AbortController();let historyController:AbortController|undefined;let attemptController:AbortController|undefined;
interface Pending {field:EditableProfileField;value:unknown;version:number;key:string}
const pending=ref<Pending>();const nodeLimit=ref(6);const node=ref('');const history=ref<MasteryRevision[]>([]);const before=ref<number|null>(null);const historyLoading=ref(false);const historyError=ref('');const attempt=ref<Attempt>();const attemptError=ref('');const attemptLoading=ref(false);
const key=()=>`edumind:profile-correction:${owner.value}`;
const nodes=computed(()=>{const all=(mastery.value?.items??[]).map(m=>({id:m.knowledge_node_id,name:graph.value?.nodes.find(n=>n.id===m.knowledge_node_id)?.name??m.knowledge_node_id}));for(const n of graph.value?.nodes??[])if(!all.some(item=>item.id===n.id))all.push({id:n.id,name:n.name});return all;});
function state(id:string):string{const item=mastery.value?.items.find(m=>m.knowledge_node_id===id);return !item||item.status==='unseen'?'掌握度未知':`${({weak:'需要巩固',learning:'学习中',mastered:'已掌握'} as Record<string,string>)[item.status]} · ${Math.round(item.score*100)}%`;}
function clone(value:unknown):unknown{return JSON.parse(JSON.stringify(value));}
const valueLabels:Record<string,string>={major:'专业方向',education_level:'教育阶段',current_topic:'当前学习目标',current_difficulty:'当前困难',code_first:'先看代码',description:'描述',topic:'主题',level:'自述阶段'};
function text(value:unknown):string{if(value===null||value===undefined)return '未知';if(typeof value==='object')return Array.isArray(value)?value.map(text).join('；'):Object.entries(value).map(([k,v])=>`${valueLabels[k]??k}：${text(v)}`).join('；');return typeof value==='boolean'?(value?'是':'否'):String(value);}
function persist():void{if(owner.value)writeStored(key(),{editing:editing.value,draft:draft.value,pending:pending.value});}
async function initialize():Promise<void>{const token=++epoch;loading.value=true;error.value='';nodeLimit.value=6;profileError.value='';masteryError.value='';empty.value=false;historyEpoch+=1;historyController?.abort();attemptController?.abort();history.value=[];node.value='';before.value=null;attempt.value=undefined;historyLoading.value=false;attemptLoading.value=false;
 try{const session=await ensureCatalogSession();if(!alive||token!==epoch)return;if(owner.value!==session.owner){profile.value=undefined;mastery.value=undefined;graph.value=undefined;goal.value='';editing.value=undefined;draft.value=undefined;pending.value=undefined;node.value='';history.value=[];attempt.value=undefined;}owner.value=session.owner;
 const local=readStored<{editing:EditableProfileField;draft:unknown;pending?:Pending}>(key());if(local?.pending&&EDITABLE_PROFILE_FIELDS.includes(local.pending.field)){pending.value=local.pending;editing.value=local.pending.field;draft.value=local.pending.value;}else if(local&&EDITABLE_PROFILE_FIELDS.includes(local.editing)){editing.value=local.editing;draft.value=local.draft;pending.value=undefined;}
 const results=await Promise.allSettled([fetchProfile(),loadMastery(),loadGraph(),props.courseId?readCourse(props.courseId,controller.signal):Promise.resolve(null)]);if(!alive||token!==epoch)return;const [p,m,g,c]=results;
 if(p.status==='fulfilled'&&p.value&&Number.isInteger(p.value.version)&&p.value.evidence&&PROFILE_FIELDS.every(f=>Array.isArray(p.value.evidence[f]??[])&&(p.value.evidence[f]??[]).every(e=>e&&typeof e.source==='string'&&typeof e.observed_at==='string')) )profile.value=p.value;else{profile.value=undefined;if(p.status==='rejected'&&p.reason instanceof ProfileRequestError&&p.reason.code==='NOT_FOUND')empty.value=true;else profileError.value='画像未能读取，不能把失败当作未知资料。';}
 if(m.status==='fulfilled')mastery.value=m.value;else{mastery.value=undefined;masteryError.value='掌握度证据未能读取，不能显示旧分数为当前有效结果。';}
 if(g.status==='fulfilled'&&(m.status!=='fulfilled'||g.value.graph_version===m.value.graph_version))graph.value=g.value;else{graph.value=undefined;if(g.status==='fulfilled'&&m.status==='fulfilled')masteryError.value+=' 知识结构读取版本发生变化，暂按节点ID列出原证据；请重新读取。';}
 goal.value=c.status==='fulfilled'&&c.value?c.value.original_goal:'';
 }catch{if(alive&&token===epoch){error.value='当前学习身份未能读取，请重试。';profile.value=undefined;mastery.value=undefined;history.value=[];attempt.value=undefined;}}
 finally{if(alive&&token===epoch)loading.value=false;}}
function edit(field:EditableProfileField):void{if(pending.value||busy.value||!profile.value)return;editing.value=field;draft.value=clone(profile.value[field]??(field==='error_preferences'?[]:field==='learning_goals'?{current_topic:''}:{description:''}));editError.value='';savedNotice.value='';persist();}
function closeEdit():void{if(pending.value||busy.value)return;editing.value=undefined;draft.value=undefined;persist();}
async function save(retry=false):Promise<void>{if(busy.value||!editing.value||!profile.value)return;if(!retry){pending.value={field:editing.value,value:clone(draft.value),version:profile.value.version,key:crypto.randomUUID()};persist();}const request=pending.value;if(!request)return;busy.value=true;editError.value='';
 try{const session=await ensureCatalogSession();if(!alive)return;if(session.owner!==owner.value){profile.value=undefined;mastery.value=undefined;history.value=[];attempt.value=undefined;editing.value=undefined;draft.value=undefined;error.value='学习身份已变化，请重新读取。';throw new Error(error.value);}const value=await correctProfile({corrections:{[request.field]:request.value},expectedVersion:request.version,csrfToken:session.csrf,idempotencyKey:request.key});if(!alive)return;profile.value=value;pending.value=undefined;editing.value=undefined;draft.value=undefined;persist();savedNotice.value='自述已保存；正式掌握度仍来自有效学习证据。';}
 catch(failure){if(alive){if(failure instanceof ProfileRequestError&&['PROFILE_VERSION_CONFLICT','IDEMPOTENCY_CONFLICT'].includes(failure.code)){pending.value=undefined;persist();}editError.value=failure instanceof Error?failure.message:'保存结果未确认，请保留原请求。';}}
 finally{if(alive)busy.value=false;}}
async function readHistory(id:string,more=false):Promise<void>{if(historyLoading.value)return;const token=++historyEpoch;historyController?.abort();historyController=new AbortController();if(!more){attemptController?.abort();attemptLoading.value=false;node.value=id;history.value=[];before.value=null;attempt.value=undefined;attemptError.value='';}historyLoading.value=true;historyError.value='';try{const value=await readMasteryHistory(id,more?before.value??undefined:undefined,historyController.signal);if(!alive||token!==historyEpoch)return;history.value=more?[...history.value,...value.items.filter(r=>!history.value.some(old=>old.revision===r.revision))]:value.items;before.value=value.next_before_revision;}catch{if(alive&&token===historyEpoch)historyError.value='历史依据未能读取，不自动替换节点或重新评分。';}finally{if(alive&&token===historyEpoch)historyLoading.value=false;}}
async function original(ref:FreeAttemptRef):Promise<void>{if(attemptLoading.value)return;const token=historyEpoch;attemptController?.abort();attemptController=new AbortController();attemptLoading.value=true;attempt.value=undefined;attemptError.value='';try{const value=await readAttempt(ref.course_id,ref.attempt_id,attemptController.signal);if(!alive||token!==historyEpoch)return;if(value.binding.course_version!==ref.course_version||value.binding.scene_id!==ref.scene_id||value.binding.scene_version_id!==ref.scene_version_id||value.exercise_version_id!==ref.exercise_version_id||value.exercise_id!==ref.exercise_id)throw new Error('binding');attempt.value=value;}catch{if(alive&&token===historyEpoch)attemptError.value='原作答未能按准确版本读取，不回退最新内容。';}finally{if(alive&&token===historyEpoch)attemptLoading.value=false;}}
onMounted(initialize);onBeforeUnmount(()=>{alive=false;epoch+=1;historyEpoch+=1;controller.abort();historyController?.abort();attemptController?.abort();persist();});
</script>
<template>
  <main class="page-view profile-mastery">
    <p class="page-eyebrow">
      知道什么，依据是什么
    </p><h1>画像与掌握度</h1><p class="page-lead">
      自述与偏好帮助理解你的起点。正式掌握度只采用符合条件的有效证据。
    </p><button
      class="secondary"
      type="button"
      :disabled="loading || busy"
      @click="initialize"
    >
      重新读取画像与证据
    </button>
    <WorkspaceState
      v-if="loading"
      kind="loading"
      detail="正在读取已有画像与学习证据。"
    /><WorkspaceState
      v-if="error"
      kind="error"
      :detail="error"
    />
    <section
      v-if="goal"
      class="surface profile-section"
    >
      <h2>当前课程原始目标</h2><p>{{ goal }}</p><p>课程目标与以下全局自述分别保留；纠正自述不改写已有课程。</p>
    </section>
    <div class="profile-grid">
      <section
        class="surface profile-section"
        aria-label="自述与来源"
      >
        <h2>你告诉我们的</h2><p
          v-if="profileError"
          role="alert"
        >
          {{ profileError }}
        </p><p v-if="empty">
          还没有全局学习画像。课程内临时起点不等于此处已建立画像；没有资料的字段保持未知。
        </p><template v-if="profile">
          <p>画像 v{{ profile.version }} · 原始起点：{{ profile.initial_query }}</p><article
            v-for="field in PROFILE_FIELDS"
            :key="field"
            class="profile-field"
          >
            <h3>{{ PROFILE_FIELD_LABELS[field] }} <small>{{ profile[field]!=null&&!profile.evidence[field]?.length?'来源未记录':PROFILE_FIELD_STATUS_LABELS[profileFieldStatus(field,profile)] }}</small></h3><p>{{ text(profile[field]) }}</p><ul>
              <li
                v-for="(source,index) in profile.evidence[field]??[]"
                :key="index"
              >
                {{ EVIDENCE_SOURCE_LABELS[source.source]??'未知来源' }} · 画像 v{{ source.profile_version }} · {{ source.observed_at }}
              </li>
            </ul><button
              v-if="EDITABLE_PROFILE_FIELDS.includes(field as EditableProfileField)"
              class="secondary"
              type="button"
              :disabled="busy || Boolean(pending)"
              @click="edit(field as EditableProfileField)"
            >
              纠正{{ PROFILE_FIELD_LABELS[field] }}
            </button>
          </article>
        </template><p
          v-if="savedNotice"
          role="status"
        >
          {{ savedNotice }}
        </p>
        <form
          v-if="editing"
          class="profile-edit surface"
          @submit.prevent="save(false)"
        >
          <h3>纠正{{ PROFILE_FIELD_LABELS[editing] }}</h3><p>只保存你明确提供的内容，不修改作答成绩。原请求未确认时保留原文，避免补发另一份修改。</p><fieldset
            :disabled="busy || Boolean(pending)"
            class="profile-value-editor"
          >
            <ProfileValueEditor
              v-model="draft"
              :label="PROFILE_FIELD_LABELS[editing]"
              @update:model-value="persist"
            />
          </fieldset><div class="action-row">
            <button
              class="primary"
              type="submit"
              :disabled="busy || Boolean(pending) || !profile"
            >
              保存本次自述
            </button><button
              v-if="pending"
              class="secondary"
              type="button"
              :disabled="busy || !profile"
              @click="save(true)"
            >
              确认原修正请求
            </button><button
              class="secondary"
              type="button"
              :disabled="busy || Boolean(pending)"
              @click="closeEdit"
            >
              关闭自述编辑
            </button>
          </div><p
            v-if="editError"
            role="alert"
          >
            {{ editError }}
          </p>
        </form>
      </section>
      <section
        class="surface profile-section"
        aria-label="知识点掌握情况"
      >
        <h2>知识点掌握情况</h2><p
          v-if="masteryError"
          role="alert"
        >
          {{ masteryError }}
        </p><p v-if="mastery">
          读取时知识结构 {{ mastery.graph_version }}；查看课程不直接构成掌握。
        </p><p v-if="mastery && !mastery.items.length">
          尚无有效掌握度记录。未可靠核定的草稿题反馈只保留课程表现，不补成正式分数。
        </p><article
          v-for="item in nodes.slice(0,nodeLimit)"
          :key="item.id"
          class="mastery-summary"
        >
          <h3>{{ item.name }}</h3><p>{{ mastery ? state(item.id) : '当前证据未读到' }}</p><button
            class="secondary"
            type="button"
            :disabled="historyLoading || !mastery"
            @click="readHistory(item.id)"
          >
            查看{{ item.name }}依据
          </button>
        </article><button
          v-if="nodes.length>nodeLimit"
          class="secondary"
          type="button"
          @click="nodeLimit += 6"
        >
          显示更多知识点（{{ nodes.length-nodeLimit }}）
        </button><p v-if="!nodes.length && !loading">
          没有读到可列出的知识点；没有补入示例成绩。
        </p>
      </section>
    </div>
    <section
      v-if="node"
      class="surface profile-section"
      aria-label="掌握度历史依据"
    >
      <h2>{{ nodes.find(n=>n.id===node)?.name??node }} · 记录依据</h2><p>以下是历史计算快照，不代表当前仍有效。撤销后按有效事实重算，不以新题答案评价旧作答。</p><p
        v-if="historyLoading"
        role="status"
      >
        正在读取原记录。
      </p><p
        v-if="historyError"
        role="alert"
      >
        {{ historyError }}
      </p><button
        v-if="historyError"
        class="secondary"
        type="button"
        @click="readHistory(node)"
      >
        重新读取该节点依据
      </button><p v-if="!historyLoading && !historyError && !history.length">
        此节点没有历史掌握度修订；未知不等于零分。
      </p><article
        v-for="revision in history"
        :key="revision.revision"
        class="mastery-history-item"
      >
        <h3>计算版本 {{ revision.revision }} · {{ revision.status==='unseen'?'无有效证据':`${Math.round(revision.score*100)}%` }}</h3><p>{{ revision.created_at }} · 规则 {{ revision.rule_version }}</p><p v-if="revision.recomputed_from_revision">
          由计算版本 {{ revision.recomputed_from_revision }} 重算
        </p><ul>
          <li
            v-for="(summary,index) in revision.evidence_summary"
            :key="index"
          >
            {{ summary }}
          </li>
        </ul><template v-if="revision.source.reference?.kind==='free_course_attempt'">
          <p>{{ revision.source.protocol==='free-course-correction-v1'?'撤销/更正来源':'作答来源' }} · 课程 v{{ revision.source.reference.course_version }} · 题组 {{ revision.source.reference.exercise_version_id }}</p><button
            class="secondary"
            type="button"
            :disabled="attemptLoading"
            @click="original(revision.source.reference)"
          >
            读取原始作答 {{ revision.revision }}
          </button>
        </template><p v-else-if="revision.source.reference?.kind==='legacy_evidence'">
          旧记录引用：资源 {{ revision.source.reference.resource_id??'未记录' }} / 版本 {{ revision.source.reference.resource_version??'未记录' }} / 课程 {{ revision.source.reference.learning_unit_id??'未记录' }}。不公开旧私有原文。
        </p><p v-else>
          来源无法可靠连接，保持未知，不借用最新版本。
        </p>
      </article><button
        v-if="before"
        class="secondary"
        type="button"
        :disabled="historyLoading"
        @click="readHistory(node,true)"
      >
        读取更早计算版本
      </button><p
        v-if="attemptError"
        role="alert"
      >
        {{ attemptError }}
      </p><section
        v-if="attempt"
        aria-label="准确原始作答"
      >
        <h3>原始作答 · 课程 v{{ attempt.binding.course_version }}</h3><p>{{ attempt.mastery_effect==='revoked'?'贡献已撤销':attempt.mastery_effect==='admitted'?'已准入有效证据':'仅课程表现' }} · {{ attempt.reliability==='withdrawn'?'原比较反馈已撤回':attempt.reliability==='verified'?'可靠核定':attempt.reliability==='provisional'?'暂定反馈':'反馈不可用' }}</p><blockquote
          v-for="answer in attempt.answers"
          :key="answer.question_id"
        >
          {{ answer.question_id }}：{{ answer.answer }}
        </blockquote><p v-if="attempt.reliability==='withdrawn'">
          保留自己的原始输入；不显示失效参考答案与解释，也不重新评分。
        </p>
      </section>
    </section>
  </main>
</template>
