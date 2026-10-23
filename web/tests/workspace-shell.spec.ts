import { mount, flushPromises } from '@vue/test-utils';
import { describe, it, expect, vi } from 'vitest';
import Shell from '../src/components/WorkspaceShell.vue';
import State from '../src/components/WorkspaceState.vue';
import Product from '../src/ProductApp.vue';
vi.mock('../src/api/catalog', async importOriginal => ({ ...await importOriginal<typeof import('../src/api/catalog')>(), loadProductMode: vi.fn(async () => 'catalog_only'), ensureCatalogSession: vi.fn(async () => ({owner:'owner',csrf:'csrf'})) }));
describe('workspace shell', () => {
  it('offers only implemented navigation, keyboard escape and page focus', async () => {
    const w = mount(Shell, { props: { page: 'learning' }, slots: { default: '<h1>学习</h1>' }, attachTo: document.body });
    expect(w.text()).not.toMatch(/题库|学习报告|RAG|辩论/);
    await w.get('.mobile-menu').trigger('click');
    expect(w.get('.mobile-menu').attributes('aria-expanded')).toBe('true');
    await w.get('aside').trigger('keydown', { key: 'Escape' });
    expect(document.activeElement).toBe(w.get('.mobile-menu').element);
    await w.setProps({ page: 'catalog' }); await flushPromises();
    expect(document.activeElement).toBe(w.get('h1').element);
    w.unmount();
  });
  it.each(['loading', 'empty', 'unknown', 'forbidden', 'error', 'invalid'] as const)('labels %s and retries read only', async kind => {
    const w = mount(State, { props: { kind, retry: true } });
    expect(w.get('h2').text()).toBeTruthy(); await w.get('button').trigger('click'); expect(w.emitted('retry')).toHaveLength(1);
  });
  it('pins an exact history restore and preserves explicit outline management across refresh',async()=>{
    sessionStorage.clear();sessionStorage.setItem('edumind:free:reading:owner:c',JSON.stringify({version:2,scene:'s2',following:true,scroll:100,visited:['s2']}));
    const options={global:{stubs:{LearningHome:{template:'<h1>学习</h1>'},LearningHistory:{template:'<div><h1>记录</h1><button @click="$emit(\'restore\',\'c\',1,\'s\',\'op\')">恢复原记录</button><button @click="$emit(\'manage\',\'c\',\'op\')">管理原操作</button></div>'},CourseWorkspace:{props:['initialVersion','initialScene'],template:'<h1>课堂 {{ initialVersion }} {{ initialScene }}</h1>'},CourseOutline:{props:['autoEnter'],template:'<h1>大纲管理 {{ autoEnter }}</h1>'}}}};
    let w=mount(Product,options);await flushPromises();await w.findAll('nav button').find(b=>b.text()==='学习记录')!.trigger('click');await flushPromises();await w.findAll('button').find(b=>b.text()==='恢复原记录')!.trigger('click');await flushPromises();expect(w.text()).toContain('课堂 1 s');const reading=JSON.parse(sessionStorage.getItem('edumind:free:reading:owner:c')!);expect(reading).toMatchObject({version:1,scene:'s',following:false,visited:[]});
    await w.findAll('nav button').find(b=>b.text()==='学习记录')!.trigger('click');await flushPromises();await w.findAll('button').find(b=>b.text()==='管理原操作')!.trigger('click');await flushPromises();expect(w.text()).toContain('大纲管理 false');w.unmount();w=mount(Product,options);await flushPromises();expect(w.text()).toContain('大纲管理 false');w.unmount();
  });
  it('keeps unsaved inputs and existing settings reachable without generation', async () => {
    sessionStorage.clear();
    const w = mount(Product, { global: { stubs: { LearningHome: { template: '<div><h1>学习</h1><input aria-label="未保存" /></div>' }, CatalogPage: { template: '<div><h1>课程目录</h1><input aria-label="未保存" /></div>' }, ProviderSettings: { template: '<h1>连接设置</h1>' }, ModelPreferences: { template: '<h1>偏好</h1>' } } } });
    await flushPromises(); await w.get('input').setValue('保留我的输入');
    await w.findAll('nav button').find(b => b.text() === '模型设置')!.trigger('click');
    await flushPromises();
    await w.findAll('nav button').find(b => b.text() === '学习')!.trigger('click');
    expect((w.get('input').element as HTMLInputElement).value).toBe('保留我的输入');
  });
});
