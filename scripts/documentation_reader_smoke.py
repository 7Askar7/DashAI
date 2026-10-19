"""Documentation reader regression against isolated SQLite/API and current Vite source.

All 1684 paths and document contents are synthetic. No user database or profile is opened.
"""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/qa/documentation-reader'
SECTIONS = ['Цель и границы', 'Архитектура и сценарии', 'Описания файлов',
            'Решения и дополнительные документы', 'Проверки и ограничения']
SECTION_IDS = ['intro', 'diagrams', 'files', 'decisions', 'verification']
MODULE_MARKDOWN = '''# Reader heading

## Nested reader heading

###### Deep reader heading

**Bold reader decision** and `inline-reader-code`.

1. Ordered reader step
   - Nested reader detail

- [x] Completed reader check
- [ ] Pending reader check

| Reader column | Result |
| --- | --- |
| Synthetic row | Preserved |

```typescript
const readerMarker = "<literal>";
```

```html
<img src="https://example.invalid/code" onerror="window.__documentationAttack=1">
```

[Safe reader link](https://example.com/reader)
[Mail reader link](mailto:qa@example.com)
[Unsafe script link](javascript:alert%281%29)
[Unsafe encoded link](jav&#x61;script:alert%281%29)
[Unsafe data link](data:text/html,attack)
[Unsafe file link](file:///C:/reader)
[Unsafe command link](command:workbench.action.closeWindow)
[Unsafe VSCode link](vscode://file/reader)
[Unsafe relative link](../README.md)
[Unsafe fragment link](#reader)
![Unfetched image](https://example.invalid/reader.png)

<img src="https://example.invalid/raw" onerror="window.__documentationAttack=1">
<script>window.__documentationAttack=1</script>
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def assert_module_rendered(container):
    expect(container.get_by_role('heading', name='Reader heading', level=3, exact=True)).to_have_count(1)
    expect(container.get_by_role('heading', name='Nested reader heading', level=4, exact=True)).to_have_count(1)
    expect(container.get_by_role('heading', name='Deep reader heading', level=6, exact=True)).to_have_count(1)
    expect(container.locator('strong').filter(has_text='Bold reader decision')).to_have_count(1)
    expect(container.locator('th')).to_have_text(['Reader column', 'Result'])
    expect(container.locator('td')).to_have_text(['Synthetic row', 'Preserved'])
    expect(container.locator('pre code').filter(has_text='const readerMarker')).to_have_text('const readerMarker = "<literal>";\n')
    expect(container.locator('pre code').filter(has_text='https://example.invalid/code')).to_have_count(1)
    expect(container.locator('ol ul li').filter(has_text='Nested reader detail')).to_have_count(1)
    expect(container).to_contain_text('[x] Completed reader check')
    expect(container).to_contain_text('[ ] Pending reader check')
    expect(container.get_by_role('link', name='Safe reader link', exact=True)).to_have_attribute('href', 'https://example.com/reader')
    expect(container.get_by_role('link', name='Safe reader link', exact=True)).to_have_attribute('target', '_blank')
    expect(container.get_by_role('link', name='Safe reader link', exact=True)).to_have_attribute('rel', 'noopener noreferrer')
    expect(container.get_by_role('link', name='Mail reader link', exact=True)).to_have_attribute('href', 'mailto:qa@example.com')
    expect(container.get_by_role('link', name=re.compile('Unsafe|Unfetched'))).to_have_count(0)
    for label in ['Unfetched image', 'Unsafe script link', 'Unsafe encoded link', 'Unsafe data link',
                  'Unsafe file link', 'Unsafe command link', 'Unsafe VSCode link', 'Unsafe relative link', 'Unsafe fragment link']:
        expect(container).to_contain_text(label)
    expect(container.locator('img,script,iframe,input,style')).to_have_count(0)
    expect(container).to_contain_text('<img src="https://example.invalid/raw" onerror="window.__documentationAttack=1">')
    expect(container).to_contain_text('<script>window.__documentationAttack=1</script>')
    expect(container).not_to_contain_text('DISABLED-MODULE-MARKER')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    opener = build_opener(ProxyHandler({}))
    api_port, ui_port = free_port(), free_port()
    api_url, ui_url = f'http://127.0.0.1:{api_port}', f'http://127.0.0.1:{ui_port}'

    def request(path, method='GET', body=None):
        req = Request(api_url + '/api' + path, method=method,
                      headers={'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
                      data=json.dumps(body).encode() if body is not None else None)
        with opener.open(req, timeout=30) as response:
            return json.load(response)

    children = []
    checks = []
    with tempfile.TemporaryDirectory(prefix='dashai-document-reader-') as data_dir, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        try:
            children.append(subprocess.Popen([sys.executable, '-m', 'server', '--port', str(api_port), '--data-dir', data_dir], cwd=ROOT, stdout=log, stderr=log))
            vite = f"import {{createServer}} from './node_modules/vite/dist/node/index.js'; const server=await createServer({{configFile:false,cacheDir:{json.dumps(str(OUTPUT / 'vite-cache'))},optimizeDeps:{{entries:['index.html']}},server:{{host:'127.0.0.1',port:{ui_port},strictPort:true,watch:null,hmr:false,proxy:{{'/api':{{target:'{api_url}',changeOrigin:false}}}}}}}}); await server.listen();"
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

            project = request('/projects', 'POST', {'name': 'Documentation reader QA', 'description': 'Synthetic reader scope, no user project content.', 'reason': 'Isolated reader regression'})
            paths = [f'packages/reader/src/component-{i:04d}.ts' for i in range(1684)]
            paths[1] = 'packages/reader/src/component-0001-' + 'longpath' * 20 + '.ts'
            files = [{'path': path, 'sha256': '1' * 64, **({'description': {
                'title': f'Synthetic reader module {i}', 'summary': f'Summary of synthetic file {i}.',
                'purpose': 'semantic-tail-needle' if i == 1683 else f'Purpose of synthetic file {i}.',
                'workflow': ['workflow-tail-needle' if i == 1683 else f'Read synthetic input {i}.', 'Return the documented result.'],
                'related_paths': []}} if i != 2 else {})} for i, path in enumerate(paths)]
            map_path = f"/projects/{project['id']}/map"
            diagram = {'id': 'reader-flow', 'title': 'Synthetic reader flow', 'notation': 'flowchart',
                       'scope': 'Isolated QA only', 'explanation': 'A reader receives the full document.',
                       'legend': 'Boxes are synthetic actors.', 'source': 'flowchart LR\n Reader --> Document', 'related_paths': [paths[0]]}
            request(map_path, 'PUT', {'expected_version': 0, 'source_revision': 'synthetic-reader-v1', 'files': files, 'diagrams': [diagram], 'reason': 'Publish synthetic reader fixture'})
            request(map_path + '/review', 'POST', {'expected_version': 1, 'path': paths[0], 'reason': 'Exercise human review status with synthetic content'})
            request(map_path, 'PUT', {'expected_version': 2, 'source_revision': 'synthetic-reader-v2',
                                    'files': [{'path': path, 'sha256': ('2' if i == 1 else '1') * 64} for i, path in enumerate(paths)], 'reason': 'Exercise stale description status'})
            document = {'title': 'Synthetic reader handbook', 'context': 'Reader context marker.',
                        'sections': SECTION_IDS, 'diagram_ids': ['reader-flow']}
            request(map_path + '/document', 'PATCH', {'expected_version': 3, 'document': document, 'reason': 'Include all reader sections'})
            published = request(map_path)
            assert len(published['files']) == 1684 and published['version'] == 4
            modules_path = f"/projects/{project['id']}/modules"
            request(modules_path + '/decisions', 'PUT', {'expected_version': 0, 'enabled': True, 'content': MODULE_MARKDOWN, 'reason': 'Exercise safe Markdown rendering'})
            request(modules_path + '/risks', 'PUT', {'expected_version': 0, 'enabled': False, 'content': 'DISABLED-MODULE-MARKER', 'reason': 'Keep disabled documents excluded'})

            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors = []
                external_requests = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.context.on('request', lambda req: external_requests.append(req.url) if 'example.invalid' in req.url else None)
                page.goto(ui_url, timeout=60000)
                page.locator('.sidebar').get_by_role('button', name='Documentation reader QA', exact=False).click()
                page.locator('.project-tabs').get_by_role('button', name='Документация', exact=True).click()
                preview = page.locator('.map-document-preview')
                navigation = page.get_by_role('navigation', name='Оглавление документа', exact=True)
                settings_button = page.get_by_role('button', name='Настроить состав', exact=True)
                settings = page.get_by_role('group', name='Состав документа', exact=True)
                expect(preview).to_be_visible(timeout=30000)
                expect(settings).not_to_be_visible()
                expect(navigation.get_by_role('button')).to_have_count(5)

                def select_section(name):
                    picker = page.get_by_role('combobox', name='Раздел документа', exact=True)
                    if picker.is_visible():
                        picker.focus()
                        picker.select_option(SECTION_IDS[SECTIONS.index(name)])
                        expect(picker).to_be_focused()
                        expect(picker).to_have_value(SECTION_IDS[SECTIONS.index(name)])
                    else:
                        navigation.get_by_role('button', name=name, exact=True).click()
                        expect(preview.get_by_role('heading', level=2)).to_be_focused()
                        expect(navigation.locator('button[aria-current="page"]')).to_have_attribute('aria-label', name)
                    expect(preview.get_by_role('heading', level=2)).to_have_text(name)

                def download(label, filename):
                    try:
                        with page.expect_download(timeout=90000 if label == 'HTML' else 30000) as downloaded:
                            page.get_by_role('button', name=label, exact=True).click()
                    except Exception:
                        page.screenshot(path=str(OUTPUT / 'export-failure.png'))
                        print(json.dumps({'export': label, 'alerts': page.locator('[role=alert]').all_text_contents(), 'page_errors': errors}, ensure_ascii=False), flush=True)
                        raise
                    downloaded.value.save_as(OUTPUT / filename)
                    return (OUTPUT / filename).read_text(encoding='utf-8')

                select_section('Описания файлов')
                entries = preview.locator('details')
                summaries = preview.locator('details > summary')
                expect(entries).to_have_count(30)
                expect(summaries.first).to_contain_text(paths[0])
                expect(summaries.first).to_contain_text('Проверено человеком')
                expect(summaries.nth(1)).to_contain_text('Требует обновления')
                expect(summaries.nth(2)).to_contain_text('Нет описания')
                assert all(path in text for path, text in zip(paths[:30], summaries.all_text_contents()))
                expect(entries.first.get_by_text('Purpose of synthetic file 0.', exact=True)).not_to_be_visible()
                summaries.first.focus()
                summaries.first.press('Enter')
                expect(entries.first.get_by_text('Purpose of synthetic file 0.', exact=True)).to_be_visible()
                expect(entries.first).to_contain_text('Read synthetic input 0.')
                next_page = page.get_by_role('button', name='Следующие файлы', exact=True)
                previous_page = page.get_by_role('button', name='Предыдущие файлы', exact=True)
                expect(previous_page).to_be_disabled()
                next_page.focus()
                next_page.press('Enter')
                expect(summaries.first).to_contain_text(paths[30])
                expect(entries).to_have_count(30)
                assert all(path in text for path, text in zip(paths[30:60], summaries.all_text_contents()))
                assert page.evaluate('document.activeElement.tagName !== "BODY"'), 'Keyboard page navigation lost focus'
                previous_page.focus()
                previous_page.press('Space')
                expect(summaries.first).to_contain_text(paths[0])
                search = page.get_by_label('Поиск по файлам документа', exact=True)
                search.fill('SEMANTIC-TAIL-NEEDLE')
                expect(summaries).to_have_count(1)
                expect(summaries.first).to_contain_text(paths[-1])
                search.fill('workflow-tail-needle')
                expect(summaries).to_have_count(1)
                expect(previous_page).not_to_be_visible()
                expect(next_page).not_to_be_visible()
                search.fill('reader-no-match-999999')
                expect(summaries).to_have_count(0)
                search.fill('component-0000')
                expect(summaries).to_have_count(1)
                checks.append('1684 real API files; bounded 30-row document pages, status labels, native details, keyboard pagination, path/purpose/workflow search')

                # Export from a filtered page before visiting the diagram section: all content must survive.
                markdown = download('Markdown', 'reader.md')
                html = download('HTML', 'reader.html')
                for content in (markdown, html):
                    assert paths[0] in content and paths[-1] in content
                    assert all(title in content for title in SECTIONS)
                    assert 'DISABLED-MODULE-MARKER' not in content
                assert sum(f'### {path}\n' in markdown for path in paths) == 1684
                assert '<svg' in html and 'Content-Security-Policy' in html and '<script' not in html and '<img' not in html
                assert MODULE_MARKDOWN.strip() in markdown
                exported = page.context.new_page()
                exported.goto((OUTPUT / 'reader.html').as_uri())
                assert_module_rendered(exported.locator('section').filter(has=exported.get_by_role('heading', name='Reader heading', exact=True)).last)
                assert exported.locator('h3').filter(has_text=re.compile(r'^packages/reader/')).count() == 1684
                exported.close()
                page.evaluate('''() => { window.__readerPrint = null; window.print = () => {
                    const article = document.querySelector('.doc-print-content');
                    window.__readerPrint = article ? {html: article.innerHTML, text: article.textContent,
                        files: [...article.querySelectorAll('h3')].filter(h => h.textContent.startsWith('packages/reader/')).length} : null;
                }; }''')
                page.get_by_role('button', name='Печать / PDF', exact=True).click()
                page.wait_for_function('window.__readerPrint !== null')
                printed = page.evaluate('window.__readerPrint')
                assert paths[0] in printed['text'] and paths[-1] in printed['text']
                assert all(title in printed['text'] for title in SECTIONS) and '<svg' in printed['html']
                assert printed['files'] == 1684
                page.emulate_media(media='print')
                expect(page.locator('.doc-print-content')).to_be_visible()
                expect(navigation).not_to_be_visible()
                page.emulate_media(media='screen')
                page.evaluate('window.dispatchEvent(new Event("afterprint"))')
                expect(page.locator('.doc-print-content')).to_have_count(0)
                checks.append('filtered-page Markdown/HTML exports and print snapshot retain all 1684 files and every selected section, including an unvisited Mermaid diagram')

                select_section('Решения и дополнительные документы')
                assert_module_rendered(preview)
                assert page.evaluate('window.__documentationAttack === undefined')
                checks.append('same semantic Markdown in preview/export: headings, strong, table, fenced code; raw HTML literal; unsafe links/images inactive; disabled module excluded')
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                    select_section('Описания файлов')
                    search.fill('')
                    expect(entries).to_have_count(30)
                    if entries.nth(1).get_attribute('open') is None:
                        summaries.nth(1).click()
                    expect(entries.nth(1).get_by_text('Purpose of synthetic file 1.', exact=True)).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Horizontal page overflow at {width}'
                    preview.scroll_into_view_if_needed()
                    page.screenshot(path=str(OUTPUT / f'reader-files-{width}.png'))
                    select_section('Решения и дополнительные документы')
                    assert_module_rendered(preview)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Markdown page overflow at {width}'
                    page.screenshot(path=str(OUTPUT / f'reader-markdown-{width}.png'))
                assert request(map_path)['version'] == published['version'], 'Reading, filtering and exporting must not mutate the document'
                checks.append('desktop/mobile 390 px navigation and long-path reflow; reading and exports do not mutate map')

                settings_button.click()
                expect(settings).to_be_visible()
                settings.get_by_label('Название', exact=True).fill('Unsaved reader title')
                select_section('Цель и границы')
                expect(settings.get_by_label('Название', exact=True)).to_have_value('Unsaved reader title')
                assert page.evaluate('''() => {const event = new Event('beforeunload', {cancelable:true}); window.dispatchEvent(event); return event.defaultPrevented;}''')
                dialogs = []
                page.once('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
                page.locator('.project-tabs').get_by_role('button', name=re.compile('^Доска')).click()
                assert dialogs and 'несохран' in dialogs[0].lower()
                expect(preview).to_be_visible()
                expect(settings.get_by_label('Название', exact=True)).to_have_value('Unsaved reader title')
                settings.get_by_label('Причина сохранения', exact=True).fill('Persist the synthetic reader title')
                settings.get_by_role('button', name='Сохранить состав', exact=True).click()
                expect(settings.get_by_role('button', name='Сохранить состав', exact=True)).to_be_disabled()
                expect(settings.get_by_label('Название', exact=True)).to_be_enabled()
                assert request(map_path)['document']['title'] == 'Unsaved reader title'
                assert not page.evaluate('''() => {const event = new Event('beforeunload', {cancelable:true}); window.dispatchEvent(event); return event.defaultPrevented;}''')
                checks.append('composition is collapsed by default; section reading preserves drafts; leave/beforeunload guards; successful save clears dirty guard')

                page.locator('details.doc-source > summary').click()
                page.get_by_label('Номер версии карты', exact=True).fill(str(published['version']))
                page.locator('.map-version').get_by_role('button', name='Открыть', exact=True).click()
                if not settings.is_visible():
                    settings_button.click()
                expect(settings.get_by_label('Название', exact=True)).to_be_disabled()
                select_section('Решения и дополнительные документы')
                expect(preview).to_contain_text('Модули документов не входят в историческую ревизию карты')
                expect(preview).not_to_contain_text('Reader heading')
                historical = download('Markdown', 'reader-historical.md')
                assert 'Reader heading' not in historical and paths[-1] in historical
                page.route('**/api' + modules_path, lambda route: route.fulfill(status=503, json={'detail': 'Reader QA modules unavailable'}))
                page.get_by_role('button', name='К текущей карте', exact=True).click()
                expect(page.locator('.project-map [role=alert]')).to_contain_text('Reader QA modules unavailable')
                for label in ('Markdown', 'HTML', 'Печать / PDF'):
                    expect(page.get_by_role('button', name=label, exact=True)).to_be_disabled()
                expect(preview).not_to_contain_text('Reader heading')
                page.unroute('**/api' + modules_path)
                page.get_by_role('button', name='Повторить загрузку модулей', exact=True).click()
                assert_module_rendered(preview)
                expect(page.get_by_role('button', name='HTML', exact=True)).to_be_enabled()
                checks.append('historical composition read-only, current modules excluded from historical exports; module errors clear stale content and block incomplete export until retry')
                assert not errors, errors
                assert not external_requests, external_requests
                browser.close()
            evidence = {'result': 'PASS', 'fixture': '1684 synthetic files published through real isolated HTTP API',
                        'frontend': 'current Vite source', 'backend': 'real isolated SQLite and HTTP API',
                        'page_size': 30, 'viewports': [1440, 390], 'checks': checks, 'page_errors': errors, 'external_content_requests': external_requests,
                        'synthetic': ['module API 503 response', 'window.print captures the full print document without opening a system dialog']}
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
