"""Real Chromium / explicit HTTP + SSE synthetic fixtures. No model."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t024');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page(); ready=[False];state=['running'];writes=[];errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if (!sessionStorage.getItem('edumind:free:location:owner')) sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'outline',course:'c',operation:'op',version:1,scene:''}));""")
    def api(route):
        path=route.request.url.split('/api/')[-1]
        if path=='runtime':data={'mode':'dynamic'}
        elif path.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif path=='catalog':data={'status':'not_ready','releases':[]}
        elif '/events?' in path:route.fulfill(status=200,content_type='text/event-stream',body=': fixture heartbeat\n\n');return
        elif path.endswith('/cancel'):
            writes.append(path);state[0]='cancelled';data={'state':'cancel_requested'}
        elif path.endswith('/operations') and route.request.method=='POST':writes.append(json.loads(route.request.post_data));data={'course_id':'c','operation_id':'op-new'}
        elif '/operations/' in path:data={'course_id':'c','operation_id':path.split('/operations/')[1],'state':state[0],'kind':'create','last_event_id':1,'base_head_version':None,'head_version':1,'clarification_questions':[],'reason_code':None,'steps':[],'budget':{'attempts_used':1,'attempts_remaining':12,'usage_unknown':False}}
        elif '/impact?' in path:data={'course_id':'c','base_head_version':1,'kind':'adjust_outline','affected_scene_ids':['s'],'requires_outline_adjustment':True,'max_attempts':13,'max_seconds':600,'impact_digest':'a'*64}
        elif '/scenes/' in path:data={'course_id':'c','course_version':1,'scene_id':'s','scene_version_id':'sv','blocks':[{'kind':'text','anchor_id':'intro','markdown':'真实可学的合成讲解，用于浏览器检查。'}],'actions':[]}
        elif path=='free-courses/c':data={'course_id':'c','original_goal':'看懂指针与链表','course_kind':'ai_draft','endorsement':'unendorsed','teaching_language':'zh-CN','code_language':'c','head':{'course_id':'c','version':1,'plan_id':'p','created_at':'','complete':False,'node_links':[],'scenes':[{'scene_id':'s','title':'从一次头插开始','scene_version_id':'sv' if ready[0] else None}]}}
        elif path.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5181/api/.*'),api)
    for width in [1440,850,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5181');page.wait_for_load_state('networkidle');page.get_by_role('heading',name='你的课程大纲').wait_for()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not writes
        page.screenshot(path=str(OUT/f'outline-{width}.png'),full_page=True)
    page.get_by_role('button',name='调整大纲',exact=True).click();page.get_by_label('希望怎样调整').fill('增加前置解释');ready[0]=True
    page.get_by_role('button',name='重新读取进度').click();page.get_by_role('button',name='进入已就绪场景').wait_for();assert page.get_by_label('希望怎样调整').input_value()=='增加前置解释'
    page.get_by_role('button',name='停止当前生成').click();page.get_by_text('已停止',exact=True).wait_for();assert len(writes)==1
    page.get_by_label('我确认全课调整和新操作的影响').check();page.get_by_role('button',name='确认调整',exact=True).click()
    page.get_by_text('真实可学的合成讲解',exact=False).wait_for();assert writes[1]['kind']=='adjust_outline'
    before=len(writes);page.reload();page.wait_for_load_state('networkidle');page.get_by_text('真实可学的合成讲解',exact=False).wait_for();assert len(writes)==before
    assert not errors,errors;browser.close()
print('PASS Chromium:4 widths; GET restore, edit blocks auto navigation, explicit stop/adjust, ready learning; mock HTTP/SSE only')
