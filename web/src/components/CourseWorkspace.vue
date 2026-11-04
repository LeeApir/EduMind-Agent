<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, toRef, watch } from 'vue';
import { FreeCourseError, listVersions, readManifest, readScene, readStored, terminalOperation, writeStored, type Manifest, type SceneProjection } from '../api/freeCourses';
import { useCourseFeed } from '../composables/useCourseFeed';
import CourseFeedback from './CourseFeedback.vue';
import CourseRevision from './CourseRevision.vue';
import CourseTutor from './CourseTutor.vue';
import CourseExercise from './CourseExercise.vue';
import CoursePresentation from './CoursePresentation.vue';
import WorkspaceState from './WorkspaceState.vue';
const props = withDefaults(defineProps<{courseId:string;operationId:string;initialVersion:number;initialScene:string;mode?:'catalog_only'|'dynamic';active?:boolean}>(),{active:true,mode:'catalog_only'});
const emit = defineEmits<{ outline:[]; home:[]; position:[version:number,scene:string];operation:[id:string] }>();
const {course,operation,owner,error,loading,reload,inaccessible}=useCourseFeed(toRef(props,'courseId'),toRef(props,'operationId'),toRef(props,'active'));
const manifest=ref<Manifest>();const scene=ref<SceneProjection>();const selectedScene=ref(props.initialScene);const version=ref(props.initialVersion);
const following=ref(true);const sceneLoading=ref(false);const sceneError=ref('');const sceneErrorKind=ref<'error'|'invalid'|'forbidden'>('error');const manifestError=ref('');const invalid=ref(false);
const highlightedAnchor=ref('');
const directoryOpen=ref(false);const tutorOpen=ref(false);const tutorTrigger=ref<HTMLButtonElement>();const tutorQuestion=ref('');
const visited=ref<string[]>([]);const versions=ref<{version:number;created_at:string}[]>([]);const versionsCursor=ref<string|null>(null);const versionsOpen=ref(false);const versionsError=ref('');
const unavailableVersions=ref(new Set<string>());
const sceneTitles=computed(()=>Object.fromEntries(manifest.value?.scenes.map(s=>[s.scene_id,s.title])??[]));
const courseTitle=ref<HTMLElement>();const readingPane=ref<HTMLElement>();let epoch=0;let controller:AbortController|undefined;let manifestEpoch=0;let manifestController:AbortController|undefined;let versionsEpoch=0;let versionsController:AbortController|undefined;let restored=false;let scroll=0;
interface Position {version:number;scene:string;following:boolean;scroll:number;visited:string[];tutorQuestion?:string}
const positionKey=()=>`edumind:free:reading:${owner.value}:${props.courseId}`;
function save():void {if(owner.value && manifest.value && !invalid.value)writeStored(positionKey(),{version:version.value,scene:selectedScene.value,following:following.value,scroll,visited:visited.value,tutorQuestion:tutorQuestion.value});}
function rememberScroll():void {scroll=window.scrollY;save();}
function saveQuestion():void {save();}
const selected=computed(()=>manifest.value?.scenes.find(s=>s.scene_id===selectedScene.value));
const readyCount=computed(()=>manifest.value?.scenes.filter(s=>s.scene_version_id&&!unavailableVersions.value.has(s.scene_version_id)).length ?? 0);
const generating=computed(()=>operation.value && !terminalOperation(operation.value.state));
const newer=computed(()=>course.value?.head && manifest.value && course.value.head.version>manifest.value.version);
const stepLabels:Record<string,string>={pending:'等待生成',running:'正在生成',blocked_dependency:'等待前置场景',failed:'生成失败',cancelled:'已停止',invalidated:'内容失效'};
function stateOf(id:string,ready:string|null):string {if(ready)return unavailableVersions.value.has(ready)?'内容暂不可用':'可学习';const state=operation.value?.steps.find(s=>s.scene_id===id)?.state;return state ? stepLabels[state] ?? '等待生成':'等待生成';}
async function loadScene(resetScroll=false):Promise<void>{
  const token=++epoch;controller?.abort();controller=new AbortController();if(scene.value?.course_version!==version.value || scene.value?.scene_id!==selectedScene.value)scene.value=undefined;sceneError.value='';sceneErrorKind.value='error';sceneLoading.value=false;
  if(!props.active || !manifest.value || invalid.value)return;
  if(!selected.value){sceneErrorKind.value='invalid';sceneError.value='记录中的场景不属于此版本，请从目录显式选择；不会自动替换阅读位置。';return;}
  if(!selected.value.scene_version_id)return;
  const cid=props.courseId;const v=version.value;const sid=selectedScene.value;const expected=selected.value.scene_version_id;sceneLoading.value=true;
  try{
    const value=await readScene(cid,v,sid,controller.signal);if(token!==epoch || !props.active)return;
    if(value.scene_version_id!==expected)throw new FreeCourseError(502,'VERSION_MISMATCH');scene.value=value;unavailableVersions.value.delete(value.scene_version_id);
    if(!visited.value.includes(sid))visited.value.push(sid);emit('position',v,sid);save();
    await nextTick();if(token!==epoch || !props.active)return;
    if(resetScroll){readingPane.value?.querySelector<HTMLElement>('h2')?.focus();scroll=0;}else window.scrollTo({top:scroll,behavior:'instant'});
  }catch(failure){if(token!==epoch)return;sceneError.value=failure instanceof Error?failure.message:'场景暂时无法读取。';if(failure instanceof FreeCourseError){if([401,403,404,409].includes(failure.status)){scene.value=undefined;if(expected)unavailableVersions.value.add(expected);}sceneErrorKind.value=[404,409].includes(failure.status)?'invalid':[401,403].includes(failure.status)?'forbidden':'error';if([401,403].includes(failure.status)){invalid.value=true;manifest.value=undefined;course.value=undefined;inaccessible.value=true;error.value='无法访问此内容，请重新读取。';}}}
  finally{if(token===epoch)sceneLoading.value=false;}
}
async function loadVersion(target:number,desired=selectedScene.value,pin=true):Promise<void>{
  const token=++manifestEpoch;manifestController?.abort();manifestController=new AbortController();epoch+=1;controller?.abort();scene.value=undefined;manifest.value=undefined;manifestError.value='';invalid.value=false;version.value=target;selectedScene.value=desired;emit('position',target,desired);
  if(pin)following.value=false;
  try{
    const value=await readManifest(props.courseId,target,manifestController.signal);if(token!==manifestEpoch || !props.active)return;
    manifest.value=value;version.value=value.version;selectedScene.value=desired || value.scenes.find(s=>s.scene_version_id)?.scene_id || value.scenes[0]?.scene_id || '';
    if(!value.scenes.some(s=>s.scene_id===desired)&&desired)scroll=0;
    save();emit('position',version.value,selectedScene.value);await loadScene();
  }catch(failure){if(token!==manifestEpoch)return;manifestError.value=failure instanceof Error?failure.message:'此课程版本无法读取。';invalid.value=failure instanceof FreeCourseError && [401,403,404,409].includes(failure.status);}
}
function selectScene(id:string):void{if(id===selectedScene.value)return;selectedScene.value=id;scroll=0;directoryOpen.value=false;save();emit('position',version.value,id);void loadScene(true);}
function additive(next:Manifest,current:Manifest):boolean{return next.plan_id===current.plan_id&&current.scenes.every(s=>next.scenes.some(n=>n.scene_id===s.scene_id&&(!s.scene_version_id||s.scene_version_id===n.scene_version_id)));}
watch(()=>course.value?.head,async head=>{
  if(!head || !props.active)return;
  if(!restored){
    restored=true;const saved=readStored<Position>(positionKey());
    if(saved && saved.version===props.initialVersion && saved.scene===props.initialScene){following.value=saved.following!==false;scroll=Number.isFinite(saved.scroll)?Math.max(0,saved.scroll):0;visited.value=Array.isArray(saved.visited)?saved.visited.filter(s=>typeof s==='string'):[];tutorQuestion.value=typeof saved.tutorQuestion==='string'?saved.tutorQuestion:'';}
    await loadVersion(props.initialVersion,props.initialScene,false);await nextTick();courseTitle.value?.focus({preventScroll:true});return;
  }
  if(manifest.value && following.value && head.version>manifest.value.version && additive(head,manifest.value)){
    // A revision is never adopted implicitly; ordinary ready additions retain the selected scene.
    manifest.value=head;version.value=head.version;save();emit('position',version.value,selectedScene.value);await loadScene();
  }else if(manifest.value){await loadScene();}
});
watch(inaccessible,()=>{if(inaccessible.value){epoch+=1;controller?.abort();scene.value=undefined;manifest.value=undefined;invalid.value=true;}});
watch(()=>props.courseId,()=>{epoch+=1;manifestEpoch+=1;versionsEpoch+=1;controller?.abort();manifestController?.abort();versionsController?.abort();manifest.value=undefined;scene.value=undefined;restored=false;version.value=props.initialVersion;selectedScene.value=props.initialScene;following.value=true;invalid.value=false;sceneError.value='';manifestError.value='';versions.value=[];versionsOpen.value=false;visited.value=[];tutorQuestion.value='';scroll=0;});
watch(()=>props.active,active=>{if(!active){save();epoch+=1;controller?.abort();manifestEpoch+=1;manifestController?.abort();versionsEpoch+=1;versionsController?.abort();}else if(manifest.value)void loadScene();});
async function readVersions(more=false):Promise<void>{
  versionsOpen.value=true;versionsError.value='';const token=++versionsEpoch;versionsController?.abort();versionsController=new AbortController();
  try{const result=await listVersions(props.courseId,more?versionsCursor.value??'':'',versionsController.signal);if(token!==versionsEpoch || !props.active)return;versions.value=more?[...versions.value,...result.items.filter(v=>!versions.value.some(old=>old.version===v.version))]:result.items;versionsCursor.value=result.next_cursor;}
  catch{if(token===versionsEpoch)versionsError.value='版本列表未能读取，当前内容保留。';}
}
function followLatest():void{if(!course.value?.head)return;following.value=true;scroll=0;void loadVersion(course.value.head.version,selectedScene.value,false);}
function closeTutor():void{tutorOpen.value=false;void nextTick(()=>tutorTrigger.value?.focus());}
window.addEventListener('scroll',rememberScroll,{passive:true});
onBeforeUnmount(()=>{save();epoch+=1;manifestEpoch+=1;versionsEpoch+=1;controller?.abort();manifestController?.abort();versionsController?.abort();window.removeEventListener('scroll',rememberScroll);});
</script>
<template>
  <main class="page-view course-workspace">
    <div class="action-row">
      <button
        class="secondary"
        type="button"
        @click="$emit('home')"
      >
        ← 我的学习
      </button><button
        class="secondary"
        type="button"
        @click="$emit('outline')"
      >
        查看大纲与生成进度
      </button>
    </div>
    <WorkspaceState
      v-if="loading && !course"
      kind="loading"
      detail="正在读取已有课程，没有发起生成。"
    />
    <WorkspaceState
      v-if="error"
      :kind="invalid ? 'forbidden':'error'"
      :detail="error"
      retry
      @retry="reload"
    />
    <template v-if="course">
      <header class="course-heading">
        <div>
          <h1
            ref="courseTitle"
            tabindex="-1"
          >
            {{ course.original_goal }}
          </h1><div class="action-row">
            <span class="badge warning">AI 生成草稿 · 未签核，内容可能有误</span><span class="badge">阅读版本 v{{ version }}</span>
          </div>
        </div><button
          class="secondary directory-toggle"
          type="button"
          :aria-expanded="directoryOpen"
          aria-controls="scene-directory"
          @click="directoryOpen = !directoryOpen"
        >
          课程目录
        </button>
      </header>
      <div class="action-row">
        <button
          class="secondary"
          type="button"
          @click="readVersions()"
        >
          查看课程版本
        </button><button
          class="secondary"
          type="button"
          @click="reload"
        >
          重新读取生成状态
        </button><button
          v-if="newer || !following"
          class="secondary"
          type="button"
          @click="followLatest"
        >
          确认读取最新版本 v{{ course.head?.version }}
        </button>
      </div>
      <p v-if="newer && !following">
        正在保留准确历史版本，不自动回退或替换。选择最新版本会改变本次阅读内容。
      </p>
      <p v-else-if="newer">
        有修订版本可读取；确认后才替换当前内容。原版本仍可从版本列表读取。
      </p>
      <section
        v-if="versionsOpen"
        class="surface"
        aria-label="课程版本"
      >
        <h2>选择准确版本</h2><p>选择历史版本会停止自动跟随增量；版本失效时不会自动退回最新。</p><p
          v-if="versionsError"
          role="alert"
        >
          {{ versionsError }}
        </p><div class="action-row">
          <button
            v-for="item in versions"
            :key="item.version"
            class="secondary"
            type="button"
            :aria-pressed="version === item.version"
            @click="scroll = 0; loadVersion(item.version)"
          >
            读取 v{{ item.version }}
          </button><button
            v-if="versionsCursor"
            class="secondary"
            type="button"
            @click="readVersions(true)"
          >
            读取更多版本
          </button><button
            class="secondary"
            type="button"
            @click="versionsOpen = false"
          >
            关闭版本列表
          </button>
        </div>
      </section>
      <WorkspaceState
        v-if="manifestError"
        :kind="invalid ? 'invalid':'error'"
        :detail="manifestError"
        retry
        @retry="loadVersion(version,selectedScene,false)"
      />
      <WorkspaceState
        v-if="!manifest && !manifestError && !loading && !course.head"
        kind="empty"
        detail="课程场景尚未就绪，请从大纲查看当前生成进度。"
      />
      <div
        v-if="manifest"
        class="course-columns"
      >
        <aside
          id="scene-directory"
          class="scene-directory surface"
          :class="{'directory-open':directoryOpen}"
        >
          <h2>课程目录 <small>{{ manifest.scenes.length }} 节</small></h2><nav aria-label="课程场景">
            <button
              v-for="(item,index) in manifest.scenes"
              :key="item.scene_id"
              type="button"
              :aria-current="selectedScene === item.scene_id ? 'step':undefined"
              @click="selectScene(item.scene_id)"
            >
              <span>{{ String(index+1).padStart(2,'0') }} · {{ item.title }}</span><small>{{ stateOf(item.scene_id,item.scene_version_id) }}</small>
            </button>
          </nav><p>生成进度：{{ readyCount }} / {{ manifest.scenes.length }} 场景可读</p><p>学习进度：本机已查看 {{ visited.filter(id=>manifest?.scenes.some(s=>s.scene_id===id)).length }} / {{ manifest.scenes.length }} 场景</p><small>查看记录不代表掌握度，也不是作答评分。</small><p v-if="generating">
            后续场景仍在生成，可继续阅读已就绪内容。
          </p><p v-else-if="!manifest.complete">
            生成尚未完整，可在大纲页查看失败原因并显式恢复。
          </p>
        </aside>
        <article
          ref="readingPane"
          class="lesson-sheet surface"
        >
          <p class="page-eyebrow">
            {{ manifest.scenes.findIndex(s=>s.scene_id===selectedScene)+1 }} / {{ manifest.scenes.length }} · 场景阅读
          </p><h2 tabindex="-1">
            {{ selected?.title ?? '选择一个场景' }}
          </h2>
          <WorkspaceState
            v-if="sceneError"
            :kind="sceneErrorKind"
            :detail="sceneError"
            retry
            @retry="loadScene()"
          />
          <WorkspaceState
            v-else-if="sceneLoading"
            kind="loading"
            detail="正在读取当前版本场景。"
          />
          <WorkspaceState
            v-else-if="!selected?.scene_version_id"
            :kind="stateOf(selectedScene,null) === '内容失效' ? 'invalid':'empty'"
            :detail="`${stateOf(selectedScene,null)}。已有场景仍可从目录打开；此处不会自动重试生成。`"
          />
          <div
            v-if="scene"
            class="scene-content"
          >
            <aside
              v-if="scene.generation_source"
              class="replay-source"
              aria-label="新课程来源"
            >
              <strong>{{ scene.generation_source.evidence_kind === 'targeted_fact_revision' ? '模型四字段事实修订' : scene.generation_source.evidence_kind === 'program_format_recovery' ? '程序格式恢复 · r03 派生课程' : scene.generation_source.evidence_kind === 'offline_fixture' ? '离线接线夹具 · 非真实生成' : '新目标真实生成 · 头插支持域' }} · 未签核</strong>
              <p
                v-if="scene.generation_source.teaching_review?.verdict !== 'pass' && scene.generation_source.evidence_kind === 'program_format_recovery'"
                role="alert"
              >
                <strong>教学评估未通过 · 仅供审查预览</strong>：原文存在字段初始化顺序的错误因果，以及 NULL 检查的歧义。请勿据此学习这两项结论；原文保留供逐项复核。
              </p>
              <p>{{ scene.generation_source.model }} · {{ scene.generation_source.prompt_version }} · {{ scene.generation_source.batch }}</p>
              <p>候选 {{ scene.generation_source.candidate_digest }}</p>
              <p v-if="scene.generation_source.parent_digest">
                父稿 {{ scene.generation_source.parent_digest }}
              </p>
              <p>规划 {{ scene.generation_source.plan_digest }} · 共享材料 {{ scene.generation_source.materials_digest }}</p>
              <small v-if="scene.generation_source.evidence_kind === 'offline_fixture'">本页教学文字为离线接线夹具，未调用模型；代码、事实、轨迹和参考答案由程序派生。</small>
              <small v-else-if="scene.generation_source.evidence_kind === 'program_format_recovery'">教学文字沿用 r03 模型原稿，仅删除四题完全相同的重复成员，未补写或改写。首稿结构不合格记录保留；代码、状态和答案由程序派生。新增模型调用为 0。</small>
              <small v-else-if="scene.generation_source.evidence_kind === 'targeted_fact_revision'">沿用 r03 模型正文，仅四处文字由本批一次真实模型请求修订；程序重装配代码、状态和答案。独立教学重评通过，保留段落重复和引用粒度的非阻断意见；原首稿结构失败及父版保留。</small>
              <small v-else>教学文字由模型生成；代码、事实、轨迹和参考答案由程序派生，自述先备知识不代表已测掌握。</small>
            </aside>
            <aside
              v-if="scene.replay_source"
              class="replay-source"
              aria-label="课程来源"
            >
              <strong>既有真实候选回放 · {{ scene.replay_source.slot }} · 未签核</strong>
              <p>{{ scene.replay_source.model }} · {{ scene.replay_source.prompt_version }} · {{ scene.replay_source.batch }}</p>
              <p>候选 {{ scene.replay_source.candidate_digest }}</p><p v-if="scene.replay_source.parent_digest">
                父稿 {{ scene.replay_source.parent_digest }}
              </p>
              <small>模型原文保留；代码、状态与参考答案由程序派生。本次接入没有新的模型调用。</small>
            </aside>
            <template
              v-for="block in scene.blocks"
              :key="block.anchor_id"
            >
              <div
                v-if="block.kind === 'text'"
                class="scene-prose"
                :class="{'presentation-highlight': highlightedAnchor === block.anchor_id}"
              >
                {{ block.markdown }}
              </div>
              <section
                v-else-if="block.kind === 'code' && !(scene.replay_source || scene.generation_source)"
                class="code-reading"
                :class="{'presentation-highlight': highlightedAnchor === block.anchor_id}"
              >
                <h3>C 语言代码</h3><pre
                  tabindex="0"
                  role="region"
                  aria-label="C 语言代码，可横向滚动"
                ><code>{{ block.source }}</code></pre><small>代码仅供阅读，没有执行。</small>
              </section>
              <span v-else-if="block.kind === 'code'" />
              <CoursePresentation
                v-else-if="block.kind === 'visualization' && (scene.replay_source || scene.generation_source)"
                :scene="scene"
                :active="active"
              />
              <span v-else-if="block.kind === 'visualization'" />
              <CourseExercise
                v-else-if="block.kind === 'exercise'"
                :key="`${scene.course_version}:${block.exercise_version_id}`"
                :course-id="courseId"
                :course-version="scene.course_version"
                :scene-id="scene.scene_id"
                :scene-version-id="scene.scene_version_id"
                :block="block"
                :head-version="course.head?.version ?? null"
                :mode="mode"
                :active="active"
              />
              <WorkspaceState
                v-else
                heading="题组已停用"
                kind="invalid"
                detail="题组已停用，不展示错误反馈；无关讲解与代码可继续阅读。"
              />
            </template>
            <CoursePresentation
              v-if="!(scene.replay_source || scene.generation_source)"
              :scene="scene"
              :active="active"
              @highlight="highlightedAnchor = $event"
            />
          </div>
          <template v-if="selected?.scene_version_id">
            <CourseFeedback
              :key="`feedback:${version}:${selected.scene_version_id}`"
              :course-id="courseId"
              :course-version="version"
              :scene-id="selectedScene"
              :scene-version-id="selected.scene_version_id"
              :blocks="scene?.blocks ?? []"
              @confirmed="loadScene()"
            />
            <CourseRevision
              v-if="operation?.execution_mode !== 'finite_head_foreground'"
              :key="`revision:${version}:${selected.scene_version_id}`"
              :course-id="courseId"
              :course-version="version"
              :scene-id="selectedScene"
              :scene-version-id="selected.scene_version_id"
              :head-version="course.head?.version ?? null"
              :mode="mode"
              :generation-active="Boolean(generating)"
              :scene-titles="sceneTitles"
              :blocked-content="!scene && Boolean(sceneError)"
              @operation="$emit('operation',$event)"
              @adopt="followLatest"
              @outline="$emit('outline')"
            />
          </template>
          <div
            v-if="operation?.execution_mode !== 'finite_head_foreground'"
            class="tutor-area"
          >
            <button
              ref="tutorTrigger"
              class="secondary"
              type="button"
              :aria-expanded="tutorOpen"
              aria-controls="course-tutor"
              @click="tutorOpen = !tutorOpen"
            >
              {{ tutorOpen ? '收起导师区域':'有疑问？打开导师区域' }}
            </button><section
              v-if="tutorOpen"
              id="course-tutor"
              class="tutor-panel"
              aria-label="按需导师"
              @keydown.esc="closeTutor"
            >
              <div class="section-heading">
                <h3>启智导师</h3><button
                  class="secondary"
                  type="button"
                  @click="closeTutor"
                >
                  关闭导师
                </button>
              </div>
              <CourseTutor
                v-if="scene"
                :key="`${scene.course_version}:${scene.scene_version_id}`"
                v-model="tutorQuestion"
                :course-id="courseId"
                :course-version="scene.course_version"
                :scene-id="scene.scene_id"
                :scene-version-id="scene.scene_version_id"
                :head-version="course.head?.version ?? null"
                :mode="mode"
                :generation-active="Boolean(generating)"
                :active="active"
                @update:model-value="saveQuestion"
              />
              <p v-else>
                当前场景尚未可读，暂不能发送提问；已有问题保留。
              </p>
            </section>
          </div>
        </article>
      </div>
    </template>
  </main>
</template>
