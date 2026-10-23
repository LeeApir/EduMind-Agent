import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Workspace from '../src/components/CourseWorkspace.vue';
const fixture=vi.hoisted(()=>({head:1,revision:false,unavailable:false,reads:[] as string[],posts:0,owner:'owner',delayed:null as null|((value:Response)=>void)}));
vi.mock('../src/api/catalog',()=>({ensureCatalogSession:vi.fn(async()=>({owner:fixture.owner,csrf:'csrf'}))}));
class Stream{static instances:Stream[]=[];closed=false;listeners=new Map<string,EventListener>();onerror:(()=>void)|null=null;constructor(readonly url:string){Stream.instances.push(this);}addEventListener(t:string,f:EventListener){this.listeners.set(t,f);}close(){this.closed=true;}send(seq=2){this.listeners.get('scene_ready')?.(new MessageEvent('scene_ready',{data:JSON.stringify({schema_version:'free-course-events-v1',operation_id:'op',seq,type:'scene_ready'})}));}}
function manifest(version:number,course='c'){return{course_id:course,version,plan_id:fixture.revision&&version===3?'new-plan':'p',created_at:'',complete:false,node_links:[],scenes:[{scene_id:'s1',title:'第一节',scene_version_id:fixture.revision&&version===3?'rev':'sv1'},{scene_id:'s2',title:'第二节',scene_version_id:version>=2?'sv2':null},{scene_id:'s3',title:'第三节失败',scene_version_id:null}]};}
function projection(course='c',version=1,sid='s1'){return{course_id:course,course_version:version,scene_id:sid,scene_version_id:sid==='s1'?'sv1':'sv2',blocks:[{kind:'text',anchor_id:'a',markdown:sid==='s1'?'旧版第一节讲解':'第二节新增讲解'},{kind:'code',anchor_id:'c',language:'c',source:'<script>bad()</script>'},{kind:'exercise_unavailable',anchor_id:'e',exercise_id:'e',exercise_version_id:'ev',reason_code:'EXERCISE_UNAVAILABLE'}],actions:[]};}
function json(value:unknown,status=200){return new Response(JSON.stringify(value),{status});}
beforeEach(()=>{
  fixture.head=1;fixture.revision=false;fixture.unavailable=false;fixture.reads=[];fixture.posts=0;fixture.owner='owner';fixture.delayed=null;Stream.instances=[];sessionStorage.clear();vi.stubGlobal('EventSource',Stream);vi.spyOn(window,'scrollTo').mockImplementation(()=>{});
  vi.stubGlobal('fetch',vi.fn(async(path:string,init:RequestInit={})=>{
    fixture.reads.push(path);if(init.method==='POST')fixture.posts+=1;const course=path.includes('/other')?'other':'c';
    if(path.includes('/operations/'))return json({course_id:course,operation_id:'op',state:'running',kind:'create',last_event_id:1,clarification_questions:[],steps:[{step_key:'s3',scene_id:'s3',state:'failed',reason_code:'SCHEMA_INVALID'}],budget:{}});
    const match=path.match(/\/versions\/(\d+)(?:\/scenes\/([^?]+))?/);
    if(match){const v=Number(match[1]);const sid=match[2];if(v===99)return json({code:'NOT_FOUND'},404);if(sid){if(fixture.unavailable)return json({code:'CONTENT_UNAVAILABLE'},409);if(sid==='s2'&&fixture.delayed)return await new Promise<Response>(resolve=>{fixture.delayed=resolve;});return json(projection(course,v,sid));}return json(manifest(v,course));}
    if(path.includes('/versions?'))return json({items:[{version:99,created_at:''},{version:2,created_at:''},{version:1,created_at:''}],next_cursor:null});
    return json({course_id:course,original_goal:course==='c'?'我的自由目标':'另一课程',course_kind:'ai_draft',endorsement:'unendorsed',head:manifest(fixture.head,course)});
  }));
});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});
const props={courseId:'c',operationId:'op',initialVersion:1,initialScene:'s1'};
async function click(w:ReturnType<typeof mount>,label:string){await w.findAll('button').find(b=>b.text()===label)!.trigger('click');await flushPromises();}
describe('progressive course workspace',()=>{
  it('separates course type, generation and local reading; keeps ready content beside failed/waiting scenes',async()=>{
    const w=mount(Workspace,{props});await flushPromises();expect(w.text()).toContain('未签核');expect(w.text()).toContain('旧版第一节讲解');expect(w.text()).toContain('生成失败');expect(w.text()).toContain('等待生成');expect(w.text()).toContain('本机已查看 1 / 3');expect(w.find('script').exists()).toBe(false);expect(fixture.posts).toBe(0);
    await w.get('nav button:nth-child(3)').trigger('click');await flushPromises();expect(w.text()).toContain('此处不会自动重试生成');await w.get('nav button:first-child').trigger('click');await flushPromises();expect(w.text()).toContain('旧版第一节讲解');w.unmount();
  });
  it('adopts ready additions keeping the scene, but never silently replaces a revision',async()=>{
    const w=mount(Workspace,{props});await flushPromises();fixture.head=2;Stream.instances[0]!.send();await flushPromises();expect(w.text()).toContain('阅读版本 v2');expect(w.get('nav button:first-child').attributes('aria-current')).toBe('step');
    await w.get('nav button:nth-child(2)').trigger('click');await flushPromises();expect(w.text()).toContain('第二节新增讲解');
    fixture.head=3;fixture.revision=true;Stream.instances[0]!.send(3);await flushPromises();expect(w.text()).toContain('阅读版本 v2');expect(w.text()).toContain('有修订版本可读取');w.unmount();
  });
  it('pins exact history, failed version never falls back, retry keeps target version',async()=>{
    fixture.head=2;const w=mount(Workspace,{props:{...props,initialVersion:2,initialScene:'s2'}});await flushPromises();await click(w,'查看课程版本');await click(w,'读取 v1');expect(w.text()).toContain('阅读版本 v1');
    await click(w,'读取 v99');expect(w.text()).toContain('此版本已不可用');const count=fixture.reads.length;await click(w,'重新读取');expect(fixture.reads.slice(count)).toContain('/api/free-courses/c/versions/99');expect(w.text()).not.toContain('旧版第一节讲解');w.unmount();
  });
  it('ignores late scene results and aborts wait on course switch/unmount',async()=>{
    fixture.head=2;const w=mount(Workspace,{props:{...props,initialVersion:2}});await flushPromises();fixture.delayed=()=>{};await w.get('nav button:nth-child(2)').trigger('click');await flushPromises();const resolve=fixture.delayed!;const old=Stream.instances[0]!;
    await w.setProps({courseId:'other',initialVersion:2,initialScene:'s1'});await flushPromises();resolve(json(projection('c',2,'s2')));old.send();await flushPromises();expect(w.text()).toContain('另一课程');expect(w.text()).not.toContain('第二节新增讲解');expect(old.closed).toBe(true);
    w.unmount();expect(Stream.instances.at(-1)!.closed).toBe(true);expect(fixture.posts).toBe(0);
  });
  it('restores exact reading position and keeps a local tutor question without sending',async()=>{
    sessionStorage.setItem('edumind:free:reading:owner:c',JSON.stringify({version:2,scene:'s2',following:false,scroll:123,visited:['s1'],tutorQuestion:'为什么先改next？'}));fixture.head=2;
    const w=mount(Workspace,{props:{...props,initialVersion:2,initialScene:'s2'},attachTo:document.body});await flushPromises();expect(w.text()).toContain('第二节新增讲解');expect(window.scrollTo).toHaveBeenCalledWith({top:123,behavior:'instant'});
    await click(w,'有疑问？打开导师区域');expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('为什么先改next？');expect(w.text()).toContain('导师发送尚未接入');await w.get('textarea').setValue('保存草稿');await click(w,'关闭导师');expect(document.activeElement?.textContent).toContain('有疑问');expect(fixture.posts).toBe(0);w.unmount();
    const saved=JSON.parse(sessionStorage.getItem('edumind:free:reading:owner:c')!);expect(saved.version).toBe(2);expect(saved.scene).toBe('s2');expect(saved.tutorQuestion).toBe('保存草稿');
  });
  it('does not substitute a missing saved scene, and drops content when owner changes',async()=>{
    const missing=mount(Workspace,{props:{...props,initialScene:'gone'}});await flushPromises();expect(missing.text()).toContain('不会自动替换阅读位置');expect(missing.text()).not.toContain('旧版第一节讲解');missing.unmount();
    const w=mount(Workspace,{props});await flushPromises();expect(w.text()).toContain('旧版第一节讲解');fixture.owner='other';await click(w,'重新读取生成状态');expect(w.text()).not.toContain('旧版第一节讲解');expect(w.text()).toContain('学习身份已变化');w.unmount();
  });
  it('removes unavailable scene text and permits another unaffected scene',async()=>{
    fixture.head=2;const w=mount(Workspace,{props:{...props,initialVersion:2}});await flushPromises();fixture.unavailable=true;await click(w,'重新读取生成状态');expect(w.text()).not.toContain('旧版第一节讲解');await w.get('nav button:nth-child(2)').trigger('click');await flushPromises();expect(w.text()).toContain('此版本已不可用');expect(w.text()).not.toContain('第二节新增讲解');fixture.unavailable=false;await w.get('nav button:first-child').trigger('click');await flushPromises();expect(w.text()).toContain('旧版第一节讲解');w.unmount();
  });
});
