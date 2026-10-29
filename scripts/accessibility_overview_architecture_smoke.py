"""WCAG checks for Overview, Architecture and PRISM themes on an isolated store.

Uses production dist and a pinned axe-core test asset; no runtime dependency or
personal store. Gradient contrast is sampled from rendered, text-free backgrounds
because axe reports those backgrounds as incomplete. This is a regression check,
not a claim of complete WCAG conformance or a screen-reader user study.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/qa/accessibility-overview-architecture'
AXE_HASH = 'e9e5863c33a874f09bc01acd9234b7e3c871479f5eef8802fa582544465e6d01'
THEMES = ['violet', 'blue', 'cyan', 'emerald', 'amber', 'rose']
TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
OPENER = build_opener(ProxyHandler({}))


def axe_asset():
    path = OUTPUT / 'axe-4.11.0.min.js'
    if not path.exists():
        with OPENER.open('https://registry.npmjs.org/axe-core/-/axe-core-4.11.0.tgz', timeout=30) as response:
            with tarfile.open(fileobj=io.BytesIO(response.read()), mode='r:gz') as archive:
                path.write_bytes(archive.extractfile('package/axe.min.js').read())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == AXE_HASH, 'Unexpected axe-core test asset'
    return path


def luminance(rgb):
    channels = [v / 255 for v in rgb]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))


def rendered_contrast(page):
    """Sample visible text bounds over actual composited gradient backgrounds."""
    nodes = page.evaluate("""() => {
      const rows=[], walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()) {
        const node=walker.currentNode, e=node.parentElement, text=node.textContent.trim();
        if(!text || !e || e.closest('svg,script,style,[aria-hidden="true"],[aria-disabled="true"],[inert],button:disabled,fieldset:disabled')) continue;
        const s=getComputedStyle(e); if(s.visibility!=='visible') continue;
        let opacity=1; for(let p=e;p;p=p.parentElement) opacity*=Number(getComputedStyle(p).opacity);
        if(!opacity) continue;
        const range=document.createRange();range.selectNodeContents(node);
        const rects=[...range.getClientRects()].filter(r=>r.width>1&&r.height>1&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight)
          .filter(r=>{const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit&&(e===hit||e.contains(hit));})
          .map(r=>({x:r.x,y:r.y,w:r.width,h:r.height}));
        if(rects.length) rows.push({text:text.slice(0,100),color:s.color,opacity,large:parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700),rects});
      }
      for(const e of document.querySelectorAll('input:not([type=radio]):not([type=checkbox]),textarea,select')) {
        if(e.disabled||e.closest('[inert],fieldset:disabled'))continue;
        const text=e.tagName==='SELECT'?e.selectedOptions[0]?.textContent:e.value||e.placeholder;
        const s=getComputedStyle(e),r=e.getBoundingClientRect();
        if(!text||s.visibility!=='visible'||!r.width||r.top<0||r.bottom>innerHeight||r.right>innerWidth)continue;
        if(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)!==e)continue;
        const color=!e.value&&e.placeholder?getComputedStyle(e,'::placeholder').color:s.color;
        const left=parseFloat(s.paddingLeft)+2,h=parseFloat(s.fontSize)*1.2;
        rows.push({text:text.slice(0,100),color,opacity:1,large:false,rects:[{x:r.x+left,y:r.y+(r.height-h)/2,w:Math.max(1,r.width-left-34),h}]});
      } return rows;
    }""")
    sheet = page.add_style_tag(content='* { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; caret-color: transparent !important; } *::placeholder { color: transparent !important; -webkit-text-fill-color: transparent !important; }')
    try:
        encoded = base64.b64encode(page.screenshot()).decode('ascii')
    finally:
        sheet.evaluate('e=>e.remove()')
    pixels = page.evaluate("""async ({encoded,nodes}) => {
      const image=new Image();image.src='data:image/png;base64,'+encoded;await image.decode();
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);
      return nodes.map(node=>node.rects.flatMap(r=>[.1,.3,.5,.7,.9].flatMap(fx=>[.2,.5,.8].map(fy=>
        [...context.getImageData(Math.floor(r.x+r.w*fx),Math.floor(r.y+r.h*fy),1,1).data].slice(0,3)))));
    }""", {'encoded': encoded, 'nodes': nodes})
    samples, failures = [], []
    for node, background in zip(nodes, pixels):
        rgba = [float(v) for v in re.findall(r'[\d.]+', node['color'])]
        if len(rgba) < 3:
            continue
        alpha = (rgba[3] if len(rgba) > 3 else 1) * node['opacity']
        ratios = []
        for pixel in background:
            foreground = [a * alpha + b * (1 - alpha) for a, b in zip(rgba[:3], pixel)]
            light, dark = sorted((luminance(foreground), luminance(pixel)), reverse=True)
            ratios.append((light + .05) / (dark + .05))
        if not ratios:
            continue
        row = {'text': node['text'], 'ratio': round(min(ratios), 3), 'required': 3 if node['large'] else 4.5}
        samples.append(row)
        if row['ratio'] + .01 < row['required']:
            failures.append(row)
    return {'sampled': len(samples), 'minimum': min((x['ratio'] for x in samples), default=None), 'failures': failures}


def audit(page, name, axe_path, records):
    page.add_script_tag(path=str(axe_path))
    result = page.evaluate('async tags => await axe.run(document, {runOnly:{type:"tag",values:tags}})', TAGS)
    violations = [{'id': v['id'], 'nodes': [{'target': n['target'], 'summary': n.get('failureSummary')} for n in v['nodes']]} for v in result['violations']]
    contrast = rendered_contrast(page)
    record = {'view': name, 'violations': violations, 'incomplete': [{'id': v['id'], 'nodes': len(v['nodes'])} for v in result['incomplete']], 'contrast': contrast,
              'overflow': page.evaluate('document.documentElement.scrollWidth > innerWidth')}
    records.append(record)
    page.screenshot(path=str(OUTPUT / f'{name}.png'))
    (OUTPUT / 'accessibility-results.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    failed = bool(violations or record['overflow'] or contrast['failures'])
    print(f'{name}: {"FAIL (see accessibility-results.json)" if failed else "PASS"}; {contrast["sampled"]} rendered text samples', flush=True)


def browser_path():
    configured = os.environ.get('AGENTBOARD_BROWSER')
    if configured or os.name != 'nt':
        return configured
    paths = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda p: int(p.parents[1].name.split('-')[-1]))
    return str(paths[-1]) if paths else None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    axe_path = axe_asset()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    checks, errors, records = [], [], []

    def request(path, method='GET', body=None):
        req = Request(url + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
                      data=json.dumps(body).encode() if body is not None else None)
        with OPENER.open(req, timeout=30) as response:
            return json.load(response)

    def create(path, **body):
        return request(path, 'POST', {'reason': 'Isolated accessibility fixture', **body})

    with tempfile.TemporaryDirectory(prefix='dashai-accessibility-') as data, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(port), '--data-dir', data], cwd=ROOT, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    request('/health')
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.1)
            projects = [create('/projects', name=f'Доступность {i:02d}' + (' · ' + 'ДлинноеНазвание' * 8 if i == 0 else ''),
                               description='Синтетический проект для проверки доступности.') for i in range(15)]
            tasks = []
            for i in range(30):
                status = ['backlog', 'in_progress', 'review', 'done', 'blocked'][i % 5]
                task = create('/tasks', project_id=projects[i % 3]['id'], title=f'Синтетическая задача {i:02d}',
                              description='Текст для поиска overview-needle' if i == 29 else 'Синтетическое описание',
                              rationale='Проверка клавиатуры и поиска', acceptance_criteria='Интерфейс доступен с клавиатуры', priority='high' if i % 2 else 'medium')
                if status != 'backlog':
                    create(f"/tasks/{task['id']}/notes", kind='evidence', body='Синтетическая запись для подготовки fixture; не реальная проверка.')
                    task = request(f"/tasks/{task['id']}", 'PATCH', {'expected_version': task['version'], 'changes': {'status': status}, 'reason': 'Prepare isolated status'})
                tasks.append(task)
            diagrams = []
            notations = ['c4_context', 'c4_containers', 'c4_components', 'sequence', 'state', 'erd', 'flowchart']
            for i in range(21):
                notation = notations[i % 7]
                source = {'sequence': 'sequenceDiagram\n A->>B: Synthetic request',
                          'state': 'stateDiagram-v2\n [*] --> Ready',
                          'erd': 'erDiagram\n PROJECT ||--o{ TASK : contains'}.get(notation, f'flowchart LR\n A[Ввод {i}] --> B[Результат {i}]')
                diagrams.append({'id': f'qa-diagram-{i:02d}', 'title': f'Схема {i:02d}' + (' · ' + 'ДлинноеНазвание' * 12 if i == 20 else ''),
                                 'notation': notation, 'scope': 'Контекст синтетического проекта',
                                 'explanation': 'needle-alpha explain-beta' if i == 20 else f'Синтетическое объяснение {i}',
                                 'legend': 'Прямоугольники обозначают этапы.', 'source': source,
                                 'related_paths': ['src/synthetic.py']})
            map_path = f"/projects/{projects[0]['id']}/map"
            request(map_path, 'PUT', {'expected_version': 0, 'source_revision': 'accessibility-v1',
                                    'files': [{'path': 'src/synthetic.py', 'sha256': 'a' * 64}], 'diagrams': diagrams, 'reason': 'Publish isolated diagrams'})
            request(map_path + '/review', 'POST', {'expected_version': 1, 'diagram_id': diagrams[0]['id'], 'reason': 'Synthetic human review fixture'})
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=browser_path())
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                page.locator('.sidebar').get_by_role('button', name='Обзор', exact=True).click()
                # Stable semantic selectors are shared with the two feature owners.
                expect(page.get_by_role('heading', name=re.compile(r'^Обзор\.?$'))).to_be_visible()
                rows = page.locator('.overview-task-row')
                expect(rows).to_have_count(12)
                expect(page.locator('.overview-project-link')).to_have_count(6)
                page.get_by_role('button', name='Показать все проекты (15)', exact=True).click()
                expect(page.locator('.overview-project-link')).to_have_count(15)
                page.get_by_role('button', name='Свернуть проекты', exact=True).click()
                search = page.get_by_role('searchbox', name='Поиск задач в обзоре')
                search.fill('overview-needle')
                expect(rows.get_by_text(tasks[29]['title'], exact=True)).to_be_visible()
                search.fill('no-such-accessibility-task')
                expect(page.locator('.overview-result-summary')).to_have_text('Задач не найдено')
                expect(rows).to_have_count(0)
                search.fill('')
                page.get_by_role('combobox', name='Проект в обзоре').select_option(projects[2]['id'])
                status_filters = page.get_by_role('group', name='Статус задач в обзоре')
                status_filters.get_by_role('button', name=re.compile('^Все открытые')).click()
                expect(rows).to_have_count(8)
                page.get_by_role('combobox', name='Проект в обзоре').select_option('')
                pagination = page.get_by_role('navigation', name='Страницы задач в обзоре')
                expect(rows).to_have_count(12)
                first_ids = rows.evaluate_all('els=>els.map(e=>e.dataset.taskId)')
                pending = []
                next_request = '**/api/overview?*offset=12*'
                page.route(next_request, lambda route: pending.append(route))
                pagination.get_by_role('button', name='Далее', exact=True).click()
                expect(pagination.get_by_role('button', name='Далее', exact=True)).to_have_attribute('aria-disabled', 'true')
                expect(pagination.get_by_role('button', name='Далее', exact=True)).to_be_focused()
                page.keyboard.press('Enter')
                assert len(pending) == 1, 'Pending pagination must not schedule duplicate or skipped pages'
                pending.pop().continue_()
                page.unroute(next_request)
                expect(page.locator('.overview-result-summary')).to_have_text('Показаны 13–24 из 24')
                expect(pagination.get_by_role('button', name='Далее', exact=True)).to_be_focused()
                assert not set(first_ids) & set(rows.evaluate_all('els=>els.map(e=>e.dataset.taskId)'))
                pagination.get_by_role('button', name='Назад', exact=True).click()
                expect(page.locator('.overview-result-summary')).to_have_text('Показаны 1–12 из 24')
                checks.append('Overview uses actual counts, bounded pages, expandable projects and correct search/project/status filters')

                page.route('**/api/overview?*', lambda route: route.fulfill(status=503, json={'detail': 'Synthetic unavailable'}))
                search.fill('failure-needle')
                expect(page.get_by_role('alert')).to_contain_text('Не удалось обновить обзор')
                expect(search).to_have_value('failure-needle')
                page.unroute('**/api/overview?*')
                page.get_by_role('button', name='Обновить данные', exact=True).click()
                expect(page.get_by_role('alert')).to_have_count(0)
                expect(page.locator('.overview-result-summary')).to_have_text('Задач не найдено')
                search.fill('')
                status_filters.get_by_role('button', name=re.compile('^Требует внимания')).click()
                expect(rows).to_have_count(12)
                cross_project = page.locator(f'.overview-task-row[data-task-id="{tasks[29]["id"]}"]')
                page.keyboard.press('Tab')
                cross_project.focus()
                assert cross_project.evaluate('e=>getComputedStyle(e).outlineStyle') != 'none'
                page.keyboard.press('Enter')
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_role('heading', name=tasks[29]['title'], exact=True)).to_be_visible()
                assert dialog.evaluate('e=>e.matches(":modal")')
                page.keyboard.press('Escape')
                expect(dialog).to_have_count(0)
                expect(cross_project).to_be_focused()
                expect(status_filters.get_by_role('button', name=re.compile('^Требует внимания'))).to_have_attribute('aria-pressed', 'true')
                checks.append('Overview errors preserve filters; a cross-project task opens by keyboard and returns focus to the same queue')

                violet = page.get_by_role('radio', name='Фиолетовый', exact=True)
                violet.focus()
                page.keyboard.press('ArrowRight')
                expect(page.locator('html')).to_have_attribute('data-theme', 'blue')
                assert page.get_by_role('radio', name='Синий', exact=True).evaluate('e=>getComputedStyle(e.parentElement).outlineStyle') != 'none'

                for theme in THEMES:
                    page.locator(f'input[type="radio"][value="{theme}"]').check()
                    expect(page.locator('html')).to_have_attribute('data-theme', theme)
                    assert page.evaluate('localStorage.getItem("dashai.theme")') == theme
                    audit(page, f'{theme}-overview-1440', axe_path, records)
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', THEMES[-1])
                checks.append('All six native theme choices persist and pass visible text contrast/axe on Overview')

                page.locator('.project-nav-item').filter(has_text=projects[0]['name']).click()
                page.locator('.project-tabs').get_by_role('button', name='Архитектура', exact=True).click()
                reader = page.locator('.architecture-reader')
                expect(reader.locator('iframe')).to_be_visible(timeout=30000)
                library = page.locator('.architecture-library')
                diagram_search = page.get_by_role('searchbox', name='Найти схему')
                diagram_search.fill('needle-alpha explain-beta')
                expect(page.get_by_role('list', name='Схемы проекта').get_by_role('button')).to_have_count(1)
                expect(reader.get_by_role('heading', level=2)).to_contain_text('Схема 00')
                page.get_by_role('combobox', name='Нотация', exact=True).select_option('flowchart')
                page.get_by_role('combobox', name='Проверка схемы', exact=True).select_option('reviewed')
                expect(page.get_by_text('Схемы не найдены', exact=True)).to_be_visible()
                page.get_by_role('button', name='Сбросить фильтры', exact=True).click()
                expect(page.get_by_role('list', name='Схемы проекта').get_by_role('button')).to_have_count(21)
                choice = page.get_by_role('list', name='Схемы проекта').get_by_role('button').last
                choice.focus()
                page.keyboard.press('Enter')
                expect(reader.get_by_role('heading', level=2)).to_contain_text('Схема 20')
                expect(choice).to_have_attribute('aria-current', 'true')
                expect(reader.locator('iframe')).to_have_attribute('sandbox', '')
                source = reader.locator('.architecture-source > summary')
                source.focus()
                source.press('Enter')
                expect(reader.locator('.architecture-source pre')).to_have_text(diagrams[-1]['source'])
                source.press('Enter')
                with page.expect_download() as downloaded:
                    reader.get_by_role('button', name='Скачать .mmd', exact=True).click()
                downloaded.value.save_as(OUTPUT / 'synthetic-diagram.mmd')
                assert (OUTPUT / 'synthetic-diagram.mmd').read_text(encoding='utf-8') == diagrams[-1]['source']
                checks.append('Architecture all-word search, AND filters, keyboard selection, exact source download and sandbox preserved')

                for theme in THEMES:
                    page.locator(f'input[type="radio"][value="{theme}"]').check()
                    page.evaluate('window.scrollTo(0,0)')
                    audit(page, f'{theme}-architecture-1440', axe_path, records)
                page.set_viewport_size({'width': 320, 'height': 844})
                if not library.evaluate('e=>e.open'):
                    library.locator('summary').click()
                expect(diagram_search).to_be_visible()
                page.get_by_role('list', name='Схемы проекта').get_by_role('button').first.click()
                assert not library.evaluate('e=>e.open')
                expect(reader.get_by_role('heading', level=2)).to_be_focused()
                assert 0 <= reader.get_by_role('heading', level=2).bounding_box()['y'] <= 60, 'Mobile selection must reveal the reader at the top'
                page.evaluate('window.scrollTo(0,0)')
                audit(page, 'architecture-320', axe_path, records)
                reader.get_by_role('heading', level=2).evaluate('e=>e.scrollIntoView({block:"start"})')
                audit(page, 'architecture-reader-320', axe_path, records)
                source.scroll_into_view_if_needed()
                assert source.bounding_box()['height'] >= 44
                menu = page.get_by_role('button', name='Открыть меню', exact=True)
                menu.click()
                sidebar = page.get_by_role('dialog', name='Проекты и навигация')
                expect(sidebar).to_be_visible()
                sidebar.get_by_role('radio', name='Фиолетовый', exact=True).check()
                sidebar.get_by_role('button').first.focus()
                for key in ['Tab'] * 24 + ['Shift+Tab'] * 24:
                    page.keyboard.press(key)
                    assert sidebar.evaluate('e=>e.contains(document.activeElement)'), 'Native radio groups must contribute only their checked Tab stop'
                page.keyboard.press('Escape')
                expect(menu).to_be_focused()
                menu.click()
                sidebar.get_by_role('button', name='Обзор', exact=True).click()
                mobile_status = page.get_by_role('combobox', name='Статус задач', exact=True)
                expect(mobile_status.locator('option')).to_have_count(7)
                mobile_status.select_option('in_progress')
                expect(rows).to_have_count(6)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                expect(page.get_by_role('group', name='Статус задач в обзоре').get_by_role('button', name=re.compile('^В работе'))).to_have_attribute('aria-pressed', 'true')
                page.set_viewport_size({'width': 320, 'height': 844})
                expect(mobile_status).to_have_value('in_progress')
                mobile_status.select_option('attention')
                expect(rows).to_have_count(12)
                page.evaluate('window.scrollTo(0,0)')
                audit(page, 'overview-320', axe_path, records)
                checks.append('320px reflow; mobile library focuses reader; menu traps Tab and returns focus on Escape')

                fallback = browser.new_context(viewport={'width': 1440, 'height': 1000})
                fallback.add_init_script("localStorage.setItem('dashai.theme','invalid-theme')")
                fallback_page = fallback.new_page()
                fallback_page.goto(url)
                expect(fallback_page.locator('html')).to_have_attribute('data-theme', 'violet')
                expect(fallback_page.locator('main button').first).to_be_visible()
                fallback_page.keyboard.press('Tab')
                expect(fallback_page.locator('.skip-link')).to_be_focused()
                fallback_page.keyboard.press('Enter')
                fallback_page.keyboard.press('Tab')
                assert fallback_page.locator('main').evaluate('e=>e.contains(document.activeElement)')
                fallback_page.evaluate("() => { Storage.prototype.setItem=function(){throw new DOMException('Synthetic blocked storage','SecurityError')}; }")
                fallback_page.get_by_role('radio', name='Синий', exact=True).check()
                expect(fallback_page.locator('html')).to_have_attribute('data-theme', 'blue')
                expect(fallback_page.locator('.theme-picker').get_by_role('status')).to_have_text('Цвет изменён. Сохранение в этом браузере недоступно.')
                fallback.close()
                checks.append('Skip link bypasses navigation; invalid theme falls back; blocked storage reports the unsaved preference')
                assert not errors, errors
                assert not [record for record in records if record['violations'] or record['overflow'] or record['contrast']['failures']], 'Accessibility failures: see accessibility-results.json'
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=20)
    result = {'checks': checks, 'page_errors': errors, 'axe': '4.11.0', 'axe_sha256': AXE_HASH,
              'dist_sha256': hashlib.sha256((ROOT / 'dist/index.html').read_bytes()).hexdigest(), 'audits': len(records),
              'limits': 'Visible text sampling complements axe gradient incomplete results; screen-reader usability and every state are not certified.'}
    (OUTPUT / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
