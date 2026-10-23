"""Real Chromium; explicit HTTP mocks, no provider or database claims."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path('/tmp/edumind-p15-t022'); OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on('pageerror', lambda e: print('PAGEERROR:', e, flush=True))
    page.on('console', lambda m: print('CONSOLE:', m.text, flush=True) if m.type == 'error' else None)
    def api(route):
        path = route.request.url.split('/api/')[-1]
        data = {'mode': 'catalog_only'} if path == 'runtime' else {'user': {'id': 'browser-owner'}, 'csrf_token': 'mock-csrf'} if path.startswith('auth/') else {'status': 'not_ready', 'releases': []} if path == 'catalog' else {}
        route.fulfill(status=200, json=data)
    page.route(re.compile(r'http://127[.]0[.]0[.]1:5179/api/.*'), api)
    for width in [1440, 850, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto('http://127.0.0.1:5179'); page.wait_for_load_state('networkidle')
        page.screenshot(path=str(OUT / 'inspection.png'), full_page=True)
        print(page.locator('body').inner_text()[:1200])
        page.get_by_role('heading', name='课程目录', exact=True).wait_for()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        if width <= 850:
            page.get_by_role('button', name='打开导航').click()
            page.get_by_role('button', name='学习', exact=True).focus()
            page.keyboard.press('Escape')
            assert page.get_by_role('button', name='打开导航').evaluate('(e)=>e===document.activeElement')
        page.screenshot(path=str(OUT / f'shell-{width}.png'), full_page=True)
    browser.close()
print(json.dumps({'widths': [1440,850,390,320], 'source': 'explicit HTTP mocks', 'screenshots': str(OUT)}))
