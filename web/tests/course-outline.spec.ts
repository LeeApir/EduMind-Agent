import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import Outline from '../src/components/CourseOutline.vue';
const fixture = vi.hoisted(() => ({ ready: false, state: 'running', posts: [] as {path:string;init:RequestInit}[], unknown:false }));
vi.mock('../src/api/catalog', () => ({ ensureCatalogSession: vi.fn(async () => ({owner:'owner',csrf:'csrf'})) }));
class Stream {
  static instances: Stream[]=[]; closed=false; listeners=new Map<string,EventListener>(); onerror: (()=>void)|null=null;
  constructor(readonly url:string) {Stream.instances.push(this);}
  addEventListener(name:string, callback:EventListener):void{this.listeners.set(name,callback);}
  close():void{this.closed=true;}
  send(type='scene_ready', seq=2):void{this.listeners.get(type)?.(new MessageEvent(type,{data:JSON.stringify({schema_version:'free-course-events-v1',operation_id:'op',seq,type})}));}
}
function course() { return {course_id:'c',original_goal:'原始目标',course_kind:'ai_draft',endorsement:'unendorsed',teaching_language:'zh-CN',code_language:'c',head:{course_id:'c',version:1,plan_id:'p',created_at:'',complete:false,node_links:[],scenes:[{scene_id:'s',title:'第一场景',scene_version_id:fixture.ready?'sv':null}]}}; }
function operation(){return {course_id:'c',operation_id:'op',state:fixture.state,kind:'create',last_event_id:1,head_version:1,base_head_version:null,clarification_questions:fixture.state==='awaiting_clarification'?['你希望理解哪种操作？']:[],reason_code:fixture.unknown?'OUTCOME_UNKNOWN':null,steps:[],budget:{attempts_used:1,attempts_remaining:12,usage_unknown:fixture.unknown}};}
beforeEach(()=>{
  fixture.ready=false;fixture.state='running';fixture.posts=[];fixture.unknown=false;Stream.instances=[];sessionStorage.clear();
  vi.stubGlobal('EventSource',Stream);vi.stubGlobal('fetch',vi.fn(async(path:string,init:RequestInit={})=>{
    if(init.method==='POST'){fixture.posts.push({path,init});if(path.endsWith('/cancel')){fixture.state='cancelled';return new Response(JSON.stringify(operation()));}return new Response(JSON.stringify({course_id:'c',operation_id:'op-new'}));}
    return new Response(JSON.stringify(path.includes('/impact?')?{course_id:'c',base_head_version:1,kind:'adjust_outline',affected_scene_ids:['s'],requires_outline_adjustment:true,max_attempts:13,max_seconds:600,impact_digest:'a'.repeat(64)}:path.includes('/operations/')?operation():course()));
  }));
});
afterEach(()=>vi.unstubAllGlobals());
describe('durable course outline',()=>{
  it('loads only GET, tolerates no graph links, and enters when first complete scene arrives',async()=>{
    const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();expect(fixture.posts).toHaveLength(0);expect(w.text()).toContain('原始目标');expect(w.emitted('learn')).toBeUndefined();
    fixture.ready=true;Stream.instances[0]!.send();await flushPromises();expect(w.emitted('learn')?.[0]).toEqual([1,'s']);w.unmount();expect(Stream.instances[0]!.closed).toBe(true);
  });
  it('stays in management when reopened from history, while keeping a readable scene entry',async()=>{
    fixture.ready=true;const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic',autoEnter:false}});await flushPromises();expect(w.emitted('learn')).toBeUndefined();expect(w.text()).toContain('第一场景');expect(fixture.posts).toHaveLength(0);w.unmount();
  });
  it('keeps adjustment text and suppresses automatic navigation while editing; cancel is explicit',async()=>{
    const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();await w.findAll('button').find(b=>b.text()==='调整大纲')!.trigger('click');await flushPromises();
    await w.get('#outline-instruction').setValue('增加基础说明');fixture.ready=true;Stream.instances[0]!.send();await flushPromises();expect(w.emitted('learn')).toBeUndefined();expect(fixture.posts).toHaveLength(0);
    await w.findAll('button').find(b=>b.text()==='停止当前生成')!.trigger('click');await flushPromises();expect(fixture.posts[0]!.path).toContain('/op/cancel');
    await w.get('input[type=checkbox]').setValue(true);await w.get('form').trigger('submit');await flushPromises();
    expect(JSON.parse(String(fixture.posts[1]!.init.body))).toEqual({kind:'adjust_outline',expected_head_version:1,instruction:'增加基础说明',impact_digest:'a'.repeat(64)});expect(w.emitted('operation')?.[0]).toEqual(['op-new']);w.unmount();
  });
  it('asks only actual clarification; blocks unknown transport and catalog-only new operations',async()=>{
    fixture.state='awaiting_clarification';const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();expect(w.get('#clarification').exists()).toBe(true);expect(Stream.instances).toHaveLength(0);
    await w.get('#clarification').setValue('头插');await w.get('form').trigger('submit');await flushPromises();expect(JSON.parse(String(fixture.posts[0]!.init.body)).kind).toBe('clarify');w.unmount();
    fixture.state='failed';fixture.unknown=true;fixture.posts=[];const unknown=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();expect(unknown.text()).toContain('后续发送已暂停');expect(unknown.findAll('button').some(b=>b.text()==='确认继续缺失内容')).toBe(false);unknown.unmount();
  });
  it('refreshes same operation without POST; ignores late events after leaving',async()=>{
    let w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();const old=Stream.instances[0]!;w.unmount();fixture.ready=true;old.send();await flushPromises();expect(w.emitted('learn')).toBeUndefined();
    w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'catalog_only'}});await flushPromises();expect(fixture.posts).toHaveLength(0);expect(w.emitted('learn')?.[0]).toEqual([1,'s']);w.unmount();
  });
  it('restores an in-progress outline edit across refresh without auto entering',async()=>{
    sessionStorage.setItem('edumind:free:outline-edit:owner:c',JSON.stringify({editing:true,instruction:'保留修改意图'})); fixture.ready=true;
    const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();
    expect((w.get('#outline-instruction').element as HTMLTextAreaElement).value).toBe('保留修改意图');expect(w.emitted('learn')).toBeUndefined();
    Stream.instances[0]!.listeners.get('error')?.(new Event('error'));await flushPromises();expect(w.text()).not.toContain('进度事件无效');w.unmount();
  });
  it('requires explicit new-operation consent to resume missing content',async()=>{
    fixture.state='cancelled';const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic'}});await flushPromises();
    expect(fixture.posts).toHaveLength(0);await w.get('input[type=checkbox]').setValue(true);await w.findAll('button').find(b=>b.text()==='确认继续缺失内容')!.trigger('click');await flushPromises();expect(JSON.parse(String(fixture.posts[0]!.init.body))).toEqual({kind:'resume',expected_head_version:1,source_operation_id:'op'});w.unmount();
  });
});
