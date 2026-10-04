# DashAI в VS Code

Расширение для **Windows 10/11 x64, VS Code 1.95 или новее** открывает личную доску внутри редактора. В комплекте находятся API, интерфейс и MCP companion. Python, Node.js и отдельная установка настольного DashAI пользователю не нужны.

## Установить и открыть

1. Скачать `Agentboard-VSCode-<версия>-win32-x64.vsix` из [DashAI Releases](https://github.com/7Askar7/DashAI/releases/latest).
2. В VS Code открыть Extensions (`Ctrl+Shift+X`), меню «…» → **Install from VSIX…** и выбрать скачанный файл.
3. Нажать значок **DashAI** на левой панели → **Открыть доску**. Та же команда доступна через `Ctrl+Shift+P` → **DashAI: Открыть доску** и меню папки в Explorer.

Создайте проект, вложенные подпроекты и карточки на общей Kanban-доске. Подпроект и тип задачи выбираются отдельно из списков; карточки и журнал показывают, что менялось, кем, в какой сессии и по какой причине. Dashboard открыт во вкладке VS Code и использует тот же API, что и Codex/Claude Code.

Расширение запускается локально в доверенном проекте. Виртуальные папки и браузерный VS Code не поддерживаются. Подключение агентов рассчитано на локальные папки и клиентов Windows; настройка агентов внутри SSH, WSL или Dev Containers не выполняется автоматически.

## Подключить агентов

Открыть нужную локальную папку в VS Code и выполнить **DashAI: Подключить Codex и Claude Code**. Команда использует существующий setup и создает project-scoped `.codex/config.toml` и `.mcp.json`, сохраняя остальные настройки. Начните новую сессию клиента; Claude Code может запросить обычное разрешение project MCP. Наличие этих файлов означает настройку, а фактическое подключение подтверждается запросом агента к API.

Клиенты агентов устанавливаются отдельно. Расширение не запускает модели и не требует ключей OpenAI или Anthropic. Агенты создают карточки с `project_id` и `task_type`, читают историю и явно записывают изменения через `log_change`.

## Данные и работа сервера

База, credentials, история, резервные копии и логи находятся в `%LOCALAPPDATA%\Agentboard`. Настольное приложение и расширение используют одну личную папку. В VSIX нет проектов и credentials разработчика. Закрытие вкладки не удаляет данные; команда **DashAI: Остановить локальный сервер** предназначена для завершения сервера расширения, когда он не занят агентами.

MCP companion сохраняется в постоянной личной папке runtime; конфигурация проекта не зависит от каталога `.vscode/extensions`, который VS Code заменяет при обновлении. Удаление или обновление расширения не удаляет личную базу.

## Обновления

Расширение проверяет отдельный подписанный канал [GitHub Releases](https://github.com/7Askar7/DashAI/releases): `vscode-latest.json`. Оно принимает более новую версию для Windows x64, проверяет Ed25519-подпись издателя, скачивает VSIX по HTTPS и сверяет размер и SHA-256. Установку выполняет штатная команда VS Code; редактор может предложить перезапустить расширения. Данные и история остаются в личной папке.

После запуска обновленного runtime новые MCP-сессии автоматически используют его коннектор: прежний постоянный путь проверяет активную версию и передает ей stdio. Переписывать конфигурации проектов после каждого обновления не требуется. Уже открытые агентные чаты завершают работу со своей версией; новые инструменты будут доступны в следующей сессии клиента.

Настройка **DashAI: Automatic Updates** включена по умолчанию и относится к приложению, а не к содержимому проекта. Ее можно отключить в настройках VS Code; команда **DashAI: Проверить обновления** доступна для ручной проверки. При недоступной сети или неверной подписи продолжает работать установленная версия. Также можно установить новый VSIX вручную через **Install from VSIX…**.

GitHub Releases продолжает распространять VSIX с подписанным каналом. Издатель **DashAI**, ID **7Askar7**, зарегистрирован пользователем в Visual Studio Marketplace. Само создание издателя не публикует расширение; до успешной загрузки и проверки Marketplace доступность в поиске не заявляется. Регистр publisher ID не меняет идентичность существующего `7askar7.agentboard`; данные и command IDs сохранены.

## Первая публикация в Marketplace

1. В [Manage Publishers & Extensions](https://marketplace.visualstudio.com/manage) выбрать **DashAI (7Askar7)**.
2. Нажать **New extension → Visual Studio Code**.
3. Выбрать готовый файл `Agentboard-VSCode-1.4.1-win32-x64.vsix` из `artifacts/releases` и выполнить загрузку.
4. Дождаться завершения проверки Marketplace; затем открыть страницу расширения и проверить установку через VS Code.

Пакет имеет PNG-логотип 128×128, английское описание, выбранную обложку и target Windows x64. Для этой ручной загрузки токен публикации в проект не добавляется. Будущую автоматическую публикацию можно настроить отдельно после первого успешного upload. Пакеты, опубликованные в Marketplace, обновляются также штатным механизмом VS Code; подписанный GitHub канал продолжает работать.

Ручная загрузка VSIX описана в [официальной инструкции Microsoft](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#publish-an-extension). Локальная готовность пакета и проверка в редакторе отделены от факта публикации.

## Отказ «suspicious content» при загрузке

Первая ручная загрузка пакета 1.4.1 отклонена Marketplace с сообщением `Your extension has suspicious content`. Оно не указывает конкретное поле или файл. Повторная локальная проверка и независимый review не выявили нарушения metadata; это не доказывает прохождение серверной проверки или ложноположительное срабатывание. [Отчет](reviews/marketplace-rejection-review.md).

Открыть **Manage Publishers & Extensions → Contact Microsoft** и запросить проверку. Этот путь указан в [официальном FAQ публикации](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#i-need-help-with-my-vs-marketplace-account-or-support-in-publishing-an-extension). Команда Marketplace также направляет случаи с той же ошибкой на **VSMarketplace@microsoft.com**: [ответ команды](https://github.com/microsoft/vsmarketplace/issues/2010#issuecomment-4959860814).

Готовый английский текст: [marketplace-support.txt](marketplace-support.txt). Перед отправкой приложить скриншот ошибки; точный VSIX предоставить по запросу или через разрешенный поддержкой способ передачи. В тексте зафиксированы версия, source commit, размер и SHA-256 отклоненного файла. Письмо подготовлено, но не отправлено. В **Details** издателя также проверить, есть ли отдельное требование подтвердить контактный email; выполнение этого требования само по себе не гарантирует устранение данного отказа.

Пакет и его identity сохранены до получения диагностик; повторные изменения бренда, версии, runtime или защиты обновлений без подтвержденной причины не являются исправлением. Расширение остается доступным для локальной установки через **Install from VSIX…**. Публикация в Marketplace пока не выполнена.

## Собрать и выпустить

Из корня репозитория:

```powershell
./scripts/build-desktop.ps1 -ManifestUrl 'https://github.com/7Askar7/DashAI/releases/latest/download/latest.json'
./scripts/build-vscode.ps1
npm --prefix vscode-extension test
```

Сборка использует зафиксированные devDependencies `@vscode/vsce` и `@vscode/test-electron`. Инструментам сборки нужен Node.js 22; при локальном Node.js 20 скрипт запускает Node 22 через `npx`, не меняя глобальную версию. Runtime расширения использует Node из VS Code и стандартные модули. Результат: `artifacts/releases/Agentboard-VSCode-<версия>-win32-x64.vsix`.

Версии корневых `package.json`/`package-lock.json` и manifest расширения должны совпадать. Workflow **Windows release** собирает свежий frozen bundle и VSIX, запускает проверки и подписывает два независимых feed одним существующим ключом издателя. Release включает EXE, `latest.json`, VSIX и `vscode-latest.json`. Приватный ключ передается только шагу подписи через `AGENTBOARD_UPDATE_PRIVATE_KEY` и не входит в пакеты.

Официальные источники: [упаковка и платформенные VSIX](https://code.visualstudio.com/api/working-with-extensions/publishing-extension), [manifest и расположение extension host](https://code.visualstudio.com/api/references/extension-manifest), [установка VSIX штатной командой](https://code.visualstudio.com/api/references/commands), [безопасность Webview](https://code.visualstudio.com/api/extension-guides/webview), [Microsoft test-electron](https://github.com/microsoft/vscode-test).
