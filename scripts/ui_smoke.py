"""Browser integration check against an isolated real SQLite/API server, not mocked responses."""
import json
import os
import re
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
                expect(page.get_by_role('heading',name='С чего начнём этот проект?')).to_be_visible()
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

                header_edit=dialog.get_by_role('button',name=re.compile(r'^(Редактировать задачу|Отменить редактирование)$'))
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
                    page.once('dialog', lambda confirmation: confirmation.accept())
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
                page.once('dialog', lambda confirmation: confirmation.accept())
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
                expect(dialog.locator('.task-properties .priority-mark')).to_contain_text('Высокий')
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
                expect(page.locator('.connector-configurator pre')).to_contain_text('--agent')
                expect(page.get_by_label('Приложение / MCP-клиент',exact=False).locator('option')).to_have_count(6)
                page.get_by_label('Приложение / MCP-клиент',exact=False).select_option('cursor')
                expect(page.locator('.connector-configurator')).to_contain_text('.cursor/mcp.json')
                assert 'mcpServers' in page.locator('.connector-configurator pre').inner_text()
                page.get_by_role('button',name='Отдельный агент',exact=True).click()
                dialog.get_by_label('Имя модели или агента',exact=False).fill('Qwen · локальный ревьюер')
                expect(dialog.get_by_label('Тип идентичности',exact=True)).to_have_value('custom')
                dialog.get_by_role('button',name='Создать идентичность',exact=True).click()
                expect(dialog.get_by_role('heading',name='Сохраните токен агента')).to_be_visible()
                dialog.get_by_role('button',name='Токен сохранен',exact=True).click()
                identity=next(agent for agent in request('/bootstrap')['agents'] if agent['name']=='Qwen · локальный ревьюер')
                assert identity['kind']=='custom' and identity['last_seen'] is None
                expect(page.get_by_label('Имя агента в истории',exact=False)).to_have_value(identity['id'])
                page.locator('.connector-config-controls input').fill(str((ARTIFACTS/'never-read-token-file.json').resolve()))
                expect(page.locator('.connector-configurator pre')).to_contain_text(identity['id'])
                assert '--token-file' in page.locator('.connector-configurator pre').inner_text()
                checks.append('six MCP client formats, custom model identity, isolated token path and truthful last-seen')
                # Production documentation uses the real API/store and renders published Mermaid.
                docs_project=request('/projects','POST',{'name':'Production Map QA','description':'Isolated documentation verification','reason':'Verify production map'})
                page.reload()
                page.locator('.sidebar').get_by_role('button',name='Production Map QA',exact=False).click()
                page.locator('.project-tabs').get_by_role('button',name='Карта проекта',exact=True).click()
                expect(page.get_by_text('Агент ещё не опубликовал карту этого проекта',exact=True)).to_be_visible()
                page.get_by_role('button',name='Задача на анализ',exact=True).click()
                expect(page.get_by_role('button',name='ожидает агента',exact=False)).to_be_visible()
                assert request('/projects/'+docs_project['id'])['tasks'][0]['task_type']=='documentation'
                prototype=context.new_page()
                prototype.goto((ROOT/'docs/design/project-map.html').as_uri())
                manifest=prototype.evaluate('''() => ({source_revision:'isolated-browser-QA',
                  files:files.map(f=>({path:f.path,kind:'file',sha256:'1'.repeat(64),description:{title:f.title,summary:f.summary,purpose:f.why,workflow:f.steps.map(s=>s.join(': ')),related_paths:f.related}})),
                  diagrams:Object.entries(notations).filter(([id])=>id!=='overview').map(([id,n])=>({id,title:n.title,notation:({context:'c4_context',containers:'c4_containers',components:'c4_components',sequence:'sequence',states:'state',data:'erd',flow:'flowchart'})[id],scope:n.scope,explanation:n.explanation.join('\\n'),legend:n.legend,source:n.source,related_paths:n.files}))})''')
                prototype.close()
                page.locator('.map-import summary').click()
                page.get_by_label('Снимок JSON',exact=True).fill(json.dumps(manifest,ensure_ascii=False))
                page.get_by_label('Причина публикации',exact=True).fill('Проверка реального импорта, без пользовательских данных')
                page.get_by_role('button',name='Опубликовать снимок',exact=True).click()
                page.get_by_label('Найти файл или объяснение',exact=True).fill('server/app.py')
                expect(page.get_by_role('treeitem')).to_have_count(1)
                page.get_by_role('treeitem').click()
                expect(page.get_by_role('tree')).to_be_focused()
                page.get_by_label('Найти файл или объяснение',exact=True).fill('')
                expect(page.locator('.map-file-article')).to_contain_text('Единые правила для человека и агентов')
                page.get_by_label('Основание проверки',exact=True).fill('Проверены текст и снимок в изолированном QA')
                page.get_by_role('button',name='Подтвердить после сверки',exact=True).click()
                expect(page.locator('.map-meta')).to_contain_text('Проверено человеком')
                page.locator('.project-tabs').get_by_role('button',name='Архитектура',exact=True).click()
                for item in manifest['diagrams']:
                    library=page.locator('.architecture-library')
                    if not library.evaluate('element=>element.open'):
                        library.locator('summary').click()
                    page.get_by_role('list',name='Схемы проекта',exact=True).get_by_role('button',name=re.compile('^'+re.escape(item['title'])+' ·')).click()
                    expect(page.locator('.map-diagram iframe')).to_have_count(1,timeout=30000)
                    expect(page.locator('.map-diagram iframe')).to_have_attribute('sandbox','')
                    expect(page.locator('.map-file-article h2')).to_have_text(item['title'])
                    assert page.locator('.map-diagram iframe').get_attribute('srcdoc').count('<svg')==1
                related_path=manifest['diagrams'][-1]['related_paths'][0]
                page.locator('.map-related').get_by_role('button',name=related_path,exact=True).click()
                expect(page.locator('.map-tree [role=treeitem][aria-selected=true]')).to_have_attribute('data-path',related_path)
                expect(page.locator('.map-file-article h2')).to_be_focused()
                page.locator('.project-tabs').get_by_role('button',name='Документация',exact=True).click()
                page.get_by_role('button',name='Настроить состав',exact=True).click()
                page.get_by_label('Название',exact=True).fill('Production documentation')
                for item in manifest['diagrams']:
                    page.locator('.map-settings').get_by_role('checkbox',name=item['title'],exact=False).check()
                page.locator('.doc-navigation').get_by_role('button',name='Архитектура и сценарии',exact=True).click()
                expect(page.locator('.map-diagram iframe')).to_have_count(7,timeout=30000)
                page.get_by_label('Причина сохранения',exact=True).fill('Сохраняем выбранные разделы и схемы')
                pending_saves=[]
                page.route('**/api/projects/*/map/document',lambda route:pending_saves.append(route))
                page.get_by_role('button',name='Сохранить состав',exact=True).click()
                expect(page.get_by_label('Название',exact=True)).to_be_disabled()
                expect(page.get_by_label('Контекст',exact=True)).to_be_disabled()
                expect(page.locator('.map-settings input[type=checkbox]').first).to_be_disabled()
                assert len(pending_saves)==1
                pending_saves.pop().continue_()
                page.unroute('**/api/projects/*/map/document')
                expect(page.get_by_label('Название',exact=True)).to_be_enabled()
                expect(page.get_by_role('button',name='Сохранить состав',exact=True)).to_be_disabled()
                page.locator('details.doc-source > summary').click()
                page.get_by_label('Номер версии карты',exact=True).fill('2')
                page.locator('.map-version').get_by_role('button',name='Открыть',exact=True).click()
                expect(page.get_by_label('Название',exact=True)).to_be_disabled()
                expect(page.locator('.map-settings input[type=checkbox]').first).to_be_disabled()
                expect(page.get_by_role('button',name='К текущей карте',exact=True)).to_be_enabled()
                with page.expect_download() as historical_download:
                    page.get_by_role('button',name='Markdown',exact=True).click()
                assert 'Версия карты: 2.' in Path(historical_download.value.path()).read_text(encoding='utf-8')
                page.get_by_role('button',name='К текущей карте',exact=True).click()
                expect(page.get_by_label('Название',exact=True)).to_be_enabled()
                expect(page.get_by_label('Название',exact=True)).to_have_value('Production documentation')
                with page.expect_download() as downloaded:
                    page.get_by_role('button',name='Markdown',exact=True).click()
                content=Path(downloaded.value.path()).read_text(encoding='utf-8')
                assert 'Production documentation' in content and 'sequenceDiagram' in content and 'erDiagram' in content
                with page.expect_download() as downloaded:
                    page.get_by_role('button',name='HTML',exact=True).click()
                exported_html=ARTIFACTS/'production-documentation.html'
                downloaded.value.save_as(exported_html)
                html=exported_html.read_text(encoding='utf-8')
                assert html.count('<svg')==7 and 'Content-Security-Policy' in html
                assert '<script' not in html and '<iframe' not in html
                page.get_by_label('Название',exact=True).fill('Draft survives conflict')
                page.get_by_label('Причина сохранения',exact=True).fill('Verify conflict')
                map_url='/projects/'+docs_project['id']+'/map'
                current_map=request(map_url)
                request(map_url+'/document','PATCH',{'expected_version':current_map['version'],'document':{**current_map['document'],'title':'Concurrent saved title'},'reason':'Concurrent document save'})
                page.get_by_role('button',name='Сохранить состав',exact=True).click()
                expect(page.locator('.project-map [role=alert]')).to_contain_text('Конфликт')
                expect(page.get_by_label('Название',exact=True)).to_have_value('Draft survives conflict')
                page.once('dialog',lambda d:d.accept())
                page.get_by_role('button',name='Перечитать карту',exact=True).click()
                expect(page.get_by_label('Название',exact=True)).to_have_value('Concurrent saved title')
                page.reload()
                page.locator('.project-tabs').get_by_role('button',name='Документация',exact=True).click()
                page.get_by_role('button',name='Настроить состав',exact=True).click()
                expect(page.get_by_label('Название',exact=True)).to_have_value('Concurrent saved title')
                page.locator('.doc-navigation').get_by_role('button',name='Архитектура и сценарии',exact=True).click()
                expect(page.locator('.map-diagram iframe')).to_have_count(7,timeout=30000)
                for width in (1440,390,320):
                    page.set_viewport_size({'width':width,'height':1000 if width==1440 else 844})
                    for name in ('Карта проекта','Архитектура','Документация'):
                        page.locator('.project-tabs').get_by_role('button',name=name,exact=True).click()
                        if name=='Документация':
                            if width<=800:
                                page.get_by_label('Раздел документа',exact=True).select_option('diagrams')
                            else:
                                page.locator('.doc-navigation').get_by_role('button',name='Архитектура и сценарии',exact=True).click()
                            expect(page.locator('.map-diagram iframe')).to_have_count(7,timeout=30000)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Map reflow {name} at {width}'
                        page.evaluate('window.scrollTo(0,0)')
                        suffix={'Карта проекта':'tree','Архитектура':'architecture','Документация':'documentation'}[name]
                        for frame in page.locator('.map-diagram iframe').all():
                            expect(frame.content_frame.locator('svg')).to_be_visible(timeout=30000)
                            frame.scroll_into_view_if_needed()
                            page.wait_for_timeout(100)
                            if name=='Архитектура':
                                frame.screenshot(path=str(ARTIFACTS/f'production-diagram-{width}.png'))
                                metrics=frame.content_frame.locator('svg').evaluate('(svg)=>({box:svg.getBoundingClientRect().toJSON(),viewBox:svg.getAttribute("viewBox"),text:svg.querySelector("text")?.getBoundingClientRect().toJSON()})')
                                (ARTIFACTS/f'production-diagram-{width}.json').write_text(json.dumps(metrics),encoding='utf-8')
                        page.evaluate('window.scrollTo(0,0)')
                        page.screenshot(path=str(ARTIFACTS/f'production-map-{suffix}-{width}.png'),full_page=True)
                        page.screenshot(path=str(ARTIFACTS/f'production-map-{suffix}-{width}-viewport.png'))
                        if name=='Документация':
                            page.locator('.map-document-preview').evaluate('(el)=>el.scrollIntoView({block:"start"})')
                            page.wait_for_timeout(100)
                            page.screenshot(path=str(ARTIFACTS/f'production-document-preview-{width}.png'))
                checks.append('production map import/review, seven Mermaid renders, architecture-to-file focus, delayed-save guard, historical read-only/export, composition, exports, conflicts, reload and mobile reflow')
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('.project-tabs').get_by_role('button',name='Модули',exact=True).click()
                page.get_by_role('button',name='Каталог',exact=False).click()
                page.locator('.module-info').get_by_role('button',name='Архитектурные решения',exact=True).click()
                page.get_by_role('button',name='Свой модуль',exact=True).click()
                page.locator('.module-create').get_by_label('Название',exact=True).fill('Черновик шаблона QA')
                page.get_by_label('Текст документа',exact=False).fill('## Решение QA\nИспользуем общий API. Текст сохраняется после отключения.')
                expect(page.get_by_role('button',name='Создать шаблон',exact=True)).to_be_disabled()
                pending_modules=[]
                page.route('**/api/projects/*/modules/decisions',lambda route:pending_modules.append(route))
                page.get_by_role('button',name='Добавить и сохранить',exact=True).click()
                expect(page.get_by_label('Текст документа',exact=False)).to_be_disabled()
                expect(page.locator('.module-create').get_by_label('Название',exact=True)).to_be_disabled()
                assert len(pending_modules)==1
                pending_modules.pop().continue_()
                page.unroute('**/api/projects/*/modules/decisions')
                expect(page.get_by_role('button',name='Сохранить',exact=True)).to_be_disabled()
                expect(page.get_by_role('button',name='Создать шаблон',exact=True)).to_be_enabled()
                page.once('dialog',lambda value:value.accept())
                page.get_by_role('button',name='Свой модуль',exact=True).click()
                row=page.locator('.module-row').filter(has=page.get_by_role('button',name='Архитектурные решения',exact=True))
                row.get_by_role('button',name='Убрать',exact=True).click()
                row.get_by_role('button',name='Добавить',exact=True).click()
                row.get_by_role('button',name='Архитектурные решения',exact=True).click()
                expect(page.get_by_label('Текст документа',exact=False)).to_have_value(re.compile('Используем общий API'))
                page.get_by_label('Текст документа',exact=False).fill('Несохранённый ADR')
                page.once('dialog',lambda value:value.dismiss())
                page.locator('.project-tabs').get_by_role('button',name='Доска',exact=False).click()
                expect(page.get_by_label('Текст документа',exact=False)).to_have_value('Несохранённый ADR')
                page.get_by_role('button',name='Сохранить',exact=True).click()
                expect(page.get_by_role('button',name='Сохранить',exact=True)).to_be_disabled()
                map_row=page.locator('.module-row').filter(has=page.get_by_role('button',name='Карта проекта',exact=True))
                map_row.get_by_role('button',name='Убрать',exact=True).click()
                expect(page.locator('.project-tabs').get_by_role('button',name='Карта проекта',exact=True)).to_have_count(0)
                map_row.get_by_role('button',name='Добавить',exact=True).click()
                expect(page.locator('.project-tabs').get_by_role('button',name='Карта проекта',exact=True)).to_be_visible()
                integration_row=page.locator('.module-row').filter(has=page.get_by_role('button',name='Confluence и Jira',exact=True))
                integration_row.get_by_role('button',name='Добавить',exact=True).click()
                page.locator('.project-tabs').get_by_role('button',name='Интеграции',exact=True).click()
                expect(page.locator('.integration-row')).to_have_count(2)
                expect(page.get_by_role('button',name='Проверить и подключить',exact=True).first).to_be_disabled()
                page.locator('.integration-row').first.get_by_label('Размещение',exact=False).select_option('data_center')
                expect(page.locator('.integration-row').first.get_by_label('Personal Access Token',exact=True)).to_have_attribute('type','password')
                page.once('dialog',lambda value:value.accept())
                page.locator('.project-tabs').get_by_role('button',name='Модули',exact=True).click()
                panel_rgb=page.evaluate("""() => {
                    const probe=document.createElement('span');
                    probe.hidden=true; probe.style.backgroundColor='var(--panel)';
                    document.body.append(probe);
                    const color=getComputedStyle(probe).backgroundColor;
                    probe.remove(); return color;
                }""")
                for width in (1440,390,320):
                    page.set_viewport_size({'width':width,'height':1000 if width==1440 else 844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Module reflow {width}'
                    assert page.locator('.module-search input').evaluate("node=>getComputedStyle(node).backgroundColor")==panel_rgb
                    if width<700:
                        tops=page.locator('.tabs-nav>button').evaluate_all('nodes=>nodes.map(node=>node.getBoundingClientRect().top)')
                        assert max(tops)-min(tops)<1, f'Project tabs wrap at {width}: {tops}'
                        assert page.locator('.module-search input').evaluate("node=>getComputedStyle(node).fontSize")=='16px'
                    page.screenshot(path=str(ARTIFACTS/f'workspace-modules-{width}.png'),full_page=True)
                    page.locator('.project-tabs').get_by_role('button',name='Интеграции',exact=True).click()
                    expect(page.locator('.integration-row')).to_have_count(2)
                    assert page.locator('.integration-form input[type=password]').first.evaluate("node=>getComputedStyle(node).backgroundColor")==panel_rgb
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Integration reflow {width}'
                    page.screenshot(path=str(ARTIFACTS/f'workspace-integrations-{width}.png'),full_page=True)
                    page.locator('.project-tabs').get_by_role('button',name='Модули',exact=True).click()
                checks.append('project modules enable/disable preserve text, unsaved guard, feature tabs, optional Cloud/DC connectors and responsive settings')
                assert not page_errors,page_errors
                browser.close()
            (ARTIFACTS/'ui-results.json').write_text(json.dumps({'passed':checks,'count':len(checks)},ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'PASS: {len(checks)} browser integration checks; artifacts/qa/ui-results.json')
        finally:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
