# DashAI 1.4.1: пакет для Visual Studio Marketplace

05.10.2026. Проверяющий агент `vscode_actual_test`; Ponytail full. **Локальный VSIX прошел 10 проверок в настоящем VS Code, exit 0.** Публикация в Marketplace еще не выполнена: пользователь загрузит пакет вручную в созданный publisher `7Askar7`. Этот отчет не утверждает наличие расширения в поиске Marketplace или публичного релиза GitHub 1.4.1.

## Проверенный пакет

`artifacts/releases/Agentboard-VSCode-1.4.1-win32-x64.vsix`, **35 895 190 байт**, SHA-256:

```text
45606ffcbd11de215ff09705e0c4fdbd9d57b5c08d5e0ee7647b3d387447fac2
```

Внутри проверены `extension/package.json` и метаданные bundled runtime: обе версии `1.4.1`, displayName `DashAI`, publisher точно `7Askar7`, внутреннее имя `agentboard`. Значок `assets/dashai-logo-128.png` имеет настоящую PNG-сигнатуру и размер 128 × 128. Внутреннее имя и команды сохранены для совместимости.

QA-driver продолжает вызывать `vscode.extensions.getExtension('7askar7.agentboard')`. Официальный ExtensionHost VS Code приводит ключи registry к нижнему регистру через `ExtensionIdentifier.toKey`; фактическая установка и активация пакета с publisher `7Askar7` успешно это подтвердили. Для изменения регистра не потребовалось менять runtime или QA.

## Настоящий редактор

Использован официальный portable Microsoft VS Code **1.139.1 x64**, официальный CLI установки VSIX и `--extensionTestsPath`. Созданы отдельные user-data, extensions, LOCALAPPDATA, USERNAME и тестовый repository с пробелами в пути. Рабочий редактор и личные проекты пользователя не изменялись; clipboard восстановлен после проверки.

```powershell
.venv/Scripts/python.exe scripts/vscode_smoke.py --code artifacts/qa/vscode-portable/vscode-win32-x64-archive-1.139.1/Code.exe --vsix artifacts/releases/Agentboard-VSCode-1.4.1-win32-x64.vsix
```

Доказательства: `artifacts/qa/vscode-actual-12f4bd9f20/results.json`, `install.log`, `editor-board.png`, `iframe-origins.json`, `host-reply-source.json`, `project-export.json`, `runtime-after-restart.json`, `driver-complete.json`. Все 10 сценариев — **PASS**:

1. Установка настоящего VSIX штатным CLI.
2. Открытие DashAI в настоящем iframe редактора.
3. Создание проекта и задачи через UI.
4. Общая Kanban-доска с пятью статусными колонками.
5. Создание, claim и log_change через frozen MCP companion; карточка видна в открытой доске через общий API.
6. Отказ остановки сервера при активной MCP-сессии.
7. Копирование конфигурации через настоящий VS Code clipboard bridge и получение ответа в UI.
8. Экспорт через host bridge и настоящий `vscode.workspace.fs` с задачами и историей.
9. Сохранение задач в той же личной SQLite после штатной остановки и повторного запуска runtime.
10. Постоянные MCP-пути вне заменяемого каталога расширения.

Настоящий parent origin: `vscode-webview://03ie2n934atnsf4c836d108jvms50fbtt0ft594f5obc4g31nf01`. Тест проверил оба направления host bridge с реальным preload и этим уникальным origin. Подменен **только выбор пути native Save Dialog**; HTTP export, сообщения, запись файла и проверка содержимого реальные. CDP использован для исследования Electron DOM; native UI automation не использовалась.

Этот smoke проверяет UI, API, MCP и жизненный цикл расширения; он не запускает модели Codex или Claude Code. Проверка версии 1.4.1 здесь относится к указанному локальному файлу. Публичные байты 1.4.0 и подписанные feed проверены отдельно в [предыдущем отчете](vscode-actual.md).
