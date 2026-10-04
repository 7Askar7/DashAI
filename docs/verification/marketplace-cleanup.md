# DashAI 1.4.2: проверка состава VSIX

05.10.2026. Агент `vscode_actual_test`; Ponytail full и отдельный review `dashai_critic`. **Проверка фактических архивов и все 10 сценариев в настоящем VS Code прошли, exit 0.** Это локальный кандидат для загрузки: отчет не утверждает, что Marketplace принял пакет, и не связывает отказ Marketplace с найденными лишними файлами.

## Что изменено

В `packaging/agentboard.spec` оба PyInstaller Analysis исключают `pytest` и `_pytest`. До изменения каждый EXE содержал четыре `_pytest` модуля: xref показывает импорт из AnyIO TestRunner, а чтение источника — только методы запуска тестов и fixtures. Приложение эти методы не вызывает. Проверка `Analysis.pure` останавливает сборку, если тестовые модули снова попали в runtime.

Из `Analysis.datas` удаляется только префикс `jsonschema/benchmarks/`. Официальный PyInstaller hook собирал upstream fixture `issue232/issue.json`: 117 105 байт, 7 427 байт внутри ZIP. Production-схемы находятся в другом пакете, `jsonschema_specifications`; они сохранены.

Setuptools, Tcl/Tk, API, MCP, криптография, обновления, инструкции и исследования сохранены. Setuptools действительно импортируется startup hook; общий GUI launcher использует Tk. `AGENTS.md` и README ссылаются на исследования, поэтому их удаление создало бы недоступные ссылки и инструкции. Здесь не делалось предположений, что эти зависимости являются причиной удаленного отказа.

## Фактические архивы

Финальный файл `artifacts/releases/Agentboard-VSCode-1.4.2-win32-x64.vsix`: **35 881 575 байт**, 1 128 ZIP entries, SHA-256:

```text
7cf58fef889944f794eef99bca921288b6556ea86f20d95080e4d08078fa982e
```

Доказательство: `artifacts/qa/marketplace-cleanup-4a641863f8/results.json`. PyInstaller archive reader проверил реальные PYZ, а не только spec; оба проверенных EXE побайтно совпадают с файлами внутри VSIX.

| Проверка | До, 1.4.1 | После, 1.4.2 |
|---|---:|---:|
| GUI PYZ modules | 999 | 995 |
| MCP PYZ modules | 956 | 952 |
| `pytest` / `_pytest` в каждом PYZ | 4 | 0 |
| Benchmark JSON files | 1 | 0 |
| Production JSON-schema assets | 20 | 20, побайтно неизменны |

Проверено наличие production modules MCP, AnyIO, jsonschema и Ed25519, обеих Ponytail skills и исследований. Manifest и bundled runtime имеют версию 1.4.2, publisher — `7Askar7`.

Исходный подробный аудит сохранен в `artifacts/qa/marketplace-runtime-audit-4e58837cb5/results.json` и `zip-inventory.json`. Чтение рекурсивных code constants и имен файлов не выполняло код из архивов. Известные шаблоны приватных ключей и токенов в проверенных constants/data не найдены; это ограниченная проверка, а не исчерпывающий security clearance. Найденные Windows-пути были общими примерами из Click (`<user>`) и CPython (`Galahad`); личных абсолютных `co_filename` не обнаружено. PE branding/version корректны; unsigned Authenticode статус сам по себе не устанавливает причину Marketplace rejection.

## Настоящий VS Code

```powershell
.venv/Scripts/python.exe scripts/vscode_smoke.py --code artifacts/qa/vscode-portable/vscode-win32-x64-archive-1.139.1/Code.exe --vsix artifacts/releases/Agentboard-VSCode-1.4.2-win32-x64.vsix
```

Официальный Microsoft VS Code **1.139.1 x64**, штатная установка VSIX и extension-test entry point; отдельные profile, extensions, LOCALAPPDATA, USERNAME и repository. Рабочий редактор и личные данные пользователя не изменялись, clipboard восстановлен.

Доказательства: `artifacts/qa/vscode-actual-e283ed9022/results.json`, `editor-board.png`, `project-export.json`, `host-reply-source.json`, `iframe-origins.json`, `runtime-after-restart.json`, `driver-complete.json`. Все 10 сценариев — **PASS**:

1. Установка настоящего VSIX.
2. Открытие настоящего editor iframe.
3. Создание проекта и задачи через UI.
4. Единая Kanban-доска с пятью статусами.
5. Frozen MCP create / claim / log_change; карточка появилась в редакторе через общий API.
6. Остановка запрещена при активном MCP.
7. Настоящий VS Code clipboard bridge и ответ в UI.
8. Export bridge, HTTP export и настоящий filesystem write.
9. Задачи сохранены в той же SQLite после штатного перезапуска runtime.
10. MCP конфигурации используют постоянный путь вне каталога расширения.

В экспортном сценарии подменен только выбор пути native Save Dialog. Остальные сообщения, API и запись файла реальные. Проверка использует CDP для Electron DOM; native UI automation не применялась. Она проверяет MCP-протокол и коннектор, но не запускает модели Codex/Claude.

## Дополнительные проверки другого агента

Root выполнил 27 backend-тестов, 11 Node-тестов и frozen smoke — PASS. Native MCP handoff также PASS: `artifacts/qa/vscode-handoff-04431529cb/results.json` фиксирует parent/child процессы, общий store, session/actor и освобождение handle. Новая версия 1.5.0 в этом тесте — **только metadata fixture того же бинарного build**, а не реальный будущий выпуск.

Root запустил Microsoft Defender с `-DisableRemediation`: exit 0, «found no threats», журнал `artifacts/qa/marketplace-defender-1.4.2.log`. Официальный `@vscode/vsce 4.0.0 secretLint` проверил все 1 128 VSIX entries с принудительным UTF-8 чтением, включая raw binary strings: findings `[]`, exit 0; `artifacts/qa/marketplace-secret-results-1.4.2.json`. Этот scanner не распаковывал PYZ; описанное выше чтение code constants — отдельная ограниченная проверка. Локальные результаты не гарантируют совпадение с закрытыми проверками Marketplace и не означают, что публикация разрешена.
