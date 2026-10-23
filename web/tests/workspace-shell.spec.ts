import { mount, flushPromises } from '@vue/test-utils';
import { describe, it, expect, vi } from 'vitest';
import Shell from '../src/components/WorkspaceShell.vue';
import State from '../src/components/WorkspaceState.vue';
import Product from '../src/ProductApp.vue';
vi.mock('../src/api/catalog', async importOriginal => ({ ...await importOriginal<typeof import('../src/api/catalog')>(), loadProductMode: vi.fn(async () => 'catalog_only') }));
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
  it('keeps unsaved inputs and existing settings reachable without generation', async () => {
    const w = mount(Product, { global: { stubs: { LearningHome: { template: '<div><h1>学习</h1><input aria-label="未保存" /></div>' }, CatalogPage: { template: '<div><h1>课程目录</h1><input aria-label="未保存" /></div>' }, ProviderSettings: { template: '<h1>连接设置</h1>' }, ModelPreferences: { template: '<h1>偏好</h1>' } } } });
    await flushPromises(); await w.get('input').setValue('保留我的输入');
    await w.findAll('nav button').find(b => b.text() === '模型设置')!.trigger('click');
    await flushPromises();
    await w.findAll('nav button').find(b => b.text() === '学习')!.trigger('click');
    expect((w.get('input').element as HTMLInputElement).value).toBe('保留我的输入');
  });
});
