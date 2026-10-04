# DashAI: настоящий Windows VS Code и VSIX

04.10.2026. Проверяющий агент `vscode_actual_test`. Применены Ponytail full и отдельная проверка critic. Этот отчет описывает выполненные проверки, а не наличие конфигурационных файлов.

## Окружение и повторение

Использован официальный Microsoft VS Code **1.139.1 x64**, скачанный SDK `@vscode/test-electron` в ignored `artifacts/qa/vscode-portable`. Уже установленный пользовательский редактор отказался создавать новое окно из-за собственного незавершенного обновления; его процессы и профиль не изменялись. Установка VSIX выполнена официальным CLI Microsoft, тестовый entry point — `--extensionTestsPath`. Интерфейс исследован через Playwright CDP и настоящие Electron iframe targets; native UI automation не использовалась.

```powershell
.venv/Scripts/python.exe scripts/vscode_smoke.py --code artifacts/qa/vscode-portable/vscode-win32-x64-archive-1.139.1/Code.exe
```

Каждый запуск создает отдельные user-data, extensions, LOCALAPPDATA, USERNAME и локальный repository с пробелами в пути. Личные проекты и credentials пользователя не копируются. Auto-update выключен только в тестовом профиле; clipboard после проверки возвращается в прежнее состояние.

## Фактический результат

Финальный локальный VSIX **1.4.0**, 35 856 451 байт, SHA-256 `c57db522414616c8ca31c1d3ca9f81c23aad2c5fda8ddb775a0425a23ad030a6`: **PASS**, процесс тестового VS Code завершился с кодом **0**. Повторный полный прогон выполнен после последнего исправления native stdio handoff. Это хэш локального пакета; пакет GitHub CI может отличаться и проверяется отдельно.

Доказательства: `artifacts/qa/vscode-actual-e56fe158bd/results.json`, `editor-board.png`, `host-reply-source.json`, `iframe-origins.json`, `project-export.json`, `runtime-after-restart.json`, `driver-complete.json`. Предыдущий успешный полный прогон до добавления handoff сохранен в `artifacts/qa/vscode-actual-42fbfc9e9d`.

- Настоящий VSIX установлен и открыл вкладку **DashAI** с bundled UI/API без внешнего Python/Node для пользователя.
- Через интерфейс создан проект и задача типа testing. В DOM общей Kanban-доски находятся ровно пять статусных колонок.
- Настоящий frozen `AgentboardMCP.exe` создал вторую задачу через stdio MCP, выполнил claim и log_change. Карточка появилась в открытом редакторе через общий API.
- Команда остановки при активном MCP отказала; instance ID и работающий API сохранились.
- UI отправил конфигурацию через host bridge; `vscode.env.clipboard.readText()` получил точное содержимое. Ответ host вернулся в UI и включил «Скопировано».
- Экспорт через тот же bridge записал JSON штатным `vscode.workspace.fs`; проверены project ID, созданные задачи и история. **Подменен только выбор пути native Save Dialog** в API установленного расширения, оба направления сообщений, HTTP export и запись файла реальные.
- После штатной остановки и повторного открытия сервер получил новый instance ID, использовал ту же личную SQLite и сохранил обе задачи. MCP конфигурации указывают в постоянную личную папку runtime, вне каталога заменяемого расширения.

Настоящий parent origin: `vscode-webview://14aovs2lqsiircq8m72jvlup4201lemtlcda1isnkoqe21a9ponk`. Authority имеет 52 символа base32. Наблюдаемый ответ preload имел этот же origin, но `event.source === window` и сравнение с замаскированным `window.parent` оба были false. Поэтому прием host reply опирается на точный уникальный webview origin и исключает источник localhost iframe; исходящие запросы дополнительно проверяют точные iframe source/origin.

Полное копирование frozen runtime в Windows выявило временный `EPERM` при атомарном directory rename и `ENOTEMPTY` при уборке собственной staging папки. Ограниченное повторение только временных блокировок и штатные `fs.rm maxRetries/retryDelay` прошли с настоящим bundle. Личные данные и старые runtime пути не удаляются.

## Опубликованный пакет 1.4.0

После успешного [Windows CI 37230779187](https://github.com/7Askar7/DashAI/actions/runs/37230779187) штатный extension updater скачал публичный signed feed и VSIX, проверил pinned Ed25519, размер и SHA-256; same-version update отклонен. Доказательство: `artifacts/qa/public-vsix-1.4.0/results.json`. При transient network failures выполнены ограниченные повторы без изменения transport или security checks.

Публичный VSIX **36 863 662 bytes**, SHA-256 `132ef00c2b4078462e9949e10a64e31b04fa54d9c9fe1899bd9ee25a17cb4b8f` отдельно установлен в portable VS Code **1.139.1**: **все 10 checks PASS, exit 0**, `artifacts/qa/vscode-actual-88996f0743/results.json`. Сценарии и граница SaveDialog stub те же, что у локального прогона. Именно опубликованные binary bytes проверены в редакторе; отличие hash от локального rebuild ожидаемо и не скрывается.

Независимый критик повторно прочитал результаты и screenshot этого прогона, сверил весь JSON export с SQLite после restart и audit историей: точное равенство, `integrity_check=ok`, credentials отсутствуют. Отдельные downloads, обе подписи, latest feeds и ZIP public package подтверждены в [независимом отчете](../reviews/vscode-review.md).

## Границы

Этот smoke проверяет установленный VSIX, runtime lifecycle и MCP, а не запускает сами модели Codex/Claude. Он не утверждает публикацию Marketplace. Подпроектные циклы, версии, конфликтующие записи и мобильный UI проверены в отдельных backend/UI отчетах; подписанный публичный GitHub канал проверен после публикации, как описано выше.

Реальная stdio передача из старого постоянного companion пути в новый active runtime проверена отдельным [frozen handoff smoke](vscode-handoff.md), включая native parent/child proof, общий API и освобождение handle при EOF.
