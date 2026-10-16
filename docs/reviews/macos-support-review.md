# macOS support 1.5.1

Причина: опубликованный пакет 1.5.0 содержит Windows x64 EXE и точный `win32-x64` target. Удаление ограничения manifest не делает такой runtime исполняемым на Mac.

Исправление: нативные arm64/x64 сборки, платформенные пути и имена бинарников, POSIX desktop/MCP locks, общий проверяющий упаковщик и CI на двух macOS runner. На Mac нет PowerShell/Inno Setup updater: используется штатный Marketplace. Store/API/domain behavior остаются общими.

Независимый correctness review обнаружил гонку shared MCP lock с health probe и проблему directory symlinks PyInstaller в VSCE. Исправлено ожиданием shared lock, запретом запуска без lock, `--follow-symlinks` и smoke извлечённого итогового VSIX. Отдельный Ponytail review: удалён неиспользуемый `Invoke-BuildNode`; новых runtime-зависимостей нет. `macholib` — необходимая зафиксированная build-зависимость PyInstaller на macOS.

Локальные проверки до нативной сборки: 29 Python tests passed, 1 POSIX test skipped на Windows; 13 extension tests passed. Проверка блокировок и конечного Mac VSIX должна пройти на macOS, Windows mock-проверка её не заменяет. Итоговые результаты CI и Windows-сборки добавляются после выполнения.

MCP agentboard недоступен для записи задачи/evidence: `list_projects` возвращает HTTP 401 (invalid token). Личная база и credentials не обходились и не изменялись.
