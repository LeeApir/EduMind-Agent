import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Presentation from '../src/components/CoursePresentation.vue';
import type { SceneProjection } from '../src/api/freeCourses';
function scene(kind='linked_list'):SceneProjection{return{course_id:'c',course_version:1,scene_id:'s',scene_version_id:'sv',blocks:[{kind:'code',anchor_id:'code',language:'c',source:'head=n;'},{kind:'visualization',anchor_id:'vis',visualization_type:kind,text_alternative:'先连接，再更新head。',steps:[{caption:'初始',elements:[{id:'old',label:'3',next_id:null}],highlight_ids:[]},{caption:'新结点连接原链表',elements:[{id:'new',label:'8',next_id:'old'},{id:'old',label:'3',next_id:null}],highlight_ids:['new']}]}],actions:[{type:'highlight_block',anchor_id:'code',step_index:null},{type:'show_step',anchor_id:'vis',step_index:1},{type:'pause',anchor_id:'vis',step_index:null}]};}
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
async function button(w:ReturnType<typeof mount>,name:string){await w.findAll('button').find(b=>b.text()===name)!.trigger('click');}
describe('bounded scene presentation',()=>{
  it.each(['array','linked_list','stack','queue'])('renders real %s elements and bounded manual steps',async kind=>{
    const w=mount(Presentation,{props:{scene:scene(kind)}});expect(w.text()).toContain('先连接');expect(w.text()).toContain('非代码执行');
    await button(w,'下一步');expect(w.text()).toContain('新结点连接原链表');expect(w.findAll('.element-highlight')).toHaveLength(1);expect(w.findAll('.visual-elements li')).toHaveLength(2);
    await button(w,'上一步');expect(w.text()).toContain('步骤 1 / 2');expect(w.text()).not.toContain('运行代码');w.unmount();
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
