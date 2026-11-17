"""Real Chromium; all business HTTP/SSE explicitly synthetic, zero Provider."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t029');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();writes=[];errors=[]
    state={'head':1,'op':'queued','feedback':'pending','blocked':False,'created':False}
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if(!sessionStorage.getItem('edumind:free:location:owner'))sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'course',course:'c',operation:'gen',version:1,scene:'s'}));""")
    def manifest(v):return {'course_id':'c','version':v,'plan_id':'p'+str(v),'created_at':'','complete':True,'node_links':[],'scenes':[{'scene_id':'s','title':'指针的方向','scene_version_id':'sv'+str(v)},{'scene_id':'s2','title':'下游练习','scene_version_id':None}]}
    def api(route):
        path=route.request.url.split('/api/')[-1];method=route.request.method
        if method=='POST':writes.append((path,json.loads(route.request.post_data)))
        if path=='runtime':data={'mode':'dynamic'}
        elif path.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif path=='catalog':data={'status':'not_ready','releases':[]}
        elif path=='free-courses/c/feedback' and method=='POST':data={'feedback_id':'f'}
        elif '/feedback/' in path:data={'feedback_id':'f','binding':{'course_version':1,'scene_id':'s','scene_version_id':'sv1'},'anchor_id':'quiz','description':'题目[q1]：答案可能有误','status':state['feedback'],'reason_code':None}
        elif '/impact?' in path:data={'course_id':'c','base_head_version':1,'kind':'revise_scene','affected_scene_ids':['s','s2'],'requires_outline_adjustment':False,'max_attempts':13,'max_seconds':600,'impact_digest':'a'*64}
        elif path=='free-courses/c/operations' and method=='POST':state['created']=True;data={'course_id':'c','operation_id':'rev'}
        elif '/operations/' in path:
            oid=path.split('/operations/')[1].split('/')[0]
            if path.endswith('/cancel'):state['op']='cancelled';data={'state':'cancel_requested'}
            elif '/events?' in path:route.fulfill(content_type='text/event-stream',body=': synthetic heartbeat\n\n');return
            else:data={'course_id':'c','operation_id':oid,'kind':'create' if oid=='gen' else 'revise_scene','state':'succeeded' if oid=='gen' else state['op'],'last_event_id':1,'clarification_questions':[],'steps':[{'step_key':'scene:s2','scene_id':'s2','state':'pending','reason_code':None}],'budget':{'usage_unknown':False}}
        elif path.startswith('free-courses/c/versions/'):
            v=int(path.split('/versions/')[1].split('/')[0])
            if '/scenes/' in path:
                if state['blocked'] and v==1:route.fulfill(status=409,json={'code':'CONTENT_UNAVAILABLE'});return
                data={'course_id':'c','course_version':v,'scene_id':'s','scene_version_id':'sv'+str(v),'blocks':[{'kind':'text','anchor_id':'intro','markdown':'原课程正文保持不变' if v==1 else '新版本已经明确读取'},{'kind':'exercise','anchor_id':'quiz','exercise_id':'e','exercise_version_id':'ev','question':'小练习','items':[{'question_id':'q1','question':'next 的作用是什么？','input_type':'short_text'}]}],'actions':[]}
            else:data=manifest(v)
        elif path=='free-courses/c':data={'course_id':'c','original_goal':'理解链表头插','course_kind':'ai_draft','endorsement':'unendorsed','head':manifest(state['head'])}
        elif path.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5186/api/.*'),api)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5186');page.wait_for_load_state('networkidle')
        button=page.get_by_role('button',name='准备局部修订',exact=True)
        if button.count():button.click()
        else:page.get_by_role('button',name='读取影响范围',exact=True).click()
        page.get_by_text('本次影响范围',exact=True).wait_for()
        assert page.get_by_role('button',name='确认开始局部修订').is_disabled();assert not writes
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'revision-{width}.png'),full_page=True)
    page.get_by_label('反馈位置',exact=True).select_option(label='题目 1：next 的作用是什么？');page.get_by_label('问题描述',exact=True).fill('答案可能有误');page.get_by_role('button',name='提交问题反馈',exact=True).click();page.get_by_role('heading',name='已提交 · 待核对').wait_for()
    assert writes[-1][1]['description']=='题目[q1]：答案可能有误'
    page.reload();page.wait_for_load_state('networkidle');page.get_by_role('heading',name='已提交 · 待核对').wait_for();assert len(writes)==1
    page.get_by_role('button',name='读取影响范围',exact=True).click();page.get_by_label('希望怎样修改这个场景？').fill('更清楚解释指针');page.get_by_label('确认受影响场景、证据撤销与新操作预算').check();page.get_by_role('button',name='确认开始局部修订',exact=True).click();page.get_by_text('修订排队中，保留旧版本',exact=True).wait_for()
    assert page.get_by_text('原课程正文保持不变',exact=True).is_visible();assert len(writes)==2
    page.reload();page.wait_for_load_state('networkidle');page.get_by_text('修订排队中，保留旧版本',exact=True).wait_for();assert len(writes)==2
    state['op']='running';page.get_by_role('button',name='读取修订进度',exact=True).click();page.get_by_text('正在准备完整替换集合，下游场景就绪前不切换',exact=True).wait_for()
    state['op']='succeeded';state['head']=2;page.get_by_role('button',name='读取修订进度',exact=True).click()
    # Parent snapshot remains pinned until its own explicit read; reload still restores v1.
    page.reload();page.wait_for_load_state('networkidle');page.get_by_role('button',name='确认读取当前最新版本 v2',exact=True).wait_for();assert page.get_by_text('原课程正文保持不变',exact=True).is_visible()
    state['feedback']='confirmed';state['blocked']=True;page.get_by_role('button',name='读取反馈处置',exact=True).click();page.get_by_role('heading',name='已确认 · 按规则处置').wait_for();page.wait_for_timeout(100)
    assert page.get_by_text('原课程正文保持不变',exact=True).count()==0;assert page.get_by_text('内容暂不可用',exact=True).count()==1
    page.get_by_role('button',name='确认读取当前最新版本 v2',exact=True).click();page.get_by_text('新版本已经明确读取',exact=True).wait_for();assert len(writes)==2;assert not errors,errors
    page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/'revision-adopted-320.png'),full_page=True)
    browser.close()
print('PASS six widths, exact-question feedback/pending/confirmed pause, impact consent, GET-only restore, downstream wait, old version kept until explicit latest; synthetic HTTP/SSE only')
