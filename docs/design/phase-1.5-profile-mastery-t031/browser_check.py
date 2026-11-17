"""Chromium with explicit synthetic profile/history HTTP, no PG or Provider call."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t031');OUT.mkdir(exist_ok=True)
graph=json.loads(Path('data/knowledge/phase-1.1.0.json').read_text())
u=lambda n:f'00000000-0000-4000-8000-{n:012d}'
profile={'id':u(10),'version':1,'initial_query':'我会一些 C 语法，想弄懂链表','professional_background':{'major':'软件工程'},'knowledge_base':None,'cognitive_style':None,'learning_goals':{'current_topic':'链表'},'error_preferences':None,'engineering_preference':{'code_first':True},'extended_dimensions':None,'evidence':{'learning_goals':[{'source':'learner_statement','confidence':1,'observed_at':'2026-10-23','profile_version':1}]},'updated_at':'2026-10-23'}
reference={'kind':'free_course_attempt','course_id':u(1),'course_version':1,'scene_id':u(2),'scene_version_id':u(3),'exercise_id':u(4),'exercise_version_id':u(5),'attempt_id':u(6)}
revision={'revision':2,'previous_score':.55,'score':0,'status':'unseen','rule_version':'mastery-v1','created_at':'2026-10-23','evidence_summary':[],'recomputed_from_revision':1,'source':{'protocol':'free-course-correction-v1','evidence_id':u(7),'reference':reference}}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();writes=[];errors=[];current=[profile]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if(!sessionStorage.getItem('edumind:free:location:owner'))sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'profile'}));""")
    def api(route):
        endpoint=route.request.url.split('/api/')[-1]
        if route.request.method=='PATCH':
            writes.append((endpoint,json.loads(route.request.post_data)));current[0]={**current[0],**writes[-1][1],'version':2,'evidence':{'learning_goals':[{'source':'manual_correction','observed_at':'2026-10-23','profile_version':2}]}}
        if endpoint=='runtime':data={'mode':'catalog_only'}
        elif endpoint.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif endpoint=='profile/me':data=current[0]
        elif endpoint=='graph':data=graph
        elif endpoint=='mastery':data={'graph_version':graph['graph_version'],'items':[{'knowledge_node_id':'array','previous_score':.55,'score':0,'status':'unseen','revision':2,'rule_version':'mastery-v1','evidence_summary':[]}]}
        elif endpoint.startswith('mastery/nodes/array/revisions'):data={'node_id':'array','items':[revision],'next_before_revision':None}
        elif endpoint.endswith('/attempts/'+u(6)):data={'attempt_id':u(6),'binding':{k:reference[k] for k in ['course_version','scene_id','scene_version_id']},'exercise_id':u(4),'exercise_version_id':u(5),'answers':[{'question_id':u(8),'answer':'<script>我保留的原始回答</script>'}],'completeness':'complete','reliability':'withdrawn','comparison_score':None,'question_results':[],'mastery_effect':'revoked','reason_code':'REVOKED'}
        elif endpoint=='catalog':data={'status':'not_ready','releases':[]}
        elif endpoint.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5188/api/.*'),api)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5188');page.wait_for_load_state('networkidle')
        page.get_by_role('button',name='查看数组依据',exact=True).click();page.get_by_role('button',name='读取原始作答 2',exact=True).click();page.get_by_role('heading',name='原始作答 · 课程 v1',exact=True).wait_for()
        assert page.locator('[aria-label="准确原始作答"] script').count()==0;assert page.get_by_text('贡献已撤销',exact=False).is_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width;assert not writes
        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'profile-{width}.png'),full_page=True)
    page.get_by_role('button',name='纠正学习目标',exact=True).click();page.get_by_label('当前学习目标',exact=True).fill('先理解数组访问');page.get_by_role('button',name='保存本次自述',exact=True).click();page.get_by_text('自述已保存；正式掌握度仍来自有效学习证据。',exact=True).wait_for()
    assert writes==[('profile/me',{'learning_goals':{'current_topic':'先理解数组访问'}})]
    page.reload();page.wait_for_load_state('networkidle');page.get_by_text('用户修正',exact=False).first.wait_for();assert len(writes)==1;assert not errors,errors
    browser.close()
print('PASS six widths, genuine-source labels/unknown mastery, exact revoked attempt and escaped raw input, native self-report correction, GET-only refresh; explicit HTTP Mock only')
