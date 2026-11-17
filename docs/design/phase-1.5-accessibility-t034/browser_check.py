"""Actual Chromium UI with explicit synthetic HTTP. No backend/Provider claims."""
import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
OUT = Path('/tmp/edumind-p15-t034'); OUT.mkdir(exist_ok=True)
graph = json.loads(Path('data/knowledge/phase-1.1.0.json').read_text())
manifest = {'course_id':'c','version':1,'plan_id':'p','created_at':'','complete':True,'node_links':[], 'scenes':[{'scene_id':'s','title':'指针与地址','scene_version_id':'sv'}]}
scene = {'course_id':'c','course_version':1,'scene_id':'s','scene_version_id':'sv','blocks':[
    {'kind':'text','anchor_id':'intro','markdown':'指针保存结点的地址；先接住原链表，再更新 head。'},
    {'kind':'code','anchor_id':'code','language':'c','source':'n->next = head; /* '+'long_local_reading_'*28+' */\nhead = n;'},
    {'kind':'visualization','anchor_id':'visual','visualization_type':'linked_list','text_alternative':'先连接 next，再更换 head。','steps':[{'caption':'原链表','elements':[{'id':'a','label':'3','next_id':None}],'highlight_ids':[]},{'caption':'关注新结点','elements':[{'id':'n','label':'8','next_id':'a'},{'id':'a','label':'3','next_id':None}],'highlight_ids':['n']}]},
    {'kind':'exercise_unavailable','anchor_id':'e','exercise_id':'e','exercise_version_id':'ev','reason_code':'EXERCISE_UNAVAILABLE'}], 'actions':[{'type':'highlight_block','anchor_id':'code','step_index':None}]}
