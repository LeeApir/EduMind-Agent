import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import Home from '../src/components/LearningHome.vue';
const state = vi.hoisted(() => ({ owner: 'owner', posts: [] as RequestInit[], failed: false }));
vi.mock('../src/api/catalog', () => ({ ensureCatalogSession: vi.fn(async () => ({ owner: state.owner, csrf: 'csrf' })), loadCatalog: vi.fn(async () => ({ status: 'ready', releases: [] })) }));
beforeEach(() => {
  state.owner = 'owner'; state.posts = []; state.failed = false; sessionStorage.clear();
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') { state.posts.push(init); if (state.failed) throw new Error('network'); return new Response(JSON.stringify({ course_id: 'c1', operation_id: 'op1' }), { status: 201 }); }
    return new Response(JSON.stringify({ items: [], next_cursor: null }));
  }));
});
afterEach(() => vi.unstubAllGlobals());
describe('goal-driven home', () => {
  it('shows truthful empty state, optional language, never generates on load', async () => {
    const w = mount(Home, { props: { mode: 'dynamic' } }); await flushPromises();
    expect(w.text()).toContain('还没有自由课程'); expect(w.text()).not.toContain('已学 1 / 6'); expect(state.posts).toHaveLength(0);
    await w.get('textarea').setValue('解释任意目标'); await w.get('form').trigger('submit'); await flushPromises();
    expect(w.emitted('open')?.[0]).toEqual(['c1', 'op1']);
    expect(JSON.parse(String(state.posts[0]!.body))).toEqual({ goal: '解释任意目标', teaching_language: 'zh-CN', code_language: 'c' });
  });
  it('preserves goal when unavailable and does not POST', async () => {
    const w = mount(Home, { props: { mode: 'catalog_only' } }); await flushPromises(); await w.get('textarea').setValue('保留目标');
    await w.get('form').trigger('submit'); expect(w.get('[role=alert]').text()).toContain('当前只开放'); expect(state.posts).toHaveLength(0);
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('保留目标');
  });
  it('reuses one exact key after uncertain failure, refresh and repeated click', async () => {
    state.failed = true; let w = mount(Home, { props: { mode: 'dynamic' } }); await flushPromises(); await w.get('textarea').setValue('同一个目标');
    await w.get('form').trigger('submit'); await w.get('form').trigger('submit'); await flushPromises();
    expect(state.posts).toHaveLength(1); const key = (state.posts[0]!.headers as Record<string,string>)['Idempotency-Key'];
    w.unmount(); w = mount(Home, { props: { mode: 'dynamic' } }); await flushPromises();
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('同一个目标'); state.failed = false;
    await w.get('form').trigger('submit'); await flushPromises();
    expect((state.posts[1]!.headers as Record<string,string>)['Idempotency-Key']).toBe(key);
    await w.get('form').trigger('submit'); await flushPromises(); expect(state.posts).toHaveLength(2);
    await w.get('textarea').setValue('新的目标'); await w.get('form').trigger('submit'); await flushPromises(); expect((state.posts[2]!.headers as Record<string,string>)['Idempotency-Key']).not.toBe(key);
  });
  it('blocks a changed identity and retains the current goal', async () => {
    const w = mount(Home, { props: { mode: 'dynamic' } }); await flushPromises(); await w.get('textarea').setValue('我的目标'); state.owner = 'other';
    await w.get('form').trigger('submit'); await flushPromises(); expect(state.posts).toHaveLength(0); expect(w.text()).toContain('身份已变化');
  });
  it('renders server records as private drafts with unknown learning progress', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ items: [{course_id:'c1',original_goal:'<script>unsafe</script>',course_kind:'ai_draft',endorsement:'unendorsed',head_version:2,created_at:''}], next_cursor:null })));
    const w = mount(Home, { props: { mode:'catalog_only' } }); await flushPromises(); expect(w.text()).toContain('未签核'); expect(w.find('script').exists()).toBe(false);
    await w.findAll('button').find(b => b.text().includes('继续学习'))!.trigger('click'); expect(w.emitted('open')?.[0]).toEqual(['c1','']);
  });
});
