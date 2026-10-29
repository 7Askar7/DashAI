"""Docked inspector regression against a temporary real API and production UI.

Exercises the newly reachable task-switching paths; no personal store is read.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/qa/prism-workspace'
OUTPUT.mkdir(parents=True, exist_ok=True)
OPENER = build_opener(ProxyHandler({}))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    checks, errors = [], []

    def request(path, method='GET', body=None):
        req = Request(url + '/api' + path, method=method,
                      headers={'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
                      data=json.dumps(body).encode() if body is not None else None)
        with OPENER.open(req, timeout=20) as response:
            return json.load(response)

    def create(path, **body):
        return request(path, 'POST', {'reason': 'Isolated PRISM inspector regression', **body})

    with tempfile.TemporaryDirectory(prefix='dashai-prism-') as directory, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(port), '--data-dir', directory],
                                   cwd=ROOT, stdout=log, stderr=log,
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
            project = create('/projects', name='PRISM · изолированная проверка')
            tasks = []
            for status in ('backlog', 'in_progress', 'review', 'done', 'blocked'):
                task = create('/tasks', project_id=project['id'], title=f'Проверка интерфейса · {status}',
                              rationale='Убедиться, что выбор задачи сохраняет контекст',
                              acceptance_criteria='Переходы защищают черновик и сохраняют доступ с клавиатуры')
                if status != 'backlog':
                    create(f"/tasks/{task['id']}/notes", kind='evidence', body='Синтетическая запись для проверки отображения.')
                    request(f"/tasks/{task['id']}", 'PATCH', {'expected_version': task['version'], 'changes': {'status': status}, 'reason': 'Prepare isolated status group'})
                tasks.append(task)

            with sync_playwright() as playwright:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = playwright.chromium.launch(executable_path=executable)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                page.locator('.project-nav').get_by_role('button', name=project['name'], exact=False).click()
                expect(page.get_by_role('dialog')).to_have_count(0)
                expect(page.get_by_role('button', name='Показать доску', exact=True)).to_have_attribute('aria-pressed', 'true')
                page.get_by_role('button', name='Показать список', exact=True).click()
                expect(page.locator('.task-group')).to_have_count(5)
                expect(page.locator('.task-card')).to_have_count(5)
                summary = page.locator('.task-group.backlog > summary')
                summary.focus()
                page.keyboard.press('Enter')
                expect(page.locator('.task-group.backlog .task-card')).not_to_be_visible()
                page.keyboard.press('Enter')
                first = page.locator(f'.task-card[data-task-id="{tasks[0]["id"]}"]')
                second = page.locator(f'.task-card[data-task-id="{tasks[2]["id"]}"]')
                first.focus()
                page.keyboard.press('Enter')
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_role('heading', name=tasks[0]['title'], exact=True)).to_be_visible()
                assert dialog.evaluate('node => !node.matches(":modal") && node.classList.contains("is-docked")')
                expect(first).to_have_attribute('aria-current', 'true')
                assert first.bounding_box()['x'] + first.bounding_box()['width'] < dialog.bounding_box()['x']
                second.click()
                expect(dialog.get_by_role('heading', name=tasks[2]['title'], exact=True)).to_be_visible()
                expect(second).to_have_attribute('aria-current', 'true')
                page.screenshot(path=str(OUTPUT / 'desktop.png'), full_page=True)
                page.keyboard.press('Escape')
                expect(dialog).to_have_count(0)
                expect(second).to_be_focused()
                checks.append('Five native collapsible status groups; desktop inspector leaves rows usable, selects the actual row and restores keyboard focus')

                pending = []
                task_request = f'**/api/tasks/{tasks[0]["id"]}'
                page.route(task_request, lambda route: pending.append(route))
                first.click()
                expect(dialog.get_by_role('heading', name='Открываем задачу…', exact=True)).to_be_visible()
                second.click()
                expect(dialog.get_by_role('heading', name=tasks[2]['title'], exact=True)).to_be_visible()
                assert len(pending) == 1
                pending.pop().continue_()
                page.unroute(task_request)
                page.wait_for_load_state('networkidle')
                expect(dialog.get_by_role('heading', name=tasks[2]['title'], exact=True)).to_be_visible()
                expect(second).to_have_attribute('aria-current', 'true')
                assert tasks[2]['id'] in page.url
                checks.append('Switching while the prior real detail request is held opens the latest selection; the late response cannot replace it')

                first.click()
                expect(dialog.get_by_role('heading', name=tasks[0]['title'], exact=True)).to_be_visible()
                dialog.get_by_role('button', name='Редактировать задачу', exact=True).click()
                task_type = dialog.get_by_label('Тип задачи', exact=True)
                task_type.focus()
                task_type.press('Alt+ArrowDown')
                task_type.press('Escape')
                expect(dialog).to_be_visible()
                expect(task_type).to_be_focused()
                task_type.select_option('research')
                dialog.get_by_label('Почему меняем задачу').fill('Проверить фокус после сохранения')
                dialog.get_by_role('button', name='Сохранить', exact=True).click()
                edit_button = dialog.get_by_role('button', name='Редактировать задачу', exact=True)
                expect(edit_button).to_be_enabled()
                expect(edit_button).to_be_focused()
                assert request(f"/tasks/{tasks[0]['id']}")['task']['task_type'] == 'research'
                edit_button.click()
                draft = dialog.get_by_label('Название задачи')
                draft.fill('Несохранённый черновик')
                page.once('dialog', lambda prompt: prompt.dismiss())
                second.click()
                expect(draft).to_have_value('Несохранённый черновик')
                expect(first).to_have_attribute('aria-current', 'true')
                page.once('dialog', lambda prompt: prompt.dismiss())
                page.get_by_role('button', name='Новая задача', exact=True).click()
                expect(draft).to_have_value('Несохранённый черновик')
                expect(dialog).to_have_count(1)
                page.get_by_role('button', name='Показать доску', exact=True).click()
                page.once('dialog', lambda prompt: prompt.dismiss())
                page.locator(f'.kanban-card[data-task-id="{tasks[0]["id"]}"] select').select_option('review')
                expect(draft).to_have_value('Несохранённый черновик')
                expect(dialog).to_have_count(1)
                assert request(f"/tasks/{tasks[0]['id']}")['task']['status'] == 'backlog'
                page.get_by_role('button', name='Показать список', exact=True).click()
                page.once('dialog', lambda prompt: prompt.accept())
                second.click()
                expect(dialog.get_by_role('heading', name=tasks[2]['title'], exact=True)).to_be_visible()
                assert request(f"/tasks/{tasks[0]['id']}")['task']['title'] == tasks[0]['title']
                checks.append('Native select Escape keeps the inspector; successful save restores focus; task switching, creation and Kanban moves preserve rejected drafts')

                note = dialog.locator('.note-form')
                note.get_by_label('Текст записи').fill('Held PRISM note')
                note.get_by_label('Почему добавляем запись').fill('Проверить блокировку навигации')
                held = []
                page.route('**/api/tasks/*/notes', lambda route: held.append(route))
                note.get_by_role('button', name='Добавить в историю', exact=True).click()
                expect(note.get_by_role('button', name='Сохраняем…', exact=True)).to_be_disabled()
                first.click()
                page.keyboard.press('Escape')
                page.get_by_role('button', name='Новая задача', exact=True).click()
                expect(dialog.get_by_role('heading', name=tasks[2]['title'], exact=True)).to_be_visible()
                expect(note.get_by_label('Текст записи')).to_have_value('Held PRISM note')
                assert len(held) == 1
                held.pop().continue_()
                page.unroute('**/api/tasks/*/notes')
                expect(note.get_by_role('button', name='Добавить в историю', exact=True)).to_be_enabled()
                assert sum(item['body'] == 'Held PRISM note' for item in request(f"/tasks/{tasks[2]['id']}")['notes']) == 1
                checks.append('Pending real note save blocks row switching, Escape and opening a new form; result persists exactly once')

                note.get_by_label('Текст записи').fill('Черновик при смене ширины')
                note.get_by_label('Текст записи').focus()
                page.set_viewport_size({'width': 390, 'height': 844})
                expect(dialog).to_have_attribute('aria-modal', 'true')
                assert dialog.evaluate('node => node.matches(":modal")')
                expect(note.get_by_label('Текст записи')).to_have_value('Черновик при смене ширины')
                expect(note.get_by_label('Текст записи')).to_be_focused()
                dialog.get_by_role('button', name='Закрыть', exact=True).focus()
                first.evaluate('node => node.focus()')
                expect(dialog.get_by_role('button', name='Закрыть', exact=True)).to_be_focused()
                page.screenshot(path=str(OUTPUT / 'mobile.png'), full_page=True)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                expect(dialog).to_have_attribute('aria-modal', 'false')
                expect(note.get_by_label('Текст записи')).to_have_value('Черновик при смене ширины')
                page.once('dialog', lambda prompt: prompt.dismiss())
                page.locator('.project-tabs').get_by_role('button', name='История', exact=True).click()
                expect(dialog).to_be_visible()
                page.once('dialog', lambda prompt: prompt.accept())
                page.locator('.project-tabs').get_by_role('button', name='История', exact=True).click()
                expect(dialog).to_have_count(0)
                assert '?task=' not in page.url
                checks.append('Resizing keeps the same draft and focus while switching native modal mode; project navigation respects discard choice')

                page.locator('.project-tabs').get_by_role('button', name='Доска', exact=False).click()
                expect(page.get_by_role('button', name='Показать список', exact=True)).to_have_attribute('aria-pressed', 'true')
                page.get_by_role('button', name='Новая задача', exact=True).click()
                expect(dialog.get_by_role('heading', name='Новая задача', exact=True)).to_be_visible()
                assert dialog.evaluate('node => node.matches(":modal")')
                page.keyboard.press('Escape')
                expect(dialog).to_have_count(0)
                page.reload()
                expect(page.get_by_role('button', name='Показать список', exact=True)).to_have_attribute('aria-pressed', 'true')
                expect(page.get_by_role('dialog')).to_have_count(0)
                checks.append('Creation forms remain native modal; chosen list layout persists and no arbitrary task opens')
                assert not errors, errors
                browser.close()
            evidence = {'result': 'PASS', 'checks': checks, 'page_errors': errors,
                        'backend': 'real isolated SQLite/API and production dist', 'viewports': [1440, 390],
                        'frontend_entry_sha256': hashlib.sha256((ROOT / 'dist/index.html').read_bytes()).hexdigest()}
            (OUTPUT / 'results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
