# macOS support and interface updates 1.5.2

## Исправление кэша интерфейса 1.5.2

После повторного сообщения пользователя закрытие/переоткрытие вкладки не помогло. Проверка исключила второй desktop-процесс и активную установку 1.4.3: registry выбирал 1.5.0, живой сервер тоже 1.5.0. Обнаружен конкретный дефект: iframe использовал постоянный `/?vscode=1`, а HTML entry point не имел `Cache-Control`, поэтому браузер мог эвристически сохранить прежний HTML и его старые hash-ресурсы.

В 1.5.2 iframe query включает URL-encoded версию и экземпляр runtime, а общий frontend отвечает `Cache-Control: no-cache` для HTML и SPA fallback. Hash-ресурсы JS/CSS сохраняют прежнюю политику. Открытая страница не перезагружается самопроизвольно, защита несохранённого состава документа и MCP shutdown guard сохранены. Новый клиент может получить свежую страницу уже существующего совместимого runtime 1.5.0 без остановки агентных сессий.

Проверки: 30 Python tests passed, 1 POSIX-only test skipped на Windows; 13 extension tests passed; production build, повторный Windows frozen HTTP/MCP smoke (включая реальный `Cache-Control`) и упаковка VSIX passed. Независимый correctness review и отдельный Ponytail review приняты без замечаний. В отдельном Chromium-тесте воспроизведено сохранение старого iframe после обновления HTTP body и переоткрытия: `initial=OLD, reopened=OLD`; новый revision query получил `NEW`, повторная навигация с `no-cache` получила `REVALIDATED` (1 запрос до revision, 3 всего). Личная база в этом тесте не использовалась.

Windows 1.5.2 установлен штатным `code.cmd --install-extension ... --force` в текущий профиль; registry подтвердил `7askar7.dashai` 1.5.2. Личный сервер и MCP не останавливались. Полный Windows GUI smoke в отдельном профиле заблокирован ожиданием собственного обновления VS Code (`vscode-updating` mutex), а не ошибкой запуска DashAI; лог `artifacts/qa/vscode-actual-b8a53f096b/vscode.log`. Наличие новых вкладок именно в окне пользователя требует **Developer: Reload Window**; DOM этого окна не проверялся.

Нативная проверка пакетов 1.5.2: [38950373566](https://github.com/7Askar7/DashAI/actions/runs/38950373566), commit `1369b60`. ARM прошёл core checks и GUI assertions в VS Code 1.142.0 (`driver-complete.json: passed`); завершение тестового родительского VS Code проверяется отдельно. Финальные пакеты и результаты обеих архитектур добавляются после выполнения.

## Предыдущий кандидат 1.5.1

Причина: опубликованный пакет 1.5.0 содержит Windows x64 EXE и точный `win32-x64` target. Удаление ограничения manifest не делает такой runtime исполняемым на Mac.

Исправление: нативные arm64/x64 сборки, платформенные пути и имена бинарников, POSIX desktop/MCP locks, общий проверяющий упаковщик и CI на двух macOS runner. На Mac нет PowerShell/Inno Setup updater: используется штатный Marketplace. Store/API/domain behavior остаются общими.

Независимый correctness review обнаружил гонку shared MCP lock с health probe и проблему directory symlinks PyInstaller в VSCE. Исправлено ожиданием shared lock, запретом запуска без lock, `--follow-symlinks` и smoke извлечённого итогового VSIX. Отдельный Ponytail review: удалён неиспользуемый `Invoke-BuildNode`; новых runtime-зависимостей нет. `macholib` — необходимая зафиксированная build-зависимость PyInstaller на macOS.

Локальные проверки: 29 Python tests passed, 1 POSIX test skipped на Windows; 13 extension tests passed; production frontend build и Windows frozen HTTP/MCP smoke passed. Installer и Windows Marketplace VSIX 1.5.1 пересобраны; общий упаковщик проверил состав, версии, target и отсутствие личных данных.

Нативная сборка [38946612650](https://github.com/7Askar7/DashAI/actions/runs/38946612650), commit `c1413a7f235900b636fd0b6e1a2d04089a270c33`: **обе архитектуры прошли** 30 Python-тестов (включая настоящие POSIX locks), 13 extension tests, запуск HTTP/MCP из извлечённого итогового VSIX и `codesign --verify --deep --strict` обоих executable. Архивы скачаны из Actions, SHA-256 внешних ZIP совпал с API digest, каждый VSIX повторно прошёл `verify_package` локально. Последующие изменения касались QA harness и документации; production runtime в этих пакетах не менялся.

| VSIX 1.5.1 | Bytes | SHA-256 |
| --- | ---: | --- |
| `win32-x64` | 37500214 | `f1b02846d162d6952758ad8f6ba127f258ef179aac7c792fb9c6e8344a31d6a4` |
| `darwin-arm64` | 41405335 | `f64bfb522e539b8a1c07cd2c9375f44da7d99864051ae959815d606127b4bea1` |
| `darwin-x64` | 40528298 | `7dbda1873b3329140e9a820c12c2e0656dd3913798061251b56aec8edb94736c` |

Пакеты и инструкция загрузки собраны в `artifacts/releases/1.5.1/marketplace/`. Они не опубликованы в Marketplace автоматически: издателю нужно загрузить три target-варианта существующего `7Askar7.dashai` одной версии. Локальная готовность и успешный CI не означают принятие Marketplace.

Дополнительная проверка открытия расширения в настоящем VS Code отделена от проверки native runtime. Первый QA-запуск редактора не завершился; production failure из него не установлен. В harness удалено ненужное обращение к clipboard для native smoke, добавлены progress markers, уникальная временная HOME, удаление наследованных VSCODE/ELECTRON/token env и 5-минутный timeout. Новый прогон: [38948405977](https://github.com/7Askar7/DashAI/actions/runs/38948405977); итог будет записан после завершения. Изолированные QA logs собираются без папок данных и credentials.

## Прежний интерфейс после установки 1.5.0

Повторная read-only проверка машины пользователя показала установленное расширение 1.5.0 и живой runtime 1.5.0 с активным MCP. HTTP entry `/assets/index-Cm5tfBDy.js` содержит все три новые вкладки без условия наличия карты; его index совпадает с опубликованным VSIX 1.5.0. Скриншот с двумя вкладками не соответствует текущему HTTP bundle. Сохранённый старый webview — наиболее вероятное объяснение, но DOM самого редактора не проверялся. В инструкции добавлено сохранение правок → закрытие вкладки → **DashAI: Открыть доску**, затем при необходимости **Developer: Reload Window**. Автоматическая перезагрузка каждого открытия отклонена: она обошла бы защиту несохранённого состава документа. Личный runtime и MCP не останавливались.

MCP agentboard недоступен для записи задачи/evidence: `list_projects` возвращает HTTP 401 (invalid token). Личная база и credentials не обходились и не изменялись.
