"""Check the standalone design prototype without the application or its store."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'qa' / 'project-map'
ARTIFACTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    executable = os.environ.get('AGENTBOARD_BROWSER')
    if not executable and os.name == 'nt':
        available = sorted(
            (Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'),
            key=lambda path: int(path.parents[1].name.split('-')[-1]),
        )
        executable = str(available[-1]) if available else None
    browser = p.chromium.launch(executable_path=executable)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors, network = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: network.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
    page.goto((ROOT / 'docs/design/project-map.html').as_uri())
    expect(page.locator('#file-title')).to_have_text('app.py')
    assert page.locator('.brand img').evaluate('(img) => img.complete && img.naturalWidth > 0')
    page.locator('.file-row[data-file="src/App.tsx"]').click()
    expect(page.locator('#file-title')).to_have_text('App.tsx')
    expect(page.locator('#file-title')).to_be_focused()
    page.locator('#file-search').fill('несуществующий-файл-999')
    expect(page.locator('.file-row')).to_have_count(0)
    expect(page.locator('#tree-empty')).to_be_visible()
    page.locator('#file-search').fill('транзакц')
    expect(page.locator('.file-row')).to_have_count(1)
    expect(page.locator('.file-row')).to_have_attribute('data-file', 'server/app.py')
    page.locator('#file-search').fill('единые правила')
    expect(page.locator('.file-row')).to_have_count(1)
    page.locator('.file-row').click()
    page.locator('#file-search').fill('')
    for state, text in [('stale', 'Исходник изменился'), ('empty', 'Здесь появится'), ('loading', 'Агент готовит'), ('error', 'Не удалось получить')]:
        page.locator('#state-select').select_option(state)
        expect(page.locator('#file-document')).to_contain_text(text)
    page.locator('#state-select').select_option('draft')
    page.locator('[data-show-node="api"]').click()
    expect(page.locator('#architecture-view')).to_be_visible()
    expect(page.locator('[data-node="api"]')).to_have_attribute('aria-pressed', 'true')
    page.locator('[data-node="mcp"]').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#node-title')).to_have_text('MCP-коннектор')
    page.locator('#node-detail [data-file="connectors/mcp_server.py"]').click()
    expect(page.locator('#file-title')).to_have_text('mcp_server.py')
    expect(page.locator('#file-title')).to_be_focused()
    page.locator('#how-toggle').click()
    expect(page.locator('#how-panel')).to_be_visible()
    page.locator('#how-toggle').click()
    page.reload()

    # The document contains the selected models and sections, not just a mock export button.
    page.locator('[data-view="architecture"]').click()
    for notation in ['context', 'containers', 'components', 'sequence', 'states', 'data', 'flow']:
        page.locator('#notation-select').select_option(notation)
        expect(page.locator(f'#notation-view svg[data-notation="{notation}"]')).to_be_visible()
        expect(page.locator('#mermaid-source')).not_to_have_text('')
        page.locator('#notation-select').focus()
        page.screenshot(path=str(ARTIFACTS / f'notation-{notation}-1440.png'), full_page=True)
    page.locator('#diagram-source-toggle').click()
    expect(page.locator('#diagram-source')).to_be_visible()
    with page.expect_download() as downloaded:
        page.locator('#download-source').click()
    assert Path(downloaded.value.path()).read_text(encoding='utf-8').startswith('flowchart TD')
    page.locator('#include-diagram').click()
    expect(page.locator('#include-diagram')).to_be_disabled()
    page.locator('[data-view="documentation"]').click()
    expect(page.locator('[data-diagram="flow"]')).to_be_checked()
    expect(page.locator('#document-preview svg[data-notation="flow"]')).to_have_count(1)
    page.locator('#document-name').fill('Документ <img src=x onerror=alert(1)>')
    expect(page.locator('#document-preview h1')).to_have_text('Документ <img src=x onerror=alert(1)>')
    expect(page.locator('#document-preview img')).to_have_count(0)
    page.locator('#document-name').fill('DashAI — документация проекта')
    page.locator('[data-section="files"]').uncheck()
    page.locator('[data-diagram="sequence"]').uncheck()
    expect(page.locator('#document-preview #doc-files')).to_have_count(0)
    expect(page.locator('#document-preview svg[data-notation="sequence"]')).to_have_count(0)
    with page.expect_download() as downloaded:
        page.locator('#export-markdown').click()
    markdown = Path(downloaded.value.path()).read_text(encoding='utf-8')
    assert '```mermaid\nflowchart' in markdown and 'erDiagram' in markdown
    assert '## Описания файлов' not in markdown and 'sequenceDiagram' not in markdown
    assert 'Подготовленный пример' in markdown and 'Легенда:' in markdown
    with page.expect_download() as downloaded:
        page.locator('#export-html').click()
    exported = ARTIFACTS / 'export-documentation.html'
    downloaded.value.save_as(str(exported))
    standalone = browser.new_page()
    standalone.goto(exported.as_uri())
    expect(standalone.locator('h1')).to_have_text('DashAI — документация проекта')
    expect(standalone.locator('svg')).to_have_count(4)
    expect(standalone.locator('script')).to_have_count(0)
    assert 'file:' not in exported.read_text(encoding='utf-8')
    standalone.close()
    page.locator('[data-section="files"]').check()
    page.evaluate('window.dispatchEvent(new Event("beforeprint"))')
    assert page.locator('#document-preview details:not([open])').count() == 0
    page.emulate_media(media='print')
    assert page.locator('.document-settings').evaluate('(node) => getComputedStyle(node).display') == 'none'
    assert page.locator('.document-preview').evaluate('(node) => getComputedStyle(node).overflow') == 'visible'
    page.emulate_media(media='screen')
    page.evaluate('window.dispatchEvent(new Event("afterprint"))')
    assert page.locator('#document-preview details[open]').count() == 0
    page.reload()

    captures = []
    for width, height in [(1440, 1000), (1280, 800), (390, 844), (320, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        page.emulate_media(reduced_motion='reduce')
        for view in ['files', 'architecture', 'documentation']:
            page.locator(f'[data-view="{view}"]').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}: {view}'
            if view == 'architecture' and width > 620:
                assert page.locator('.edge-label').evaluate_all('labels => labels.every(label => getComputedStyle(label).fontSize === "12px" && label instanceof HTMLSpanElement)')
            for button in page.locator('button:visible').all():
                box = button.bounding_box()
                assert box and box['width'] >= 24 and box['height'] >= 24, f'Small target: {button.inner_text()}'
            page.evaluate('window.scrollTo(0, 0)')
            name = f'{view}-{width}.png'
            page.screenshot(path=str(ARTIFACTS / name), full_page=True)
            captures.append(name)
        page.locator('[data-view="architecture"]').click()
        for notation in ['context', 'containers', 'components', 'sequence', 'states', 'data', 'flow']:
            page.locator('#notation-select').select_option(notation)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Notation overflow at {width}: {notation}'
        if width == 320:
            page.screenshot(path=str(ARTIFACTS / 'notation-flow-320.png'), full_page=True)
        page.locator('#notation-select').select_option('overview')
    page.locator('[data-view="files"]').click()
    expect(page.locator('#tree-toggle')).to_have_attribute('aria-expanded', 'false')
    page.locator('#tree-toggle').click()
    expect(page.locator('#tree-toggle')).to_have_attribute('aria-expanded', 'true')
    page.locator('.file-row[data-file="src/api.ts"]').click()
    expect(page.locator('#tree-toggle')).to_have_attribute('aria-expanded', 'false')
    expect(page.locator('#file-title')).to_be_focused()
    assert not errors, errors
    assert not network, network
    print(json.dumps({'result': 'PASS', 'checks': ['tree and search', 'description states', 'architecture and return navigation', 'seven diagram notations', 'diagram source download', 'document inclusion and exclusion', 'safe title rendering', 'Markdown and standalone HTML exports', 'print disclosure and layout', 'keyboard and focus', 'mobile tree disclosure', 'no page overflow', 'pointer targets', 'reduced motion', 'no network or application store access'], 'screenshots': captures}, ensure_ascii=False))
    browser.close()
