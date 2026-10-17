"""Real isolated production-UI regression for release records and reusable assignees.

Uses a temporary SQLite/API server. Only the explicit failed-save response is synthetic;
held requests continue to the real backend after pending-state assertions.
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
OUTPUT = ROOT / 'artifacts/qa/project-releases-1.7'
OUTPUT.mkdir(parents=True, exist_ok=True)
OPENER = build_opener(ProxyHandler({}))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    checks, screenshots, errors = [], [], []

    def request(path, method='GET', body=None):
        req = Request(url + '/api' + path, method=method,
                      headers={'Content-Type': 'application/json', 'X-Dashboard-Client': 'browser'},
                      data=json.dumps(body).encode() if body is not None else None)
        with OPENER.open(req, timeout=20) as response:
            return json.load(response)

    def write(path, **body):
        return request(path, 'POST', {'reason': 'Isolated real browser regression', **body})

    with tempfile.TemporaryDirectory(prefix='dashai-releases-ui-') as data_dir, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(port), '--data-dir', data_dir],
                                   cwd=ROOT, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = time.monotonic() + 60
            while True:
                try:
                    request('/health')
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.1)
            project = write('/projects', name='Release QA')
            other = write('/projects', name='Second QA')
            release_path = f"/projects/{project['id']}/releases"
            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                def page_error(error):
                    errors.append(str(error))
                    print('PAGE ERROR: ' + str(error), flush=True)
                page.on('pageerror', page_error)
                page.goto(url, timeout=60000)
                page.locator('.sidebar').get_by_role('button', name='Release QA', exact=False).click()
                tabs = page.locator('.project-tabs')
                expect(tabs.get_by_role('button', name='Версии', exact=True)).to_have_count(0)

                # New assignee from the task form; unsaved and pending names block parent submission.
                page.get_by_role('button', name='Новая задача', exact=True).click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_label('Название задачи').fill('Проверить общий каталог исполнителей')
                dialog.get_by_label('Зачем это нужно').fill('Выбирать собственные имена во всех проектах')
                dialog.get_by_role('button', name='Свой исполнитель', exact=True).click()
                name = dialog.get_by_label('Имя нового исполнителя', exact=True)
                name.fill('Qwen Team / Анна')
                assert not dialog.locator('form').evaluate('form=>form.checkValidity()')
                dialog.locator('form').evaluate('form=>form.requestSubmit()')
                assert not request(f"/projects/{project['id']}")['tasks']
                held = []
                def hold_agent(route):
                    held.append(route)
                page.route('**/api/agents', hold_agent)
                dialog.get_by_role('button', name='Сохранить исполнителя', exact=True).click()
                expect(name).to_have_attribute('aria-disabled', 'true')
                expect(dialog.get_by_label('Исполнитель', exact=True)).to_be_disabled()
                assert not dialog.locator('form').evaluate('form=>form.checkValidity()')
                dialog.locator('form').evaluate('form=>form.requestSubmit()')
                assert not request(f"/projects/{project['id']}")['tasks']
                assert len(held) == 1
                held.pop().continue_()
                page.unroute('**/api/agents', hold_agent)
                expect(name).to_have_count(0)
                agent = next(item for item in request('/bootstrap')['agents'] if item['name'] == 'Qwen Team / Анна')
                expect(dialog.get_by_label('Исполнитель', exact=True)).to_have_value(agent['id'])
                dialog.get_by_role('button', name='Создать', exact=True).click()
                expect(page.locator('.task-detail-heading')).to_contain_text('Проверить общий каталог исполнителей')
                task = request(f"/projects/{project['id']}")['tasks'][0]
                assert task['assignee_id'] == agent['id']
                checks.append('task creation: custom assignee, native unsaved/pending guard, real save and assignment')
                print('PASS task create and pending guards', flush=True)

                # Duplicate names reuse IDs; failed save preserves input; drawer can add another assignee.
                dialog.get_by_role('button', name='Редактировать задачу', exact=True).click()
                edit = dialog.locator('.edit-form')
                edit.get_by_label('Почему меняем задачу').fill('Проверка повторного выбора и нового исполнителя')
                before = len(request('/bootstrap')['agents'])
                edit.get_by_role('button', name='Свой исполнитель', exact=True).click()
                edit.get_by_label('Имя нового исполнителя', exact=True).fill('  qWEN tEAM / АнНа  ')
                edit.get_by_role('button', name='Сохранить исполнителя', exact=True).click()
                expect(edit.get_by_label('Исполнитель', exact=True)).to_have_value(agent['id'])
                assert len(request('/bootstrap')['agents']) == before
                edit.get_by_role('button', name='Свой исполнитель', exact=True).click()
                name = edit.get_by_label('Имя нового исполнителя', exact=True)
                name.fill('Ревью / Ольга')
                def fail_agent(route):
                    route.fulfill(status=503, json={'detail': 'QA intentional save failure'})
                page.route('**/api/agents', fail_agent)
                edit.get_by_role('button', name='Сохранить исполнителя', exact=True).click()
                expect(edit.get_by_role('alert')).to_contain_text('QA intentional save failure')
                expect(name).to_have_value('Ревью / Ольга')
                assert not edit.evaluate('form=>form.checkValidity()')
                page.unroute('**/api/agents', fail_agent)
                name.press('Enter')
                expect(name).to_have_count(0)
                second_agent = next(item for item in request('/bootstrap')['agents'] if item['name'] == 'Ревью / Ольга')
                expect(edit.get_by_label('Исполнитель', exact=True)).to_have_value(second_agent['id'])
                edit.get_by_role('button', name='Сохранить', exact=True).click()
                expect(dialog.locator('.edit-form')).to_have_count(0)
                assert request(f"/tasks/{task['id']}")['task']['assignee_id'] == second_agent['id']
                dialog.get_by_role('button', name='Закрыть', exact=True).click()
                page.locator('.sidebar').get_by_role('button', name='Second QA', exact=False).click()
                page.reload()
                page.get_by_role('button', name='Новая задача', exact=True).click()
                select = dialog.get_by_label('Исполнитель', exact=True)
                expect(select.locator(f'option[value="{agent["id"]}"]')).to_have_text('Qwen Team / Анна')
                expect(select.locator(f'option[value="{second_agent["id"]}"]')).to_have_text('Ревью / Ольга')
                dialog.get_by_role('button', name='Отмена', exact=True).click()
                checks.append('drawer: duplicate casefold reuse, failed-save input retained, Enter retry, cross-project reload persistence')
                print('PASS duplicate, drawer, failed save and cross-project persistence', flush=True)

                # Enable the optional module through the actual catalog.
                page.locator('.sidebar').get_by_role('button', name='Release QA', exact=False).click()
                tabs.get_by_role('button', name='Модули', exact=True).click()
                page.get_by_role('button', name='Каталог', exact=False).click()
                row = page.locator('.module-row').filter(has=page.get_by_role('button', name='Версии проекта', exact=True))
                row.get_by_role('button', name='Добавить', exact=True).click()
                tabs.get_by_role('button', name='Версии', exact=True).click()
                try:
                    expect(page.get_by_role('heading', name='Журнал релизов пока пуст', exact=True)).to_be_visible()
                except AssertionError:
                    page.screenshot(path=str(OUTPUT / 'release-initial-failure.png'), full_page=True)
                    print(page.locator('body').inner_text(), flush=True)
                    raise
                page.get_by_role('button', name='Добавить версию', exact=True).click()
                form = page.locator('.release-form')
                form.get_by_label('Номер версии', exact=True).fill('1.7.0')
                form.get_by_label('Название выпуска', exact=True).fill('История версий и собственные исполнители')
                form.get_by_label('Что сделали', exact=True).fill('Добавили журнал выпусков.\nИсправили выбор исполнителя во всех проектах.\n<unsafe> остаётся обычным текстом.')
                form.get_by_label('Commit или tag', exact=False).fill('v1.7.0')
                form.get_by_label('Ссылка на выпуск', exact=False).fill('https://example.com/releases/1.7.0')
                assert form.evaluate('form=>form.checkValidity()')
                form.get_by_role('button', name='Сохранить версию', exact=True).click()
                expect(page.locator('.release-document')).to_contain_text('История версий и собственные исполнители')
                release = request(release_path)['releases'][0]
                assert release['status'] == 'draft' and release['released_at'] is None
                page.get_by_role('button', name='Изменить запись', exact=True).click()
                form.get_by_label('Состояние').select_option('released')
                form.get_by_label('Комментарий к записи', exact=True).fill('Выложили версию в production')
                assert not form.evaluate('form=>form.checkValidity()')
                expect(form.get_by_label('Дата выпуска', exact=True)).to_have_attribute('required', '')
                form.get_by_role('button', name='Сохранить версию', exact=True).click()
                assert request(release_path + '/' + release['id'])['version'] == 1
                form.get_by_label('Дата выпуска', exact=True).fill('2026-10-17')
                form.get_by_role('button', name='Сохранить версию', exact=True).click()
                expect(page.locator('.release-document .release-status')).to_have_text('Выпущена')
                released = request(release_path + '/' + release['id'])
                assert released['status'] == 'released' and released['environment'] == 'production' and released['version'] == 2
                checks.append('optional releases catalog: real draft save, release-date constraint and production record readback')
                print('PASS release draft and production publish', flush=True)

                # A concurrent real API update must not silently overwrite local text.
                expect(page.get_by_role('button', name='Изменить запись', exact=True)).to_be_enabled()
                page.get_by_role('button', name='Изменить запись', exact=True).click()
                try:
                    expect(form).to_be_visible()
                except AssertionError:
                    page.screenshot(path=str(OUTPUT / 'release-edit-failure.png'), full_page=True)
                    print(page.locator('body').inner_text(), flush=True)
                    raise
                form.get_by_label('Что сделали').fill('Local unsaved conflict text')
                form.get_by_label('Комментарий к записи', exact=True).fill('Проверка защиты от чужой записи')
                page.once('dialog', lambda value: value.dismiss())
                tabs.get_by_role('button', name='Модули', exact=True).click()
                expect(form.get_by_label('Что сделали')).to_have_value('Local unsaved conflict text')
                request(release_path + '/' + release['id'], 'PATCH', {'expected_version': 2, 'changes': {'changelog': 'Remote verified update'}, 'reason': 'Real concurrent API edit'})
                form.get_by_role('button', name='Сохранить версию', exact=True).click()
                expect(page.locator('.project-releases [role=alert]')).to_contain_text('изменена')
                expect(form.get_by_label('Что сделали')).to_have_value('Local unsaved conflict text')
                expect(form.get_by_role('button', name='Сохранить версию', exact=True)).to_be_disabled()
                page.once('dialog', lambda value: value.dismiss())
                page.get_by_role('button', name='Перечитать запись', exact=True).click()
                expect(form.get_by_label('Что сделали')).to_have_value('Local unsaved conflict text')
                page.once('dialog', lambda value: value.accept())
                page.get_by_role('button', name='Перечитать запись', exact=True).click()
                expect(page.locator('.release-document')).to_contain_text('Remote verified update')
                expect(page.locator('.release-row')).to_contain_text('Remote verified update')
                assert request(release_path + '/' + release['id'])['version'] == 3
                events = request('/history?project_id=' + project['id'] + '&limit=500')['events']
                actions = [item for item in events if item['entity_type'] == 'project_release']
                assert [item['action'] for item in actions] == ['project_release.created', 'project_release.updated', 'project_release.updated']
                assert actions[-1]['before']['version'] == 2 and actions[-1]['after']['version'] == 3
                checks.append('real concurrent release conflict preserves draft; explicit confirmed refresh; atomic audit readback')
                print('PASS release conflict and audit', flush=True)

                # First visual batch: collect every view before making any visual judgement.
                expect(page.locator('.toast.visible')).to_have_count(0, timeout=10000)
                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'release detail overflow at {width}'
                    assert page.locator('.release-search input').evaluate('node=>parseFloat(getComputedStyle(node).paddingLeft)>=38'), f'release search icon overlap at {width}'
                    path = OUTPUT / f'release-detail-{width}.png'
                    page.screenshot(path=str(path), full_page=True)
                    screenshots.append(path.name)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.get_by_role('button', name='Изменить запись', exact=True).click()
                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'release editor overflow at {width}'
                    path = OUTPUT / f'release-editor-{width}.png'
                    page.screenshot(path=str(path), full_page=True)
                    screenshots.append(path.name)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                form.get_by_role('button', name='Отмена', exact=True).click()

                tabs.get_by_role('button', name='Модули', exact=True).click()
                row.get_by_role('button', name='Убрать', exact=True).click()
                expect(tabs.get_by_role('button', name='Версии', exact=True)).to_have_count(0)
                assert request(release_path + '/' + release['id'])['changelog'] == 'Remote verified update'
                page.get_by_role('button', name='Каталог', exact=False).click()
                row.get_by_role('button', name='Добавить', exact=True).click()
                tabs.get_by_role('button', name='Версии', exact=True).click()
                page.locator('.release-row').click()
                expect(page.locator('.release-document')).to_contain_text('Remote verified update')
                page.reload()
                tabs.get_by_role('button', name='Версии', exact=True).click()
                page.locator('.release-row').click()
                expect(page.locator('.release-document')).to_contain_text('Remote verified update')
                checks.append('release module disable/re-enable and page reload preserve version history')

                tabs.get_by_role('button', name='Доска', exact=False).click()
                page.get_by_role('button', name='Новая задача', exact=True).click()
                dialog.get_by_role('button', name='Свой исполнитель', exact=True).click()
                dialog.get_by_label('Имя нового исполнителя', exact=True).fill('Собственная команда проверяет интерфейс на маленьком экране')
                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                    dialog.locator('.assignee-select').scroll_into_view_if_needed()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'assignee overflow at {width}'
                    if width < 700:
                        assert dialog.locator('.assignee-select').evaluate('node=>node.getBoundingClientRect().width>=node.parentElement.getBoundingClientRect().width-1'), f'assignee field too narrow at {width}'
                    path = OUTPUT / f'assignee-create-{width}.png'
                    page.screenshot(path=str(path))
                    screenshots.append(path.name)
                assert not errors, errors
                browser.close()
            evidence = {'result': 'PASS', 'checks': checks, 'screenshots': screenshots, 'page_errors': errors,
                        'backend': 'real isolated SQLite and HTTP API; real production dist',
                        'synthetic': ['one deliberate 503 assignee-save response; delay-only routes continue to the real backend'],
                        'app_version': json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version'],
                        'frontend_entry_sha256': hashlib.sha256((ROOT / 'dist/index.html').read_bytes()).hexdigest(),
                        'viewports': [1440, 390, 320]}
            (OUTPUT / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(evidence, ensure_ascii=False))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
