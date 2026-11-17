"""Chromium checks with explicit synthetic HTTP fixtures."""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/edumind-p15-t023');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(); writes=[]; mode=['catalog_only']; fail=[False]
    def api(route):
        path=route.request.url.split('/api/')[-1]
        if path=='runtime': data={'mode':mode[0]}
        elif path.startswith('auth/'): data={'user':{'id':'mock-owner'},'csrf_token':'mock-csrf'}
        elif path.startswith('free-courses') and route.request.method=='POST':
            writes.append(route.request.headers['idempotency-key'])
            if fail[0]: route.abort(); return
            data={'course_id':'mock-course','operation_id':'mock-operation'}
        elif path.startswith('free-courses'): data={'items':[],'next_cursor':None}
        elif path=='catalog': data={'status':'not_ready','releases':[]}
        else: route.fulfill(status=503,json={'code':'MOCK_UNAVAILABLE'});return
        route.fulfill(json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5180/api/.*'),api)
    for width in [1440,850,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:5180');page.wait_for_load_state('networkidle')
        page.get_by_label('这次学习的目标').fill('弄懂链表的指针')
        page.get_by_role('button',name='组织我的课程').click(); assert page.get_by_role('alert').inner_text().startswith('当前只开放')
        assert not writes
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/f'home-{width}.png'),full_page=True)
    mode[0]='dynamic';fail[0]=True;page.reload();page.wait_for_load_state('networkidle')
    page.get_by_role('button',name='组织我的课程').click();page.get_by_role('alert').wait_for()
    page.reload();page.wait_for_load_state('networkidle'); assert page.get_by_label('这次学习的目标').input_value()=='弄懂链表的指针'
    fail[0]=False;page.get_by_role('button',name='组织我的课程').click();page.get_by_text('课程请求已保存',exact=False).wait_for()
    assert len(writes)==2 and writes[0]==writes[1]
    browser.close()
print('PASS: Chromium 4 widths, unavailable/no POST, failure/refresh/idempotency; explicit mock; Provider 0')
