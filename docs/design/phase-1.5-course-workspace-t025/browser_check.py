"""Chromium actual UI; explicit synthetic HTTP/SSE, no Provider or PG."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t025');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();head=[1];unavailable=[False];writes=[];errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if (!sessionStorage.getItem('edumind:free:location:owner')) sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'course',course:'c',operation:'op',version:1,scene:'s1'}));""")
    def manifest(v):return {'course_id':'c','version':v,'plan_id':'p','created_at':'','complete':False,'node_links':[],'scenes':[{'scene_id':'s1','title':'看清指针的方向','scene_version_id':'sv1'},{'scene_id':'s2','title':'一次头插，两个动作','scene_version_id':'sv2' if v>=2 else None},{'scene_id':'s3','title':'失败的后续场景','scene_version_id':None}]}
    def api(route):
        path=route.request.url.split('/api/')[-1]
        if route.request.method=='POST':writes.append(path)
        if path=='runtime':data={'mode':'catalog_only'}
        elif path.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif path=='catalog':data={'status':'not_ready','releases':[]}
        elif '/events?' in path:route.fulfill(status=200,content_type='text/event-stream',body=': fixture heartbeat\n\n');return
        elif '/operations/' in path:data={'course_id':'c','operation_id':'op','state':'running','kind':'create','last_event_id':head[0],'clarification_questions':[],'reason_code':None,'steps':[{'step_key':'s3','scene_id':'s3','state':'failed','reason_code':'SCHEMA_INVALID'}],'budget':{'attempts_used':1,'attempts_remaining':12}}
        elif '/versions?' in path:data={'items':[{'version':99,'created_at':''},{'version':2,'created_at':''},{'version':1,'created_at':''}],'next_cursor':None}
        elif '/versions/' in path:
            match=re.search(r'/versions/(\d+)(?:/scenes/(.*))?',path);v=int(match[1]);sid=match[2]
            if v==99:route.fulfill(status=404,json={'code':'NOT_FOUND'});return
            if not sid:data=manifest(v)
            elif unavailable[0]:route.fulfill(status=409,json={'code':'CONTENT_UNAVAILABLE'});return
            else:data={'course_id':'c','course_version':v,'scene_id':sid,'scene_version_id':'sv1' if sid=='s1' else 'sv2','blocks':[{'kind':'text','anchor_id':'intro','markdown':'指针保存的是结点的地址。先连接原链表，再更新 head。' if sid=='s1' else '第二节已经就绪：先让 n.next 接住原 head。'},{'kind':'code','anchor_id':'code','language':'c','source':'n->next = head;\nhead = n;\n/* <img src=x onerror=alert(1)> */'},{'kind':'exercise_unavailable','anchor_id':'e','exercise_id':'e','exercise_version_id':'ev','reason_code':'EXERCISE_UNAVAILABLE'}],'actions':[]}
        elif path=='free-courses/c':data={'course_id':'c','original_goal':'把链表头插看明白','course_kind':'ai_draft','endorsement':'unendorsed','head':manifest(head[0])}
        elif path.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5182/api/.*'),api)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5182');page.wait_for_load_state('networkidle');page.get_by_text('指针保存的是结点的地址',exact=False).wait_for()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        assert page.locator('.scene-content img').count()==0
        page.screenshot(path=str(OUT/f'course-{width}.png'),full_page=True)
    page.get_by_role('button',name='有疑问？打开导师区域').click();page.get_by_label('记下问题').fill('为什么先接 next？');page.get_by_label('记下问题').press('Escape');assert page.get_by_role('button',name='有疑问？打开导师区域').evaluate('(e)=>e===document.activeElement')
    head[0]=2;page.get_by_role('button',name='重新读取生成状态').click();page.get_by_text('阅读版本 v2',exact=True).wait_for()
    page.get_by_role('button',name='课程目录',exact=True).click();page.get_by_role('button',name='02 · 一次头插，两个动作').click();page.get_by_text('第二节已经就绪',exact=False).wait_for()
    page.reload();page.wait_for_load_state('networkidle');page.get_by_text('第二节已经就绪',exact=False).wait_for()
    page.get_by_role('button',name='有疑问？打开导师区域').click();assert page.get_by_label('记下问题').input_value()=='为什么先接 next？'
    page.get_by_role('button',name='查看课程版本').click();page.get_by_role('button',name='读取 v1',exact=True).click();page.get_by_text('阅读版本 v1',exact=True).wait_for()
    page.get_by_role('button',name='读取 v99',exact=True).click();page.get_by_role('heading',name='此版本已不可用').wait_for();assert page.get_by_text('第二节已经就绪',exact=False).count()==0
    assert not writes,writes;assert not errors,errors;browser.close()
print('PASS Chromium 6 widths, incremental same scene, scene selection/refresh, tutor draft/Escape, historical invalidation; HTTP/SSE mock; writes 0')
