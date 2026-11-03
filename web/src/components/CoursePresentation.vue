<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { SceneProjection, SceneBlock, HeadReplayFrame } from '../api/freeCourses';
const props = withDefaults(defineProps<{scene: SceneProjection; active?: boolean}>(),{active:true});
const emit = defineEmits<{highlight:[anchor:string]}>();
type Visual = Extract<SceneBlock,{kind:'visualization'}>;
interface Element {id:string;label:string;next_id:string|null}
interface Action {type:'highlight_block'|'show_step'|'pause';anchor_id:string;step_index:number|null}
const index = ref(-1);const playing = ref(false);const reduced = ref(false);const frames = ref<Record<string,number>>({});const highlighted = ref('');
let timer: ReturnType<typeof setTimeout>|undefined;let media: MediaQueryList|undefined;
const visuals = computed(()=>props.scene.blocks.filter((b):b is Visual=>b.kind==='visualization'));
const replay = computed(()=>visuals.value.find(b=>b.visualization_type==='head_insertion_replay_v1'));
function validVisual(block: Visual): boolean {
  if(block.visualization_type==='head_insertion_replay_v1')return Boolean(props.scene.replay_source)&&Array.isArray(block.steps)&&block.steps.length>0&&block.steps.length<=13&&block.steps.every((s,i)=>{
    const f=s.head_frame;const code=props.scene.blocks.find(b=>b.anchor_id===f?.code_anchor&&b.kind==='code');
    return f&&f.frame_id===`f${String(i).padStart(2,'0')}`&&typeof f.title==='string'&&typeof f.note==='string'&&f.state&&typeof f.state.nodes==='object'&&code?.kind==='code'&&(f.line===null||Number.isInteger(f.line)&&f.line>0&&f.line<=code.source.trimEnd().split('\n').length)&&['active','inactive'].includes(f.locals_scope);
  });
  if(!['array','linked_list','stack','queue'].includes(block.visualization_type)||!Array.isArray(block.steps)||!block.steps.length||block.steps.length>50)return false;
  return block.steps.every(s=>{
    if(typeof s.caption!=='string'||!Array.isArray(s.elements)||s.elements.length>32||!Array.isArray(s.highlight_ids))return false;
    const elements=s.elements as Element[];
    if(!elements.every(e=>e&&typeof e.id==='string'&&typeof e.label==='string'&&(e.next_id===null||typeof e.next_id==='string')))return false;
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
  index.value=Math.max(replay.value?0:-1,Math.min(target,actions.value.length-1));frames.value={};highlighted.value='';
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
function headFrame(block:Visual):HeadReplayFrame|undefined{return validVisual(block)?block.steps[frames.value[block.anchor_id]??0]?.head_frame:undefined;}
function replayCode(frame:HeadReplayFrame):string{const code=props.scene.blocks.find(b=>b.kind==='code'&&b.anchor_id===frame.code_anchor);return code?.kind==='code'?code.source:'';}
function pointer(value:string|null|undefined):string{return value===null?'NULL':value==='indeterminate'?'未知（未初始化）':value??'';}
function chain(frame:HeadReplayFrame):string{let id=frame.state.caller_head;const parts:string[]=[];const seen=new Set<string>();while(id!==null){if(id==='indeterminate'||seen.has(id)||!frame.state.nodes[id]){parts.push('未知或重复');return parts.join(' → ');}seen.add(id);parts.push(`${id}(${frame.state.nodes[id]!.data})`);id=frame.state.nodes[id]!.next;}parts.push('NULL');return parts.join(' → ');}
function elements(block:Visual): Element[] {return validVisual(block)?block.steps[frames.value[block.anchor_id]??0]!.elements as Element[]:[];}
function highlightedElement(block:Visual,id:string):boolean{return validVisual(block)&&block.steps[frames.value[block.anchor_id]??0]!.highlight_ids?.includes(id)===true;}
function label(block:Visual):string{return ({array:'数组',linked_list:'链表',stack:'栈',queue:'队列',head_insertion_replay_v1:'链表'} as Record<string,string>)[block.visualization_type]??'状态';}
function motionChanged():void{reduced.value=media?.matches??false;if(reduced.value)stop();}
function visibilityChanged():void{if(document.hidden)stop();}
watch(()=>props.scene,()=>{stop();index.value=replay.value?0:-1;frames.value={};highlighted.value='';emit('highlight','');},{immediate:true});
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
        {{ replay ? '播放':'播放动作' }}
      </button><button
        class="secondary"
        type="button"
        :disabled="!playing"
        @click="stop"
      >
        {{ replay ? '暂停':'暂停动作' }}
      </button><button
        class="secondary"
        type="button"
        :disabled="replay ? index <= 0 : index < 0"
        @click="apply(index-1)"
      >
        {{ replay ? '上一步':'上一动作' }}
      </button><button
        class="secondary"
        type="button"
        :disabled="index >= actions.length-1"
        @click="apply(index+1)"
      >
        {{ replay ? '下一步':'下一动作' }}
      </button><button
        v-if="replay"
        type="button"
        class="secondary"
        @click="apply(0)"
      >
        重置
      </button><span role="status">{{ replay ? '步骤':'动作' }} {{ index+1 }} / {{ actions.length }}</span>
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
          v-if="headFrame(block)"
          class="head-replay-frame"
          :data-frame="headFrame(block)!.frame_id"
        >
          <div class="head-replay-grid">
            <pre
              class="head-replay-code"
              tabindex="0"
              aria-label="逐行 C 语言代码"
            ><code><span
              v-for="(line,i) in replayCode(headFrame(block)!).trimEnd().split('\n')"
              :key="i"
              class="course-code-line"
              :class="{'active-code-line':headFrame(block)!.line===i+1}"
              :data-line="i+1"
            >{{ i+1 }}  {{ line }}</span></code></pre><div>
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
        <p v-if="!headFrame(block) && !elements(block).length">
          当前结构为空。
        </p>
        <div
          v-if="!replay"
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
