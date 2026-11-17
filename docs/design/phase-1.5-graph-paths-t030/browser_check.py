"""Chromium with explicit synthetic HTTP fixtures using the versioned 30-node graph."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t030');OUT.mkdir(exist_ok=True)
graph=json.loads(Path('data/knowledge/phase-1.1.0.json').read_text())
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();writes=[];errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if(!sessionStorage.getItem('edumind:free:location:owner')){sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'graph'}));sessionStorage.setItem('edumind:free:goal:owner',JSON.stringify({goal:'保留我的原目标',language:'c'}));}""")
    saved=[False]
    path={'version':1,'target_node_id':'linked-list-concept','graph_version':graph['graph_version'],'profile_version':1,'mastery_revision_watermark':0,'planner_rule_version':'path-v2','nodes':['c-pointer','linked-list-concept'],'node_details':[{'node_id':n,'score':0,'status':'unseen','mastery_known':False,'cost':1,'recommended_resource':'explanation','estimated_minutes':10} for n in ['c-pointer','linked-list-concept']],'current_node_id':'c-pointer','prerequisite_node_ids':['c-pointer'],'next_node_id':'linked-list-concept','reasons':[{'kind':'prerequisite','summary':'链表需要理解指针关联；建议不改变你的原目标。'}],'changes':{'kind':'initial_plan','trigger':'initial_plan','added_node_ids':['c-pointer','linked-list-concept'],'removed_node_ids':[],'reordered_node_ids':[]},'is_stale':False}
    def api(route):
        endpoint=route.request.url.split('/api/')[-1]
        if route.request.method=='POST':writes.append(endpoint)
        if endpoint=='runtime':data={'mode':'catalog_only'}
        elif endpoint.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif endpoint.startswith('graph'):data=graph
        elif endpoint=='mastery':data={'graph_version':graph['graph_version'],'items':[]}
        elif endpoint=='catalog':data={'status':'ready','releases':[{'id':'r','package_id':'TEST_ONLY','version':'1','digest':'TEST_ONLY','nodes':[{'id':'array','name':'数组','description':'合成签核课程元数据','prerequisites':[]}]}]}
        elif endpoint=='path/plan':saved[0]=True;data=path
        elif endpoint.startswith('path/current'):
            if not saved[0]:route.fulfill(status=404,json={'code':'PATH_NOT_FOUND'});return
            data=path
        elif endpoint.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5187/api/.*'),api)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5187');page.wait_for_load_state('networkidle')
        assert page.locator('svg g[role=button]').count()==30
        page.get_by_role('button',name='节点列表',exact=True).click();assert page.locator('.graph-node-list li').count()==30
        page.get_by_role('button',name='关系图',exact=True).click();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'graph-{width}.png'),full_page=True);assert not writes
    name=next(n['name'] for n in graph['nodes'] if n['id']=='linked-list-concept')
    page.get_by_role('button',name=name,exact=True).click();page.get_by_text('节点存在，尚无对应签核课程。',exact=True).wait_for()
    page.get_by_role('button',name='带入学习目标',exact=True).click();page.get_by_role('heading',name='从图谱带来的目标').wait_for();assert page.get_by_label('这次学习的目标').input_value()=='保留我的原目标';assert not writes
    page.get_by_role('button',name='确认替换目标输入',exact=True).click();assert name in page.get_by_label('这次学习的目标').input_value();assert not writes
    page.get_by_role('button',name='打开导航',exact=True).click();page.get_by_role('button',name='图谱与路径',exact=True).click();page.get_by_role('button',name='明确规划该节点路径',exact=True).click();page.get_by_text('链表需要理解指针关联；建议不改变你的原目标。',exact=True).wait_for();assert writes==['path/plan']
    page.reload();page.wait_for_load_state('networkidle');page.get_by_text('链表需要理解指针关联；建议不改变你的原目标。',exact=True).wait_for();assert writes==['path/plan'];assert not errors,errors
    browser.close()
print('PASS six widths/30 nodes/graph+list/unknown vs course availability/confirmed goal transfer/explicit path plan/GET-only restore; explicit HTTP Mock, zero Provider')
