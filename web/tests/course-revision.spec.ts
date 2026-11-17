import { mount,flushPromises } from '@vue/test-utils';
import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest';
import Feedback from '../src/components/CourseFeedback.vue';
import Revision from '../src/components/CourseRevision.vue';
import type { SceneBlock } from '../src/api/freeCourses';
const fixture=vi.hoisted(()=>({owner:'owner',posts:[] as {path:string;init:RequestInit}[],feedback:'pending',operation:'queued',head:1,fail:false}));
vi.mock('../src/api/catalog',()=>({ensureCatalogSession:vi.fn(async()=>({owner:fixture.owner,csrf:'csrf'}))}));
class Stream{static instances:Stream[]=[];closed=false;listeners=new Map<string,EventListener>();onerror:((e:Event)=>void)|null=null;constructor(readonly url:string){Stream.instances.push(this);}addEventListener(t:string,f:EventListener){this.listeners.set(t,f);}close(){this.closed=true;}send(seq=2){this.listeners.get('progress')?.(new MessageEvent('progress',{data:JSON.stringify({schema_version:'free-course-events-v1',operation_id:'rev',seq,type:'progress'})}));}}
const binding={courseId:'c',courseVersion:1,sceneId:'s',sceneVersionId:'sv'};
const blocks:SceneBlock[]=[{kind:'text',anchor_id:'intro',markdown:'正文'},{kind:'exercise',anchor_id:'quiz',exercise_id:'e',exercise_version_id:'ev',question:'题组',items:[{question_id:'q1',question:'第一个题目',input_type:'short_text'},{question_id:'q2',question:'第二个题目',input_type:'short_text'}]}];
const props={...binding,headVersion:1,mode:'dynamic' as const,generationActive:false,sceneTitles:{s:'当前场景',s2:'下游场景'}};
function json(value:unknown){return new Response(JSON.stringify(value));}
beforeEach(()=>{sessionStorage.clear();fixture.owner='owner';fixture.posts=[];fixture.feedback='pending';fixture.operation='queued';fixture.head=1;fixture.fail=false;Stream.instances=[];vi.stubGlobal('EventSource',Stream);
  vi.stubGlobal('fetch',vi.fn(async(path:string,init:RequestInit={})=>{
    if(init.method==='POST'){fixture.posts.push({path,init});if(fixture.fail)throw new Error('网络结果未确认');if(path.includes('/feedback'))return json({feedback_id:'f'});if(path.endsWith('/cancel')){fixture.operation='cancelled';return json({state:'cancel_requested'});}return json({course_id:'c',operation_id:'rev'});}
    if(path.includes('/feedback/'))return json({feedback_id:'f',binding:{course_version:1,scene_id:'s',scene_version_id:'sv'},anchor_id:'quiz',description:'题目[q1]：这里可能有误',status:fixture.feedback,reason_code:null});
    if(path.includes('/impact?'))return json({course_id:'c',base_head_version:1,kind:'revise_scene',affected_scene_ids:['s','s2'],requires_outline_adjustment:false,max_attempts:13,max_seconds:600,impact_digest:'a'.repeat(64)});
    if(path.includes('/operations/'))return json({course_id:'c',operation_id:'rev',kind:'revise_scene',state:fixture.operation,last_event_id:fixture.operation==='queued'?1:3,clarification_questions:[],steps:[{scene_id:'s2',step_key:'scene:s2',state:'pending',reason_code:null}],budget:{usage_unknown:false}});
    return json({course_id:'c',original_goal:'原目标',course_kind:'ai_draft',endorsement:'unendorsed',head:{course_id:'c',version:fixture.head,plan_id:'p',complete:false,node_links:[],scenes:[{scene_id:'s',title:'当前场景',scene_version_id:'sv'}]}});
  }));
});afterEach(()=>vi.unstubAllGlobals());
async function click(w:ReturnType<typeof mount>,label:string){await w.findAll('button').find(b=>b.text()===label)!.trigger('click');await flushPromises();}
async function prepare(w:ReturnType<typeof mount>){await click(w,'准备局部修订');await w.get('textarea').setValue('更清楚地说明指针');await w.get('input[type=checkbox]').setValue(true);}
describe('bound content feedback and atomic revision UI',()=>{
  it('reports an exact question as pending, refreshes authoritative confirmation without a model call',async()=>{
    const w=mount(Feedback,{props:{...binding,blocks}});await flushPromises();await w.get('select').setValue(JSON.stringify(['quiz','q1']));await w.get('textarea').setValue('这里可能有误');await w.get('form').trigger('submit');await flushPromises();
    expect(JSON.parse(String(fixture.posts[0]!.init.body))).toEqual({course_version:1,scene_id:'s',scene_version_id:'sv',anchor_id:'quiz',exercise_id:'e',exercise_version_id:'ev',description:'题目[q1]：这里可能有误'});expect(w.text()).toContain('已提交 · 待核对');fixture.feedback='confirmed';await click(w,'读取反馈处置');expect(w.text()).toContain('已确认 · 按规则处置');expect(w.emitted('confirmed')).toHaveLength(1);expect(fixture.posts).toHaveLength(1);w.unmount();
  });
  it('retains original feedback request across failure/refresh and does not duplicate submission',async()=>{
    fixture.fail=true;let w=mount(Feedback,{props:{...binding,blocks}});await flushPromises();await w.get('textarea').setValue('保留问题');await w.get('form').trigger('submit');await flushPromises();const request=fixture.posts[0]!.init;w.unmount();fixture.fail=false;w=mount(Feedback,{props:{...binding,blocks}});await flushPromises();expect(fixture.posts).toHaveLength(1);await click(w,'确认原反馈请求');expect(fixture.posts[1]!.init.headers).toEqual(request.headers);expect(fixture.posts[1]!.init.body).toBe(request.body);w.unmount();
  });
  it('requires exact impact and consent; does not automatically stop generation or replace the old version',async()=>{
    const w=mount(Revision,{props});await flushPromises();await click(w,'准备局部修订');expect(w.text()).toContain('下游场景');expect(fixture.posts).toHaveLength(0);await w.get('textarea').setValue('更清楚解释');await w.get('form').trigger('submit');expect(fixture.posts).toHaveLength(0);await w.get('input[type=checkbox]').setValue(true);await w.get('form').trigger('submit');await flushPromises();expect(w.emitted('operation')?.[0]).toEqual(['rev']);expect(w.emitted('adopt')).toBeUndefined();
    expect(JSON.parse(String(fixture.posts[0]!.init.body))).toEqual({kind:'revise_scene',expected_head_version:1,scene_id:'s',instruction:'更清楚解释',impact_digest:'a'.repeat(64)});expect(w.text()).toContain('保留旧版本');w.unmount();
  });
  it('restores only the original operation with GET, explains downstream waiting and adopts latest only explicitly',async()=>{
    let w=mount(Revision,{props});await flushPromises();await prepare(w);await w.get('form').trigger('submit');await flushPromises();w.unmount();w=mount(Revision,{props});await flushPromises();expect(fixture.posts).toHaveLength(1);fixture.operation='running';Stream.instances.at(-1)!.send();await flushPromises();expect(w.text()).toContain('下游场景就绪前不切换');fixture.operation='succeeded';fixture.head=2;Stream.instances.at(-1)!.send(4);await flushPromises();await w.setProps({headVersion:2});expect(w.emitted('adopt')).toBeUndefined();await click(w,'确认读取当前最新版本 v2');expect(w.emitted('adopt')).toHaveLength(1);w.unmount();
  });
  it.each(['failed','cancelled'])('keeps original version when operation is %s',async state=>{
    const w=mount(Revision,{props});await flushPromises();await prepare(w);await w.get('form').trigger('submit');await flushPromises();fixture.operation=state;Stream.instances[0]!.send();await flushPromises();expect(w.text()).toContain('保留原版本');expect(w.emitted('adopt')).toBeUndefined();w.unmount();
  });
  it('retains a revision request with the same body and key after an unknown POST outcome',async()=>{
    fixture.fail=true;let w=mount(Revision,{props});await flushPromises();await prepare(w);await w.get('form').trigger('submit');await flushPromises();const original=fixture.posts[0]!.init;w.unmount();fixture.fail=false;
    w=mount(Revision,{props});await flushPromises();expect(fixture.posts).toHaveLength(1);await click(w,'确认原修订请求');expect(fixture.posts).toHaveLength(2);expect(fixture.posts[1]!.init.body).toBe(original.body);expect(fixture.posts[1]!.init.headers).toEqual(original.headers);expect(w.emitted('operation')?.[0]).toEqual(['rev']);w.unmount();
  });
  it('blocks active generation, catalog mode and stale baseline and cancels only explicitly',async()=>{
    for(const extra of [{generationActive:true},{mode:'catalog_only' as const},{headVersion:2}]){const w=mount(Revision,{props:{...props,...extra}});await flushPromises();await prepare(w);await w.get('form').trigger('submit');await flushPromises();expect(fixture.posts).toHaveLength(0);w.unmount();sessionStorage.clear();}
    const w=mount(Revision,{props});await flushPromises();await prepare(w);await w.get('form').trigger('submit');await flushPromises();await click(w,'停止这次修订');expect(fixture.posts.map(p=>p.path)).toEqual(['/api/free-courses/c/operations','/api/free-courses/c/operations/rev/cancel']);expect(w.text()).toContain('修订已停止');w.unmount();
  });
});
