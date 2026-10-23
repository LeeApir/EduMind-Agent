<script setup lang="ts">
import { computed, onBeforeUnmount, ref, toRef, watch } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { cancelOperation, readImpact, readStored, submitOperation, terminalOperation, writeStored, type Impact, type OperationRequest } from '../api/freeCourses';
import { useCourseFeed } from '../composables/useCourseFeed';
import WorkspaceState from './WorkspaceState.vue';
const props = withDefaults(defineProps<{ courseId: string; operationId: string; mode: 'catalog_only' | 'dynamic'; active?: boolean }>(), { active: true });
const emit = defineEmits<{ learn: [version: number, scene: string]; operation: [id: string]; back: [] }>();
const active = computed(() => props.active !== false);
const { course, operation, owner, error, loading, reload } = useCourseFeed(toRef(props,'courseId'),toRef(props,'operationId'),active);
const editing = ref(false); const instruction = ref(''); const supplement = ref(''); const impact = ref<Impact>(); const confirmed = ref(false);
const busy = ref(false); const commandError = ref(''); const resumeConfirm = ref(false); let autoEntered = false; let alive = true; onBeforeUnmount(() => { alive = false; });
const running = computed(() => operation.value && !terminalOperation(operation.value.state));
const unknown = computed(() => Boolean(operation.value?.budget.usage_unknown || operation.value?.reason_code?.includes('UNKNOWN')));
const firstReady = computed(() => course.value?.head?.scenes.find(s => s.scene_version_id !== null));
const labels: Record<string,string> = { queued:'等待生成',running:'正在生成',cancel_requested:'正在停止，等待可靠收尾',succeeded:'生成已完成',partially_succeeded:'部分内容就绪',awaiting_clarification:'需要补充目标',failed:'生成未完成',cancelled:'已停止',timed_out:'本次操作已超时',pending:'等待生成',blocked_dependency:'等待前置场景',ready:'可学习',invalidated:'已失效' };
watch(owner, id => {
  if (!id) return;
  const saved = readStored<{editing:boolean;instruction:string}>(`edumind:free:outline-edit:${id}:${props.courseId}`);
  if (saved && typeof saved.instruction === 'string') { editing.value = saved.editing === true; instruction.value = saved.instruction; }
});
watch([editing,instruction], () => { if (owner.value) writeStored(`edumind:free:outline-edit:${owner.value}:${props.courseId}`, {editing:editing.value,instruction:instruction.value}); });
watch([firstReady,editing,error], () => {
  if (active.value && firstReady.value && course.value?.head && !editing.value && !error.value && !autoEntered) { autoEntered = true; emit('learn',course.value.head.version,firstReady.value.scene_id); }
});
watch(() => props.courseId, () => { editing.value = false; instruction.value = ''; impact.value = undefined; autoEntered = false; });
watch(() => course.value?.head?.version, () => { impact.value = undefined; confirmed.value = false; });
async function inspectImpact(): Promise<void> {
  editing.value = true; confirmed.value = false; commandError.value = '';
  try { impact.value = await readImpact(props.courseId,course.value?.head?.version ?? null); }
  catch (failure) { commandError.value = failure instanceof Error ? failure.message : '影响范围读取失败。'; }
}
async function execute(body: OperationRequest | {kind:'cancel'}): Promise<void> {
  if (busy.value || !owner.value) return;
  if (body.kind !== 'cancel' && (props.mode !== 'dynamic' || unknown.value)) return;
  busy.value = true; commandError.value = '';
  const cid = props.courseId; const oid = props.operationId; const originalOwner = owner.value;
  try {
    const session = await ensureCatalogSession(); if (!alive) return; if (session.owner !== originalOwner) throw new Error('学习身份已变化，请重新打开课程。');
    const signature = JSON.stringify({cid,oid,body}); const storageKey = `edumind:free:command:${session.owner}:${cid}`;
    let saved = readStored<{signature:string;key:string;operation?:string}>(storageKey);
    if (!saved || saved.signature !== signature) saved = {signature,key:crypto.randomUUID()}; writeStored(storageKey,saved);
    if (body.kind === 'cancel') { await cancelOperation(cid,oid,session.csrf,saved.key); await reload(); }
    else {
      const id = saved.operation ?? (await submitOperation(cid,body,session.csrf,saved.key)).operation_id;
      if (!alive || cid !== props.courseId || oid !== props.operationId) return;
      saved.operation = id; writeStored(storageKey,saved); writeStored(`edumind:free:operation:${session.owner}:${cid}`,id);
      editing.value = false; resumeConfirm.value = false; emit('operation',id);
    }
  } catch (failure) { commandError.value = failure instanceof Error ? failure.message : '请求结果未确认，请重试同一请求。'; }
  finally { busy.value = false; }
}
function adjust(): void {
  if (!impact.value || !confirmed.value || !instruction.value.trim() || running.value) return;
  void execute({kind:'adjust_outline',expected_head_version:impact.value.base_head_version,instruction:instruction.value.trim(),impact_digest:impact.value.impact_digest});
}
function resume(): void { if (resumeConfirm.value && !running.value) void execute({kind:'resume',expected_head_version:course.value?.head?.version ?? null,source_operation_id:props.operationId}); }
function clarify(): void { if (supplement.value.trim() && operation.value?.state === 'awaiting_clarification') void execute({kind:'clarify',expected_head_version:course.value?.head?.version ?? null,source_operation_id:props.operationId,supplement:supplement.value.trim()}); }
</script>
<template>
  <main class="page-view outline-page">
    <button
      class="secondary"
      type="button"
      @click="$emit('back')"
    >
      ← 返回学习目标
    </button>
    <WorkspaceState
      v-if="loading"
      kind="loading"
      detail="正在读取原课程与原操作，没有重新生成。"
    />
    <WorkspaceState
      v-if="error"
      kind="error"
      :detail="error"
      retry
      @retry="reload"
    />
    <template v-if="course">
      <p class="page-eyebrow">
        为这一次学习组织内容
      </p><h1>{{ course.original_goal }}</h1><span class="badge warning">AI 生成草稿 · 未签核，内容可能有误</span>
      <div class="outline-grid">
        <section class="surface">
          <div class="section-heading">
            <h2>你的课程大纲</h2><button
              class="secondary"
              type="button"
              :disabled="busy"
              @click="inspectImpact"
            >
              调整大纲
            </button>
          </div>
          <p>{{ course.head?.scenes.length ?? 0 }} 个教学场景 · {{ course.code_language === 'c' ? 'C 语言' : '未指定代码语言' }} · {{ course.head ? `v${course.head.version}` : '结构尚未就绪' }}</p>
          <ol class="outline-list">
            <li
              v-for="scene in course.head?.scenes"
              :key="scene.scene_id"
            >
              <strong>{{ scene.title }}</strong><span class="badge">{{ scene.scene_version_id ? '可学习' : labels[operation?.steps.find(s => s.scene_id === scene.scene_id)?.state ?? 'pending'] || '等待生成' }}</span>
            </li>
          </ol>
          <WorkspaceState
            v-if="!course.head"
            kind="empty"
            detail="大纲还未就绪，保留原目标并等待当前操作。"
          />
          <form
            v-if="editing"
            class="outline-edit"
            @submit.prevent="adjust"
          >
            <h3>调整影响确认</h3><p>已暂停自动进入课堂。旧内容保留；请先主动停止仍在进行的操作并等其收尾。</p>
            <label for="outline-instruction">希望怎样调整？</label><textarea
              id="outline-instruction"
              v-model="instruction"
              rows="3"
              maxlength="4000"
            />
            <template v-if="impact">
              <p>影响全课大纲，当前涉及 {{ impact.affected_scene_ids.length }} 个场景。开始新操作，最多 {{ impact.max_attempts }} 次任务尝试、{{ impact.max_seconds }} 秒，实际仍受服务端预算限制。</p><p>旧版本保留，受影响的评分与证据按修订规则撤销。结果未知时不能继续发送。</p><label><input
                v-model="confirmed"
                type="checkbox"
              >我确认全课调整和新操作的影响</label>
            </template>
            <div class="action-row">
              <button
                class="primary"
                type="submit"
                :disabled="busy || running || !impact || !confirmed || !instruction.trim() || mode !== 'dynamic' || unknown"
              >
                确认调整
              </button><button
                class="secondary"
                type="button"
                @click="editing = false"
              >
                返回原大纲
              </button><button
                v-if="!impact"
                class="secondary"
                type="button"
                @click="inspectImpact"
              >
                重新读取影响
              </button>
            </div>
          </form>
        </section>
        <aside class="surface">
          <h2>这次学习的起点</h2><blockquote>{{ course.original_goal }}</blockquote><p>原始目标由你提供；未提供的学情保持未知。图谱未关联不会阻止课程。</p>
          <p role="status">
            {{ operation ? labels[operation.state] : '只读恢复，未发现本机操作记录' }}
          </p>
          <p
            v-if="unknown"
            role="alert"
          >
            调用结果或用量待确认，后续发送已暂停；保留已有内容，不自动重试。
          </p>
          <p v-if="operation">
            尝试已用 {{ operation.budget.attempts_used ?? '未知' }} · 剩余 {{ operation.budget.attempts_remaining ?? '未知' }}
          </p>
          <p v-if="mode === 'catalog_only'">
            当前仅开放签核课程：已有草稿可读取和停止，不可发起新生成。
          </p>
          <div class="action-row">
            <button
              v-if="firstReady && course.head"
              class="primary"
              type="button"
              @click="$emit('learn',course.head.version,firstReady.scene_id)"
            >
              进入已就绪场景 →
            </button><button
              class="secondary"
              type="button"
              :disabled="loading"
              @click="reload"
            >
              重新读取进度
            </button><button
              v-if="running"
              class="secondary"
              type="button"
              :disabled="busy || operation?.state === 'cancel_requested'"
              @click="execute({kind:'cancel'})"
            >
              停止当前生成
            </button>
          </div>
          <form
            v-if="operation?.state === 'awaiting_clarification' && operation.clarification_questions.length"
            @submit.prevent="clarify"
          >
            <h3>请补充目标</h3><ul>
              <li
                v-for="question in operation.clarification_questions"
                :key="question"
              >
                {{ question }}
              </li>
            </ul><label for="clarification">补充说明</label><textarea
              id="clarification"
              v-model="supplement"
              maxlength="4000"
            /><button
              class="primary"
              type="submit"
              :disabled="busy || !supplement.trim() || mode !== 'dynamic' || unknown"
            >
              补充并继续
            </button>
          </form>
          <div v-else-if="operation && !running && operation.state !== 'succeeded' && mode === 'dynamic' && !unknown">
            <label><input
              v-model="resumeConfirm"
              type="checkbox"
            >新操作仅补生成缺失场景；保留原内容和历史用量，最多13次尝试/600秒</label><button
              class="secondary"
              type="button"
              :disabled="busy || !resumeConfirm"
              @click="resume"
            >
              确认继续缺失内容
            </button>
          </div>
          <p
            v-if="commandError"
            role="alert"
          >
            {{ commandError }}
          </p>
        </aside>
      </div>
    </template>
  </main>
</template>
