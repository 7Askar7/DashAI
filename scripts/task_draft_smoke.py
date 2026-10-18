"""Draft safety and task review regression against an isolated real HTTP/SQLite store."""
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
OUTPUT = ROOT / 'artifacts/qa/task-drafts'
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

    with tempfile.TemporaryDirectory(prefix='dashai-draft-ui-') as directory, (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
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
            project = request('/projects', 'POST', {'name': 'Draft QA', 'reason': 'Isolated browser regression'})
            with sync_playwright() as p:
                executable = os.environ.get('AGENTBOARD_BROWSER')
                if not executable and os.name == 'nt':
                    available = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'), key=lambda path: int(path.parents[1].name.split('-')[-1]))
                    executable = str(available[-1]) if available else None
                browser = p.chromium.launch(executable_path=executable)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                page.get_by_role('button', name='Новая задача', exact=True).click()
                dialog = page.get_by_role('dialog')
                title = dialog.get_by_label('Название задачи')
                title.fill('Проверить сохранность черновика')
                dialog.get_by_label('Зачем это нужно').fill('Не терять введённую работу')
                confirms = []

                def dismiss(confirm):
                    confirms.append(confirm.message)
                    confirm.dismiss()

                page.on('dialog', dismiss)
                for close in (lambda: page.keyboard.press('Escape'),
                              lambda: dialog.get_by_role('button', name='Закрыть', exact=True).click(),
                              lambda: page.mouse.click(4, 4),
                              lambda: dialog.get_by_role('button', name='Отмена', exact=True).click()):
                    close()
                    expect(title).to_have_value('Проверить сохранность черновика')
                assert len(confirms) == 4, confirms
                assert page.evaluate("() => { const e = new Event('beforeunload', {cancelable:true}); window.dispatchEvent(e); return e.defaultPrevented; }")
                checks.append('Escape, close, backdrop, cancel and beforeunload preserve the rejected draft')

                held = []
                page.route('**/api/tasks', lambda route: held.append(route))
                dialog.get_by_role('button', name='Создать', exact=True).click()
                expect(dialog.get_by_role('button', name='Закрыть', exact=True)).to_be_disabled()
                expect(title).to_be_disabled()
                page.keyboard.press('Escape')
                expect(dialog).to_be_visible()
                assert len(held) == 1
                held.pop().fulfill(status=503, json={'detail': 'QA intentional unavailable save'})
                expect(dialog.get_by_role('alert')).to_contain_text('QA intentional unavailable save')
                expect(title).to_have_value('Проверить сохранность черновика')
                page.unroute('**/api/tasks')
                dialog.get_by_role('button', name='Создать', exact=True).click()
                expect(dialog.locator('.task-detail-heading')).to_contain_text('Проверить сохранность черновика')
                task = request(f"/projects/{project['id']}")['tasks'][0]
                checks.append('Pending disables fields and close; failed save preserves draft; retry creates one real task')

                review = dialog.get_by_role('region', name='Готовность к завершению')
                expect(review).to_contain_text('Добавьте критерии готовности')
                expect(review).to_contain_text('Проверка пока не приложена')
                note = dialog.locator('.note-form')
                note.get_by_label('Добавить запись').select_option('change')
                note.get_by_label('Что изменено').fill('Черновик правки кода')
                note.get_by_label('Измененные файлы').fill('src/App.tsx')
                note.get_by_label('Diff', exact=True).fill('+ draft guard')
                before = len(confirms)
                review.get_by_role('button', name='Добавить проверку', exact=True).click()
                expect(note.get_by_label('Добавить запись')).to_have_value('change')
                expect(note.get_by_label('Измененные файлы')).to_have_value('src/App.tsx')
                note.get_by_label('Добавить запись').select_option('evidence')
                expect(note.get_by_label('Добавить запись')).to_have_value('change')
                expect(note.get_by_label('Diff', exact=True)).to_have_value('+ draft guard')
                assert len(confirms) == before + 2
                note.get_by_label('Измененные файлы').fill('')
                note.get_by_label('Diff', exact=True).fill('')
                review.get_by_role('button', name='Добавить проверку', exact=True).click()
                expect(note.get_by_label('Добавить запись')).to_have_value('evidence')
                note.get_by_label('Что проверили и какой результат').fill('Проверено вручную: отмена сохраняет все введённые поля.')
                note.get_by_label('Почему добавляем запись').fill('Зафиксировать проверенный результат')
                before = len(confirms)
                dialog.get_by_role('button', name='Редактировать задачу', exact=True).click()
                assert len(confirms) == before + 1
                expect(note).to_be_visible()
                page.route('**/api/tasks/*/notes', lambda route: held.append(route))
                note.get_by_role('button', name='Добавить в историю', exact=True).click()
                expect(dialog.get_by_role('button', name='Изменить статус или детали', exact=True)).to_be_disabled()
                assert len(held) == 1
                held.pop().continue_()
                page.unroute('**/api/tasks/*/notes')
                expect(review).to_contain_text('Проверка приложена')
                expect(review).to_contain_text('Проверено вручную: отмена сохраняет все введённые поля.')
                expect(review).to_contain_text('Запись автора; DashAI не выполняет проверки.')
                review.get_by_role('button', name='К записям и проверкам', exact=True).click()
                expect(dialog.locator('.note.evidence')).to_be_focused()
                before = len(confirms)
                dialog.get_by_role('button', name='Закрыть', exact=True).click()
                expect(dialog).to_have_count(0)
                assert len(confirms) == before, 'saved note must not trigger an unsaved warning'
                assert request(f"/tasks/{task['id']}")['notes'][0]['kind'] == 'evidence'
                checks.append('Evidence shortcut and note-type select protect change metadata; note survives edit intent; saved evidence appears with provenance')

                page.get_by_role('button', name=f"Открыть задачу {task['short_id']}: {task['title']}", exact=True).click()
                dialog.get_by_role('button', name='Редактировать задачу', exact=True).click()
                edit = dialog.locator('.edit-form')
                edit.get_by_label('Название задачи').fill('Несохранённая новая формулировка')
                edit.get_by_role('button', name='Отмена', exact=True).click()
                expect(edit.get_by_label('Название задачи')).to_have_value('Несохранённая новая формулировка')
                edit.get_by_label('Название задачи').fill(task['title'])
                before = len(confirms)
                edit.get_by_role('button', name='Отмена', exact=True).click()
                expect(edit).to_have_count(0)
                assert len(confirms) == before, 'reverting edits must not show a discard warning'
                checks.append('Edit cancellation protects changes; reverted edits cancel without a warning')
                edit_button = dialog.get_by_role('button', name='Редактировать задачу', exact=True)
                edit_button.click()
                edit.get_by_label('Критерии готовности').fill('Черновик сохраняется при ошибке, фокус возвращается после сохранения')
                edit.get_by_label('Почему меняем задачу').fill('Зафиксировать критерии завершения')
                edit.get_by_role('button', name='Сохранить', exact=True).click()
                expect(edit).to_have_count(0)
                expect(edit_button).to_be_focused()
                expect(review).to_contain_text('Критерии заданы')
                checks.append('Successful task edit restores focus after pending controls are enabled')

                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                    review.scroll_into_view_if_needed()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'page overflow: {width}'
                    assert dialog.evaluate('node => node.scrollWidth <= node.clientWidth + 1'), f'drawer overflow: {width}'
                    page.screenshot(path=str(OUTPUT / f'task-review-{width}.png'))
                checks.append('Task review remains within drawer and page at 1440, 390 and 320 px')
                assert not errors, errors
                browser.close()
            evidence = {'result': 'PASS', 'checks': checks, 'page_errors': errors,
                        'backend': 'real isolated SQLite/API and production dist',
                        'synthetic': 'one intentional 503 save response; held request used to verify pending state',
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
