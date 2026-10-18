"""Workspace restoration and task links on a temporary real API/SQLite store.

No personal data is read. A held note request is released to the real backend;
corrupt/denied browser storage is deliberate fault injection.
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
from urllib.parse import parse_qs, urlparse
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/qa/workspace-navigation'
OUTPUT.mkdir(parents=True, exist_ok=True)
KEY = 'dashai.workspace.v1'
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
        return request(path, 'POST', {'reason': 'Isolated workspace navigation regression', **body})

    def saved(page):
        return page.evaluate('key => JSON.parse(localStorage.getItem(key))', KEY)

    def wait_saved(page, expected):
        page.wait_for_function('([key, expected]) => { const value = JSON.parse(localStorage.getItem(key) || "null"); return value && Object.entries(expected).every(([name, item]) => JSON.stringify(value[name]) === JSON.stringify(item)); }', arg=[KEY, expected])

    with tempfile.TemporaryDirectory(prefix='dashai-navigation-') as directory, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
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

            alpha = create('/projects', name='Навигация · Альфа')
            beta = create('/projects', name='Навигация · Бета')
            subproject = create(f"/projects/{alpha['id']}/subprojects", title='Восстановление состояния')
            alpha_task = create('/tasks', project_id=alpha['id'], title='Навигация между задачами',
                                task_type='development', rationale='Вернуться к своей работе после перезагрузки',
                                acceptance_criteria='Проект, фильтры и карточка восстановлены',
                                subproject_id=subproject['id'], assignee_id='human', priority='high')
            create(f"/tasks/{alpha_task['id']}/notes", kind='evidence', body='Изолированные исходные данные для проверки навигации.')
            request(f"/tasks/{alpha_task['id']}", 'PATCH', {'expected_version': alpha_task['version'], 'changes': {'status': 'review'}, 'reason': 'Prepare review task'})
            alpha_other = create('/tasks', project_id=alpha['id'], title='Другая задача Альфы', task_type='testing', rationale='Проверить действительную фильтрацию')
            beta_task = create('/tasks', project_id=beta['id'], title='Память второго проекта',
                               task_type='bugfix', rationale='Не переносить фильтры между проектами', priority='low')
            request(f"/tasks/{beta_task['id']}", 'PATCH', {'expected_version': beta_task['version'], 'changes': {'status': 'blocked'}, 'reason': 'Prepare independent project filters'})

            with sync_playwright() as playwright:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = playwright.chromium.launch(executable_path=executable)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, permissions=['clipboard-read', 'clipboard-write'])
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                page.locator('.project-nav').get_by_role('button', name=alpha['name'], exact=False).click()
                page.locator('.filter-toggle').click()
                page.get_by_role('textbox', name='Поиск задач в проекте').fill('Навигация')
                filters = {
                    'Фильтр типа задачи': 'development', 'Фильтр подпроекта': subproject['id'],
                    'Фильтр исполнителя': 'human', 'Фильтр статуса': 'review', 'Фильтр приоритета': 'high',
                }
                for label, value in filters.items():
                    page.get_by_label(label, exact=True).select_option(value)
                page.get_by_role('button', name='Показать список', exact=True).click()
                expect(page.locator('.task-card')).to_have_count(1)
                page.locator('.task-card').click()
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_role('heading', name=alpha_task['title'], exact=True)).to_be_visible()
                wait_saved(page, {'version': 1, 'projectId': alpha['id'], 'view': 'board', 'taskId': alpha_task['id']})
                alpha_preferences = saved(page)['projects'][alpha['id']]
                expected_alpha = {'view': 'board', 'query': 'Навигация', 'taskTypeFilter': 'development',
                                  'subprojectFilter': subproject['id'], 'agentFilter': 'human', 'statusFilter': 'review',
                                  'priorityFilter': 'high', 'listView': True, 'filtersOpen': True}
                assert alpha_preferences == expected_alpha, alpha_preferences
                delayed_bootstrap = []
                page.route('**/api/bootstrap', lambda route: delayed_bootstrap.append(route))
                page.reload(wait_until='domcontentloaded')
                expect(dialog.get_by_role('heading', name=alpha_task['title'], exact=True)).to_be_visible()
                assert len(delayed_bootstrap) == 1
                assert saved(page)['projects'][alpha['id']]['agentFilter'] == 'human'
                delayed_bootstrap.pop().continue_()
                page.unroute('**/api/bootstrap')
                dialog.get_by_role('button', name='Закрыть', exact=True).click()
                expect(page.get_by_role('button', name='Показать список', exact=True)).to_have_attribute('aria-pressed', 'true')
                expect(page.get_by_role('textbox', name='Поиск задач в проекте')).to_have_value('Навигация')
                for label, value in filters.items():
                    expect(page.get_by_label(label, exact=True)).to_have_value(value)
                checks.append('Reload with delayed bootstrap preserves the human assignee filter, every other project filter, list layout and open task')

                page.locator('.project-nav').get_by_role('button', name=beta['name'], exact=False).click()
                if not page.locator('#board-filters').is_visible():
                    page.locator('.filter-toggle').click()
                page.get_by_role('textbox', name='Поиск задач в проекте').fill('Память')
                for label, value in {'Фильтр типа задачи': 'bugfix', 'Фильтр исполнителя': 'unassigned',
                                     'Фильтр статуса': 'blocked', 'Фильтр приоритета': 'low'}.items():
                    page.get_by_label(label, exact=True).select_option(value)
                page.get_by_role('button', name='Показать доску', exact=True).click()
                page.locator('.project-tabs').get_by_role('button', name='История', exact=True).click()
                page.locator('.project-nav').get_by_role('button', name=alpha['name'], exact=False).click()
                expect(page.get_by_role('textbox', name='Поиск задач в проекте')).to_have_value('Навигация')
                expect(page.get_by_role('button', name='Показать список', exact=True)).to_have_attribute('aria-pressed', 'true')
                page.locator('.project-nav').get_by_role('button', name=beta['name'], exact=False).click()
                expect(page.locator('.project-tabs').get_by_role('button', name='История', exact=True)).to_have_attribute('aria-current', 'page')
                page.reload()
                expect(page.locator('.project-tabs').get_by_role('button', name='История', exact=True)).to_have_attribute('aria-current', 'page')
                page.locator('.project-tabs').get_by_role('button', name='Доска', exact=False).click()
                expect(page.get_by_role('textbox', name='Поиск задач в проекте')).to_have_value('Память')
                expect(page.get_by_label('Фильтр статуса', exact=True)).to_have_value('blocked')
                expect(page.get_by_role('button', name='Показать доску', exact=True)).to_have_attribute('aria-pressed', 'true')
                page.locator('.sidebar').get_by_role('button', name='Обзор', exact=True).click()
                wait_saved(page, {'view': 'overview'})
                page.reload()
                expect(page.get_by_role('heading', name='Вся работа на виду', exact=False)).to_be_visible()
                checks.append('Per-project tabs and board preferences remain independent; workspace overview survives reload')

                snapshot = saved(page)
                snapshot.update(projectId=alpha['id'], view='overview', taskId=alpha_task['id'])
                page.evaluate('([key, value]) => localStorage.setItem(key, JSON.stringify(value))', [KEY, snapshot])
                page.goto(f"{url}/?task={beta_task['id']}&vscode=1&v=fixture&instance_id=fixture#old")
                expect(dialog.get_by_role('heading', name=beta_task['title'], exact=True)).to_be_visible()
                expect(dialog.locator('.drawer-breadcrumb')).to_contain_text(beta['name'])
                wait_saved(page, {'projectId': beta['id'], 'taskId': beta_task['id']})
                dialog.get_by_role('button', name='Скопировать ссылку на задачу', exact=True).click()
                page.wait_for_function('async () => (await navigator.clipboard.readText()).includes("?task=")')
                copied = page.evaluate('navigator.clipboard.readText()')
                copied_url = urlparse(copied)
                assert copied_url.scheme == 'http' and copied_url.netloc == urlparse(url).netloc
                assert copied_url.path == '/' and parse_qs(copied_url.query) == {'task': [beta_task['id']]}
                assert not copied_url.fragment, copied
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                    dialog.get_by_role('button', name='Скопировать ссылку на задачу', exact=True).scroll_into_view_if_needed()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow {width}px'
                    page.screenshot(path=str(OUTPUT / f'task-link-{width}.png'))
                page.set_viewport_size({'width': 1440, 'height': 1000})
                checks.append('Explicit task URL overrides another project snapshot; clipboard link strips host/cache/hash flags')

                for task_id in (str(uuid4()), 'not-a-task'):
                    page.goto(f'{url}/?task={task_id}')
                    error_dialog = page.get_by_role('dialog', name='Не удалось открыть задачу', exact=True)
                    expect(error_dialog.get_by_role('alert')).to_be_visible()
                    expect(error_dialog.get_by_role('button', name='Повторить', exact=True)).to_be_visible()
                    error_dialog.get_by_role('button', name='Закрыть сообщение', exact=True).click()
                    expect(error_dialog).to_have_count(0)
                    page.wait_for_function('!new URL(location.href).searchParams.has("task")')
                    wait_saved(page, {'taskId': None})
                checks.append('Missing and malformed task links show dismissible errors and clear the failed task selection')
                page.close()

                history_page = context.new_page()
                history_page.on('pageerror', lambda error: errors.append(str(error)))
                history_page.add_init_script(f'localStorage.removeItem({json.dumps(KEY)}); localStorage.removeItem("agentboard.project");')
                history_page.goto(url)
                history_page.locator('.project-nav').get_by_role('button', name=alpha['name'], exact=False).click()
                history_page.locator(f".kanban-card[data-task-id='{alpha_task['id']}'] .kanban-card-open").click()
                history_dialog = history_page.get_by_role('dialog')
                expect(history_dialog.get_by_role('heading', name=alpha_task['title'], exact=True)).to_be_visible()
                task_url = history_page.url
                history_page.go_back()
                expect(history_dialog).to_have_count(0)
                assert 'task' not in parse_qs(urlparse(history_page.url).query)
                history_page.go_forward()
                expect(history_dialog.get_by_role('heading', name=alpha_task['title'], exact=True)).to_be_visible()
                checks.append('Browser Back closes an opened task and Forward restores it')

                history_dialog.get_by_role('button', name='Закрыть', exact=True).click()
                history_page.locator(f".kanban-card[data-task-id='{alpha_other['id']}'] .kanban-card-open").click()
                expect(history_dialog.get_by_role('heading', name=alpha_other['title'], exact=True)).to_be_visible()
                task_url = history_page.url
                history_page.reload()
                expect(history_dialog.get_by_role('heading', name=alpha_other['title'], exact=True)).to_be_visible()
                history_dialog.get_by_role('button', name='Редактировать задачу', exact=True).click()
                edit = history_dialog.locator('.edit-form')
                edit.get_by_label('Название задачи').fill('Локальный черновик не должен попасть в storage')
                history_page.once('dialog', lambda confirmation: confirmation.dismiss())
                history_page.go_back()
                history_page.wait_for_url(task_url)
                expect(edit.get_by_label('Название задачи')).to_have_value('Локальный черновик не должен попасть в storage')
                assert 'Локальный черновик' not in history_page.evaluate('key => localStorage.getItem(key)', KEY)
                history_page.once('dialog', lambda confirmation: confirmation.accept())
                history_page.go_back()
                expect(history_dialog).to_have_count(0)
                assert 'task' not in parse_qs(urlparse(history_page.url).query)
                history_page.go_forward()
                expect(history_dialog.get_by_role('heading', name=alpha_other['title'], exact=True)).to_be_visible()
                assert request(f"/tasks/{alpha_other['id']}")['task']['title'] == alpha_other['title']
                checks.append('After opening A, closing A, opening B and reloading, rejected Back retains the draft; second accepted Back reaches the correct prior entry')

                note = history_dialog.locator('.note-form')
                note.get_by_label('Текст записи').fill('Delayed navigation regression note')
                note.get_by_label('Почему добавляем запись').fill('Проверить уход во время сохранения')
                held, unexpected_dialogs = [], []
                history_page.route('**/api/tasks/*/notes', lambda route: held.append(route))
                note.get_by_role('button', name='Добавить в историю', exact=True).click()
                expect(note.get_by_role('button', name='Сохраняем…', exact=True)).to_be_disabled()

                def reject_unexpected(confirmation):
                    unexpected_dialogs.append(confirmation.message)
                    confirmation.dismiss()

                history_page.on('dialog', reject_unexpected)
                history_page.go_back()
                history_page.wait_for_url(task_url)
                expect(history_dialog).to_be_visible()
                expect(note.get_by_label('Текст записи')).to_have_value('Delayed navigation regression note')
                assert len(held) == 1 and not unexpected_dialogs, unexpected_dialogs
                held.pop().continue_()
                history_page.unroute('**/api/tasks/*/notes')
                expect(history_dialog.locator('.note.progress').filter(has_text='Delayed navigation regression note')).to_have_count(1)
                expect(note.get_by_role('button', name='Добавить в историю', exact=True)).to_be_enabled()
                history_page.remove_listener('dialog', reject_unexpected)
                history_page.go_back()
                expect(history_dialog).to_have_count(0)
                assert sum(item['body'] == 'Delayed navigation regression note' for item in request(f"/tasks/{alpha_other['id']}")['notes']) == 1
                checks.append('Back during pending note save is blocked without a discard prompt; real result is saved exactly once')
                history_page.close()

                for fault in ('corrupt', 'denied'):
                    fault_context = browser.new_context()
                    fault_page = fault_context.new_page()
                    fault_page.on('pageerror', lambda error: errors.append(str(error)))
                    if fault == 'corrupt':
                        fault_page.add_init_script(f'localStorage.setItem({json.dumps(KEY)}, "{{invalid-json");')
                    else:
                        fault_page.add_init_script("for (const name of ['getItem','setItem']) Object.defineProperty(Storage.prototype, name, {value() { throw new DOMException('QA denied storage', 'SecurityError'); }});")
                    fault_page.goto(url)
                    expect(fault_page.locator('.project-nav-item')).to_have_count(2)
                    fault_page.locator('.project-nav').get_by_role('button', name=alpha['name'], exact=False).click()
                    fault_page.locator(f".kanban-card[data-task-id='{alpha_task['id']}'] .kanban-card-open").click()
                    expect(fault_page.get_by_role('heading', name=alpha_task['title'], exact=True)).to_be_visible()
                    fault_context.close()
                checks.append('Corrupt JSON and denied browser storage degrade to working navigation without uncaught page errors')
                assert not errors, errors
                browser.close()

            evidence = {'result': 'PASS', 'checks': checks, 'page_errors': errors,
                        'backend': 'real isolated SQLite/API and production dist',
                        'synthetic': ['held real bootstrap and note requests', 'corrupt JSON and denied localStorage contexts'],
                        'frontend_entry_sha256': hashlib.sha256((ROOT / 'dist/index.html').read_bytes()).hexdigest(),
                        'viewports': [1440, 390]}
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
