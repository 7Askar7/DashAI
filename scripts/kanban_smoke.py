"""Real Kanban/browser regression check on a temporary SQLite store. Build UI first."""
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


def detail(task):
    return request('/tasks/' + task['id'])


def patch(task, changes, reason):
    return request('/tasks/' + task['id'], 'PATCH', {
        'expected_version': detail(task)['task']['version'], 'changes': changes, 'reason': reason,
    })


checks, geometry, page_errors = [], {}, []
with tempfile.TemporaryDirectory(prefix='agentboard-kanban-') as directory:
    with (ARTIFACTS / 'kanban-server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([
            sys.executable, '-m', 'server', '--port', str(port), '--data-dir', directory,
        ], cwd=ROOT, stdout=log, stderr=log,
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
            project = request('/projects', 'POST', {
                'name': 'Kanban QA', 'description': 'Isolated real browser verification',
                'reason': 'Create disposable integration fixture',
            })
            sections = [request('/projects/' + project['id'] + '/sections', 'POST', {
                'title': title, 'reason': 'Create a cross-section board fixture',
            }) for title in ('Платформа и инфраструктура', 'Интерфейс и доступность')]
            tasks = {}
            for i, (name, status) in enumerate((
                ('Cancel', 'backlog'), ('Native drag across project sections', 'backlog'),
                ('Concurrent update', 'backlog'), ('Keyboard move', 'backlog'),
                ('Review existing work', 'review'), ('Verified completion', 'done'),
                ('Blocked work', 'blocked'), ('Active work', 'in_progress'),
            )):
                task = request('/tasks', 'POST', {
                    'project_id': project['id'], 'section_id': sections[i % 2]['id'],
                    'title': name, 'rationale': 'Verify a real whole-project Kanban board',
                    'description': 'Original description',
                    'acceptance_criteria': 'The status and its audit event persist together',
                    'reason': 'Seed isolated test task',
                })
                if status == 'done':
                    request('/tasks/' + task['id'] + '/notes', 'POST', {
                        'kind': 'evidence', 'body': 'Fixture preparation verified',
                        'reason': 'Supply completion evidence for the done fixture',
                    })
                if status != 'backlog':
                    task = patch(task, {'status': status}, 'Seed initial status')
                tasks[name] = task

            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob(
                        'chromium-*/chrome-win*/chrome.exe'),
                        key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                page.on('pageerror', lambda error: page_errors.append(str(error)))
                page.goto(url)
                expect(page.locator('.kanban-card')).to_have_count(len(tasks))

                def card(task):
                    return page.locator('[data-task-id="' + task['id'] + '"]')

                def move(task, status):
                    card(task).get_by_role('combobox').select_option(status)
                    return page.get_by_role('dialog', name='Переместить задачу', exact=True)

                def confirm(dialog, reason):
                    dialog.get_by_label('Почему перемещаем задачу').fill(reason)
                    dialog.get_by_role('button', name='Переместить', exact=True).click()
                    expect(dialog).to_have_count(0)

                columns = page.locator('.kanban-column')
                expect(columns).to_have_count(5)
                bounds = [columns.nth(i).bounding_box() for i in range(5)]
                assert all(bounds[i]['x'] + bounds[i]['width'] <= bounds[i+1]['x'] for i in range(4))
                for task in tasks.values():
                    expect(card(task)).to_have_count(1)
                    expect(page.locator('[data-status="' + task['status'] + '"]')
                           .locator('[data-task-id="' + task['id'] + '"]')).to_have_count(1)
                backlog = page.locator('[data-status="backlog"]')
                assert set(backlog.locator('.kanban-section-tag').all_text_contents()) == {
                    section['title'] for section in sections}
                geometry['desktop'] = page.locator('.kanban-scroll').evaluate(
                    'e => ({client: e.clientWidth, scroll: e.scrollWidth})')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ARTIFACTS / 'kanban-desktop.png'), full_page=True)
                checks.append('default whole-project columns contain each task once, including both sections')

                section_filter = page.get_by_role('combobox', name='Фильтр раздела')
                section_filter.select_option(sections[0]['id'])
                expect(page.locator('.kanban-card')).to_have_count(4)
                expect(columns).to_have_count(5)
                assert set(page.locator('.kanban-section-tag').all_text_contents()) == {sections[0]['title']}
                section_filter.select_option('')
                page.get_by_role('button', name='Показать список', exact=True).click()
                page.get_by_role('combobox', name='Фильтр статуса').select_option('done')
                expect(page.locator('.task-card')).to_have_count(1)
                page.get_by_role('button', name='Показать доску', exact=True).click()
                expect(page.get_by_role('combobox', name='Фильтр статуса')).to_have_count(0)
                expect(page.locator('.kanban-card')).to_have_count(len(tasks))
                expect(columns).to_have_count(5)
                checks.append('section filtering preserves five columns; list-only status filter never hides board tasks')

                task = tasks['Cancel']
                original = detail(task)
                dialog = move(task, 'in_progress')
                expect(dialog).to_be_visible()
                assert detail(task) == original
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog.get_by_label('Почему перемещаем задачу')).to_be_focused()
                assert detail(task) == original
                dialog.get_by_label('Почему перемещаем задачу').fill('Canceled reason')
                dialog.get_by_role('button', name='Отмена', exact=True).click()
                expect(dialog).to_have_count(0)
                assert detail(task) == original
                dialog = move(task, 'review')
                page.keyboard.press('Escape')
                expect(dialog).to_have_count(0)
                assert detail(task) == original
                checks.append('required reason, cancellation and Escape never mutate status or history')

                dialog = move(task, 'done')
                dialog.get_by_label('Почему перемещаем задачу').fill('Attempt without evidence')
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('проверки')
                expect(dialog.get_by_role('button', name='Обновить данные')).to_have_count(0)
                assert detail(task) == original
                dialog.get_by_role('button', name='Отмена', exact=True).click()
                checks.append('completion evidence gate rejects a board move without a successful audit event')

                dialog = move(task, 'in_progress')
                retry_reason = 'Retry the same successful move after losing its network response'
                dialog.get_by_label('Почему перемещаем задачу').fill(retry_reason)
                intercept = url + '/api/tasks/' + task['id']
                submitted_keys = []

                def lose_response(route):
                    if route.request.method != 'PATCH':
                        route.continue_()
                        return
                    submitted_keys.append(route.request.post_data_json['idempotency_key'])
                    response = route.fetch()
                    assert response.status == 200
                    route.abort('failed')

                page.route(intercept, lose_response)
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('Нет связи с сервером')
                page.unroute(intercept, lose_response)
                expect(dialog.get_by_label('Почему перемещаем задачу')).to_have_value(retry_reason)
                assert detail(task)['task']['status'] == 'in_progress'

                def allow_retry(route):
                    if route.request.method == 'PATCH':
                        submitted_keys.append(route.request.post_data_json['idempotency_key'])
                    route.continue_()

                page.route(intercept, allow_retry)
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog).to_have_count(0)
                page.unroute(intercept, allow_retry)
                assert len(submitted_keys) == 2 and submitted_keys[0] == submitted_keys[1]
                assert len([event for event in detail(task)['events'] if event['reason'] == retry_reason]) == 1
                checks.append('lost real response retries the same idempotency key without duplicate status audit')

                task = tasks['Native drag across project sections']
                original = detail(task)
                expect(card(task)).to_have_attribute('draggable', 'true')
                card(task).drag_to(page.locator('[data-status="in_progress"] .kanban-cards'),
                                   source_position={'x': 30, 'y': 30},
                                   target_position={'x': 60, 'y': 310})
                dialog = page.get_by_role('dialog', name='Переместить задачу', exact=True)
                expect(dialog).to_be_visible()
                assert detail(task) == original
                reason = 'Native drag confirmed after the reason was recorded'
                confirm(dialog, reason)
                final = detail(task)
                assert final['task']['status'] == 'in_progress'
                events = [event for event in final['events'] if event['reason'] == reason]
                assert len(events) == 1 and events[0]['actor_kind'] == 'human'
                assert events[0]['before']['status'] == 'backlog'
                assert events[0]['after']['status'] == 'in_progress'
                expect(page.locator('[data-status="in_progress"]').locator(
                    '[data-task-id="' + task['id'] + '"]')).to_have_count(1)
                card(task).get_by_role('button').click()
                drawer = page.get_by_role('dialog')
                expect(drawer.get_by_text(reason, exact=True)).to_be_visible()
                page.keyboard.press('Escape')
                page.reload()
                expect(card(task)).to_have_count(1)
                assert detail(task) == final
                checks.append('native drag confirms once with reason, before/after and author; history survives reload')

                task = tasks['Concurrent update']
                dialog = move(task, 'review')
                reason = 'Keep this reason draft across a real optimistic version conflict'
                dialog.get_by_label('Почему перемещаем задачу').fill(reason)
                intercept = url + '/api/tasks/' + task['id']

                def concurrent_patch(route):
                    # Delay the real PATCH at the browser/network boundary; do not mock its response.
                    page.keyboard.press('Escape')
                    expect(dialog).to_be_visible()
                    patch(task, {'description': 'Concurrent external description', 'priority': 'high'},
                          'A concurrent writer updated different fields')
                    route.continue_()

                page.route(intercept, concurrent_patch)
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('Конфликт изменений.')
                page.unroute(intercept, concurrent_patch)
                expect(dialog.get_by_label('Почему перемещаем задачу')).to_have_value(reason)
                expect(dialog.get_by_role('button', name='Переместить', exact=True)).to_be_disabled()
                assert detail(task)['task']['status'] == 'backlog'
                dialog.get_by_role('button', name='Обновить данные', exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('Причина сохранена')
                expect(dialog.get_by_label('Почему перемещаем задачу')).to_have_value(reason)
                assert detail(task)['task']['status'] == 'backlog'
                dialog.get_by_role('button', name='Переместить', exact=True).click()
                expect(dialog).to_have_count(0)
                final = detail(task)
                assert final['task']['status'] == 'review'
                assert final['task']['description'] == 'Concurrent external description'
                assert final['task']['priority'] == 'high'
                assert len([event for event in final['events'] if event['reason'] == reason]) == 1
                checks.append('busy Escape stays modal; stale PATCH preserves draft and concurrent fields until reconfirmed')

                task = tasks['Keyboard move']
                selector = card(task).get_by_role('combobox')
                selector.focus()
                page.keyboard.press('ArrowDown')
                dialog = page.get_by_role('dialog', name='Переместить задачу', exact=True)
                expect(dialog).to_be_visible()
                dialog.get_by_label('Почему перемещаем задачу').fill('Keyboard-only status change')
                dialog.get_by_role('button', name='Переместить', exact=True).focus()
                page.keyboard.press('Enter')
                expect(dialog).to_have_count(0)
                assert detail(task)['task']['status'] == 'in_progress'
                try:
                    expect(card(task).get_by_role('combobox')).to_be_focused()
                except AssertionError:
                    print('Focus failure:', page.evaluate('({tag: document.activeElement.tagName, '
                          'label: document.activeElement.getAttribute("aria-label"), '
                          'scripts: [...document.scripts].map(e => e.src), openDialogs: document.querySelectorAll("dialog[open]").length})'))
                    page.screenshot(path=str(ARTIFACTS / 'kanban-focus-failure.png'), full_page=True)
                    raise
                checks.append('native status select and reason confirmation work with the keyboard')

                for width in (390, 320):
                    page.set_viewport_size({'width': width, 'height': 844})
                    nav = page.get_by_role('navigation', name='Статус задач')
                    expect(nav).to_be_visible()
                    expect(nav.get_by_role('button')).to_have_count(5)
                    expect(page.locator('.kanban-column:visible')).to_have_count(1)
                    nav.get_by_role('button', name='В работе').click()
                    expect(nav.get_by_role('button', name='В работе')).to_have_attribute('aria-pressed', 'true')
                    expect(page.locator('[data-status="in_progress"]')).to_be_visible()
                    visible = page.locator('.kanban-card:visible')
                    active = [item for item in request('/projects/' + project['id'])['tasks']
                              if item['status'] == 'in_progress']
                    expect(visible).to_have_count(len(active))
                    expect(card(task)).to_have_attribute('draggable', 'false')
                    assert card(task).get_by_role('combobox').bounding_box()['height'] >= 44
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                    geometry[str(width)] = page.locator('.kanban-scroll').evaluate(
                        'e => ({client: e.clientWidth, scroll: e.scrollWidth})')
                    capture_state = '''() => {
                        const link = document.querySelector('.skip-link');
                        const rect = link.getBoundingClientRect();
                        return {scroll_y: scrollY, skip_top: rect.top, skip_bottom: rect.bottom,
                            skip_focused: document.activeElement === link,
                            active_tag: document.activeElement.tagName,
                            active_text: document.activeElement.textContent.trim()};
                    }'''
                    geometry[str(width)]['before_capture'] = page.evaluate(capture_state)
                    if width == 320:
                        page.screenshot(path=str(ARTIFACTS / 'kanban-viewport-before-320.png'))
                    # Full-page Chromium capture can paint an offscreen fixed element at scrollY + top.
                    page.evaluate('window.scrollTo(0, 0)')
                    expect(page.locator('.toast')).to_have_text('')
                    state = page.evaluate(capture_state)
                    assert state['scroll_y'] == 0 and state['skip_bottom'] <= 0 and not state['skip_focused']
                    geometry[str(width)]['after_scroll_to_top'] = state
                    page.screenshot(path=str(ARTIFACTS / f'kanban-mobile-{width}.png'), full_page=True)
                dialog = move(task, 'blocked')
                confirm(dialog, 'Mobile status change keeps a reason and the project context')
                assert detail(task)['task']['status'] == 'blocked'
                expect(nav.get_by_role('button', name='В работе')).to_be_focused()
                nav.get_by_role('button', name='Блокировка').click()
                expect(page.locator('.kanban-column:visible')).to_have_count(1)
                expect(card(task)).to_be_visible()
                expect(card(task)).to_have_count(1)
                checks.append('390px/320px status navigation exposes one column and mobile moves preserve history')
                assert not page_errors, page_errors
                browser.close()
            result = {'passed': checks, 'count': len(checks), 'geometry': geometry, 'page_errors': page_errors}
            (ARTIFACTS / 'kanban-results.json').write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'PASS: {len(checks)} real Kanban integration checks; artifacts/qa/kanban-results.json')
            print(json.dumps(geometry))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
