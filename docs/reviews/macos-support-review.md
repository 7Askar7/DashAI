# macOS support and interface updates 1.5.2

## Исправление кэша интерфейса 1.5.2

После повторного сообщения пользователя закрытие/переоткрытие вкладки не помогло. Проверка исключила второй desktop-процесс и активную установку 1.4.3: registry выбирал 1.5.0, живой сервер тоже 1.5.0. Обнаружен конкретный дефект: iframe использовал постоянный `/?vscode=1`, а HTML entry point не имел `Cache-Control`, поэтому браузер мог эвристически сохранить прежний HTML и его старые hash-ресурсы.

В 1.5.2 iframe query включает URL-encoded версию и экземпляр runtime, а общий frontend отвечает `Cache-Control: no-cache` для HTML и SPA fallback. Hash-ресурсы JS/CSS сохраняют прежнюю политику. Открытая страница не перезагружается самопроизвольно, защита несохранённого состава документа и MCP shutdown guard сохранены. Новый клиент может получить свежую страницу уже существующего совместимого runtime 1.5.0 без остановки агентных сессий.

Проверки: 30 Python tests passed, 1 POSIX-only test skipped на Windows; 13 extension tests passed; production build, повторный Windows frozen HTTP/MCP smoke (включая реальный `Cache-Control`) и упаковка VSIX passed. Независимый correctness review и отдельный Ponytail review приняты без замечаний. В отдельном Chromium-тесте воспроизведено сохранение старого iframe после обновления HTTP body и переоткрытия: `initial=OLD, reopened=OLD`; новый revision query получил `NEW`, повторная навигация с `no-cache` получила `REVALIDATED` (1 запрос до revision, 3 всего). Личная база в этом тесте не использовалась.

Windows 1.5.2 установлен штатным `code.cmd --install-extension ... --force` в текущий профиль; registry подтвердил `7askar7.dashai` 1.5.2. Личный сервер и MCP не останавливались. Полный Windows GUI smoke в отдельном профиле заблокирован ожиданием собственного обновления VS Code (`vscode-updating` mutex), а не ошибкой запуска DashAI; лог `artifacts/qa/vscode-actual-b8a53f096b/vscode.log`. Наличие новых вкладок именно в окне пользователя требует **Developer: Reload Window**; DOM этого окна не проверялся.

Нативная проверка пакетов 1.5.2: [38950373566](https://github.com/7Askar7/DashAI/actions/runs/38950373566), commit `1369b60f66c41faf77975ec1b201f7d7922dab7b`. **Обе архитектуры** прошли 31 Python-тест (включая POSIX locks), 13 extension tests, запуск HTTP/MCP из извлечённого итогового VSIX и `codesign --verify --deep --strict` обоих executable. Архивы скачаны из Actions, SHA-256 внешних ZIP совпал с API digest, каждый VSIX повторно прошёл `verify_package` локально.

| VSIX 1.5.2 | Bytes | SHA-256 |
| --- | ---: | --- |
| `win32-x64` | 37501312 | `23185d92ecb622ab4def83d0e1d5b353a107dce3eca95ee55a9073c98d5ac1ce` |
| `darwin-arm64` | 41405669 | `d452106ab38f30fd071e900d60d4ac4140b0059ef0f88c9a4fca1ff547dd0565` |
| `darwin-x64` | 40528045 | `8c241eb669ec2b0e077a5f272b061a7c1c0119fceeb21368d3cab909f747cc14` |

Финальные пакеты, контрольные суммы и инструкция загрузки: `artifacts/releases/1.5.2/marketplace/`. Они не опубликованы в Marketplace автоматически: издателю нужно загрузить три target-варианта существующего `7Askar7.dashai` одной версии. Локальная готовность не означает принятие Marketplace.

Финальная проверка установки и запуска в настоящем VS Code: [38955202383](https://github.com/7Askar7/DashAI/actions/runs/38955202383), QA commit `765ed2fbb6c463ebce9324f37a81f0c8f7af4fa8`. **Обе архитектуры прошли** установку готового VSIX 1.5.2 штатным CLI в отдельный профиль, активацию установленного продукта, открытие доски, создание project MCP-конфигураций с постоянным native companion, остановку и повторный запуск с той же папкой данных и новым instance ID. Созданная конфигурация не считается подключением модели; реальный MCP-протокол проверен отдельно frozen smoke. Проверка повторно использует указанные выше готовые VSIX из `38950373566`: последующие изменения затрагивали только QA harness и документацию, production binaries не пересобирались.

Предыдущие GUI-прогоны выявили нестабильность активации тестового host и выхода родительского редактора. Диагностика ARM в `38954314514` зафиксировала `isActive=false`, отсутствие папки данных и отсутствие входа в product activate: runtime ещё не запускался. Из native QA удалена ненужная предварительная подмена API продукта; Windows export QA сохраняет свой save-dialog hook. Успех по-прежнему требует `driver-complete.json: passed` после всех product assertions. Очистка обращается только к собственному QA ChildProcess: SIGTERM, затем при необходимости SIGKILL с ограничением времени; исходная ошибка не заменяется ошибкой очистки. Штатный выход самого приложения VS Code этим тестом не утверждается. Проверены пять сценариев контроллера (успех, ошибка драйвера, принудительная очистка, ошибка очистки с сохранением исходной ошибки, ранний выход), syntax checks и независимые correctness/Ponytail reviews. Изолированные диагностические артефакты не содержат папок данных или credentials; trace-логирование отключено.

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

Предыдущие GUI-запуски, в том числе [38948405977](https://github.com/7Askar7/DashAI/actions/runs/38948405977), не завершились штатно: на ARM активация задержалась, на Intel product assertions завершились, но родительский VS Code не вышел. Это не считается успешным GUI smoke. В harness удалено ненужное обращение к clipboard, добавлены progress markers, уникальная временная HOME, удаление наследованных VSCODE/ELECTRON/token env и ограничение времени. Изолированные QA logs собираются без папок данных и credentials.

## Прежний интерфейс после установки 1.5.0

Повторная read-only проверка машины пользователя показала установленное расширение 1.5.0 и живой runtime 1.5.0 с активным MCP. HTTP entry `/assets/index-Cm5tfBDy.js` содержит все три новые вкладки без условия наличия карты; его index совпадает с опубликованным VSIX 1.5.0. Скриншот с двумя вкладками не соответствует текущему HTTP bundle; DOM самого редактора не проверялся. После ответа пользователя, что закрытие/переоткрытие не помогло, исправлена политика HTTP-кэша (см. 1.5.2 выше). Актуальная инструкция: сохранить правки → **Developer: Reload Window** → **DashAI: Открыть доску**. Автоматическая перезагрузка каждого открытия отклонена: она обошла бы защиту несохранённого состава документа. Личный runtime и MCP не останавливались.

MCP agentboard недоступен для записи задачи/evidence: `list_projects` возвращает HTTP 401 (invalid token). Личная база и credentials не обходились и не изменялись.
