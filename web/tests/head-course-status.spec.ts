import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Outline from '../src/components/CourseOutline.vue';
const fixture = vi.hoisted(() => ({ finite: true, posts: 0 }));
vi.mock('../src/api/catalog', () => ({ ensureCatalogSession: vi.fn(async () => ({owner:'owner',csrf:'csrf'})) }));
beforeEach(() => {
  fixture.finite=true; fixture.posts=0; sessionStorage.clear();
  vi.stubGlobal('fetch',vi.fn(async (path:string,init:RequestInit={})=>{
    if(init.method==='POST'){fixture.posts++;throw new Error('No new operation allowed in this check');}
    const operation={course_id:'c',operation_id:'op',kind:'create',state:'failed',last_event_id:3,head_version:1,base_head_version:null,reason_code:'TEACHING_REVIEW_FAILED',clarification_questions:[],steps:[],...(fixture.finite?{execution_mode:'finite_head_foreground',budget:null}:{budget:{attempts_used:2,attempts_remaining:11}})};
    const course={course_id:'c',original_goal:'准确B目标',course_kind:'ai_draft',endorsement:'unendorsed',teaching_language:'zh-CN',code_language:'c',head:{course_id:'c',version:1,plan_id:'p',created_at:'',complete:false,node_links:[],scenes:[{scene_id:'s',title:'头插全过程',scene_version_id:null}]}};
    return new Response(JSON.stringify(path.includes('/operations/')?operation:course));
  }));
});
afterEach(()=>vi.unstubAllGlobals());
describe('finite foreground stopped status',()=>{
  it('shows stopped, hides scheduler budget and resume; refresh is GET-only',async()=>{
    const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic',autoEnter:false}});
    await flushPromises();
    expect(w.text()).toContain('生成已停止');
    expect(w.text()).toContain('独立授权的前台步骤');
    expect(w.text()).not.toContain('尝试已用');
    expect(w.text()).not.toContain('剩余 13');
    expect(w.text()).not.toContain('继续缺失内容');
    const reload=w.findAll('button').find(b=>b.text()==='重新读取进度');
    await reload!.trigger('click');await flushPromises();
    expect(w.text()).toContain('生成已停止');expect(fixture.posts).toBe(0);w.unmount();
  });
  it('preserves an ordinary scheduler course budget and normal failure label',async()=>{
    fixture.finite=false;
    const w=mount(Outline,{props:{courseId:'c',operationId:'op',mode:'dynamic',autoEnter:false}});
    await flushPromises();
    expect(w.text()).toContain('尝试已用 2 · 剩余 11');
    expect(w.text()).toContain('生成未完成');
    expect(w.text()).toContain('确认继续缺失内容');
    expect(w.text()).not.toContain('生成已停止');expect(fixture.posts).toBe(0);w.unmount();
  });
});
