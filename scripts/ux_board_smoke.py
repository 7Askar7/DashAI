"""UX regression against a temporary real API/store; never touches personal data."""
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
OUTPUT = ROOT / 'artifacts/qa/ux-audit'
OUTPUT.mkdir(parents=True, exist_ok=True)
opener = build_opener(ProxyHandler({}))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'

    def request(path, method='GET', body=None):
        req = Request(url + '/api' + path, method=method, headers={
            'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
            data=json.dumps(body).encode() if body is not None else None)
        with opener.open(req, timeout=20) as response:
            return json.load(response)

    def create(path, **body):
        return request(path, 'POST', {'reason': 'Isolated UX regression', **body})

    checks, errors = [], []
    with tempfile.TemporaryDirectory(prefix='dashai-ux-') as data_dir, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(port), '--data-dir', data_dir],
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
            project = create('/projects', name='DashAI · рабочая доска', description='Изолированный тестовый проект: задачи, решения и проверяемые результаты.')
            empty = create('/projects', name='Новый проект')
            sub = create(f"/projects/{project['id']}/subprojects", title='Интерфейс')
            fixtures = [
                ('Упростить создание первой задачи', 'backlog', 'medium'),
                ('Сохранённые представления проекта', 'backlog', 'low'),
                ('Защитить несохранённые черновики', 'in_progress', 'high'),
                ('Сделать поиск удобным на телефоне', 'in_progress', 'medium'),
                ('Проверить восстановление offline-сессии', 'review', 'high'),
                ('Проверить навигацию с клавиатуры', 'review', 'medium'),
                ('Показать последние события первыми', 'done', 'high'),
                ('Уточнить доступ к Confluence', 'blocked', 'medium'),
            ]
            tasks = []
            for title, status, priority in fixtures:
                task = create('/tasks', project_id=project['id'], title=title, task_type='development',
                              rationale='Сделать ежедневную работу понятнее', acceptance_criteria='Сценарий пройден с клавиатуры и на телефоне',
                              subproject_id=sub['id'], priority=priority)
                if status in ('review', 'done'):
                    create(f"/tasks/{task['id']}/notes", kind='evidence', body='Изолированный сценарий проверен автором записи.')
                if status != 'backlog':
                    task = request(f"/tasks/{task['id']}", 'PATCH', {'expected_version': task['version'], 'changes': {'status': status}, 'reason': 'Prepare test scenario'})
                tasks.append(task)
            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                page.locator('.project-nav').get_by_role('button', name=project['name']).click()
                quick = page.get_by_role('group', name='Быстрые выборки задач')
                expect(page.locator('#board-filters')).to_be_hidden()
                quick.get_by_role('button', name='Проверка').click()
                expect(page.locator('.kanban-card')).to_have_count(2)
                expect(page.locator('.kanban-column')).to_have_count(1)
                page.get_by_role('button', name='Показать список').click()
                expect(page.locator('.task-card')).to_have_count(2)
                page.locator('.filter-toggle').click()
                expect(page.get_by_label('Фильтр статуса', exact=True)).to_have_value('review')
                page.get_by_label('Фильтр приоритета', exact=True).select_option('high')
                expect(page.locator('.task-card')).to_have_count(1)
                page.get_by_role('button', name='Показать доску').click()
                expect(page.locator('.kanban-card')).to_have_count(1)
                quick.get_by_role('button', name='Все задачи').click()
                expect(page.locator('.kanban-card')).to_have_count(8)
                checks.append('Quick views and combined filters retain status across board/list; reset restores all tasks')

                page.get_by_label('Фильтр подпроекта', exact=True).select_option(sub['id'])
                page.get_by_role('button', name='Новая задача', exact=True).click()
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_label('Подпроект', exact=True)).to_have_value(sub['id'])
                dialog.get_by_label('Название задачи').fill('Задача из контекста подпроекта')
                dialog.get_by_label('Зачем это нужно').fill('Сохранить выбранный контекст')
                dialog.get_by_role('button', name='Создать', exact=True).click()
                expect(dialog.get_by_role('heading', name='Задача из контекста подпроекта')).to_be_visible()
                dialog.get_by_role('button', name='Закрыть', exact=True).click()
                expect(page.locator('.kanban-card')).to_have_count(9)
                checks.append('New task inherits subproject and is visible after creation')
                page.locator('.filter-toggle').click()
                search = page.get_by_role('textbox', name='Поиск задач в проекте')
                expect(page.locator('.toast')).to_have_text('')
                for width in (1440, 1024, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000 if width > 700 else 844})
                    search.fill('  offline  ')
                    expect(page.locator('.kanban-card:visible')).to_have_count(1)
                    expect(page.locator('.kanban-card:visible')).to_contain_text('offline')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow {width}px'
                    search.fill('')
                    page.evaluate('window.scrollTo(0,0)')
                    page.screenshot(path=str(OUTPUT / f'board-{width}.png'), full_page=True)
                checks.append('Trimmed mobile search reveals matching review column; no page overflow at 1440/1024/390/320px')
                search.fill('No matches')
                expect(page.get_by_role('heading', name='Задачи не найдены')).to_be_visible()
                page.get_by_role('button', name='Сбросить фильтры', exact=True).last.click()

                page.set_viewport_size({'width': 1440, 'height': 1000})
                for index in range(105):
                    create(f"/tasks/{tasks[0]['id']}/notes", kind='progress', body=f'History entry {index}')
                create(f"/tasks/{tasks[0]['id']}/notes", kind='progress', body='Newest history entry', reason='Latest history regression')
                page.locator('.project-tabs').get_by_role('button', name='История', exact=True).click()
                expect(page.locator('.timeline-event').first).to_contain_text('Latest history regression')
                expect(page.locator('.timeline-event')).to_have_count(100)
                page.get_by_role('button', name='Загрузить более ранние события').click()
                expect(page.locator('.timeline-event').first).to_contain_text('Latest history regression')
                assert page.locator('.timeline-event').count() > 100
                checks.append('History opens newest slice and appends older events without reversing it')
                page.locator('.project-tabs').get_by_role('button', name='Доска', exact=False).click()
                quick.get_by_role('button', name='Проверка').click()
                page.locator(f".kanban-card[data-task-id='{tasks[4]['id']}'] select").select_option('backlog')
                dialog.get_by_label('Почему перемещаем задачу').fill('Возвращаем на доработку')
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog).not_to_be_visible()
                expect(quick.get_by_role('button', name='Проверка')).to_be_focused()
                expect(page.locator('.kanban-card')).to_have_count(1)
                checks.append('Moving a card out of a filtered column restores focus to the visible quick view')
                page.locator('.project-nav-item').filter(has_text=empty['name']).click()
                expect(page.get_by_role('heading', name='С чего начнём этот проект?')).to_be_visible()
                expect(page.get_by_role('button', name='Создать первую задачу')).to_be_visible()
                expect(page.locator('.kanban-column')).to_have_count(0)
                page.screenshot(path=str(OUTPUT / 'empty-project.png'), full_page=True)
                checks.append('Empty project explains the first action and real external-agent workflow')
                assert not errors, errors
                browser.close()
            (OUTPUT / 'results.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == '__main__':
    main()
