import { mount,flushPromises } from '@vue/test-utils';
import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest';
import Tutor from '../src/components/CourseTutor.vue';
const state=vi.hoisted(()=>({owner:'owner',status:'queued',posts:[] as {path:string;init:RequestInit}[],fail:false,unknown:false}));
vi.mock('../src/api/catalog',()=>({ensureCatalogSession:vi.fn(async()=>({owner:state.owner,csrf:'csrf'}))}));
class Stream{static instances:Stream[]=[];closed=false;listeners=new Map<string,EventListener>();onerror:((event:Event)=>void)|null=null;constructor(readonly url:string){Stream.instances.push(this);}addEventListener(t:string,f:EventListener){this.listeners.set(t,f);}close(){this.closed=true;}send(type='tutor_ready'){this.listeners.get(type)?.(new MessageEvent(type,{data:JSON.stringify({schema_version:'free-course-events-v1',operation_id:'op',seq:3,type})}));}}
const props={courseId:'c',courseVersion:1,sceneId:'s',sceneVersionId:'sv',headVersion:1,mode:'dynamic' as const,generationActive:false,modelValue:'请再解释一次'};
function json(value:unknown){return new Response(JSON.stringify(value));}
beforeEach(()=>{sessionStorage.clear();Stream.instances=[];state.owner='owner';state.status='queued';state.posts=[];state.fail=false;state.unknown=false;vi.stubGlobal('EventSource',Stream);
  vi.stubGlobal('fetch',vi.fn(async(path:string,init:RequestInit={})=>{
    if(init.method==='POST'){state.posts.push({path,init});if(state.fail)throw new Error('网络结果未知');if(path.endsWith('/cancel')){state.status='cancelled';return json({state:'cancel_requested'});}return json({operation_id:'op',turn_id:'turn'});}
    if(path.includes('/tutor-turns/'))return json({turn_id:'turn',operation_id:'op',binding:{course_version:1,scene_id:'s',scene_version_id:'sv'},message:'请再解释一次',status:state.status,markdown:['ready','invalidated'].includes(state.status)?'<script>补充解释</script>':null,anchor_refs:[],reason_code:null});
    if(path.includes('/operations/'))return json({course_id:'c',operation_id:'op',kind:'tutor_turn',state:state.status==='ready'?'succeeded':state.status==='invalidated'?'succeeded':state.status,last_event_id:state.status==='queued'?1:4,clarification_questions:[],steps:[],budget:{usage_unknown:state.unknown}});
    return json({course_id:'c',original_goal:'目标',course_kind:'ai_draft',endorsement:'unendorsed',head:{course_id:'c',version:1,plan_id:'p',complete:true,node_links:[],scenes:[{scene_id:'s',title:'当前场景',scene_version_id:'sv'}]}});
  }));
});afterEach(()=>vi.unstubAllGlobals());
async function click(w:ReturnType<typeof mount>,text:string){await w.findAll('button').find(b=>b.text()===text)!.trigger('click');await flushPromises();}
async function send(w:ReturnType<typeof mount>){await w.get('input[type=checkbox]').setValue(true);await w.get('form').trigger('submit');await flushPromises();}
describe('exact-context tutor panel',()=>{
  it('never sends on mount, requires explicit assisted-practice acknowledgement and exact binding',async()=>{
    const w=mount(Tutor,{props});await flushPromises();expect(state.posts).toHaveLength(0);await w.get('form').trigger('submit');expect(state.posts).toHaveLength(0);await send(w);expect(state.posts).toHaveLength(1);
    expect(JSON.parse(String(state.posts[0]!.init.body))).toEqual({course_version:1,scene_id:'s',scene_version_id:'sv',message:'请再解释一次',acknowledge_assisted_practice:true});expect(w.text()).toContain('等待导师回复');w.unmount();
  });
  it('handles durable tutor_ready, escapes reply, and closes its wait on leaving',async()=>{
    const w=mount(Tutor,{props});await flushPromises();await send(w);state.status='ready';Stream.instances[0]!.send();await flushPromises();expect(w.text()).toContain('AI 补充解释');expect(w.find('script').exists()).toBe(false);expect(w.text()).toContain('补充解释');expect(state.posts).toHaveLength(1);w.unmount();expect(Stream.instances[0]!.closed).toBe(true);
  });
  it('refreshes known receipts with GET only and hides invalidated historical replies',async()=>{
    let w=mount(Tutor,{props});await flushPromises();await send(w);w.unmount();state.status='ready';w=mount(Tutor,{props});await flushPromises();expect(state.posts).toHaveLength(1);expect(w.text()).toContain('AI 补充解释');state.status='invalidated';await click(w,'重新读取本次提问');expect(w.text()).toContain('已隐藏旧回复');expect(w.text()).not.toContain('<script>补充解释</script>');expect(state.posts).toHaveLength(1);w.unmount();
  });
  it('preserves one exact key on unknown create failure and refresh, does not resend automatically',async()=>{
    state.fail=true;let w=mount(Tutor,{props});await flushPromises();await send(w);expect(state.posts).toHaveLength(1);const original=state.posts[0]!.init;w.unmount();state.fail=false;w=mount(Tutor,{props});await flushPromises();expect(state.posts).toHaveLength(1);await click(w,'确认原提问请求');expect(state.posts).toHaveLength(2);expect(state.posts[1]!.init.headers).toEqual(original.headers);expect(state.posts[1]!.init.body).toBe(original.body);w.unmount();
  });
  it('blocks generation, history, catalog-only and changed identity instead of implicit cancellation',async()=>{
    for(const extra of [{generationActive:true},{headVersion:2},{mode:'catalog_only' as const}]){const w=mount(Tutor,{props:{...props,...extra}});await flushPromises();await send(w);expect(state.posts).toHaveLength(0);w.unmount();}
    const w=mount(Tutor,{props});await flushPromises();state.owner='other';await send(w);expect(state.posts).toHaveLength(0);expect(w.text()).toContain('身份已变化');w.unmount();
  });
  it('does not start another send while prior outcome/usage is unknown',async()=>{
    const w=mount(Tutor,{props});await flushPromises();await send(w);state.status='failed';state.unknown=true;await click(w,'重新读取本次提问');expect(w.text()).toContain('不能开始新的发送');await click(w,'开始新问题');expect(state.posts).toHaveLength(1);w.unmount();
  });
  it('only explicitly cancels current tutor and does not revise the course or auto-retry failure',async()=>{
    const w=mount(Tutor,{props});await flushPromises();await send(w);await click(w,'停止本次提问');expect(state.posts.map(p=>p.path)).toEqual(['/api/free-courses/c/tutor-turns','/api/free-courses/c/operations/op/cancel']);expect(w.text()).toContain('未修改课程');await click(w,'重新读取本次提问');expect(state.posts).toHaveLength(2);w.unmount();
  });
});
