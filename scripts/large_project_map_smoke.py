"""Real isolated API/browser check with a 2000-entry map, plus a view-only 10k stress fixture.

Runs current source through an isolated Vite server; never opens the user's database or VS Code profile.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/qa/large-project-map'
OUTPUT.mkdir(parents=True, exist_ok=True)
opener = build_opener(ProxyHandler({}))


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    api_port, ui_port = free_port(), free_port()
    api_url, ui_url = f'http://127.0.0.1:{api_port}', f'http://127.0.0.1:{ui_port}'

    def request(path, method='GET', body=None):
        req = Request(api_url + '/api' + path, method=method,
                      headers={'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
                      data=json.dumps(body).encode() if body else None)
        with opener.open(req, timeout=20) as response:
            return json.load(response)

    children = []
    with tempfile.TemporaryDirectory(prefix='dashai-large-map-') as data_dir, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        try:
            children.append(subprocess.Popen([sys.executable, '-m', 'server', '--port', str(api_port), '--data-dir', data_dir], cwd=ROOT, stdout=log, stderr=log))
            vite = f"import {{createServer}} from './node_modules/vite/dist/node/index.js'; const server=await createServer({{configFile:false,cacheDir:{json.dumps(str(OUTPUT / 'vite-cache'))},optimizeDeps:{{entries:['index.html'],exclude:['mermaid']}},server:{{host:'127.0.0.1',port:{ui_port},strictPort:true,watch:null,hmr:false,proxy:{{'/api':'{api_url}'}}}}}}); await server.listen();"
            children.append(subprocess.Popen([shutil.which('node') or 'node', '--input-type=module', '-e', vite], cwd=ROOT, stdout=log, stderr=log))
            for url in [api_url + '/api/health', ui_url]:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with opener.open(url, timeout=2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.1)

            project = request('/projects', 'POST', {'name': 'Large map QA', 'reason': 'Isolated UI regression'})
            paths = [f'packages/platform/src/feature-{i:04d}.ts' for i in range(1999)]
            description = lambda title, related: {'title': title, 'summary': 'Published description for scale QA', 'purpose': 'Find semanticneedle reliably', 'workflow': ['Read the permitted snapshot'], 'related_paths': related}
            files = [{'path': 'packages', 'kind': 'directory', 'description': description('Published package description', [])}]
            files += [{'path': path, 'sha256': '1' * 64, **({'description': description('First feature' if i == 0 else 'Last feature', [paths[-1] if i == 0 else paths[0]])} if i in (0, 1998) else {})} for i, path in enumerate(paths)]
            map_path = f"/projects/{project['id']}/map"
            request(map_path, 'PUT', {'expected_version': 0, 'source_revision': 'isolated-2000-entry-snapshot', 'files': files, 'reason': 'Browser scale regression'})
            request(map_path + '/document', 'PATCH', {'expected_version': 1, 'document': {'title': 'Large map documentation', 'sections': ['decisions'], 'diagram_ids': []}, 'reason': 'Limit document composition to the module regression'})
            published = request(map_path)
            assert len(published['files']) == 2000
            measurements = {}
            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(ui_url, timeout=60000)
                page.locator('.sidebar').get_by_role('button', name='Large map QA', exact=False).click()
                page.locator('.project-tabs').get_by_role('button', name='Карта проекта', exact=True).click()
                expect(page.locator('.map-file-article h2')).to_have_text('Published package description', timeout=30000)
                expect(page.get_by_role('treeitem')).to_have_count(1)
                search = page.get_by_label('Найти файл или объяснение', exact=True)
                started = time.monotonic()
                search.fill('feature-')
                expect(page.locator('.map-tree-toolbar')).to_contain_text('Найдено: 1999')
                measurements['search_2000_ms'] = round((time.monotonic() - started) * 1000)
                assert 1 < page.get_by_role('treeitem').count() < 40, page.get_by_role('treeitem').count()
                search.press('ArrowDown')
                tree = page.get_by_role('tree')
                expect(tree).to_be_focused()
                tree.press('End')
                tree.press('Enter')
                expect(page.locator('.map-file-article h2')).to_have_text('Last feature')
                expect(tree).to_be_focused()
                assert page.locator('[aria-selected=true][role=treeitem]').get_attribute('data-path') == paths[-1]
                search.fill('')
                expect(page.locator('[aria-selected=true][role=treeitem]')).to_be_in_viewport()
                page.get_by_role('button', name='Свернуть все папки', exact=True).click()
                expect(page.get_by_role('treeitem')).to_have_count(1)
                page.get_by_role('button', name='Показать выбранный путь', exact=True).click()
                expect(page.locator('[aria-selected=true][role=treeitem]')).to_be_in_viewport()
                tree.focus()
                tree.press('ArrowLeft')
                assert tree.get_attribute('aria-activedescendant') == page.locator('[role=treeitem][data-path="packages/platform/src"]').get_attribute('id')
                tree.press('ArrowLeft')
                expect(page.locator('[role=treeitem][data-path="packages/platform/src"]')).to_have_attribute('aria-expanded', 'false')
                tree.press('ArrowRight')
                expect(page.locator('[role=treeitem][data-path="packages/platform/src"]')).to_have_attribute('aria-expanded', 'true')
                search.fill('semanticneedle')
                expect(page.get_by_role('treeitem')).to_have_count(3)
                search.fill('not-a-real-path-999999')
                expect(page.get_by_text('Пути не найдены', exact=True)).to_be_visible()
                expect(page.locator('.map-file-article h2')).to_have_text('Last feature')
                search.fill('feature-0000')
                page.get_by_role('treeitem').click()
                expect(page.locator('.map-file-article h2')).to_have_text('First feature')
                page.locator('.map-related').get_by_role('button', name=paths[-1], exact=True).click()
                expect(search).to_have_value('')
                expect(page.locator('.map-file-article h2')).to_be_focused()
                expect(page.locator('[aria-selected=true][role=treeitem]')).to_be_in_viewport()
                for width, height in [(1440, 1000), (390, 844), (320, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    search.fill('feature-1998')
                    expect(page.get_by_role('treeitem')).to_have_count(1)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                    page.locator('.map-workspace').scroll_into_view_if_needed()
                    page.screenshot(path=str(OUTPUT / f'map-{width}.png'))
                    if width < 800:
                        page.get_by_role('treeitem').click()
                        expect(page.locator('.map-mobile-tree')).not_to_have_attribute('open', '')
                        expect(page.locator('.map-file-article h2')).to_be_focused()
                    search.fill('')
                assert request(map_path)['version'] == published['version'], 'Navigation must not mutate the map'

                modules_path = f"/projects/{project['id']}/modules"
                adr = 'ADRneedle: use one shared store. <img src=x onerror=alert(1)>'
                request(modules_path + '/decisions', 'PUT', {'expected_version': 0, 'enabled': True, 'content': adr, 'reason': 'Verify real module export'})
                request(modules_path + '/risks', 'PUT', {'expected_version': 0, 'enabled': False, 'content': 'HIDDEN-DOC', 'reason': 'Disabled modules must stay excluded'})
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.locator('.project-tabs').get_by_role('button', name='Документация', exact=True).click()
                expect(page.locator('.map-document-preview')).to_contain_text(adr)
                expect(page.locator('.map-document-preview')).not_to_contain_text('HIDDEN-DOC')
                expect(page.locator('.map-document-preview img')).to_have_count(0)
                with page.expect_download() as downloaded:
                    page.get_by_role('button', name='HTML', exact=True).click()
                html = Path(downloaded.value.path()).read_text(encoding='utf-8')
                assert 'ADRneedle' in html and '&lt;img' in html and '<img' not in html and 'HIDDEN-DOC' not in html
                with page.expect_download() as downloaded:
                    page.get_by_role('button', name='Markdown', exact=True).click()
                assert adr in Path(downloaded.value.path()).read_text(encoding='utf-8')
                page.get_by_label('Номер версии карты', exact=True).fill(str(published['version']))
                page.locator('.map-version').get_by_role('button', name='Открыть', exact=True).click()
                expect(page.locator('.map-document-preview')).to_contain_text('Модули документов не входят в историческую ревизию карты')
                expect(page.locator('.map-document-preview')).not_to_contain_text('ADRneedle')
                with page.expect_download() as downloaded:
                    page.get_by_role('button', name='Markdown', exact=True).click()
                assert 'ADRneedle' not in Path(downloaded.value.path()).read_text(encoding='utf-8')
                page.route('**/api' + modules_path, lambda route: route.fulfill(status=503, json={'detail': 'QA unavailable'}))
                page.get_by_role('button', name='К текущей карте', exact=True).click()
                expect(page.locator('.project-map [role=alert]')).to_contain_text('QA unavailable')
                expect(page.get_by_role('button', name='Markdown', exact=True)).to_be_disabled()
                expect(page.locator('.map-document-preview')).not_to_contain_text('ADRneedle')
                page.unroute('**/api' + modules_path)
                page.get_by_role('button', name='Повторить загрузку модулей', exact=True).click()
                expect(page.locator('.map-document-preview')).to_contain_text(adr)
                expect(page.get_by_role('button', name='Markdown', exact=True)).to_be_enabled()

                # Explicitly synthetic view-only stress: this response is not evidence of API publication capacity.
                synthetic = {**published, 'files': [{'path': f'src/stress-{i:05d}.ts', 'kind': 'file', 'sha256': '1' * 64, 'description': None, 'status': None} for i in range(10000)]}
                page.route('**/api' + map_path, lambda route: route.fulfill(json=synthetic))
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.reload()
                page.locator('.project-tabs').get_by_role('button', name='Карта проекта', exact=True).click()
                expect(page.locator('.map-tree-toolbar')).to_contain_text('Пути: 10000')
                search = page.get_by_label('Найти файл или объяснение', exact=True)
                started = time.monotonic()
                search.fill('stress-')
                expect(page.locator('.map-tree-toolbar')).to_contain_text('Найдено: 10000')
                measurements['synthetic_search_10000_ms'] = round((time.monotonic() - started) * 1000)
                measurements['mounted_rows_10000'] = page.get_by_role('treeitem').count()
                assert measurements['mounted_rows_10000'] < 40
                search.press('ArrowDown')
                page.get_by_role('tree').press('End')
                page.get_by_role('tree').press('Enter')
                expect(page.locator('.map-file-article .map-path')).to_have_text('src/stress-09999.ts')
                assert not errors, errors
                browser.close()
            evidence = {'result': 'PASS', 'real_api_entries': 2000, 'synthetic_view_only_entries': 10000, 'checks': ['bounded DOM', 'collapsed folders', 'semantic and path search', 'End/Enter and arrows', 'selected path reveal', 'related-path navigation clears filters', 'empty result preserves document', 'mobile disclosure and focus', 'no horizontal overflow', 'read navigation does not mutate map', 'enabled document modules in preview and exports', 'HTML text escaping', 'historical map excludes current modules', 'module failure clears stale data and blocks incomplete export'], 'measurements': measurements}
            (OUTPUT / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(evidence, ensure_ascii=False))
        finally:
            for child in reversed(children):
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)


if __name__ == '__main__':
    main()
