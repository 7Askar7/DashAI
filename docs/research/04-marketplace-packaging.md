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

## Повторный отказ 1.4.2: что действительно помогло другим авторам

05.10.2026 пользователь подтвердил тот же `suspicious content` после загрузки кандидата 1.4.2. Это сообщение пользователя, не независимо записанный HTTP ответ портала. Удаление pytest/benchmark **не устранило сообщенный отказ**; считать эти файлы установленной причиной нельзя. Версия и бинарники после повторного отказа не менялись.

Новый поиск в `microsoft/vsmarketplace` нашел 40 подходящих публичных issues. Критик подробно прочитал восемь свежих body/comments и исторические ветки; второй исследователь отдельно прочитал комментарии 18 релевантных случаев из 31 closed результата. Это пересекающиеся выборки, а не 71 независимый источник. Также проверены первичные отчеты в репозиториях авторов. Статус `closed` без подтверждения публикации не считается решением.

| Случай и дата | Подтвержденный результат | Значение для DashAI |
|---|---|---|
| [Vera, переписка 20–22.07.2026](https://github.com/aallan/vera/issues/1106#issuecomment-5046899010), [результат 27.07](https://github.com/aallan/vera/pull/1165) | Автор опубликовал ответ support: блокировка относится к keywords/metadata. Очищенный пакет с десятью файлами оставался отвергнут. Затем автор скачал принятую Marketplace версию с **тем же SHA-256** и установил ее в изолированный VS Code. | Есть реальный принятый неизмененный пакет после переписки. Конкретное запрещенное слово и серверное действие не раскрыты; предположения автора о `llm`/`contracts` не являются диагнозом. |
| [#344, 09.03.2022](https://github.com/microsoft/vsmarketplace/issues/344#issuecomment-1063192149) | Сотрудник сообщил, что усиление spam detection вызвало побочное срабатывание; [после серверного исправления](https://github.com/microsoft/vsmarketplace/issues/344#issuecomment-1063233941) два автора подтвердили восстановление API и публикации. | Одинаковый текст действительно может быть вызван серверным фильтром. Это исторический случай, не доказательство текущего сбоя. |
| [#352, 21.03.2022](https://github.com/microsoft/vsmarketplace/issues/352#issuecomment-1074265988) | Команда назвала временную блокировку `tinyurl.com` и разрешила публикацию без изменения пакета. [23.05.2022](https://github.com/microsoft/vsmarketplace/issues/352#issuecomment-1134216359) она назвала `bit.ly` причиной другого отказа. | В наших metadata/README этих сокращателей нет. |
| [#1117, 15.01.2025](https://github.com/microsoft/vsmarketplace/issues/1117#issuecomment-2592594435) | Команда сообщила о решении через support; [автор подтвердил публикацию](https://github.com/microsoft/vsmarketplace/issues/1117#issuecomment-2593393652) в тот же день. Поле или изменение не раскрыты. | Ручное рассмотрение имеет подтвержденные успешные исходы, но гарантированного срока нет. |
| [#1821, 05.05.2026](https://github.com/microsoft/vsmarketplace/issues/1821#issuecomment-4380248604) | Автор сообщил, что первая публикация прошла после единственной замены slug `agent-mode-discord` на `goblin-mode`. | Name filter — обоснованное направление запроса, не доказательство, что наш `agentboard` запрещен. |
| [#2019, 22.07.2026](https://github.com/microsoft/vsmarketplace/issues/2019#issuecomment-5051459684) | Автор смог создать publisher только после удаления всех упоминаний Lua из формы, включая домен. | Это отдельная ошибка **Publisher Metadata** при создании издателя. Наш издатель уже создан; универсальное правило для extension upload не установлено. |
| [#352, 20.07.2025](https://github.com/microsoft/vsmarketplace/issues/352#issuecomment-3093190269) | Автор получил успех после одновременной замены name, publisher и Git URL. | Нельзя выяснить, какое изменение помогло, или рекомендовать массовое переименование как доказанное решение. |
| [#2215, 02.10.2026](https://github.com/microsoft/vsmarketplace/issues/2215#issuecomment-5952290928) | Автор сообщает об отказе пакета из десяти файлов без native binaries; исправление license и 34 проверки не помогли. Причина не названа. | Свежий пример сохранения ошибки после корректной упаковки. Отсутствие EXE или новая лицензия не гарантируют принятие. |
| [#2197, 23–25.09.2026](https://github.com/microsoft/vsmarketplace/issues/2197#issuecomment-5826467850) | Обращение закрыто с направлением в support, без подтвержденной публикации. Account flag — предположение автора. | Не выдавать заголовок или closed status за установленную блокировку аккаунта DashAI. |
| [Sextant, PR13](https://github.com/KyleBastien/sextant-mcp/pull/13), [PR15 от 10.05.2026](https://github.com/KyleBastien/sextant-mcp/pull/15) | Добавление LICENSE было названо исправлением, но следующий PR прямо сообщает, что отказ сохранился. | Название PR с `fix` не подтверждает принятие Marketplace или запрет `UNLICENSED`. |
| [Q&A, 15.12.2025](https://learn.microsoft.com/en-sg/answers/questions/5663734/vs-code-extension-blocked-by-suspicious-content-fi) | Автор пишет, что contact email уже проверен, полные metadata добавлены, размер уменьшен; отказ сохранился. Позже обсуждение закрыли без результата. | Проверка email не является универсальным исправлением; у нас ее состояние неизвестно. |
| [Q&A, 15–18.05.2026](https://learn.microsoft.com/en-ie/answers/questions/5891990/publisher-extension-uploading-issue-in-vs-marketpl) | После общих советов автор сообщил, что они не помогли. Советы удалить `scripts`/`devDependencies` противоречат официальному manifest reference и принятым пакетам. | Не принимать готовый список советов за проверенное решение. |

В Vera отклоненный 22.07 и принятый пакет имеют SHA-256 `b04afb6a1c0a397697346553bd743dd26cd13b119edb967f8b9b29ff12612242`. Это подтверждение в первичных записях автора; DashAI не скачивал и не устанавливал этот пакет в данном исследовании. Причина отдельного принятия не может быть полностью восстановлена из публичной переписки.

Новый exact-phrase поиск с `PyInstaller`, `PowerShell`, `UNLICENSED` и `updater` не дал подтвержденных решений для этих терминов. Это ограничение поиска, не доказательство безопасности или запрета. Native cases [#1530](https://github.com/microsoft/vsmarketplace/issues/1530), [#1624](https://github.com/microsoft/vsmarketplace/issues/1624) и [#1987](https://github.com/microsoft/vsmarketplace/issues/1987) закрыты с направлением в support; публичного успешного результата исследователь не нашел.

## Текущие metadata и конкретный следующий шаг

Независимая Gallery проверка не нашла публичного exact slug `agentboard` или displayName `DashAI`. Positive controls `ruff`/`Ruff` вернули существующие расширения; text search `agentboard` нашел чужой displayName `Agentboard` с другим slug. Это проверка публичного каталога, не reserved/unpublished names, similarity rules или прав аккаунта. Доказательства: `artifacts/qa/marketplace-repeat-research/gallery-*.json`.

Повторное чтение **самого VSIX 1.4.2** подтвердило JSON/XML identity и точные generated `Tags`: `kanban,codex,claude,agents,local`. ZIP CRC, размер 35 881 575 байт и SHA-256 `7cf58fef889944f794eef99bca921288b6556ea86f20d95080e4d08078fa982e` совпали с проверенной сборкой. Доказательство: `artifacts/qa/marketplace-repeat-research/candidate-1.4.2.json`.

Опыт авторов дает основание запросить у Microsoft **конкретный metadata/tag/name finding и состояние publisher**, сохранив точный отвергнутый пакет. Он не позволяет объявить Codex/Claude запрещенными словами или назвать нашу причину отказа. Обновлен [английский draft](../marketplace-support.txt) с обеими попытками, актуальным hash, Tags и просьбой разграничить metadata/name/account validation и file/malware finding. Draft не отправлен; 1.4.2 не принят Marketplace и не выпущен отдельным GitHub Release.

Для привязки к реальной попытке полезны UTC время, `message`/`typeKey` из Response запроса загрузки и E2E/correlation ID, если они присутствуют. Их можно взять в браузере: Developer Tools → Network → запрос с отказом → Response / Response Headers. Передавать следует только эти поля и идентификаторы, без полного HAR, cookies или Authorization. Это сбор данных для диагностики, а не новая пробная публикация урезанного продукта.

Исследование и source snapshots сохранены в игнорируемых `artifacts/qa/marketplace-repeat-research/` и `artifacts/qa/marketplace-comparison/`. Проверку итоговых выводов смотри в [отдельном review](../reviews/marketplace-repeat-review.md).
