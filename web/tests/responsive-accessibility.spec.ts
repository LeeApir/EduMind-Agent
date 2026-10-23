import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Shell from '../src/components/WorkspaceShell.vue';
import State from '../src/components/WorkspaceState.vue';
import Presentation from '../src/components/CoursePresentation.vue';
import Settings from '../src/components/ModelSettings.vue';
import * as providers from '../src/api/providers';
import * as preferences from '../src/api/modelPreferences';
vi.mock('../src/api/catalog',()=>({ensureCatalogSession:vi.fn(async()=>({owner:'owner',csrf:'csrf'}))}));
import type { SceneProjection } from '../src/api/freeCourses';
let change: (()=>void)|undefined;
let query: {matches:boolean;addEventListener:ReturnType<typeof vi.fn>;removeEventListener:ReturnType<typeof vi.fn>};
beforeEach(()=>{query={matches:true,addEventListener:vi.fn((_name:string,fn:()=>void)=>{change=fn;}),removeEventListener:vi.fn()};vi.stubGlobal('matchMedia',()=>query);});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('responsive keyboard integration',()=>{
 it('includes the close control in both directions and makes background content inert',async()=>{
  const w=mount(Shell,{props:{page:'learning'},slots:{default:'<h1>学习</h1><input aria-label="目标" />'},attachTo:document.body});
  const menu=w.get('.mobile-menu');await menu.trigger('click');const nav=w.findAll('nav button');expect(document.activeElement).toBe(nav[0]!.element);expect(w.get('.workspace-body').attributes('inert')).toBeDefined();expect(w.get('.skip-link').attributes('inert')).toBeDefined();
  (menu.element as HTMLElement).focus();await menu.trigger('keydown',{key:'Tab',shiftKey:true});expect(document.activeElement).toBe(nav.at(-1)!.element);
  await nav.at(-1)!.trigger('keydown',{key:'Tab'});expect(document.activeElement).toBe(menu.element);
  await menu.trigger('keydown',{key:'Escape'});await flushPromises();expect(menu.attributes('aria-expanded')).toBe('false');expect(w.get('.workspace-body').attributes('inert')).toBeUndefined();expect(document.activeElement).toBe(menu.element);w.unmount();
 });
 it('closes expansion on navigation and focuses the visible destination heading',async()=>{
  const w=mount(Shell,{props:{page:'learning'},slots:{default:'<section style="display: none;"><h1>旧页</h1></section><h1>当前页面</h1>'},attachTo:document.body});await w.get('.mobile-menu').trigger('click');await w.setProps({page:'history'});await flushPromises();expect(w.get('.mobile-menu').attributes('aria-expanded')).toBe('false');expect(w.get('.workspace-body').attributes('inert')).toBeUndefined();expect(document.activeElement?.textContent).toBe('当前页面');w.unmount();
 });
 it('releases background content when resizing to desktop and unregisters the listener',async()=>{
  const w=mount(Shell,{props:{page:'learning'}});await w.get('.mobile-menu').trigger('click');query.matches=false;change!();await flushPromises();expect(w.get('.mobile-menu').attributes('aria-expanded')).toBe('false');expect(w.get('.workspace-body').attributes('inert')).toBeUndefined();w.unmount();expect(query.removeEventListener).toHaveBeenCalledWith('change',change);
 });
 it('distinguishes loading, unknown, empty, error and unavailable with text and read-only retries',async()=>{
  const labels=new Set<string>();for(const kind of ['loading','unknown','empty','error','invalid','forbidden'] as const){const w=mount(State,{props:{kind,retry:true}});labels.add(w.get('h2').text());expect(w.attributes('role')).toBe(['error','forbidden'].includes(kind)?'alert':'status');await w.get('button').trigger('click');expect(w.emitted('retry')).toEqual([[]]);w.unmount();}expect(labels.size).toBe(6);
 });
 it('respects reduced motion while keeping explicit manual actions available',async()=>{
  const scene:SceneProjection={course_id:'c',course_version:1,scene_id:'s',scene_version_id:'sv',blocks:[{kind:'code',anchor_id:'code',language:'c',source:'head = next;'}],actions:[{type:'highlight_block',anchor_id:'code',step_index:null}]};const w=mount(Presentation,{props:{scene}});await flushPromises();expect(w.text()).toContain('已遵循减少动效');const buttons=w.findAll('button');expect(buttons.find(b=>b.text()==='播放动作')!.attributes('disabled')).toBeDefined();const manual=buttons.find(b=>b.text()==='下一动作')!;expect(manual.attributes('disabled')).toBeUndefined();await manual.trigger('click');expect(w.emitted('highlight')?.at(-1)).toEqual(['code']);w.unmount();
 });
 it('keeps every cached model reachable without any network refresh or probe',async()=>{
  const connection:providers.Connection={id:'c',provider_type:'openai-compatible',display_name:'配置',base_url:'https://example.com/v1',is_local:false,enabled:true,config_version:1,credential_mode:'none',credential_state:'missing',credential_expires_at:null};
  vi.spyOn(providers,'listConnections').mockResolvedValue([connection]);vi.spyOn(preferences,'listPreferences').mockResolvedValue([]);
  const get=vi.spyOn(providers,'getModels').mockResolvedValue({connection_id:'c',config_version:1,refreshed_at:null,models:Array.from({length:6},(_,i)=>({id:`cached-${i}`,capabilities:{streaming:null,structured_output:null,tool_calling:null,vision:null,embedding:null,tts:null,asr:null,source:'unknown',version:'v1'}}))});
  const w=mount(Settings,{global:{stubs:{ProviderSettings:true,ModelPreferences:true}}});await flushPromises();expect(w.findAll('.capability-summary')).toHaveLength(5);await w.findAll('button').find(b=>b.text()==='查看更多缓存型号')!.trigger('click');expect(w.findAll('.capability-summary')).toHaveLength(6);expect(get).toHaveBeenCalledTimes(1);w.unmount();
 });

});
