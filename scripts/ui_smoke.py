"""Browser integration check against an isolated real SQLite/API server, not mocked responses."""
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
    req = Request(url + '/api' + path, method=method, headers={'Content-Type':'application/json','X-Dashboard-Client':'browser'}, data=json.dumps(body).encode() if body else None)
    with opener.open(req, timeout=10) as response:
        return json.load(response)

checks = []
with tempfile.TemporaryDirectory(prefix='agentboard-ui-') as directory:
    with (ARTIFACTS / 'ui-server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(port), '--data-dir', directory], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+20
            while True:
                try:
                    request('/health')
                    break
                except OSError:
                    if time.monotonic()>deadline: raise
                    time.sleep(.1)
            with sync_playwright() as p:
                executable=os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name=='nt':
                    cache=Path(os.environ['LOCALAPPDATA'])/'ms-playwright'
                    available=sorted(cache.glob('chromium-*/chrome-win*/chrome.exe'),key=lambda path:int(path.parents[1].name.split('-')[-1]))
                    executable=str(available[-1]) if available else None
                browser=p.chromium.launch(executable_path=executable)
                context=browser.new_context(viewport={'width':1440,'height':1000}, accept_downloads=True)
                page=context.new_page()
                page_errors=[]
                page.on('pageerror',lambda error:page_errors.append(str(error)))
                page.goto(url)
                expect(page.get_by_role('heading',name='У каждого проекта — своя история.')).to_be_visible()
                checks.append('empty workspace without fake activity')
                page.get_by_role('button',name='Создать первый проект').click()
                dialog=page.get_by_role('dialog')
                dialog.get_by_label('Название проекта').fill('Browser QA')
                dialog.get_by_label('Цель проекта').fill('Реальная проверка интерфейса на отдельной базе')
                dialog.get_by_role('button',name='Создать',exact=True).click()
                expect(page.get_by_role('heading',name='Browser QA')).to_be_visible()
                expect(page.get_by_role('button',name='Первый раздел')).to_have_count(0)
                expect(page.get_by_role('combobox',name='Фильтр раздела')).to_have_count(0)
                expect(page.locator('.kanban-column')).to_have_count(5)
                expect(page.get_by_role('button',name='Новая задача',exact=True)).to_be_visible()
                page.get_by_role('button',name='Новая задача',exact=True).click()
                dialog.get_by_label('Название задачи').fill('Проверить сохранение правок')
                task_type=dialog.get_by_role('combobox',name='Тип задачи',exact=True)
                assert set(task_type.locator('option').evaluate_all('items => items.map(item => item.value)')) == {
                    'research','development','testing','bugfix','documentation','other'}
                expect(task_type).to_have_value('development')
                task_type.select_option('research')
                expect(dialog.get_by_role('combobox',name='Раздел',exact=True)).to_have_count(0)
                dialog.get_by_label('Что нужно сделать').fill('Original description')
                dialog.get_by_label('Зачем это нужно').fill('Сохранить контекст и изменения без потерь')
                dialog.get_by_label('Критерии готовности').fill('Форма сохраняется, reload не теряет данные')
                dialog.get_by_role('button',name='Создать',exact=True).click()
                expect(dialog.get_by_role('heading',name='Проверить сохранение правок')).to_be_visible()
                project=request('/bootstrap')['projects'][0]
                task=request('/projects/'+project['id'])['tasks'][0]
                assert task['task_type']=='research'
                expect(dialog.locator('.task-properties').get_by_text('Исследование',exact=True)).to_be_visible()
                checks.append('fresh project creates a typed task directly without a section gate')

                header_edit=dialog.locator('.task-detail-heading').get_by_role('button')
                before_cancel=request('/tasks/'+task['id'])
                for width in (1440,390,320):
                    page.set_viewport_size({'width':width,'height':1000 if width==1440 else 844})
                    dialog.get_by_role('button',name='Изменить статус или детали').click()
                    expect(header_edit).to_be_focused()
                    type_picker=dialog.get_by_role('combobox',name='Тип задачи',exact=True)
                    type_picker.select_option('testing')
                    type_picker.focus()
                    page.keyboard.press('Alt+ArrowDown')
                    page.keyboard.press('Escape')
                    expect(dialog).to_be_visible()
                    expect(type_picker).to_be_focused()
                    dialog.get_by_role('button',name='Отмена',exact=True).click()
                    expect(header_edit).to_be_focused()
                    expect(type_picker).to_have_count(0)
                    assert request('/tasks/'+task['id'])==before_cancel
                page.set_viewport_size({'width':1440,'height':1000})
                checks.append('1440px/390px/320px native type-popup Escape and edit cancellation preserve dialog, focus and data')

                page.get_by_role('button',name='Изменить статус или детали').click()
                dialog.get_by_role('combobox',name='Тип задачи',exact=True).select_option('bugfix')
                type_reason='Уточняем тип работы: исправляем выявленную ошибку'
                dialog.get_by_label('Почему меняем задачу').fill(type_reason)
                dialog.get_by_role('button',name='Сохранить',exact=True).click()
                expect(dialog.locator('.task-properties').get_by_text('Исправление',exact=True)).to_be_visible()
                expect(header_edit).to_be_focused()
                typed=request('/tasks/'+task['id'])
                type_events=[event for event in typed['events'] if event['reason']==type_reason]
                assert typed['task']['task_type']=='bugfix' and len(type_events)==1
                assert type_events[0]['before']['task_type']=='research' and type_events[0]['after']['task_type']=='bugfix'
                type_event=dialog.locator('.timeline-event').filter(has_text=type_reason)
                type_event.locator('summary').click()
                expect(type_event.get_by_text('Тип задачи',exact=True)).to_be_visible()
                expect(type_event.get_by_text('Исследование',exact=True)).to_be_visible()
                expect(type_event.get_by_text('Исправление',exact=True)).to_be_visible()
                checks.append('task type editing stores its reason and before/after history atomically')

                page.get_by_role('button',name='Изменить статус или детали').click()
                dialog.get_by_label('Статус',exact=True).select_option('done')
                dialog.get_by_label('Почему меняем задачу').fill('Проверяем gate готовности')
                dialog.get_by_role('button',name='Сохранить',exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('проверки')
                assert request('/tasks/'+task['id'])['task']['status']=='backlog'
                dialog.get_by_role('button',name='Отмена',exact=True).click()
                expect(header_edit).to_be_focused()
                dialog.get_by_label('Добавить запись',exact=True).select_option('evidence')
                dialog.get_by_label('Что проверили и какой результат').fill('Browser integration: creation and persistence passed')
                dialog.get_by_label('Почему добавляем запись').fill('Подтверждение перед завершением')
                dialog.get_by_role('button',name='Добавить в историю').click()
                expect(dialog.locator('.note.evidence')).to_have_count(1)
                page.get_by_role('button',name='Изменить статус или детали').click()
                dialog.get_by_label('Статус',exact=True).select_option('done')
                dialog.get_by_label('Почему меняем задачу').fill('Проверка приложена')
                dialog.get_by_role('button',name='Сохранить',exact=True).click()
                expect(dialog.locator('.task-properties .status-pill')).to_contain_text('Готово')
                checks.append('evidence gate, note type selection and completion')

                page.get_by_role('button',name='Изменить статус или детали').click()
                dialog.get_by_label('Приоритет',exact=True).select_option('high')
                dialog.get_by_label('Почему меняем задачу').fill('Проверяем защиту параллельной правки')
                current=request('/tasks/'+task['id'])['task']
                request('/tasks/'+task['id'],'PATCH',{'expected_version':current['version'],'changes':{'description':'Fresh concurrent description'},'reason':'Concurrent external client changed description'})
                dialog.get_by_role('button',name='Сохранить',exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('Конфликт')
                expect(dialog.get_by_label('Что нужно сделать')).to_have_value('Original description')
                dialog.get_by_role('button',name='Обновить данные',exact=True).click()
                expect(dialog.get_by_role('alert')).to_contain_text('Черновик сохранен')
                dialog.get_by_role('button',name='Сохранить',exact=True).click()
                expect(dialog.locator('.task-properties .priority')).to_contain_text('Высокий')
                final=request('/tasks/'+task['id'])['task']
                assert final['description']=='Fresh concurrent description' and final['priority']=='high' and final['task_type']=='bugfix'
                checks.append('stale edit conflict keeps draft and never overwrites untouched concurrent fields')

                dialog.get_by_label('Добавить запись',exact=True).select_option('change')
                dialog.get_by_label('Что изменено').fill('Проверка записи code change')
                dialog.get_by_label('Измененные файлы').fill('src/App.tsx\nsrc/api.ts')
                dialog.get_by_label('Diff',exact=True).fill('- stale overwrite\n+ changed fields only')
                dialog.get_by_label('Результат проверки').fill('Browser assertion passed')
                dialog.get_by_label('Почему добавляем запись').fill('Записываем файлы и rationale')
                dialog.get_by_role('button',name='Добавить в историю').click()
                expect(dialog.locator('.note.change')).to_have_count(1)
                page.keyboard.press('Escape')
                expect(page.get_by_role('dialog')).to_have_count(0)
                checks.append('structured code change and native dialog Escape')

                page.locator('.project-tabs').get_by_role('button',name='История').click()
                expect(page.get_by_text('подготовил доску проекта',exact=True)).to_be_visible()
                expect(page.get_by_text('создал раздел',exact=True)).to_have_count(0)
                page.locator('.project-tabs').get_by_role('button',name='Доска').click()

                search=page.get_by_role('textbox',name='Поиск задач в проекте')
                search.fill('несуществующая')
                expect(page.get_by_role('heading',name='Задачи не найдены')).to_be_visible()
                page.get_by_role('button',name='Сбросить фильтры',exact=True).last.click()
                expect(page.locator('.kanban-card')).to_have_count(1)
                page.reload()
                expect(page.locator('.kanban-card')).to_have_count(1)
                expect(page.locator('.kanban-card').get_by_text('Исправление',exact=True)).to_be_visible()
                with page.expect_download() as download:
                    page.get_by_role('button',name='Экспортировать проект').click()
                export_path=ARTIFACTS/'browser-export.json'
                download.value.save_as(export_path)
                exported=json.loads(export_path.read_text(encoding='utf-8'))
                assert len(exported['events'])>=7 and len(exported['notes'])==2 and 'token' not in exported
                assert exported['tasks'][0]['id']==task['id'] and exported['tasks'][0]['task_type']=='bugfix'
                assert any(event['reason']==type_reason for event in exported['events'])
                checks.append('search/reset, typed card reload persistence and full history export')
                page.screenshot(path=str(ARTIFACTS/'ui-smoke-desktop.png'),full_page=True)
                for width in (390,320):
                    page.set_viewport_size({'width':width,'height':844})
                    page.locator('.kanban-status-nav').get_by_role('button', name='Готово').click()
                    expect(page.locator('.kanban-column:visible')).to_have_count(1)
                    expect(page.locator('.kanban-card:visible')).to_have_count(1)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'reflow failed at {width}px'
                    page.evaluate('window.scrollTo(0, 0)')
                    expect(page.locator('.toast')).to_have_text('')
                    page.screenshot(path=str(ARTIFACTS/f'ui-smoke-mobile-{width}.png'),full_page=True)
                checks.append('390px/320px board reflow')
                page.get_by_role('button',name='Открыть меню').click()
                assert page.evaluate("document.querySelector('.sidebar').contains(document.activeElement)")
                assert page.locator('.main-shell').get_attribute('inert') is not None
                for _ in range(20):
                    page.keyboard.press('Tab')
                    assert page.evaluate("document.querySelector('.sidebar').contains(document.activeElement)")
                page.keyboard.press('Escape')
                expect(page.get_by_role('button',name='Открыть меню')).to_be_focused()
                assert page.locator('.main-shell').get_attribute('inert') is None
                page.locator('.skip-link').focus()
                for _ in range(10):
                    page.keyboard.press('Tab')
                    assert not page.evaluate("document.querySelector('.sidebar').contains(document.activeElement)")
                checks.append('mobile menu focus trap, Escape restore and hidden navigation excluded from Tab')
                page.set_viewport_size({'width':1440,'height':1000})
                page.get_by_role('button',name='Коннекторы',exact=False).first.click()
                expect(page.locator('.connector-card')).to_have_count(2)
                assert '--agent' in page.locator('.connector-card.codex pre').inner_text()
                checks.append('Codex and Claude connector config displayed')
                assert not page_errors,page_errors
                browser.close()
            (ARTIFACTS/'ui-results.json').write_text(json.dumps({'passed':checks,'count':len(checks)},ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'PASS: {len(checks)} browser integration checks; artifacts/qa/ui-results.json')
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
