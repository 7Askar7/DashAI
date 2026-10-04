# DashAI: проверка отказа Visual Studio Marketplace

Проверено 05.10.2026. Исследование выполнено без публикации пробных пакетов, обращения к PAT, установки или запуска чужих бинарников. Точная причина отказа DashAI 1.4.1 **не установлена**: сообщение `Your extension has suspicious content` не называет правило или файл.

## Сравнение реально опубликованных пакетов

Публичный Gallery API вернул `validated, public` для всех пяти аналогов. VSIX скачаны из указанных в ответе официальных asset URL и прочитаны как ZIP. Нативные файлы в таблице — `.exe`, `.dll`, `.pyd`, `.node`; число файлов не включает каталоги. Размеры указаны в байтах.

| Пакет / версия / платформа | Размер VSIX | Файлов | Нативных файлов | Проверенное отличие |
|---|---:|---:|---:|---|
| DashAI 1.4.1 / win32-x64 | 35 895 190 | 1 125 | 81 | Два PyInstaller EXE и общий `_internal`, включая Tk; 55 609 629 байт нативных файлов после распаковки |
| [CodeSlicer 0.6.43](https://marketplace.visualstudio.com/items?itemName=CodeSlicer.codeslicer-impact-cockpit) / win32-x64 | 63 111 607 | 33 | 1 | Встроенный `codeslicer.exe`, 63 764 218 байт; один CLI/localhost API runtime |
| [Continue 2.1.0](https://marketplace.visualstudio.com/items?itemName=Continue.continue) / win32-x64 | 74 469 477 | 399 | 18 | 91 438 037 байт нативных файлов; сохраняет `onStartupFinished` |
| [Ruff 2026.84.0](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) / win32-x64 | 11 512 790 | 210 | 2 | Встроенный `ruff.exe`, 26 428 928 байт, и `ruff-lsp.exe` |
| [Python Debugger 2026.7.12731011](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy) / win32-x64 | 7 516 726 | 372 | 15 | Python библиотеки, DLL/PYD; опубликованная prerelease-сборка |
| [Nexus AI 4.3.1](https://marketplace.visualstudio.com/items?itemName=Hafiz408.nexus-ai) / universal | 8 319 671 | 13 | 0 | `onStartupFinished`; FastAPI/PyInstaller backend загружается с GitHub Releases с проверкой SHA-256 |

Для CodeSlicer дополнительно проверен PyInstaller CArchive cookie внутри EXE и нулевой размер PE certificate table: встроенной Authenticode-подписи нет. Его [скрипт этой версии](https://github.com/artemnoor/CodeSlicer/blob/v0.6.43/scripts/build_bundled_runtime.py) действительно использует PyInstaller `--onefile`, объединяя CLI и `local-api`. Gallery сообщает первое опубликование 30.07.2026, восемь установок, `isDomainVerified=false`. Это прямой контрпример предположениям «Marketplace запрещает unsigned PyInstaller», «VSIX 35 MB слишком большой» и «для публикации обязателен шестимесячный domain badge». Он не исключает другие проверки нового издателя.

Nexus — отдельная архитектура распространения, а не предложение переделать DashAI. У принятого CodeSlicer backend уже находится внутри VSIX. Все принятые manifest сохраняют `scripts` и `devDependencies`; эти поля сами по себе не являются ошибкой.

## Что именно проверяет vsce и Marketplace

В установленном официальном `@vscode/vsce` 4.0.0 [`publish.ts`](https://github.com/microsoft/vscode-vsce/blob/v4.0.0/src/publish.ts) для `packagePath` читает готовый VSIX и отправляет его в Marketplace без повторного `pack`. Публикация каталога вызывает `pack`; [`package.ts`](https://github.com/microsoft/vscode-vsce/blob/v4.0.0/src/package.ts) запускает secretlint, а [`secretLint.ts`](https://github.com/microsoft/vscode-vsce/blob/v4.0.0/src/secretLint.ts) задает конкретные secret/dotenv rules. `--skip-license` не выключает secret scanning. Строки `suspicious content` в локальном vsce нет: это ответ удаленного сервиса, а не диагноз локального secretlint. Сборка нашего VSIX также вызывает обычный `vsce package`; проверка готового ZIP отдельным сканированием остается полезной.

Официальная [политика безопасности](https://code.visualstudio.com/docs/configure/extensions/extension-runtime-security) описывает несколько антивирусных движков, запуск в clean-room VM, secret scanning и защиту от похожих имен. [Microsoft объясняет этапы](https://developer.microsoft.com/blog/security-and-trust-in-visual-studio-marketplace/): начальный статический scan, повторные проверки и анализ поведения. Шесть месяцев относятся к verified domain badge, а не к запрету первой публикации; Marketplace-подпись VSIX отличается от Authenticode внутри EXE.

Исторически то же общее сообщение было вызвано shortened URL: сотрудники Marketplace назвали `tinyurl.com` и `bit.ly` в [issue #352](https://github.com/microsoft/vsmarketplace/issues/352#issuecomment-1134216359). Автор [issue #1821](https://github.com/microsoft/vsmarketplace/issues/1821#issuecomment-4380248604) сообщил, что публикация прошла после единственного изменения slug `agent-mode-discord` → `goblin-mode`; это свидетельство автора, не опубликованное универсальное правило Microsoft. Отдельный критик проверил наши metadata/README: shortened URLs отсутствуют, шесть целевых HTTPS URL доступны, точных конфликтов имени DashAI/slug agentboard в Gallery не найдено.

## Вывод и степень уверенности

- **Высокая:** бинарники, PyInstaller, startup activation, размер 35 MB и обычные manifest scripts не запрещены сами по себе; есть проверенные опубликованные контрпримеры.
- **Высокая:** общий отказ не дает определить конкретное правило. Чистый Defender/secretlint не доказывает принятие всеми удаленными проверками.
- **Низкая, гипотеза:** больший состав Python runtime, два EXE и собственное обновление могут увеличивать поверхность сканирования. Сравнение аналогов не устанавливает, что это причина нашего отказа.
- Удаление доказанно неиспользуемых pytest/benchmark компонентов улучшает состав поставки. Нельзя заранее утверждать, что оно устранит Marketplace flag. Переписывать backend или обходить проверки на основании общего сообщения не требуется.

## Воспроизводимые артефакты

Публичные ответы Gallery, скачанные ZIP и `*-zip-analysis*.json` сохранены в игнорируемой папке `artifacts/qa/marketplace-comparison/`. CodeSlicer скачан через официальный `fallbackAssetUri`; ответ второго URL, не являющийся ZIP, не использован в выводах. SHA-256 проверенных VSIX:

```text
DashAI 1.4.1: 45606ffcbd11de215ff09705e0c4fdbd9d57b5c08d5e0ee7647b3d387447fac2
CodeSlicer 0.6.43: 94082c2261cbc91543778d1a751aad37edd3715468e947800579655b68f8d0bd
Continue 2.1.0: 0aa7844bcd6b042517e1bd5d77d26a14c2d68914d832fbfc6a0d49d921ac8f88
Ruff 2026.84.0: 6dc09859dcdfd5adda5a7788cd9bcfc09561f2d9b49a41327ce0922a692f65fe
Python Debugger 2026.7.12731011: 95a647492dce5306368973d4201831af2bafc6fc7ba20828921813dab3855cbd
Nexus AI 4.3.1: 35cf21d25485406e6f858d09074679e98406123931a0a2cd11909a8eb4b3d995
```
