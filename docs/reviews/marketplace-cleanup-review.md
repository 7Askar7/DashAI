# DashAI: независимый review очистки Marketplace-кандидата

05.10.2026. Критик `dashai_critic`; Ponytail full. Этот review дополняет, а не заменяет [первичный аудит отказа](marketplace-rejection-review.md). **Normal review и отдельный Ponytail-review нового локального кандидата 1.4.2 — PASS.** Причина сообщения Microsoft о suspicious content не установлена. Очистка поставки полезна сама по себе; она не подтверждает устранение серверного flag или принятие пакета Marketplace.

## Проверка metadata и реальных разрешенных случаев

Поиск в официальном `microsoft/vsmarketplace` дал 40 issues с точной фразой; предметно прочитаны комментарии 19 случаев, включая ответы команды и сообщения авторов после решения. Для конкретных выводов используются следующие первичные свидетельства:

| Проверяемая гипотеза | Что действительно найдено | Сравнение с DashAI |
|---|---|---|
| Shortened URLs | [Команда Marketplace](https://github.com/microsoft/vsmarketplace/issues/352#issuecomment-1074265988) объяснила временное блокирование `tinyurl.com` и разрешила публикацию без изменения пакета. | В наших package/README таких URL нет; шесть целевых HTTPS ссылок реально доступны. |
| Name filter | [Автор #1821](https://github.com/microsoft/vsmarketplace/issues/1821#issuecomment-4380248604) сообщил об успешной публикации после единственной замены технического slug `agent-mode-discord` на `goblin-mode`. | Наш slug `agentboard` не содержит названия платформы. Наблюдение автора не устанавливает универсальное правило Microsoft. |
| Ошибка server filter | В [#344](https://github.com/microsoft/vsmarketplace/issues/344#issuecomment-1063233941) команда сообщила об исправлении на стороне сервиса. | Это подтверждает разные причины одинакового текста ошибки; не доказывает ложноположительное срабатывание у нас. |
| Запрет упоминать Codex/Claude | Gallery вернул 30 опубликованных результатов по `Codex Claude`, включая [один monitor](https://marketplace.visualstudio.com/items?itemName=jialei2005.codex-claude-ctx-monitor) и [другой usage tracker](https://marketplace.visualstudio.com/items?itemName=ypdev.claude-codex-usage). | Универсального запрета этих слов не обнаружено; конкретная проверка нашего издателя этим не воспроизводится. |
| Public name collision | Exact Gallery searches по slug `agentboard` и displayName `DashAI` дали ноль. Text search нашел чужой displayName `Agentboard` с другим slug `thinking-logger-view`. | Наш displayName — `DashAI`; отсутствие публичного совпадения не исключает reserved/unpublished namespace. |

Общедоступный publisher URL `https://marketplace.visualstudio.com/publishers/7Askar7` реально отвечает HTTP 200 с названием DashAI. Это проверка существования публичного профиля, не подтверждение contact verification или права публикации. JSON/XML required metadata, PNG icon, HTTPS cover и отсутствие неожиданных управляющих символов проверены отдельно в предыдущем review.

[Microsoft описывает](https://developer.microsoft.com/blog/security-and-trust-in-visual-studio-marketplace/) несколько стадий проверки и рекомендует поставлять только необходимые файлы, указывать license/EULA и third-party attribution. License не является required manifest field по [официальному reference](https://code.visualstudio.com/api/references/extension-manifest). Мы не выдаем рекомендацию EULA за диагноз отказа и не назначаем проекту MIT без решения владельца; существующие third-party notices сохраняются.

## Независимая проверка опубликованных бинарных аналогов

Заново прочитаны сохраненные ответы официального Gallery API и байты всех пяти VSIX из [исследования упаковки](../research/04-marketplace-packaging.md). SHA-256, size, количество ZIP/native файлов и CRC совпали с таблицей исследования. У всех пяти есть `scripts` и `devDependencies`; Gallery flags — `validated, public`. Чужие binaries не устанавливались и не запускались.

CodeSlicer 0.6.43 проверен особенно: **63 111 607 байт**, SHA-256 `94082c2261cbc91543778d1a751aad37edd3715468e947800579655b68f8d0bd`, 33 ZIP files, один EXE. Внутри EXE есть PyInstaller CArchive cookie, PE certificate table `(0, 0)` — встроенной Authenticode signature нет. Gallery сообщает first publication 30.07.2026 и `isDomainVerified=false`. Поэтому объяснения «Marketplace вообще запрещает PyInstaller/native EXE», «35 MB слишком много» или «нужен шестимесячный domain badge» не подтверждаются. Это не исключает конкретный runtime detection или дополнительные требования к нашему аккаунту.

## Normal review минимального packaging diff

`packaging/agentboard.spec` исключает только `pytest/_pytest` в обоих PyInstaller Analysis, удаляет только data prefix `jsonschema/benchmarks/` и проверяет фактическое отсутствие тестовых pure modules через assert. Остальные четыре изменения — согласованный version bump 1.4.1 → 1.4.2 в root/extension manifests и lockfiles.

Проверена реальная цепочка сборки и callers: условные `_pytest.outcomes` imports в AnyIO `_asyncio.py` находятся внутри `TestRunner._run_tests_and_fixtures` и `run_test`; production server/connectors/desktop не вызывают TestRunner. Официальный hook-jsonschema собирает все package data; удаленный upstream benchmark не является runtime schema. Prefix не затрагивает `jsonschema_specifications`, используемый валидацией.

В первоначальном 1.4.1 наш ZIP audit проверял внешние пути. Позднейший анализ embedded PYZ выявил четыре `_pytest` modules в каждом EXE; ранняя формулировка об отсутствии tests не должна читаться как проверка всего скомпилированного runtime. Новый review включает PYZ отдельно.

Не добавляется широкое исключение setuptools: его импортирует injected PyInstaller startup hook. Tcl/Tk нужен штатному desktop launcher; research/docs нужны ссылкам установленных AGENTS/README. Они остаются. Pinned update keys, Ed25519/size/hash verification, localhost boundaries, host bridge, MCP stdio, personal data paths и atomic audit behavior не изменены.

## Финальная проверка artifact

Независимо прочитаны реальные байты `artifacts/releases/Agentboard-VSCode-1.4.2-win32-x64.vsix`: **35 881 575 байт**, 1 128 files, SHA-256 `7cf58fef889944f794eef99bca921288b6556ea86f20d95080e4d08078fa982e`. Собственное доказательство: `artifacts/qa/marketplace-cleanup-review-1.4.2/results.json`; воспроизводимый reader — `artifacts/qa/critic_cleanup_archive.py`.

- Полный ZIP CRC и отсутствие case-insensitive path duplicates — PASS. Root/extension versions, оба lockfile root entries, bundled package и VSIX XML согласованы на 1.4.2; publisher `7Askar7`, slug `agentboard`, target `win32-x64`. Manifest совпадает с 1.4.1 по всем полям, кроме version.
- Оба EXE побайтно совпали с production bundle. Проверены их настоящие embedded PYZ: GUI 995 modules, MCP 952; `pytest/_pytest` отсутствуют в обоих. MCP/AnyIO/jsonschema modules и 130 setuptools modules в каждом сохранены.
- Benchmark data отсутствует. Все 20 runtime schema assets и 926 Tcl/Tk data files побайтно совпали с 1.4.1. Third-party notices остаются. Внешние ZIP paths не содержат project store, credentials, private-key files, tests, QA или node_modules; это ограниченная проверка путей, не исчерпывающий secret clearance.
- Каналы с pinned public key, extension host и updater implementation побайтно неизменны. Icon 128×128 и выбранная cover 1672×941 совпали с исходниками и предыдущим кандидатом: SHA-256 `d860a9bc346d10920c92614524e687403f38388db140af4fed58a747b29c5217` и `6313d8a508d96f9b9920053c34b394a027d854d914e3c36170d5b4d13f5e4a54` соответственно.
- Старый VSIX 1.4.1 заново пересчитан и остался побайтово прежним: 35 895 190 байт, SHA-256 `45606ffcbd11de215ff09705e0c4fdbd9d57b5c08d5e0ee7647b3d387447fac2`.

Прочитан proof настоящего VS Code 1.139.1: `artifacts/qa/vscode-actual-e283ed9022/results.json` и `driver-complete.json` — все 10 сценариев PASS, exit 0. Независимо просмотрен editor screenshot; прочитаны реальные host origin и runtime descriptor. Origin содержит уникальную 52-character authority, reply source отличается и от window, и от masked parent, как требует официальный preload. Personal runtime находится вне extensions directory; после restart version 1.4.2 и тот же data directory. Дополнительно через read-only SQLite connection проверены integrity `ok` и точное совпадение экспортированных project, sections, subprojects, двух tasks, notes и всех шести audit events. Только выбор export destination в native Save Dialog подменен; запись файла и содержимое настоящие. Это MCP protocol proof, не запуск моделей Codex/Claude.

Прочитан native handoff proof `artifacts/qa/vscode-handoff-04431529cb/results.json`: текущая 1.4.2 запускает fixture 1.5.0 с теми же binary bytes и измененной только metadata; parent/child PIDs подтверждены, настоящий stdio MCP и shared API проходят, actor/session сохранены, EOF освобождает handle. Fixture не подтверждает неизвестный будущий runtime.

Основной агент сообщил 27 Python, 11 Node и frozen smoke PASS. Независимо прочитаны forced official secretLint result по 1 128 UTF-8-decoded ZIP entries — findings `[]`, и Defender log — no threats; эти два скана не воспроизводят все проверки Marketplace и не декодируют каждый compiled constant. [Verification report](../verification/marketplace-cleanup.md) и обновленный [installation guide](../vscode.md) правильно называют файл локальным кандидатом и не утверждают публикацию 1.4.2 в GitHub Releases или принятие Microsoft. Support draft относится к сохраненному отвергнутому 1.4.1; он не отправлен.

## Отдельный Ponytail-review

Прочитан `.agents/skills/ponytail-review/SKILL.md`. Проверен весь минимальный diff; новые abstractions, зависимости или speculative scanner обходы не добавлены. Assert проверяет необходимое свойство сборки и не является лишним framework. Дополнительных обоснованных сокращений нет. Signoff относится к локальной поставке и ее проверкам, не к одобрению Marketplace.

Lean already. Ship.
