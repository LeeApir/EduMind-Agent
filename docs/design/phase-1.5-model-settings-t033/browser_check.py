"""Real Chromium; metadata API explicitly mocked, no service probe/Provider sends."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t033');OUT.mkdir(exist_ok=True)
id='00000000-0000-4000-8000-000000000001'
conn={'id':id,'provider_type':'openai-compatible','display_name':'测试云端连接','base_url':'https://provider.example/v1','is_local':False,'enabled':True,'config_version':1,'credential_mode':'persistent','credential_state':'present','credential_expires_at':'2030-01-01T00:00:00Z'}
pref={'task_profile':'default','version':1,'route':{'connection_id':id,'config_version':1,'model_id':'synthetic-text-model','data_categories':['learning_goal']},'fallbacks':[],'state':'available'}
caps={'streaming':True,'structured_output':None,'tool_calling':None,'vision':False,'embedding':None,'tts':False,'asr':False,'source':'declared','version':'cap-v1'}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page();writes=[];errors=[];op=['running']
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script("""if(!sessionStorage.getItem('edumind:free:location:owner'))sessionStorage.setItem('edumind:free:location:owner',JSON.stringify({page:'connections',course:'c',operation:'op',version:1,scene:'s',returnPage:'course'}));""")
    manifest={'course_id':'c','version':1,'plan_id':'p','created_at':'','complete':True,'node_links':[],'scenes':[{'scene_id':'s','title':'原场景','scene_version_id':'sv'}]}
    def api(route):
        endpoint=route.request.url.split('/api/')[-1];method=route.request.method
        if method not in ['GET','HEAD']:
            body=json.loads(route.request.post_data);writes.append((endpoint,method,body))
            assert endpoint in ['providers/connections/'+id,'model-preferences/default'],endpoint
            assert 'secret' not in body and 'temporary_handle' not in body
            if endpoint.startswith('providers/'):
                assert method=='PATCH';conn.update(body);conn['config_version']=2;pref['state']='consent_required'
            else:
                assert method=='PUT' and body['consent_accepted'] is True and body['fallbacks']==[];pref.update(route=body['route'],fallbacks=body['fallbacks'],version=2,state='available')
        if endpoint=='runtime':data={'mode':'catalog_only'}
        elif endpoint.startswith('auth/'):data={'user':{'id':'owner'},'csrf_token':'csrf'}
        elif endpoint=='providers/connections':data={'items':[conn]}
        elif endpoint=='providers/connections/'+id:data=conn
        elif endpoint.endswith('/models'):data={'connection_id':id,'config_version':conn['config_version'],'models':[{'id':'synthetic-text-model','capabilities':caps}],'refreshed_at':'2026-10-23T00:00:00Z'}
        elif endpoint=='model-preferences':data={'preferences':[pref]}
        elif endpoint=='model-preferences/default':data=pref
        elif endpoint=='free-courses/c':data={'course_id':'c','original_goal':'保留原课程配置','course_kind':'ai_draft','endorsement':'unendorsed','head':manifest}
        elif '/operations/' in endpoint:data={'course_id':'c','operation_id':'op','kind':'create','state':op[0],'last_event_id':1,'head_version':1,'base_head_version':None,'clarification_questions':[],'steps':[],'budget':{'usage_unknown':False}}
        elif endpoint.startswith('free-courses/c/versions/'):
            data={'course_id':'c','course_version':1,'scene_id':'s','scene_version_id':'sv','blocks':[{'kind':'text','anchor_id':'intro','markdown':'原课程的准确阅读位置'}],'actions':[]} if '/scenes/' in endpoint else manifest
        elif endpoint.startswith('free-courses?'):data={'items':[],'next_cursor':None}
        elif endpoint=='catalog':data={'status':'not_ready','releases':[]}
        else:route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5190/api/.*'),api)
    def capture(name,width):
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'{name}-{width}.png'),full_page=True)
    for width in [1440,1024,850,620,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5190');page.wait_for_load_state('networkidle');page.get_by_role('heading',name='模型设置',exact=True).wait_for();assert page.get_by_text('已配置并启用',exact=False).is_visible();capture('overview',width)
        page.get_by_role('button',name='管理连接与凭据',exact=True).click();page.get_by_label('连接名称',exact=True).wait_for();capture('connections',width)
        page.get_by_role('button',name='管理档位与数据去向',exact=True).click();page.locator('.preferences-consent').wait_for();capture('preferences',width);assert not writes
    page.get_by_role('button',name='管理连接与凭据',exact=True).click();page.get_by_label('连接名称',exact=True).fill('显式改名的连接');page.locator('#provider-key').fill('TEST_ONLY_FAKE_KEY')
    page.get_by_role('button',name='管理档位与数据去向',exact=True).click();assert page.locator('#provider-key').input_value()==''
    page.get_by_role('button',name='管理连接与凭据',exact=True).click();assert page.get_by_label('连接名称',exact=True).input_value()=='显式改名的连接'
    page.locator('.provider-form').evaluate('(form)=>form.requestSubmit()');page.get_by_text('连接已保存。保存不会测试或下载模型。',exact=True).wait_for();assert len(writes)==1
    page.get_by_role('button',name='管理档位与数据去向',exact=True).click();page.get_by_role('button',name='重新读取设置',exact=True).click();page.wait_for_load_state('networkidle');page.locator('.preferences-consent input').check();page.locator('.preferences-form').evaluate('(form)=>form.requestSubmit()');page.get_by_text('档位已保存',exact=False).wait_for();assert len(writes)==2
    page.get_by_role('button',name='设置概览',exact=True).click();page.wait_for_load_state('networkidle');page.reload();page.wait_for_load_state('networkidle');assert len(writes)==2
    assert page.evaluate("Array.from({length:sessionStorage.length},(_,i)=>sessionStorage.getItem(sessionStorage.key(i))).join('').includes('TEST_ONLY_FAKE_KEY')") is False
    op[0]='succeeded';page.get_by_role('button',name='← 返回原页面',exact=True).click();page.get_by_text('原课程的准确阅读位置',exact=True).wait_for();assert len(writes)==2;assert not errors,errors;browser.close()
print('PASS six widths x overview/connection/preferences, clear unsent secrets, explicit metadata PATCH/consented PUT only, no fallback/probe/generation, exact return after refresh; explicit HTTP Mock')
