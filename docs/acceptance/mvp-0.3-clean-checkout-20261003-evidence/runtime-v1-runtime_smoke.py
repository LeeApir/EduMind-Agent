"""Verify a pinned clean checkout locally, with no Provider and no media benchmark."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
EXPECTED = 'c7831d1dbf34219f22c6f7da30913002fa46966d'
API = 'http://127.0.0.1:8329'
BASE = 'http://127.0.0.1:4329'
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]


def forbid(*args, **kwargs):
    raise AssertionError('Provider construction forbidden')


def guard_network():
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
            raise AssertionError('External connection forbidden')
        return original(sock, address)

    socket.socket.connect = connect


if len(sys.argv) == 4 and sys.argv[3] == '--api':
    guard_network()
    import app.core.provider_factory as factory
    factory.build_default_provider_gateway = forbid
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=8329, log_level='warning')
    raise SystemExit(0)

import httpx
from playwright.sync_api import sync_playwright
from run_catalog_db_tests import test_environment
from verify_catalog_release import trusted_release, verify
from app.core.database import create_database_engine
from app.services.catalog_package import load_package, read_json
from app.services.catalog_publication import publish_catalog
from sqlalchemy.ext.asyncio import async_sessionmaker

assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == EXPECTED
assert subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True) == ''
assert not (ROOT / '.env').exists()
guard_network()
database = 'edumind_catalog_clean_runtime_' + time.strftime('%H%M%S')
env = test_environment(database)
env['EDUMIND_PRODUCT_MODE'] = 'catalog_only'
env['EDUMIND_API_PROXY_TARGET'] = API
env['EDUMIND_ANIMATION_CACHE_DIR'] = str(OUT / 'runtime-media-unused')
package_dir = ROOT / 'data/course_catalog/linear-v1'
digest, approval_path = trusted_release(package_dir, ROOT / 'data/course_catalog/release-allowlist.json')
assert verify(package_dir, digest, approval_path)['publishable']
package = load_package(package_dir)
result = {'target_commit': EXPECTED, 'database': database, 'manifest_digest': digest,
          'reviewer': 'Lee', 'provider_requests': 0, 'external_attempts': [],
          'page_errors': [], 'assets': [], 'checks': [], 'nodes': [], 'passed': False,
          'media_rendered': False, 'benchmark_rerun': False, 'production_published': False}


def save():
    (OUT / 'runtime-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


def command(cmd, cwd, log):
    with (OUT / log).open('w') as output:
        subprocess.run(cmd, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


command([sys.executable, '-m', 'alembic', 'upgrade', 'head'], ROOT / 'backend', 'runtime-migration.log')


async def seed():
    engine = create_database_engine(env['EDUMIND_DATABASE_URL'])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            release = await publish_catalog(db, package, approval=read_json(approval_path), trusted_digest=digest)
            await db.commit()
            return str(release.id)
    finally:
        await engine.dispose()


release = asyncio.run(seed())
result['release_id'] = release
processes = []
handles = []
started = time.monotonic()
try:
    for cmd, cwd, log in [
        ([sys.executable, str(Path(__file__).resolve()), str(ROOT), str(OUT), '--api'], ROOT / 'backend', 'api-server.log'),
        (['pnpm', 'exec', 'vite', 'preview', '--host', '127.0.0.1', '--port', '4329', '--strictPort'], ROOT / 'web', 'web-server.log'),
    ]:
        handle = (OUT / log).open('w')
        handles.append(handle)
        processes.append(subprocess.Popen(cmd, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True))
    for url in (API + '/health', BASE):
        for _ in range(100):
            assert all(p.poll() is None for p in processes), 'Server exited before ready'
            try:
                response = httpx.get(url, timeout=1)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError('Local server failed to start')
    assert httpx.get(API + '/health').json() == {'status': 'ok'}
    assert httpx.get(API + '/api/runtime').json() == {'mode': 'catalog_only'}
    result['checks'].append('Real loopback API health/runtime and built Vite preview started without Provider key')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)

        def route(request):
            if urlsplit(request.request.url).hostname not in ('127.0.0.1', 'localhost', '::1'):
                result['external_attempts'].append(request.request.url)
                save()
                request.abort()
            else:
                request.continue_()

        context.route('**/*', route)
        page = context.new_page()
        page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
        page.on('response', lambda response: result['assets'].append(response.url.removeprefix(BASE)) if '/assets/' in response.url else None)
        page.goto(BASE, wait_until='networkidle')
        page.get_by_role('heading', name='课程目录', exact=True).wait_for()
        assert page.locator('.catalog-list button').count() == 10
        (OUT / 'initial-dom.html').write_text(page.content())
        page.screenshot(path=str(OUT / 'catalog-before.png'), full_page=True)

        def api(path, method='GET', body=None, csrf=True):
            return page.evaluate('''async ({path,method,body,csrf}) => {
              const headers = {};
              if (method !== 'GET') {
                headers['Content-Type']='application/json';
                headers['Idempotency-Key']=crypto.randomUUID();
                if (csrf) headers['X-CSRF-Token']=(await (await fetch('/api/auth/session')).json()).csrf_token;
              }
              const r=await fetch(path,{method,headers,credentials:'same-origin',body:body===null?undefined:JSON.stringify(body)});
              const text=await r.text(); let value; try {value=JSON.parse(text);} catch {value=text;}
              return {status:r.status,body:value};
            }''', {'path': path, 'method': method, 'body': body, 'csrf': csrf})

        listing = api('/api/catalog')
        assert listing['status'] == 200 and len(listing['body']['releases']) == 1
        assert listing['body']['releases'][0]['digest'] == digest
        # The first actual UI enrollment; inspect its real response rather than fabricate state.
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/catalog/sessions')) as event:
            page.locator('.catalog-list button').first.click()
        assert event.value.status == 201
        unit = event.value.json()['learning_unit_id']
        page.get_by_test_id('explanation-tab').wait_for()
        first_body = api('/api/learning-units/' + unit)['body']
        node = first_body['knowledge_node_id']
        assert first_body['catalog_release_id'] == release and first_body['origin_type'] == 'curated'
        page.get_by_role('button', name='代码', exact=True).click()
        assert page.get_by_test_id('code-tab').locator('code').inner_text() == package.nodes[node]['code']['source']
        page.get_by_role('button', name='练习', exact=True).click()
        for q in package.nodes[node]['exercise']['items']:
            page.get_by_label(q['question'], exact=True).fill(q['answer'])
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/quiz-submissions')) as event:
            page.get_by_role('button', name='提交练习', exact=True).click()
        assert event.value.status == 200
        score = event.value.json()
        assert score['correct_count'] == 3 and score['catalog_assessment']['reason'] == 'first_complete'
        page.get_by_role('region', name='最近一次练习提交回执').wait_for()
        mastery = api('/api/mastery')['body']
        page.get_by_role('button', name='再做一次', exact=True).click()
        for q in package.nodes[node]['exercise']['items']:
            page.get_by_label(q['question'], exact=True).fill(q['answer'])
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/quiz-submissions')) as event:
            page.get_by_role('button', name='提交练习', exact=True).click()
        repeat = event.value.json()
        assert repeat['catalog_assessment']['reason'] == 'repeat' and repeat['mastery_changes'] == []
        assert api('/api/mastery')['body'] == mastery
        page.reload(wait_until='networkidle')
        page.get_by_role('region', name='最近一次练习提交回执').wait_for()
        page.get_by_role('button', name='查看数组 vs 链表预设演示', exact=True).click()
        page.locator('.catalog-demo').wait_for()
        page.reload(wait_until='networkidle')
        page.locator('.catalog-demo').wait_for()
        page.get_by_role('button', name='退出演示，返回学习', exact=True).click()
        page.get_by_test_id('exercise-tab').wait_for(state='visible')
        with page.expect_download() as event:
            page.get_by_role('button', name='下载 Markdown 笔记', exact=True).click()
        notes = Path(event.value.path()).read_text()
        assert 'Lee' in notes and '人工审核课程包' in notes and '预设数组 vs 链表总结' in notes
        result['notes_sha256'] = hashlib.sha256(notes.encode()).hexdigest()
        assert api('/api/path/current?target_node_id=' + node)['status'] == 200
        page.locator('[aria-label="学习路径"]').wait_for()
        result['checks'].append('Built UI: exact C code, fixed quiz 3/3, repeat mastery unchanged, reload receipts/demo, signed notes and path')
        # Read all ten signed node resources over real REST; no performance matrix or media rendering.
        for node_id, content in package.nodes.items():
            enrolled = api('/api/catalog/sessions', 'POST', {'release_id': release, 'node_id': node_id})
            assert enrolled['status'] == 201
            loaded = api('/api/learning-units/' + enrolled['body']['learning_unit_id'])['body']
            assert loaded['catalog_release_id'] == release and loaded['origin_type'] == 'curated'
            resources = loaded['scenes'][0]['resources']
            assert len(resources) == 3
            for resource in resources:
                if resource['type'] == 'exercise':
                    assert len(resource['content']['items']) == 3
                    assert all(set(q) == {'id', 'question'} for q in resource['content']['items'])
                else:
                    assert resource['content'] == content[resource['type']]
            result['nodes'].append({'node_id': node_id, 'resources': 3, 'questions_without_answers': 3})
        assert api('/api/learning-sessions', 'POST', {})['status'] == 409
        assert api('/api/learning-sessions', 'POST', {}, csrf=False)['status'] == 403
        foreign = browser.new_context()
        foreign.route('**/*', route)
        other = foreign.new_page()
        other.goto(BASE, wait_until='networkidle')
        other.get_by_role('heading', name='课程目录', exact=True).wait_for()
        assert other.evaluate('''async path => (await fetch(path)).status''', '/api/learning-units/' + unit) == 404
        foreign.close()
        result['checks'].append('All 10 signed nodes/30 resources/30 hidden answers, dynamic 409, CSRF 403, foreign owner 404')
        page.screenshot(path=str(OUT / 'catalog-after.png'), full_page=True)
        assert result['assets'] and all(path.startswith('/assets/') for path in result['assets'])
        assert result['page_errors'] == result['external_attempts'] == []
        context.close()
        browser.close()
    result['passed'] = True
except Exception as error:
    result['error_type'] = type(error).__name__
    result['error'] = str(error)
    raise
finally:
    import signal
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    for handle in handles:
        handle.close()
    result['servers_stopped'] = all(process.poll() is not None for process in processes)
    result['seconds'] = round(time.monotonic() - started, 3)
    save()
    print(json.dumps(result, ensure_ascii=False))
