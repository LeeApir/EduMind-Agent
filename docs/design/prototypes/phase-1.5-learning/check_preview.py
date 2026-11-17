"""Real-browser checks of a static design fixture, never product E2E."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
views = ['home', 'plan', 'course', 'graph', 'profile', 'records', 'settings']
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    page.emulate_media(reduced_motion='reduce')
    errors = []
    remote_requests = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: remote_requests.append(request.url)
            if request.url.startswith(('http:', 'https:')) else None)
    page.goto((root / 'index.html').as_uri())
    page.wait_for_load_state('networkidle')

    def view(name):
        page.locator(f'.preview-bar nav [data-view="{name}"]').click()
        assert page.locator(f'#{name}-view').is_visible()

    def no_overflow(width, name):
        metric = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
        assert metric['scroll'] <= width, (width, name, metric)

    view('course')
    page.locator('#next-step').click()
    page.locator('#next-step').click()
    assert '8 → 3 → NULL' in page.locator('#trace-caption').inner_text()
    page.locator('[data-panel="code"]').click()
    assert page.locator('.code-line.highlight').get_attribute('data-line') == '3'
    page.locator('[data-panel="quiz"]').click()
    page.locator('#quiz-form button').click()
    assert '至少' in page.locator('#quiz-feedback').inner_text()
    page.locator('#answer-one').fill('8 → 3 → NULL')
    page.locator('#quiz-form button').click()
    assert '部分作答' in page.locator('#quiz-feedback').inner_text()
    assert 'n->next' not in page.locator('#quiz-feedback').inner_text()
    page.locator('#answer-two').fill('n->next = head;')
    page.locator('#quiz-form button').click()
    assert '暂定比较' in page.locator('#quiz-feedback').inner_text()
    assert '不计正式掌握度' in page.locator('#quiz-feedback').inner_text()
    page.locator('[data-scene="2"]').click()
    assert page.locator('#waiting-title').inner_text() == '这一节暂未完成'
    page.locator('#retry-scene').click()
    assert page.locator('#waiting-title').inner_text() == '重试仍未完成'
    page.locator('[data-scene="5"]').click()
    page.locator('#retry-scene').click()
    assert page.locator('#explain-panel').is_visible()
    page.locator('#report-issue').click()
    assert page.locator('#feedback-dialog').is_visible()
    page.keyboard.press('Escape')
    page.locator('#revise-scene').click()
    page.locator('#start-revision').click()
    assert page.locator('#revision-note').evaluate('(e)=>e===document.activeElement')
    page.locator('#revision-note').fill('用更简单的话解释 next')
    page.locator('#revision-confirm').check()
    page.locator('#start-revision').click()
    assert '旧版' in page.locator('#revision-status').inner_text()
    page.locator('#complete-revision').click()
    assert '版本 2' in page.locator('#course-version-note').inner_text()
    assert page.locator('#answer-one').input_value() == ''
    assert page.locator('#answer-two').input_value() == ''
    page.locator('#course-fixture').select_option('withdrawn')
    assert page.locator('#answer-one').is_disabled()
    assert '停止展示' in page.locator('#quiz-feedback').inner_text()
    page.locator('#course-fixture').select_option('ready')
    page.locator('#suggested-question').click()
    assert not page.locator('#tutor-reply').is_visible()
    page.locator('#tutor-assistance').check()
    page.locator('#suggested-question').click()
    assert '自环' in page.locator('#tutor-reply').inner_text()
    page.locator('#course-fixture').select_option('tutor-invalid')
    assert not page.locator('#tutor-reply').is_visible()
    page.locator('#course-fixture').select_option('ready')

    view('graph')
    page.locator('#graph-list-button').click()
    assert page.locator('#knowledge-list').is_visible()
    page.locator('#knowledge-list [data-node="pointer"]').click()
    assert page.locator('#node-title').inner_text() == 'C 指针'
    page.locator('#node-action').click()
    assert 'C 指针' in page.locator('#goal').input_value()
    view('profile')
    page.locator('#explain-mastery').click()
    assert '不计正式掌握度' in page.locator('#detail-body').inner_text()
    page.keyboard.press('Escape')
    assert page.locator('#explain-mastery').evaluate('(e)=>e===document.activeElement')
    view('records')
    page.locator('#record-filter').select_option('answers')
    assert page.locator('[data-record="courses"]').first.is_hidden()
    page.locator('#open-attempt').click()
    assert '暂定' in page.locator('#detail-title').inner_text()
    page.locator('#detail-confirm').click()
    page.locator('#record-filter').select_option('changes')
    page.locator('#open-withdrawn-attempt').click()
    assert '停止展示' in page.locator('#detail-body').inner_text()
    page.keyboard.press('Escape')
    page.locator('#record-filter').select_option('all')
    page.locator('#restore-course').click()
    assert '不重新生成' in page.locator('#notice').inner_text()
    view('settings')
    page.locator('#preview-connection-test').click()
    assert '仍未验证' in page.locator('#connection-state').inner_text()
    page.locator('#model-form button[type="submit"]').click()
    assert '运行中的配置不变' in page.locator('#model-saved').inner_text()
    assert page.locator('input[type="password"]').is_disabled()
    page.locator('#return-from-settings').click()
    assert page.locator('#course-view').is_visible()
    view('home')
    page.locator('#preferences-button').click()
    assert page.locator('#preferences').is_visible()
    page.locator('#goal-form button[type="submit"]').click()
    page.locator('#edit-plan').click()
    page.locator('#plan-note').fill('多解释 next')
    page.wait_for_timeout(7600)
    assert page.locator('#plan-view').is_visible(), 'Editing must pause auto-entry'
    page.locator('#save-plan').click()
    assert page.locator('#outline-edit').is_visible(), 'Impact acknowledgement required'
    page.locator('#plan-confirm').check()
    page.locator('#save-plan').click()
    page.locator('#enter-course').click()
    assert page.locator('#course-view').is_visible()

    page.goto((root / 'index.html').as_uri() + '#graph')
    page.locator('#graph-view').wait_for(state='visible')
    page.goto((root / 'index.html').as_uri() + '#settings')
    page.locator('#settings-view').wait_for(state='visible')

    view('graph')
    page.locator('.skip-link').focus()
    page.keyboard.press('Enter')
    assert page.locator('#main-content').evaluate('(e)=>e===document.activeElement')
    assert page.locator('#graph-view').is_visible()

    responsive = []
    state_checks = []
    for width in [1440, 1280, 1024, 768, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 960})
        for name in views:
            view(name)
            no_overflow(width, name)
            responsive.append([width, name, 'no overflow'])
            if width in [1440, 390]:
                page.screenshot(path=str(out / f'{name}-{width}.png'), full_page=True)
            if width in [1440, 320]:
                for state in ['loading', 'empty', 'error', 'forbidden', 'invalid']:
                    page.locator('#page-fixture').select_option(state)
                    assert page.locator('#page-state').is_visible()
                    assert page.locator(f'#{name}-view').is_hidden()
                    no_overflow(width, name + ':' + state)
                    state_checks.append([width, name, state])
                page.locator('#state-action').click()
                assert page.locator(f'#{name}-view').is_visible()

    page.set_viewport_size({'width': 390, 'height': 844})
    view('course')
    page.locator('#toggle-directory').click()
    assert page.locator('#course-directory').is_visible()
    page.locator('[data-scene="4"]').click()
    assert page.locator('#course-directory').is_hidden()
    page.locator('#open-tutor').click()
    assert page.locator('#question').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('Escape')
    assert page.locator('#open-tutor').evaluate('(e)=>e===document.activeElement')
    page.locator('#menu-button').click()
    assert page.locator('#global-nav').is_visible()
    page.locator('#global-nav [data-view="settings"]').focus()
    page.keyboard.press('Tab')
    assert page.locator('#close-menu').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('Escape')
    assert page.locator('#global-nav').is_hidden()
    assert page.locator('#menu-button').evaluate('(e)=>e===document.activeElement')
    view('profile')
    page.locator('#edit-profile').focus()
    page.keyboard.press('Enter')
    assert page.locator('#profile-edit-dialog').is_visible()
    page.locator('#profile-self-edit').fill('只学过变量和循环')
    page.locator('#save-profile-edit').click()
    assert '只学过变量' in page.locator('#profile-background').inner_text()
    page.locator('#edit-profile').click()
    page.locator('#save-profile-edit').focus()
    page.keyboard.press('Tab')
    assert page.locator('#close-profile-edit').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('Escape')
    assert page.locator('#edit-profile').evaluate('(e)=>e===document.activeElement')
    outline = page.locator('#edit-profile').evaluate('(e)=>getComputedStyle(e).outlineStyle')
    assert outline != 'none', 'Keyboard focus must be visible'
    assert page.evaluate('matchMedia("(prefers-reduced-motion:reduce)").matches')
    assert not errors, errors
    assert not remote_requests, remote_requests
    result = {'scope': 'static design only; no backend/Provider/product E2E',
              'responsive': responsive, 'state_checks': state_checks,
              'interactions': 'passed: seven-page navigation, trace/code, provisional partial/full quiz, withdrawal, tutor assistance/stale reply, revision, outline confirmation/pause, graph/list/goal, evidence/records, connection status/settings return',
              'keyboard': 'passed: menu loop/Escape, dialog loop/Escape/return, route headings, focus outline, reduced motion',
              'page_errors': errors, 'remote_requests': remote_requests}
    (out / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(f'PASS: {len(responsive)} responsive pages, {len(state_checks)} state checks, interactions/keyboard; no page errors or remote requests')
    browser.close()
