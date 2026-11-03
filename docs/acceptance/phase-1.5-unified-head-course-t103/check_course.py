"""Exercise the complete fixed lesson in Chromium; no model calls or C execution."""
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def main():
    data = json.loads((OUT / 'lesson.json').read_text())
    manifest = json.loads((OUT / 'manifest.json').read_text())
    for entry in manifest['sources'].values():
        assert hashlib.sha256((ROOT / entry['path']).read_bytes()).hexdigest() == entry['sha256']
    for name, digest in manifest['outputs'].items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest
    # Independent expectations for this example, rather than engine self-agreement.
    assert data['states'][-1]['caller_head'] == 't1'
    assert data['states'][-1]['nodes'] == {'i0':{'data':9,'next':None},'t0':{'data':1,'next':'i0'},'t1':{'data':2,'next':'t0'}}
    assert [q['answer_key'] for q in data['questions']] == ['t1', 'terminated', [2,1,9], 0]
    errors, requests = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1280,'height':900})
        page.on('pageerror',lambda err: errors.append(str(err)))
        page.on('request',lambda req: requests.append(req.url) if req.url.startswith(('http:','https:')) else None)
        page.goto((OUT/'course.html').as_uri(),wait_until='networkidle')
        assert '本例的可知前缀也是完整遍历结果' in page.locator('#reading').inner_text()
        assert '补入两次成功判空展示' in page.locator('#reading').inner_text()
        assert page.locator('.line').count() == len(data['code'].splitlines())
        assert page.locator('#prev').is_disabled()
        for index, frame in enumerate(data['frames']):
            if index:
                page.locator('#next').click()
            assert page.locator('#progress').get_attribute('data-cursor') == str(index)
            state = data['states'][frame['state_index']]
            assert json.loads(page.locator('#state').text_content()) == state
            active = page.locator('.line.active')
            assert active.count() == int(frame['line'] is not None)
            if frame['line'] is not None:
                assert active.get_attribute('data-line') == str(frame['line'])
            if frame['origin'] == 'assistant_success_check':
                assert frame['line'] == 5
                assert 'p == NULL 为假' in page.locator('#step-note').inner_text()
            if state['phase'] in ('initial','caller'):
                assert '不在作用域' in page.locator('#vars').inner_text()
            assert page.locator('.node').count() == len(state['nodes'])
        assert page.locator('#chain').inner_text() == 'caller_head → t1(2) → t0(1) → i0(9) → NULL'
        assert page.locator('#next').is_disabled()
        page.locator('#prev').click()
        assert page.locator('#progress').get_attribute('data-cursor') == '11'
        page.locator('#reset').click()
        assert page.locator('#progress').get_attribute('data-cursor') == '0'
        page.locator('#play').click()
        page.wait_for_function("() => document.querySelector('#progress').dataset.cursor !== '0'")
        page.locator('#pause').click()
        paused = page.locator('#progress').get_attribute('data-cursor')
        page.wait_for_timeout(1200)
        assert page.locator('#progress').get_attribute('data-cursor') == paused
        page.locator('#play').click()
        page.locator('#reset').click()
        page.wait_for_timeout(1200)
        assert page.locator('#progress').get_attribute('data-cursor') == '0'
        page.locator('#play').click()
        page.wait_for_function("() => document.querySelector('#progress').dataset.cursor === '12'",timeout=17000)
        assert page.locator('#pause').is_disabled()
        assert page.locator('#play').is_disabled()
        assert 'free(caller_head)' in page.locator('#cleanup').inner_text()
        for i, value in enumerate(['t1','terminated','[2, 1, 9]','0']):
            q = page.locator('.question').nth(i)
            q.get_by_role('button').click()
            assert '请先输入' in q.locator('.feedback').inner_text()
            q.locator('input').fill('wrong')
            q.get_by_role('button').click()
            assert '回答正确' not in q.locator('.feedback').inner_text()
            q.locator('input').fill(value)
            q.locator('input').press('Enter')
            assert q.get_attribute('data-correct') == 'true'
            q.locator('summary').click()
            assert data['questions'][i]['explanation'] in q.locator('.explanation').inner_text()
        assert page.locator('#lesson-status').inner_text() == '已答对 4 / 4 题'
        page.locator('#answer-0').fill('i0')
        assert page.locator('#lesson-status').inner_text() == '已答对 3 / 4 题'
        page.locator('#answer-0').fill('t1')
        page.locator('#answer-0').press('Enter')
        page.locator('#reset').click()
        assert page.locator('#lesson-status').inner_text() == '已答对 4 / 4 题'
        page.locator('#next').focus()
        page.keyboard.press('Enter')
        assert page.locator('#progress').get_attribute('data-cursor') == '1'
        page.screenshot(path='/private/tmp/edumind-t103-desktop.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.locator('#next').click()
        page.locator('#reset').click()
        page.screenshot(path='/private/tmp/edumind-t103-mobile.png',full_page=True)
        assert not requests and not errors, (requests,errors)
        browser.close()
    result = {'browser':'Chromium (Python Playwright)','checks':['source/output hashes; original code/state/action validation at build','independent final chain and four answers','13 synchronized frames / all code highlights / two NULL checks / scopes','play, pause, each step, previous, reset while playing, automatic completion','four blank, wrong, correct responses and explanations; editing invalidates feedback','keyboard Enter, 390px mobile layout, desktop/mobile screenshots'], 'page_errors':errors,'http_requests':requests,'new_provider_calls':0,'screenshots':['/private/tmp/edumind-t103-desktop.png','/private/tmp/edumind-t103-mobile.png'],'course_sha256':hashlib.sha256((OUT/'course.html').read_bytes()).hexdigest()}
    (OUT/'browser-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
