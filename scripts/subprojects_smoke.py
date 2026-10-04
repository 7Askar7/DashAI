"""Nested subprojects through real forms/API/SQLite, including concurrent edits."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'qa'
ARTIFACTS.mkdir(parents=True, exist_ok=True)
opener = build_opener(ProxyHandler({}))
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
url = f'http://127.0.0.1:{port}'


def request(path, method='GET', body=None):
    req = Request(url + '/api' + path, method=method,
                  headers={'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
                  data=json.dumps(body).encode() if body is not None else None)
    with opener.open(req, timeout=10) as response:
        return json.load(response)


checks, errors = [], []
with tempfile.TemporaryDirectory(prefix='dashai-subprojects-') as directory:
    with (ARTIFACTS / 'subprojects-server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(port), '--data-dir', directory],
                                   cwd=ROOT, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    request('/health')
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.1)
            project = request('/projects', 'POST', {'name': 'DashAI QA', 'reason': 'Isolated browser QA'})
            other = request('/projects', 'POST', {'name': 'Other QA', 'reason': 'Project switch regression'})
            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    cache = Path(os.environ['LOCALAPPDATA']) / 'ms-playwright'
                    available = sorted(cache.glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.get_by_role('button', name='DashAI.', exact=True)).to_be_visible()
                dialog = page.get_by_role('dialog')

                def create_group(title, parent=None):
                    page.get_by_role('button', name='Подпроект', exact=True).click()
                    dialog.get_by_label('Название подпроекта').fill(title)
                    if parent:
                        dialog.get_by_label('Родительский подпроект').select_option(parent)
                    dialog.get_by_role('button', name='Создать', exact=True).click()
                    expect(dialog).to_have_count(0)
                    return next(s for s in request('/projects/' + project['id'])['subprojects'] if s['title'] == title)

                website = create_group('Сайт')
                payment = create_group('Оплата', website['id'])
                testing = create_group('Тестирование', payment['id'])
                checks.append('three nested subprojects created through real forms on one project')
                page.get_by_role('button', name='Новая задача', exact=True).click()
                dialog.get_by_label('Название задачи').fill('Проверить платежи')
                picker = dialog.get_by_role('combobox', name='Подпроект', exact=True)
                expect(picker.locator('option', has_text='Сайт / Оплата / Тестирование')).to_have_count(1)
                picker.select_option(testing['id'])
                dialog.get_by_label('Тип задачи', exact=True).select_option('testing')
                dialog.get_by_label('Зачем это нужно').fill('Изолированный тест вложенного направления')
                dialog.get_by_role('button', name='Создать', exact=True).click()
                expect(dialog.get_by_role('heading', name='Проверить платежи')).to_be_visible()
                expect(dialog.locator('.drawer-breadcrumb')).to_contain_text('Сайт / Оплата / Тестирование')
                dialog.get_by_role('button', name='Закрыть', exact=True).click()
                task = request('/projects/' + project['id'])['tasks'][0]
                card = page.locator(f'.kanban-card[data-task-id="{task["id"]}"]')
                expect(card.locator('.subproject-tag')).to_have_text('Сайт / Оплата / Тестирование')
                request('/tasks', 'POST', {'project_id': project['id'], 'title': 'Общая задача', 'rationale': 'Общий контекст', 'reason': 'Ungrouped comparison'})
                page.reload()
                expect(page.locator('.kanban-card')).to_have_count(2)
                expect(page.locator('.kanban-column')).to_have_count(5)
                page.get_by_label('Фильтр подпроекта').select_option(website['id'])
                expect(page.locator('.kanban-card')).to_have_count(1)
                checks.append('native task dropdown, full breadcrumb, one five-status board and descendant filter')
                page.get_by_role('button', name='Other QA', exact=True).click()
                expect(page.get_by_label('Фильтр подпроекта')).to_have_value('')
                page.get_by_role('button', name='DashAI QA', exact=True).click()
                expect(page.locator('.kanban-card')).to_have_count(2)
                checks.append('project switch clears subgroup filter without hiding another project')
                page.locator('.subprojects-panel summary').click()
                page.get_by_role('button', name='Изменить подпроект Сайт', exact=True).click()
                options = dialog.get_by_label('Родительский подпроект').locator('option')
                assert set(options.evaluate_all('items => items.map(item => item.value)')) == {''}
                dialog.get_by_label('Название подпроекта').fill('Мой черновик')
                request('/subprojects/' + website['id'], 'PATCH', {'expected_version': website['version'], 'changes': {'description': 'Concurrent update'}, 'reason': 'Другой чат уточнил контекст'})
                dialog.get_by_role('button', name='Сохранить изменения').click()
                expect(dialog.get_by_role('alert')).to_contain_text('Сохранение не выполнено')
                expect(dialog.get_by_label('Название подпроекта')).to_have_value('Мой черновик')
                assert request('/projects/' + project['id'])['subprojects'][0]['title'] != 'Мой черновик'
                dialog.get_by_role('button', name='Отмена', exact=True).click()
                checks.append('descendants excluded from parent chooser; stale edit preserves draft and cannot overwrite')
                card.get_by_role('button', name='Открыть задачу', exact=False).click()
                dialog.get_by_role('button', name='Редактировать задачу').click()
                dialog.get_by_label('Подпроект', exact=True).select_option('')
                dialog.get_by_label('Почему меняем задачу').fill('Задача относится ко всему проекту')
                dialog.get_by_role('button', name='Сохранить', exact=True).click()
                expect(dialog.locator('.drawer-breadcrumb')).to_contain_text('Весь проект')
                dialog.get_by_role('button', name='Закрыть', exact=True).click()
                assert request('/tasks/' + task['id'])['task']['subproject_id'] is None
                page.get_by_label('Фильтр подпроекта').select_option('unassigned')
                expect(page.locator('.kanban-card')).to_have_count(2)
                checks.append('editing assignment to whole project is audited and ungrouped filter includes it')
                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
                    assert page.locator('.project-actions button').evaluate_all('items => items.every(item => { const r = item.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; })'), width
                    if width > 760:
                        expect(page.locator('.kanban-column')).to_have_count(5)
                    else:
                        expect(page.locator('.kanban-column:visible')).to_have_count(1)
                page.screenshot(path=str(ARTIFACTS / 'dashai-subprojects-mobile.png'), full_page=True)
                checks.append('1440/390/320px responsive board and hierarchy have no document overflow')
                assert not errors, errors
                browser.close()
            result = {'passed': checks, 'count': len(checks), 'page_errors': errors}
            (ARTIFACTS / 'subprojects-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'PASS: {len(checks)} real nested-subproject browser groups')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
