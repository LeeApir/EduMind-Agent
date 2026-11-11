<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { SceneProjection, SceneBlock, HeadReplayFrame, StackCourseFrame, QueueCourseFrame, BinarySearchFrame } from '../api/freeCourses';
const props = withDefaults(defineProps<{scene: SceneProjection; active?: boolean}>(),{active:true});
const emit = defineEmits<{highlight:[anchor:string]}>();
type OrderedFrame = StackCourseFrame | QueueCourseFrame;
type LineFrame = HeadReplayFrame | OrderedFrame | BinarySearchFrame;
type Visual = Extract<SceneBlock,{kind:'visualization'}>;
interface Element {id:string;label:string;next_id:string|null}
interface Action {type:'highlight_block'|'show_step'|'pause';anchor_id:string;step_index:number|null}
const index = ref(-1);const playing = ref(false);const reduced = ref(false);const frames = ref<Record<string,number>>({});const highlighted = ref('');
let timer: ReturnType<typeof setTimeout>|undefined;let media: MediaQueryList|undefined;
const visuals = computed(()=>props.scene.blocks.filter((b):b is Visual=>b.kind==='visualization'));
const orderedCourse = computed(() => {
  const replay = props.scene.replay_source;
  const origin = props.scene.generation_source?.origin;
  if (origin === 'queue_fifo_model_generation') return 'queue';
  if (origin === 'stack_lifo_model_generation' || (replay && 'topic' in replay && replay.topic === 'stack')) return 'stack';
  return undefined;
});
const searchCourse = computed(() => props.scene.generation_source?.origin === 'binary_search_model_generation' ||
  props.scene.replay_source?.mapping_version === 'binary-search-program-frames-v1');
const guided = computed(()=>visuals.value.find(b=>b.visualization_type==='head_insertion_replay_v1'||b.visualization_type===orderedCourse.value||
  searchCourse.value && b.visualization_type==='binary-search'));
const comparisons = {less: '<', equal: '=', greater: '>'} as const;

function validSearchFrame(frame: BinarySearchFrame | undefined, index: number, elements: Element[]): boolean {
  if (!frame || frame.frame_id !== `f${index}` || typeof frame.note !== 'string') return false;
  const code = props.scene.blocks.find(b => b.anchor_id === frame.code_anchor);
  const { left, right, mid, target, phase, comparison, line } = frame;
  if (code?.kind !== 'code' || !Number.isInteger(line) || line < 1 || line > code.source.trimEnd().split('\n').length ||
      !Number.isInteger(left) || !Number.isInteger(right) || left < 0 || left > right || right >= elements.length ||
      !Number.isInteger(target)) return false;
  if (phase === 'initial') return index === 0 && mid === null && comparison === null;
  if (mid === null || !Number.isInteger(mid) || mid < 0 || mid >= elements.length) return false;
  const value = Number(elements[mid]!.label);
  if (!Number.isInteger(value)) return false;
  if (phase === 'found') return index === 5 && mid >= left && mid <= right && comparison === 'equal' && value === target;
  if (comparison !== (value < target ? 'less' : value > target ? 'greater' : 'equal') || comparison === 'equal') return false;
  return phase === 'compare' ? mid === left + Math.floor((right - left) / 2) :
    phase === 'narrowed' && (comparison === 'less' ? left === mid + 1 : right === mid - 1);
}