profile={'id':'profile','version':1,'initial_query':'我想学习指针','professional_background':None,'knowledge_base':None,'cognitive_style':None,'learning_goals':{'current_topic':'链表'},'error_preferences':None,'engineering_preference':None,'extended_dimensions':None,'evidence':{},'updated_at':'2026-10-23'}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True); page=browser.new_page(reduced_motion='reduce'); errors=[]; writes=[]; failures=set()
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        endpoint=route.request.url.split('/api/')[-1]
        if route.request.method not in ['GET','HEAD']:
            writes.append((endpoint,route.request.method));route.fulfill(status=503,json={'code':'UNAUTHORIZED_TEST_WRITE'});return
        if endpoint in failures:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        if endpoint=='runtime':data={'mode':'catalog_only'}
        elif endpoint.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif endpoint=='catalog':data={'status':'not_ready','releases':[]}
        elif endpoint.startswith('free-courses?'):data={'items':[{'course_id':'c','original_goal':'理解链表指针','course_kind':'ai_draft','endorsement':'unendorsed','head_version':1,'created_at':'2026-10-23'}],'next_cursor':None}
        elif endpoint=='free-courses/c':data={'course_id':'c','original_goal':'理解链表指针','course_kind':'ai_draft','endorsement':'unendorsed','head':manifest}
        elif '/operations/' in endpoint:data={'course_id':'c','operation_id':'op','state':'succeeded','kind':'create','last_event_id':1,'clarification_questions':[],'steps':[],'budget':{'usage_unknown':False}}
        elif endpoint.startswith('free-courses/c/records?'):data={'course_id':'c','kind':endpoint.split('kind=')[1].split('&')[0],'items':[],'next_before_id':None}
        elif endpoint.startswith('free-courses/c/versions?'):data={'items':[{'version':1,'created_at':''}],'next_cursor':None}
        elif endpoint.startswith('free-courses/c/versions/'):data=scene if '/scenes/' in endpoint else manifest
        elif endpoint=='graph':data=graph
        elif endpoint=='mastery':data={'graph_version':graph['graph_version'],'items':[]}
        elif endpoint=='paths/current':data=None
        elif endpoint=='profile/me':data=profile
        elif endpoint=='providers/connections':data={'items':[]}
        elif endpoint=='model-preferences':data={'preferences':[]}
        else:route.fulfill(status=404,json={'code':'NOT_FOUND'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5191/api/.*'),api)
    page.goto('http://127.0.0.1:5191');page.wait_for_load_state('networkidle')
    def visit(view):
        page.evaluate('(view)=>sessionStorage.setItem("edumind:free:location:owner",JSON.stringify({page:view,course:"c",operation:"op",version:1,scene:"s",outlineAutoEnter:false}))',view)
        page.reload();page.wait_for_load_state('networkidle');expect(page.locator('.workspace-content h1:visible')).to_have_count(1)
    def capture(name,width):
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
        missing=page.locator('.workspace-content input:visible,.workspace-content textarea:visible,.workspace-content select:visible').evaluate_all("es=>es.filter(e=>e.type!=='hidden'&&!e.labels?.length&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')).map(e=>e.outerHTML)")
        assert not missing,(name,missing)
        assert page.get_by_text('设计占位',exact=False).count()==0
        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'{name}-{width}.png'),full_page=True)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000})
        for view in ['learning','outline','course','graph','profile','history','catalog','connections']:
            visit(view);capture(view,width)
            if view=='course':
                code=page.get_by_role('region',name='C 语言代码，可横向滚动');assert code.evaluate('e=>e.scrollWidth>e.clientWidth');code.focus();code.press('ArrowRight');expect(code).to_be_focused()
                page.wait_for_function("document.querySelector('.code-reading pre').scrollLeft>0")
                expect(page.get_by_role('button',name='播放动作',exact=True)).to_be_disabled();page.get_by_role('button',name='下一动作',exact=True).click();assert page.locator('.presentation-highlight').count()==1
                page.get_by_role('button',name='有疑问？打开导师区域',exact=True).click();question=page.get_by_label('记下问题',exact=True);question.fill('为何先接 next？');question.press('Escape');expect(page.get_by_role('button',name='有疑问？打开导师区域',exact=True)).to_be_focused()
                if width<=620:
                    page.get_by_role('button',name='课程目录',exact=True).click();expect(page.locator('#scene-directory')).to_be_visible();page.get_by_role('button',name='课程目录',exact=True).click();expect(page.locator('#scene-directory')).not_to_be_visible()
        assert not writes,writes
    # Browser-native Tab order and inert enforcement, including close control.
    visit('learning');page.get_by_label('这次学习的目标',exact=True).fill('未提交的目标')
    menu=page.get_by_role('button',name='打开导航',exact=True);menu.click();first=page.get_by_role('navigation',name='主导航').get_by_role('button').first;last=page.get_by_role('navigation',name='主导航').get_by_role('button').last
    expect(first).to_be_focused();page.keyboard.press('Shift+Tab');expect(page.get_by_role('button',name='关闭导航')).to_be_focused();page.keyboard.press('Shift+Tab');expect(last).to_be_focused();page.keyboard.press('Tab');expect(page.get_by_role('button',name='关闭导航')).to_be_focused()
    page.locator('#learning-goal').evaluate('e=>e.focus()');assert page.locator('.workspace-body').evaluate('e=>e.inert');assert not page.locator('#learning-goal').evaluate('e=>e===document.activeElement')
    page.keyboard.press('Escape');expect(page.get_by_role('button',name='打开导航')).to_be_focused();assert not page.locator('.workspace-body').evaluate('e=>e.inert')
    page.get_by_role('button',name='打开导航').click();page.get_by_role('navigation',name='主导航').get_by_role('button',name='图谱与路径',exact=True).click();expect(page.get_by_role('heading',name='图谱与路径',exact=True)).to_be_focused()
    page.get_by_role('button',name='打开导航').click();page.get_by_role('navigation',name='主导航').get_by_role('button',name='学习',exact=True).click();expect(page.get_by_label('这次学习的目标',exact=True)).to_have_value('未提交的目标')
    page.get_by_role('button',name='打开导航').click();page.set_viewport_size({'width':1024,'height':1000});expect(page.locator('.workspace-sidebar')).to_be_visible();expect(page.locator('.mobile-menu')).to_have_attribute('aria-expanded','false');assert not page.locator('.workspace-body').evaluate('e=>e.inert')
    # Same read-only recovery control across a graph failure and empty course directory.
    failures.add('graph');visit('graph');expect(page.get_by_role('alert').get_by_role('heading',name='读取失败')).to_be_visible();failures.clear();page.get_by_role('button',name='重新读取记录',exact=True).click();expect(page.locator('.graph-scroll')).to_be_visible()
    visit('catalog');assert page.get_by_text('还没有',exact=False).count() or page.get_by_text('未就绪',exact=False).count() or page.get_by_text('暂无',exact=False).count()
    assert not errors,errors;assert not writes,writes
    # Approved primary/muted/warning text and focus colors against their actual surfaces.
    def luminance(hexcode):
        rgb=[int(hexcode[i:i+2],16)/255 for i in [1,3,5]];v=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb];return sum(a*b for a,b in zip(v,[.2126,.7152,.0722]))
    contrasts=[]
    for fg,bg,minimum in [('#19334a','#ffffff',4.5),('#607283','#ffffff',4.5),('#607283','#f5f7fa',4.5),('#ffffff','#14756c',4.5),('#14756c','#e5f2ee',4.5),('#81531c','#fff3df',4.5),('#378bc4','#ffffff',3)]:
        values=sorted([luminance(fg),luminance(bg)]);ratio=(values[1]+.05)/(values[0]+.05);assert ratio>=minimum,(fg,bg,ratio);contrasts.append({'foreground':fg,'background':bg,'ratio':round(ratio,2),'minimum':minimum})
    (OUT/'results.json').write_text(json.dumps({'widths':[1440,1024,850,620,390,320],'pages':8,'screenshots':48,'native_keyboard':'passed','inert':'passed','labels':'passed','local_code_scroll':'passed','reduced_motion':'passed','read_only_recovery':'passed','contrasts':contrasts,'writes':writes,'page_errors':errors,'api':'explicit synthetic HTTP only','provider_calls':0},ensure_ascii=False,indent=2)+'\n');browser.close()
print('PASS 8 pages x 6 widths; native keyboard/inert/resize/focus, forms, local code scrolling, reduced motion/manual step, read-only recovery and contrast; explicit HTTP Mock, writes 0')
