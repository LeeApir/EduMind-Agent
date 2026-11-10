import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Presentation from '../src/components/CoursePresentation.vue';
import type { BinarySearchFrame, SceneProjection } from '../src/api/freeCourses';
function scene(kind='linked_list'):SceneProjection{return{course_id:'c',course_version:1,scene_id:'s',scene_version_id:'sv',blocks:[{kind:'code',anchor_id:'code',language:'c',source:'head=n;'},{kind:'visualization',anchor_id:'vis',visualization_type:kind,text_alternative:'先连接，再更新head。',steps:[{caption:'初始',elements:[{id:'old',label:'3',next_id:null}],highlight_ids:[]},{caption:'新结点连接原链表',elements:[{id:'new',label:'8',next_id:'old'},{id:'old',label:'3',next_id:null}],highlight_ids:['new']}]}],actions:[{type:'highlight_block',anchor_id:'code',step_index:null},{type:'show_step',anchor_id:'vis',step_index:1},{type:'pause',anchor_id:'vis',step_index:null}]};}
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
async function button(w:ReturnType<typeof mount>,name:string){await w.findAll('button').find(b=>b.text()===name)!.trigger('click');}
describe('bounded scene presentation',()=>{
  it.each(['array','linked_list','stack','queue'])('renders real %s elements and bounded manual steps',async kind=>{
    const w=mount(Presentation,{props:{scene:scene(kind)}});expect(w.text()).toContain('先连接');expect(w.text()).toContain('非代码执行');
    await button(w,'下一步');expect(w.text()).toContain('新结点连接原链表');expect(w.findAll('.element-highlight')).toHaveLength(1);expect(w.findAll('.visual-elements li')).toHaveLength(2);
    await button(w,'上一步');expect(w.text()).toContain('步骤 1 / 2');expect(w.text()).not.toContain('运行代码');w.unmount();
  });
  it('accepts the explicit new-generation origin, binds frames to code and escapes model text',async()=>{
    const value:SceneProjection={course_id:'c',course_version:2,scene_id:'s',scene_version_id:'sv',generation_source:{origin:'head_goal_model_generation',batch:'PHASE-1.5-T108',candidate_digest:'a'.repeat(64),parent_digest:null,model:'deepseek-flash',prompt_version:'head-goal-course-v1',plan_digest:'b'.repeat(64),materials_digest:'c'.repeat(64),evidence_kind:'offline_fixture'},blocks:[{kind:'code',anchor_id:'code',language:'c',source:'line one\nline two'},{kind:'visualization',anchor_id:'vis',visualization_type:'head_insertion_replay_v1',text_alternative:'text',steps:[0,1].map(i=>({caption:'frame',head_frame:{frame_id:`f0${i}`,state_index:i,line:i+1,kind:'caller',fact_id:`trace_step_0${i}`,title:'frame',note:'<script>bad()</script>',code_anchor:'code',locals_scope:'inactive',state:{phase:'caller',attempt:0,caller_head:null,local_head:null,p:null,returned:null,nodes:{},code_line:i+1}}}))}],actions:[0,1].map(i=>({type:'show_step',anchor_id:'vis',step_index:i}))};
    const w=mount(Presentation,{props:{scene:value}});expect(w.find('.head-replay-frame').attributes('data-frame')).toBe('f00');expect(w.find('script').exists()).toBe(false);expect(w.text()).toContain('<script>bad()</script>');await button(w,'下一步');expect(w.find('.active-code-line').attributes('data-line')).toBe('2');await w.setProps({scene:{...value,generation_source:undefined}});expect(w.text()).toContain('状态表示不可用');w.unmount();
  });
  it('shows the fixed stack top and current pop result at each highlighted line',async()=>{
    vi.useFakeTimers();
    const values=[[],[3],[3,8],[3],[3,5]];
    const lines=[22,24,25,26,27];
    const code=Array.from({length:28},(_,i)=>`C line ${i+1}`).join('\n');
    const data:SceneProjection={
      ...scene(),generation_source:{origin:'stack_lifo_model_generation',batch:'stack-lifo-deepseek-r01',
        candidate_digest:'a'.repeat(64),parent_digest:null,model:'deepseek-flash',
        prompt_version:'stack-lifo-course-v1',plan_digest:'b'.repeat(64),
        materials_digest:'c'.repeat(64),evidence_kind:'offline_fixture'},
      blocks:[
        {kind:'code',anchor_id:'stack-code',language:'c',source:code},
        {kind:'visualization',anchor_id:'vis',visualization_type:'stack',
          text_alternative:'栈底到栈顶',steps:values.map((stack,i)=>({
            caption:`操作 ${i}`,
            elements:stack.map((value,j)=>({id:`slot-${j}`,label:String(value),next_id:null})),
            highlight_ids:stack.length?[`slot-${stack.length-1}`]:[],
            stack_frame:{frame_id:`f${i}`,code_anchor:'stack-code',line:lines[i]!,popped:i===3?8:null,note:`讲解 ${i}`},
          }))},
      ],
      actions:values.map((_,i)=>({type:'show_step',anchor_id:'vis',step_index:i})),
    };
    const w=mount(Presentation,{props:{scene:data}});
    for(const [i,stack] of values.entries()){
      expect(w.find('.active-code-line').attributes('data-line')).toBe(String(lines[i]));
      expect(w.findAll('.visual-elements strong').map(x=>Number(x.text()))).toEqual(stack);
      expect(w.text()).toContain(`本步出栈结果：${i===3?8:'无'}`);
      expect(w.find('.element-highlight strong').exists()?Number(w.find('.element-highlight strong').text()):null)
        .toBe(stack.at(-1)??null);
      if(i<4)await button(w,'下一步');
    }
    await button(w,'上一步');
    expect(w.text()).toContain('本步出栈结果：8');
    await button(w,'重置');
    expect(w.text()).toContain('栈为空，没有栈顶');
    await button(w,'播放');await button(w,'暂停');
    await vi.advanceTimersByTimeAsync(2400);
    expect(w.find('.active-code-line').attributes('data-line')).toBe('24');
    await w.setProps({scene:{...data,generation_source:undefined}});
    expect(w.text()).toContain('状态表示不可用');
    w.unmount();
  });
  it('distinguishes the queue ends and removed value across all five frames',async()=>{
    const values=[[],[3],[3,8],[8],[8,5]];
    const lines=[24,26,27,28,29];
    const data:SceneProjection={
      ...scene(), generation_source:{
        origin:'queue_fifo_model_generation', batch:'queue-fifo-deepseek-r01',
        candidate_digest:'a'.repeat(64), parent_digest:null, model:'deepseek-flash',
        prompt_version:'queue-fifo-course-v1', plan_digest:'b'.repeat(64),
        materials_digest:'c'.repeat(64), evidence_kind:'offline_fixture',
      },
      blocks:[
        {kind:'code',anchor_id:'queue-code',language:'c',source:Array(30).fill('C line').join('\n')},
        {kind:'visualization',anchor_id:'queue-state',visualization_type:'queue',
          text_alternative:'有效元素从队头到队尾',steps:values.map((active,i)=>({
            caption:`操作 ${i}`,
            elements:active.map((value,j)=>({id:`slot-${j}`,label:String(value),next_id:null})),
            highlight_ids:active.map((_,j)=>`slot-${j}`),
            queue_frame:{frame_id:`f${i}`,code_anchor:'queue-code',line:lines[i]!,dequeued:i===3?3:null,note:`讲解 ${i}`},
          }))},
      ],
      actions:values.map((_,i)=>({type:'show_step',anchor_id:'queue-state',step_index:i})),
    };
    const w=mount(Presentation,{props:{scene:data}});
    for(const [i,active] of values.entries()){
      expect(w.find('.active-code-line').attributes('data-line')).toBe(String(lines[i]));
      expect(w.text()).toContain(`本步出队结果：${i===3?3:'无'}`);
      const items=w.findAll('.visual-elements li');
      expect(items.map(item=>Number(item.get('strong').text()))).toEqual(active);
      if(items.length){
        expect(items[0]!.get('small').text()).toContain('队头');
        expect(items.at(-1)!.get('small').text()).toContain('队尾');
      }else{
        expect(w.text()).toContain('队列为空，没有队头或队尾');
      }
      if(i<4)await button(w,'下一步');
    }
    await button(w,'上一步');
    expect(w.text()).toContain('本步出队结果：3');
    await button(w,'重置');
    expect(w.find('.active-code-line').attributes('data-line')).toBe('24');
    w.unmount();
  });
  it('shows the updated binary-search interval and keeps the just-used midpoint distinct', async () => {
    const tuples = [
      ['initial', 4, 0, 4, null, null], ['compare', 10, 0, 4, 2, 'greater'],
      ['narrowed', 13, 0, 1, 2, 'greater'], ['compare', 10, 0, 1, 0, 'less'],
      ['narrowed', 11, 1, 1, 0, 'less'], ['found', 8, 1, 1, 1, 'equal'],
    ] as const;
    const steps = tuples.map(([phase, line, left, right, mid, comparison], i) => {
      const frame: BinarySearchFrame = {
        frame_id: `f${i}`, code_anchor: 'binary-search-code', note: `帧 ${i}`,
        phase, line, left, right, mid, comparison, target: 5,
      };
      return {
        caption: `帧 ${i}`, binary_search_frame: frame,
        elements: [2, 5, 8, 12, 16].map((n, j) => ({ id: `index-${j}`, label: String(n), next_id: null })),
        highlight_ids: mid === null ? [] : [`index-${mid}`],
      };
    });
    const data: SceneProjection = {
      ...scene(), generation_source: {
        origin: 'binary_search_model_generation', batch: 'binary-search-deepseek-r01',
        candidate_digest: 'a'.repeat(64), parent_digest: null, model: 'deepseek-flash',
        prompt_version: 'binary-search-course-v1', plan_digest: 'b'.repeat(64),
        materials_digest: 'c'.repeat(64), evidence_kind: 'offline_fixture',
      },
      blocks: [
        { kind: 'code', anchor_id: 'binary-search-code', language: 'c', source: Array(17).fill('C').join('\n') },
        { kind: 'visualization', anchor_id: 'binary-search-state', visualization_type: 'binary-search',
          text_alternative: '固定闭区间', steps },
      ],
      actions: steps.map((_, i) => ({ type: 'show_step', anchor_id: 'binary-search-state', step_index: i })),
    };
    const w = mount(Presentation, { props: { scene: data } });
    expect(w.text()).toContain('未计算');
    for (const [i, [, line, left, right, mid]] of tuples.entries()) {
      expect(w.get('.active-code-line').attributes('data-line')).toBe(String(line));
      const cells = w.findAll('.visual-elements li');
      expect(cells[left]!.text()).toContain('left');
      expect(cells[right]!.text()).toContain('right');
      if (mid !== null) {
        expect(cells[mid]!.classes()).toContain('element-highlight');
        expect(cells[mid]!.text()).toContain(mid >= left && mid <= right ? '区间内' : '已排除');
      }
      if (i < 5) await button(w, '下一步');
    }
    expect(w.text()).toContain('返回下标 1');
    const wrong = structuredClone(data);
    const visual = wrong.blocks[1];
    if (visual?.kind === 'visualization') visual.steps[2]!.binary_search_frame!.right = 4;
    await w.setProps({ scene: wrong });
    expect(w.text()).toContain('状态表示不可用');
    w.unmount();
  });
  it('uses actual anchors for block highlight and pauses at explicit pause/last action',async()=>{
    vi.useFakeTimers();const w=mount(Presentation,{props:{scene:scene()}});await button(w,'播放动作');expect(w.emitted('highlight')?.at(-1)).toEqual(['code']);await vi.advanceTimersByTimeAsync(1200);expect(w.text()).toContain('步骤 2 / 2');await vi.advanceTimersByTimeAsync(1200);expect(w.text()).toContain('动作 3 / 3');expect(w.findAll('button').find(b=>b.text()==='暂停动作')!.attributes('disabled')).toBeDefined();expect(vi.getTimerCount()).toBe(0);w.unmount();
  });
  it('falls back without executing unknown or out-of-bounds actions',async()=>{
    const invalid=scene();invalid.actions=[{type:'eval',anchor_id:'code',step_index:null,source:'alert(1)'}];const w=mount(Presentation,{props:{scene:invalid}});expect(w.text()).toContain('动作或定位已失效');expect(w.text()).toContain('先连接');expect(w.findAll('button').some(b=>b.text()==='播放动作')).toBe(false);
    const bad=scene();bad.actions=[{type:'show_step',anchor_id:'vis',step_index:8}];await w.setProps({scene:bad});expect(w.text()).toContain('动作或定位已失效');w.unmount();
  });
  it('honors reduced motion and clears timers on scene/version change, leave and unmount',async()=>{
    vi.useFakeTimers();let change:(()=>void)|undefined;const media={matches:false,addEventListener:(_t:string,f:()=>void)=>{change=f;},removeEventListener:vi.fn()};vi.stubGlobal('matchMedia',()=>media);
    const w=mount(Presentation,{props:{scene:scene()}});await button(w,'播放动作');expect(vi.getTimerCount()).toBe(1);media.matches=true;change?.();await w.vm.$nextTick();expect(w.text()).toContain('减少动效');expect(vi.getTimerCount()).toBe(0);await button(w,'下一动作');expect(w.text()).toContain('步骤 2 / 2');
    media.matches=false;change?.();await w.setProps({scene:{...scene(),course_version:2,scene_version_id:'v2'}});expect(w.text()).toContain('动作 0 / 3');await button(w,'播放动作');await w.setProps({active:false});expect(vi.getTimerCount()).toBe(0);w.unmount();expect(media.removeEventListener).toHaveBeenCalled();
  });
  it('keeps escaped text and falls back when element references are corrupt',()=>{
    const source=scene();const visual=source.blocks[1];if(visual?.kind==='visualization')visual.steps[0]!.elements=[{id:'x',label:'<img onerror=bad()>',next_id:'missing'}];
    const w=mount(Presentation,{props:{scene:source}});expect(w.text()).toContain('状态表示不可用');expect(w.find('img').exists()).toBe(false);w.unmount();
  });
});
