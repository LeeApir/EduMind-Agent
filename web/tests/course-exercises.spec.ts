import { mount, flushPromises } from '@vue/test-utils';
import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest';
import Exercise from '../src/components/CourseExercise.vue';
import type { Attempt } from '../src/api/courseExercises';
const state=vi.hoisted(()=>({owner:'owner',fail:false,readFail:false,status:201,posts:[] as RequestInit[],read:[] as string[],records:{} as Record<string,Attempt>}));
vi.mock('../src/api/catalog',()=>({ensureCatalogSession:vi.fn(async()=>({owner:state.owner,csrf:'csrf'}))}));
const props={courseId:'c',courseVersion:1,sceneId:'s',sceneVersionId:'sv',headVersion:1,mode:'dynamic' as const,block:{kind:'exercise' as const,anchor_id:'e',exercise_id:'e',exercise_version_id:'ev',question:'解释头插过程',items:[{question_id:'q1',question:'先修改什么？',input_type:'short_text' as const},{question_id:'q2',question:'然后修改什么？',input_type:'short_text' as const}]}};
function json(data:unknown,status=200){return new Response(JSON.stringify(data),{status});}
beforeEach(()=>{sessionStorage.clear();state.owner='owner';state.fail=false;state.readFail=false;state.status=201;state.posts=[];state.read=[];state.records={};
  vi.stubGlobal('fetch',vi.fn(async(path:string,init:RequestInit={})=>{if(init.method==='POST'){state.posts.push(init);if(state.fail)throw new Error('网络结果未知');if(state.status!==201)return json({code:'STALE_COURSE_VERSION'},state.status);const body=JSON.parse(String(init.body));const id='a'+state.posts.length;state.records[id]={attempt_id:id,binding:{course_version:body.course_version,scene_id:body.scene_id,scene_version_id:body.scene_version_id},exercise_id:body.exercise_id,exercise_version_id:body.exercise_version_id,answers:body.answers,completeness:body.answers.length===2?'complete':'incomplete',reliability:'provisional',comparison_score:body.answers.length===2?.5:null,question_results:body.answers.length===2?[{question_id:'q1',matches_reference:true,explanation:'仅暂定参考'},{question_id:'q2',matches_reference:false,explanation:'仅暂定参考'}]:[],mastery_effect:'course_only',reason_code:null};return json({attempt_id:id},201);}state.read.push(path);if(state.readFail)return json({},503);return json(state.records[path.split('/').at(-1)!]);}));
});afterEach(()=>vi.unstubAllGlobals());
async function click(w:ReturnType<typeof mount>,name:string){await w.findAll('button').find(b=>b.text()===name)!.trigger('click');await flushPromises();}
describe('bound free course exercise',()=>{
  it('rejects empty input, saves partial without showing comparison, then creates a complete immutable attempt',async()=>{
    const w=mount(Exercise,{props});await flushPromises();await w.get('form').trigger('submit');expect(state.posts).toHaveLength(0);await w.findAll('textarea')[0]!.setValue('next');await w.get('form').trigger('submit');await flushPromises();expect(w.text()).toContain('部分作答已保存');expect(w.text()).not.toContain('匹配比例');
    await click(w,'继续完善或新作答');await w.findAll('textarea')[1]!.setValue('head');await w.get('form').trigger('submit');await flushPromises();expect(w.text()).toContain('暂定比较');expect(w.text()).toContain('未更新正式掌握度');expect(w.text()).toContain('50%');expect(state.posts).toHaveLength(2);expect(Object.keys(state.records)).toHaveLength(2);w.unmount();
  });
  it('keeps exact request/key after uncertain failure and refresh; duplicate clicks do not resubmit',async()=>{
    state.fail=true;let w=mount(Exercise,{props});await flushPromises();await w.findAll('textarea')[0]!.setValue('原始答案');await w.get('form').trigger('submit');await w.get('form').trigger('submit');await flushPromises();expect(state.posts).toHaveLength(1);const original=state.posts[0]!;w.unmount();
    state.fail=false;w=mount(Exercise,{props});await flushPromises();await click(w,'确认原提交');expect(state.posts).toHaveLength(2);expect(state.posts[1]!.headers).toEqual(original.headers);expect(state.posts[1]!.body).toBe(original.body);expect(w.text()).toContain('原始答案');w.unmount();
  });
  it('recovers a known receipt with GET only after feedback read fails',async()=>{
    state.readFail=true;let w=mount(Exercise,{props});await flushPromises();await w.findAll('textarea')[0]!.setValue('next');await w.get('form').trigger('submit');await flushPromises();expect(state.posts).toHaveLength(1);w.unmount();state.readFail=false;
    w=mount(Exercise,{props});await flushPromises();await click(w,'读取原提交结果');expect(state.posts).toHaveLength(1);expect(w.text()).toContain('部分作答已保存');w.unmount();
  });
  it('preserves original answers while refreshing withdrawn/revoked feedback and hiding explanations',async()=>{
    const w=mount(Exercise,{props});await flushPromises();for(const input of w.findAll('textarea'))await input.setValue('answer');await w.get('form').trigger('submit');await flushPromises();expect(w.text()).toContain('仅暂定参考');Object.assign(state.records.a1!,{reliability:'withdrawn',mastery_effect:'revoked',reason_code:'EVIDENCE_REVOKED'});await click(w,'刷新这份反馈');expect(w.text()).toContain('原始作答保留');expect(w.text()).toContain('掌握度证据已撤销');expect(w.text()).not.toContain('仅暂定参考');expect(w.text()).not.toContain('50%');w.unmount();
  });
  it('blocks catalog-only, paused, stale versions and changed owner; never guesses a new binding',async()=>{
    for(const extra of [{mode:'catalog_only' as const},{active:false},{headVersion:2}]){const w=mount(Exercise,{props:{...props,...extra}});await flushPromises();await w.findAll('textarea')[0]!.setValue('next');await w.get('form').trigger('submit');await flushPromises();expect(state.posts).toHaveLength(0);w.unmount();}
    const w=mount(Exercise,{props});await flushPromises();await w.findAll('textarea')[0]!.setValue('next');state.owner='other';await w.get('form').trigger('submit');await flushPromises();expect(state.posts).toHaveLength(0);expect(w.text()).toContain('身份已变化');w.unmount();
  });
  it('keeps a 409 submission bound to old exercise and isolates input for a new version',async()=>{
    state.status=409;let w=mount(Exercise,{props});await flushPromises();await w.findAll('textarea')[0]!.setValue('旧答案');await w.get('form').trigger('submit');await flushPromises();expect(w.text()).toContain('不使用新题答案评分');w.unmount();
    w=mount(Exercise,{props:{...props,courseVersion:2,headVersion:2,sceneVersionId:'sv2',block:{...props.block,exercise_version_id:'ev2'}}});await flushPromises();expect((w.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe('');expect(state.posts).toHaveLength(1);w.unmount();
  });
});