function validVisual(block: Visual): boolean {
  const origin = props.scene.generation_source?.origin;
  if(block.visualization_type==='head_insertion_replay_v1')return Boolean(props.scene.replay_source || origin === 'head_goal_model_generation' || origin === 'reviewed_archived_response_import')&&Array.isArray(block.steps)&&block.steps.length>0&&block.steps.length<=13&&block.steps.every((s,i)=>{
    const f=s.head_frame;const code=props.scene.blocks.find(b=>b.anchor_id===f?.code_anchor&&b.kind==='code');
    return f&&f.frame_id===`f${String(i).padStart(2,'0')}`&&typeof f.title==='string'&&typeof f.note==='string'&&f.state&&typeof f.state.nodes==='object'&&code?.kind==='code'&&(f.line===null||Number.isInteger(f.line)&&f.line>0&&f.line<=code.source.trimEnd().split('\n').length)&&['active','inactive'].includes(f.locals_scope);
  });
  const binarySearch = block.visualization_type === 'binary-search';
  if(!['array','linked_list','stack','queue','binary-search'].includes(block.visualization_type)||!Array.isArray(block.steps)||!block.steps.length||block.steps.length>50)return false;
  if (binarySearch !== searchCourse.value || (binarySearch && block.steps.length !== 6)) return false;
  if(orderedCourse.value && (block.visualization_type!==orderedCourse.value||block.steps.length!==5))return false;
  return block.steps.every((s,i)=>{
    const f=orderedCourse.value==='queue'?s.queue_frame:s.stack_frame;
    if(orderedCourse.value){
      if (orderedCourse.value==='queue' ? s.stack_frame : s.queue_frame) return false;
      const code=props.scene.blocks.find(b=>b.anchor_id===f?.code_anchor);
      if(!f||f.frame_id!==`f${i}`||typeof f.note!=='string'||code?.kind!=='code'||
        !Number.isInteger(f.line)||f.line<1||f.line>code.source.trimEnd().split('\n').length||
        !validRemovedValue(f))return false;
    }else if(s.stack_frame||s.queue_frame)return false;
    if(typeof s.caption!=='string'||!Array.isArray(s.elements)||s.elements.length>32||!Array.isArray(s.highlight_ids))return false;
    const elements=s.elements as Element[];
    if(!elements.every(e=>e&&typeof e.id==='string'&&typeof e.label==='string'&&(e.next_id===null||typeof e.next_id==='string')))return false;
    if (binarySearch) {
      if (elements.length !== 5 || !validSearchFrame(s.binary_search_frame, i, elements)) return false;
      const mid = s.binary_search_frame!.mid;
      if (mid === null ? s.highlight_ids.length !== 0 :
          s.highlight_ids.length !== 1 || s.highlight_ids[0] !== elements[mid]!.id) return false;
    } else if (s.binary_search_frame) return false;
    const ids=new Set(elements.map(e=>e.id));return ids.size===elements.length&&elements.every(e=>e.next_id===null||ids.has(e.next_id))&&s.highlight_ids.every(id=>typeof id==='string'&&ids.has(id));
  });
}
const validActions = computed(()=>{
  if(!Array.isArray(props.scene.actions)||props.scene.actions.length>100||!visuals.value.every(validVisual))return false;
  return props.scene.actions.every(raw=>{
    if(!raw||typeof raw!=='object')return false;const a=raw as Action;
    if(Object.keys(raw).some(k=>!['type','anchor_id','step_index'].includes(k)))return false;
    const block=props.scene.blocks.find(b=>b.anchor_id===a.anchor_id);if(!block)return false;
    return a.type==='show_step'?block.kind==='visualization'&&Number.isInteger(a.step_index)&&Number(a.step_index)>=0&&Number(a.step_index)<block.steps.length:['highlight_block','pause'].includes(a.type)&&a.step_index===null;
  });
});
const actions = computed(()=>validActions.value?props.scene.actions as Action[]:[]);
const activePlayback = computed(()=>props.active!==false);
function stop():void {playing.value=false;clearTimeout(timer);}
function apply(target:number):void {
  stop();if(!validActions.value)return;
  index.value=Math.max(guided.value?0:-1,Math.min(target,actions.value.length-1));frames.value={};highlighted.value='';
  for(const action of actions.value.slice(0,index.value+1)){
    if(action.type==='show_step')frames.value[action.anchor_id]=action.step_index!;
    if(action.type==='highlight_block')highlighted.value=action.anchor_id;
  }
  emit('highlight',highlighted.value);
}
function tick():void {
  if(!playing.value||!activePlayback.value||reduced.value||document.hidden){stop();return;}
  const target=index.value+1;
  if(target>=actions.value.length){stop();return;}
  apply(target);
  if(actions.value[target]?.type==='pause'||target===actions.value.length-1)return;
  playing.value=true;timer=setTimeout(tick,1200);
}
function play():void {if(!actions.value.length||reduced.value||!activePlayback.value)return;if(index.value>=actions.value.length-1)apply(-1);playing.value=true;tick();}
function chooseFrame(block:Visual,delta:number):void {stop();if(!validVisual(block))return;frames.value={...frames.value,[block.anchor_id]:Math.max(0,Math.min(block.steps.length-1,(frames.value[block.anchor_id]??0)+delta))};}
function removedValue(frame:OrderedFrame): number|null {return 'dequeued' in frame?frame.dequeued:frame.popped;}
function validRemovedValue(frame:OrderedFrame): boolean {
  const value=removedValue(frame);
  return value===null||Number.isInteger(value);
}
function headFrame(block:Visual):HeadReplayFrame|undefined{return validVisual(block)?block.steps[frames.value[block.anchor_id]??0]?.head_frame:undefined;}
function orderedFrame(block:Visual):OrderedFrame|undefined {
  if (!validVisual(block)) return undefined;
  const step=block.steps[frames.value[block.anchor_id]??0];
  return step?.queue_frame??step?.stack_frame;
}
function searchFrame(block: Visual): BinarySearchFrame | undefined {
  return validVisual(block) ? block.steps[frames.value[block.anchor_id] ?? 0]?.binary_search_frame : undefined;
}
function lineFrame(block:Visual):LineFrame|undefined{return headFrame(block)??orderedFrame(block)??searchFrame(block);}
function replayCode(frame:LineFrame):string{const code=props.scene.blocks.find(b=>b.kind==='code'&&b.anchor_id===frame.code_anchor);return code?.kind==='code'?code.source:'';}
function pointer(value:string|null|undefined):string{return value===null?'NULL':value==='indeterminate'?'未知（未初始化）':value??'';}
function chain(frame:HeadReplayFrame):string{let id=frame.state.caller_head;const parts:string[]=[];const seen=new Set<string>();while(id!==null){if(id==='indeterminate'||seen.has(id)||!frame.state.nodes[id]){parts.push('未知或重复');return parts.join(' → ');}seen.add(id);parts.push(`${id}(${frame.state.nodes[id]!.data})`);id=frame.state.nodes[id]!.next;}parts.push('NULL');return parts.join(' → ');}
function elements(block:Visual): Element[] {return validVisual(block)?block.steps[frames.value[block.anchor_id]??0]!.elements as Element[]:[];}
function highlightedElement(block:Visual,id:string):boolean{return validVisual(block)&&block.steps[frames.value[block.anchor_id]??0]!.highlight_ids?.includes(id)===true;}
function label(block:Visual):string{return ({array:'数组',linked_list:'链表',stack:'栈',queue:'队列','binary-search':'二分查找',head_insertion_replay_v1:'链表'} as Record<string,string>)[block.visualization_type]??'状态';}
function motionChanged():void{reduced.value=media?.matches??false;if(reduced.value)stop();}
function visibilityChanged():void{if(document.hidden)stop();}
watch(()=>props.scene,()=>{stop();index.value=guided.value?0:-1;frames.value={};highlighted.value='';emit('highlight','');},{immediate:true});
watch(activePlayback,value=>{if(!value)stop();});
onMounted(()=>{media=window.matchMedia?.('(prefers-reduced-motion: reduce)');motionChanged();media?.addEventListener('change',motionChanged);document.addEventListener('visibilitychange',visibilityChanged);});
onBeforeUnmount(()=>{stop();media?.removeEventListener('change',motionChanged);document.removeEventListener('visibilitychange',visibilityChanged);});
</script>
<template>
  <section
    v-if="visuals.length || scene.actions.length"
    class="course-presentation"
    aria-label="过程演示与代码对照"
  >
    <div class="section-heading">
      <h3>过程演示与代码对照</h3><span class="badge">状态快照 · 非代码执行</span>
    </div>
    <p
      v-if="!validActions"
      role="status"
    >
      动作或定位已失效，已停止播放。正文、代码和可用文字说明保留。
    </p>
    <p
      v-if="reduced"
      role="status"
    >
      已遵循减少动效设置，请用手动步进查看。
    </p>
    <div
      v-if="actions.length"
      class="action-row"
    >
      <button
        class="secondary"
        type="button"
        :disabled="reduced || playing"
        @click="play"
      >
        {{ guided ? '播放':'播放动作' }}
      </button><button
        class="secondary"
        type="button"
        :disabled="!playing"
        @click="stop"
      >
        {{ guided ? '暂停':'暂停动作' }}
      </button><button
        class="secondary"
        type="button"
        :disabled="guided ? index <= 0 : index < 0"
        @click="apply(index-1)"
      >
        {{ guided ? '上一步':'上一动作' }}
      </button><button
        class="secondary"
        type="button"
        :disabled="index >= actions.length-1"
        @click="apply(index+1)"
      >
        {{ guided ? '下一步':'下一动作' }}
      </button><button
        v-if="guided"
        type="button"
        class="secondary"
        @click="apply(0)"
      >
        重置
      </button><span role="status">{{ guided ? '步骤':'动作' }} {{ index+1 }} / {{ actions.length }}</span>
    </div>
    <section
      v-for="block in visuals"
      :key="block.anchor_id"
      class="visual-snapshot"
      :class="{'presentation-highlight':highlighted===block.anchor_id}"
      :aria-label="`${label(block)}状态演示`"
    >
      <h4>{{ label(block) }}状态</h4><p>{{ block.text_alternative }}</p>
      <template v-if="validVisual(block)">
        <p
          class="frame-caption"
          role="status"
        >
          步骤 {{ (frames[block.anchor_id]??0)+1 }} / {{ block.steps.length }}：{{ block.steps[frames[block.anchor_id]??0]?.caption }}
        </p>
        <div
          v-if="lineFrame(block)"
          class="head-replay-frame"
          :data-frame="lineFrame(block)!.frame_id"
        >
          <div class="head-replay-grid">
            <pre
              class="head-replay-code"
              tabindex="0"
              aria-label="逐行 C 语言代码"
            ><code><span
              v-for="(line,i) in replayCode(lineFrame(block)!).trimEnd().split('\n')"
              :key="i"
              class="course-code-line"
              :class="{'active-code-line':lineFrame(block)!.line===i+1}"
              :data-line="i+1"
            >{{ i+1 }}  {{ line }}</span></code></pre><div v-if="headFrame(block)">
              <h4>{{ headFrame(block)!.title }}</h4><p class="head-step-note">
                {{ headFrame(block)!.note }}
              </p>
              <p>caller_head → {{ chain(headFrame(block)!) }}</p>
              <dl class="head-pointer-state">
                <dt>caller_head</dt><dd>{{ pointer(headFrame(block)!.state.caller_head) }}</dd>
              </dl>
              <p v-if="headFrame(block)!.locals_scope==='inactive'">
                head / p：不在作用域（原局部值仅作历史快照）
              </p>
              <dl
                v-else
                class="head-pointer-state"
              >
                <dt>head</dt><dd>{{ pointer(headFrame(block)!.state.local_head) }}</dd><dt>p</dt><dd>{{ pointer(headFrame(block)!.state.p) }}</dd>
              </dl>
              <ul class="head-nodes">
                <li
                  v-for="(node,id) in headFrame(block)!.state.nodes"
                  :key="id"
                >
                  {{ id }} · {{ String(id).startsWith('i')?'栈节点':'动态节点' }} · data: {{ node.data==='indeterminate'?'未知（未初始化）':node.data }} · next: {{ pointer(node.next) }}
                </li>
              </ul>
              <details><summary>准确状态与原步骤</summary><pre>{{ JSON.stringify(headFrame(block),null,2) }}</pre></details>
            </div>
            <div v-else-if="searchFrame(block)">
              <p>{{ searchFrame(block)!.note }}</p>
              <dl class="head-pointer-state">
                <dt>left</dt><dd>{{ searchFrame(block)!.left }}</dd>
                <dt>right</dt><dd>{{ searchFrame(block)!.right }}</dd>
                <dt>mid</dt><dd>{{ searchFrame(block)!.mid ?? '未计算' }}</dd>
                <dt>target</dt><dd>{{ searchFrame(block)!.target }}</dd>
              </dl>
              <p v-if="searchFrame(block)!.comparison">
                {{ searchFrame(block)!.phase === 'narrowed' ? '刚完成的比较' : '本轮比较' }}：
                {{ elements(block)[searchFrame(block)!.mid!]!.label }}
                {{ comparisons[searchFrame(block)!.comparison!] }}
                {{ searchFrame(block)!.target }}
              </p>
              <p v-if="searchFrame(block)!.phase === 'found'">返回下标 {{ searchFrame(block)!.mid }}</p>
              <ol class="visual-elements" aria-label="数组（从下标 0 开始）">
                <li
                  v-for="(element,i) in elements(block)"
                  :key="element.id"
                  :class="{'element-highlight':highlightedElement(block,element.id)}"
                >
                  <small>下标 {{ i }}{{ i === searchFrame(block)!.left ? ' · left' : '' }}{{ i === searchFrame(block)!.right ? ' · right' : '' }}{{ i === searchFrame(block)!.mid ? ' · mid' : '' }}</small>
                  <strong>{{ element.label }}</strong>
                  <small>{{ i >= searchFrame(block)!.left && i <= searchFrame(block)!.right ? '区间内' : '已排除' }}</small>
                </li>
              </ol>
            </div>
            <div v-else-if="orderedFrame(block)">
              <p>{{ orderedFrame(block)!.note }}</p>
              <p>本步{{ orderedCourse === 'queue' ? '出队' : '出栈' }}结果：{{ removedValue(orderedFrame(block)!) ?? '无' }}</p>
              <p v-if="!elements(block).length">
                {{ orderedCourse === 'queue' ? '队列为空，没有队头或队尾。' : '栈为空，没有栈顶。' }}
              </p>
              <ol
                v-else
                class="visual-elements"
                :class="`structure-${orderedCourse}`"
                :aria-label="orderedCourse === 'queue' ? '有效元素（从队头到队尾）' : '栈内容（从栈底到栈顶）'"
              >
                <li
                  v-for="(element,i) in elements(block)"
                  :key="element.id"
                  :class="{'element-highlight':highlightedElement(block,element.id)}"
                >
                  <small>下标 {{ i }}<template v-if="orderedCourse === 'queue'">
                    {{ i === 0 ? ' · 队头' : '' }}{{ i === elements(block).length - 1 ? ' · 队尾' : '' }}
                  </template><template v-else-if="highlightedElement(block,element.id)"> · 栈顶</template></small>
                  <strong>{{ element.label }}</strong>
                </li>
              </ol>
            </div>
          </div>
        </div>
        <ol
          v-else
          class="visual-elements"
          :class="`structure-${block.visualization_type}`"
          :aria-label="`${label(block)}当前状态`"
        >
          <li
            v-for="(element,i) in elements(block)"
            :key="element.id"
            :class="{'element-highlight':highlightedElement(block,element.id)}"
          >
            <small>{{ block.visualization_type==='array' ? `下标 ${i}` : `结点 ${element.id}` }}</small><strong>{{ element.label }}</strong><span v-if="block.visualization_type==='linked_list'">next → {{ element.next_id ?? 'NULL' }}</span><span v-if="highlightedElement(block,element.id)">当前关注</span>
          </li>
        </ol>
        <p v-if="!lineFrame(block) && !elements(block).length">
          当前结构为空。
        </p>
        <div
          v-if="!guided"
          class="action-row"
        >
          <button
            class="secondary"
            type="button"
            :disabled="(frames[block.anchor_id]??0)===0"
            @click="chooseFrame(block,-1)"
          >
            上一步
          </button><button
            class="secondary"
            type="button"
            :disabled="(frames[block.anchor_id]??0)>=block.steps.length-1"
            @click="chooseFrame(block,1)"
          >
            下一步
          </button>
        </div>
      </template>
      <p
        v-else
        role="status"
      >
        状态表示不可用，请对照文字说明与代码。
      </p>
    </section>
    <p>演示使用当前版本已有状态，不请求媒体或启动渲染；没有可用演示时仍可阅读正文。</p>
  </section>
</template>
