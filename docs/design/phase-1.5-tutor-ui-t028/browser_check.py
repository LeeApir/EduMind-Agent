"""Real Chromium / explicit HTTP+SSE synthetic tutor fixtures, no model calls."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t028');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();turns={};writes=[];errors=[];auto=[True]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if (!sessionStorage.getItem('edumind:free:location:owner')) sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'course',course:'c',operation:'gen',version:1,scene:'s'}));""")
    manifest={'course_id':'c','version':1,'plan_id':'p','created_at':'','complete':True,'node_links':[],'scenes':[{'scene_id':'s','title':'指针的方向','scene_version_id':'sv'}]}
    def api(route):
        path=route.request.url.split('/api/')[-1];method=route.request.method
        if method=='POST':writes.append(path)
        if path=='runtime':data={'mode':'dynamic'}
        elif path.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif path=='catalog':data={'status':'not_ready','releases':[]}
        elif path=='free-courses/c/tutor-turns' and method=='POST':
            body=json.loads(route.request.post_data);assert body['acknowledge_assisted_practice'] is True
            tid='turn'+str(len(turns)+1);oid='op'+str(len(turns)+1);turns[oid]={'turn_id':tid,'operation_id':oid,'binding':{k:body[k] for k in ['course_version','scene_id','scene_version_id']},'message':body['message'],'status':'queued','markdown':'<script>合成导师解释，未修改课程</script>','anchor_refs':[],'reason_code':None};data={'operation_id':oid,'turn_id':tid}
        elif '/tutor-turns/' in path:data=next(t for t in turns.values() if t['turn_id']==path.split('/')[-1])
        elif '/operations/' in path:
            oid=path.split('/operations/')[1].split('/')[0]
            if oid!='gen' and path.endswith('/cancel'):
                turns[oid]['status']='cancelled';data={'state':'cancel_requested'}
            elif '/events?' in path:
                if oid in turns and auto[0] and turns[oid]['status']=='queued':
                    turns[oid]['status']='ready';event={'schema_version':'free-course-events-v1','operation_id':oid,'seq':2,'type':'tutor_ready','course_version':1,'payload':{'turn_id':turns[oid]['turn_id']}}
                    route.fulfill(content_type='text/event-stream',body='id: 2\nevent: tutor_ready\ndata: '+json.dumps(event)+'\n\n');return
                route.fulfill(content_type='text/event-stream',body=': synthetic heartbeat\n\n');return
            else:
                state='succeeded' if oid=='gen' or turns[oid]['status'] in ['ready','invalidated'] else turns[oid]['status']
                data={'course_id':'c','operation_id':oid,'kind':'create' if oid=='gen' else 'tutor_turn','state':state,'last_event_id':1 if state=='queued' else 3,'clarification_questions':[],'steps':[],'budget':{'usage_unknown':False}}
        elif path.startswith('free-courses/c/versions/'):
            data={'course_id':'c','course_version':1,'scene_id':'s','scene_version_id':'sv','blocks':[{'kind':'text','anchor_id':'intro','markdown':'原课程正文保持不变。指针保存结点地址。'}],'actions':[]} if '/scenes/' in path else manifest
        elif path=='free-courses/c':data={'course_id':'c','original_goal':'理解链表头插','course_kind':'ai_draft','endorsement':'unendorsed','head':manifest}
        elif path.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5185/api/.*'),api)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5185');page.wait_for_load_state('networkidle')
        page.get_by_role('button',name='有疑问？打开导师区域').click();page.get_by_label('记下问题').fill('请补充解释 next 的作用')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        assert page.get_by_role('button',name='发送本次提问').is_disabled();assert not writes
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(OUT/f'tutor-{width}.png'),full_page=True)
    page.get_by_label('本次上下文涉及的练习将按辅助学习记录',exact=False).check();page.get_by_role('button',name='发送本次提问').click();page.get_by_role('heading',name='AI 补充解释 · 未签核').wait_for()
    assert page.locator('.tutor-answer script').count()==0;assert len(writes)==1
    page.reload();page.wait_for_load_state('networkidle');page.get_by_role('button',name='有疑问？打开导师区域').click();page.get_by_role('heading',name='AI 补充解释 · 未签核').wait_for();assert len(writes)==1
    turns['op1']['status']='invalidated';page.get_by_role('button',name='重新读取本次提问').click();page.get_by_text('已隐藏旧回复',exact=False).wait_for();assert page.get_by_text('<script>合成导师解释',exact=False).count()==0
    page.get_by_role('button',name='开始新问题').click();auto[0]=False;page.get_by_label('记下问题').fill('第二个问题');page.get_by_label('本次上下文涉及的练习将按辅助学习记录',exact=False).check();page.get_by_role('button',name='发送本次提问').click();page.get_by_role('button',name='停止本次提问').click();page.get_by_role('heading',name='本次提问已停止').wait_for()
    assert page.get_by_text('原课程正文保持不变',exact=False).is_visible();assert len(writes)==3;assert not errors,errors
    browser.close()
print('PASS Chromium six widths, explicit consent, durable tutor_ready, escaped reply, GET-only refresh, invalidated body, explicit cancel; synthetic HTTP/SSE only')
