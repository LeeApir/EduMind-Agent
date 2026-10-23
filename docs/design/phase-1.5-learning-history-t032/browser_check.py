"""Real Chromium, explicit synthetic history HTTP/SSE, no PG or Provider calls."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t032');OUT.mkdir(exist_ok=True)
u=lambda n:f'00000000-0000-4000-8000-{n:012d}'
old=u(10)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();writes=[];errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if(!sessionStorage.getItem('edumind:free:location:owner')){sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'history'}));sessionStorage.setItem('edumind:free:reading:owner:c1',JSON.stringify({version:1,scene:'s1',following:false,scroll:0,visited:['s1']}));sessionStorage.setItem('edumind:history:old:owner',JSON.stringify({id:'00000000-0000-4000-8000-000000000010',version:2}));}""")
    def manifest(v):return {'course_id':'c1','version':v,'plan_id':'p','created_at':'','complete':False,'node_links':[],'scenes':[{'scene_id':'s1','title':'第一节','scene_version_id':'sv1'},{'scene_id':'s2','title':'后续场景','scene_version_id':None}]}
    def api(route):
        endpoint=route.request.url.split('/api/')[-1]
        if route.request.method not in ['GET','HEAD']:writes.append(endpoint)
        if endpoint=='runtime':data={'mode':'dynamic'}
        elif endpoint.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif endpoint=='catalog':data={'status':'not_ready','releases':[]}
        elif endpoint.startswith('free-courses?'):data={'items':[{'course_id':'c1','original_goal':'理解链表头插','course_kind':'ai_draft','endorsement':'unendorsed','head_version':2,'created_at':'2026-10-23'}],'next_cursor':None}
        elif endpoint.startswith('free-courses/c1/records?'):
            kind=endpoint.split('kind=')[1].split('&')[0];identity={'attempt':'a1','operation':'op','feedback':'f','tutor':'t'}[kind];data={'course_id':'c1','kind':kind,'items':[{'record_id':identity,'created_at':'2026-10-23'}],'next_before_id':None}
        elif '/operations/' in endpoint:data={'course_id':'c1','operation_id':'op','kind':'revise_scene','state':'partially_succeeded','last_event_id':1,'head_version':2,'base_head_version':1,'clarification_questions':[],'steps':[],'budget':{'usage_unknown':True}}
        elif endpoint=='free-courses/c1':data={'course_id':'c1','original_goal':'理解链表头插','course_kind':'ai_draft','endorsement':'unendorsed','head':manifest(2)}
        elif endpoint.startswith('free-courses/c1/versions?'):data={'items':[{'version':2,'created_at':''},{'version':1,'created_at':''}],'next_cursor':None}
        elif endpoint.startswith('free-courses/c1/versions/'):
            v=int(endpoint.split('/versions/')[1].split('/')[0]);data={'course_id':'c1','course_version':v,'scene_id':'s1','scene_version_id':'sv1','blocks':[{'kind':'text','anchor_id':'intro','markdown':'准确原版本讲解'}],'actions':[]} if '/scenes/' in endpoint else manifest(v)
        elif '/attempts/' in endpoint:data={'attempt_id':'a1','binding':{'course_version':1,'scene_id':'s1','scene_version_id':'sv1'},'exercise_id':'e','exercise_version_id':'ev','answers':[{'question_id':'q','answer':'<script>自己的原始回答</script>'}],'completeness':'complete','reliability':'withdrawn','comparison_score':None,'question_results':[],'mastery_effect':'revoked','reason_code':'REVOKED'}
        elif endpoint.startswith('learning-units/'+old):
            assert endpoint.endswith('?publication_version=2');data={'id':old,'publication_version':2,'origin_type':'generated','scenes':[{'id':'oldscene','scene_key':'原讲解','version':1,'resources':[{'id':'r','version':1,'type':'explanation','content':{'markdown':'旧协议准确发布版本的讲解'}}]}]}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5189/api/.*'),api)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5189');page.wait_for_load_state('networkidle');page.get_by_role('button',name='理解链表头插',exact=True).click();page.get_by_role('button',name='读取练习作答 · 2026-10-23',exact=True).click();page.get_by_role('heading',name='原始作答 · 课程 v1',exact=True).wait_for()
        assert page.locator('[aria-label="原始作答记录"] script').count()==0;assert page.get_by_text('原贡献已撤销',exact=True).is_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width;assert not writes
        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'history-{width}.png'),full_page=True)
    page.get_by_role('button',name='读取原入口引用',exact=True).click();page.get_by_text('旧协议准确发布版本的讲解',exact=True).wait_for();assert not writes
    page.get_by_role('button',name='查看生成进度与继续选项',exact=True).click();page.get_by_role('heading',name='理解链表头插',exact=True).wait_for();assert page.get_by_text('准确原版本讲解',exact=True).count()==0
    assert page.evaluate("JSON.parse(sessionStorage.getItem('edumind:free:location:owner')).outlineAutoEnter") is False
    page.reload();page.wait_for_load_state('networkidle');page.get_by_role('heading',name='理解链表头插',exact=True).wait_for();assert page.get_by_text('准确原版本讲解',exact=True).count()==0
    page.get_by_role('button',name='打开导航',exact=True).click();page.get_by_role('button',name='学习记录',exact=True).click();page.get_by_role('button',name='恢复准确阅读位置',exact=True).click();page.get_by_text('准确原版本讲解',exact=True).wait_for()
    assert page.evaluate("JSON.parse(sessionStorage.getItem('edumind:free:reading:owner:c1')).version")==1;assert page.evaluate("JSON.parse(sessionStorage.getItem('edumind:free:reading:owner:c1')).following") is False
    assert not writes;assert not errors,errors;browser.close()
print('PASS six widths, persisted index/raw revoked input, old exact publication GET, explicit management stays on outline across refresh, exact pinned restore; explicit HTTP Mock only, zero POST')
