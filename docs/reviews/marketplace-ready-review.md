# DashAI 1.4.1: независимый review пакета Marketplace

05.10.2026. Критик `dashai_critic`; Ponytail full и отдельный Ponytail-review. Прочитаны архитектура, исследования и полный diff. **Локальный пакет готов к ручной загрузке.** Этот вывод не означает, что Marketplace принял или опубликовал расширение. GitHub 1.4.0 и его подписанные feeds проверены отдельно; публичный выпуск 1.4.1 здесь не заявляется.

## Требования и совместимость

Проверены официальные [требования manifest](https://code.visualstudio.com/api/references/extension-manifest) и [инструкция публикации Microsoft](https://code.visualstudio.com/api/working-with-extensions/publishing-extension): SemVer, publisher, engines, PNG icon не менее 128×128, HTTPS для изображений README, упаковка VSIX и ручная загрузка через управление издателем. Пакет собран штатным vsce с target `win32-x64`. Дополнительная автоматизация публикации или токен в репозитории для выбранного ручного процесса не нужны.

Publisher в JSON и VSIX XML — точно `7Askar7`, displayName — `DashAI`, техническое имя — `agentboard`. Регистр не меняет прежнюю идентичность `7askar7.agentboard`: официальный [ExtensionIdentifier](https://github.com/microsoft/vscode/blob/main/src/vs/platform/extensions/common/extensions.ts#L391) использует сравнение без учета регистра и lowercase ключи. Это подтверждено фактически: прежний QA-driver с `getExtension('7askar7.agentboard')` успешно нашел и активировал установленный пакет с новым регистром publisher.

Сравнение manifest с предыдущим commit подтверждает: изменены только version, publisher case, description, icon и galleryBanner. Command/config IDs, capabilities, engines, common API и личный каталог сохранены. Runtime и transport в этом diff не изменены. README явно сообщает Windows x64, русский интерфейс, отдельную установку agent clients, общую доску и локальные данные; создание конфигурации не выдается за действующее соединение. Созданный publisher не выдается за опубликованное расширение.

## Независимая проверка установочного файла

Файл `artifacts/releases/Agentboard-VSCode-1.4.1-win32-x64.vsix`: **35 895 190 байт**. SHA-256, рассчитанный критиком по реальным байтам:

```text
45606ffcbd11de215ff09705e0c4fdbd9d57b5c08d5e0ee7647b3d387447fac2
```

- Полный ZIP CRC — PASS. Manifest JSON соответствует source, XML содержит `Publisher="7Askar7"`, `Version="1.4.1"`, `TargetPlatform="win32-x64"`.
- Root package, оба lockfile включая root entries, extension package и bundled runtime package имеют версию `1.4.1`. Настоящий frozen MCP `--version` вернул `1.4.1`; оба EXE внутри VSIX побайтово равны production frozen build.
- Icon внутри VSIX побайтово равен единственному исходнику `public/brand/dashai-logo-128.png`, PNG 128×128; визуально проверен в исходном размере. SHA-256: `d860a9bc346d10920c92614524e687403f38388db140af4fed58a747b29c5217`.
- Bundled cover побайтово равна выбранному пользователем оригиналу: PNG 1672×941, SHA-256 `6313d8a508d96f9b9920053c34b394a027d854d914e3c36170d5b4d13f5e4a54`. HTTPS URL README реально скачан: 1 255 723 байта, тот же hash. README в VSIX соответствует source после нормализации окончаний строк.
- Оба packaged update channels сохраняют GitHub latest URL и закрепленный Ed25519 public key из `packaging/update-public-key.txt`. Extension/updates code и каналы побайтово совпадают с source.
- В пакете нет личных SQLite/credentials, connector-secrets, private keys, project MCP configs, `.git`, `.codex`, QA, tests или node_modules. `certifi/cacert.pem` — штатный публичный CA bundle, не приватный ключ. Новых runtime зависимостей не добавлено.

## Установка и данные

Отдельный test agent установил эти байты в изолированный официальный VS Code **1.139.1**: **10 сценариев PASS, exit 0**, evidence `artifacts/qa/vscode-actual-12f4bd9f20/results.json`. Критик независимо прочитал results, installed manifest, host reply, restart descriptor и completion; просмотрел editor screenshot. UI creation, пять колонок, frozen MCP create/claim/log_change через общий API, active MCP stop guard, clipboard, export и restart сохранность подтверждены. Подменен только выбор пути Save Dialog; сообщения, HTTP export и запись файла реальные. Модели Codex/Claude не запускались.

Дополнительная read-only сверка критика: весь exported project/tasks/sections/subprojects/notes и все **6 audit events** точно равны post-restart SQLite; `integrity_check=ok`, credentials в экспорте отсутствуют. Runtime расположен в изолированной QA личной папке с версией `1.4.1`, не внутри заменяемого extension каталога.

Повтор native handoff `artifacts/qa/vscode-handoff-56a9d96388/results.json` — PASS: текущий build 1.4.1 запускает metadata fixture 1.5.0, настоящий parent/child и stdio работают, task/subproject используют общий store, actor/session сохранены, EOF освобождает handle. Это явно fixture с тем же binary build, не проверка будущего выпуска. Основной агент также сообщил существующие production tests 27 PASS, Node tests 11 PASS и frozen smoke PASS; они не выдаются здесь за отдельный запуск критика.

## Отдельный Ponytail-review

Проверен текущий diff по `.agents/skills/ponytail-review/SKILL.md`: один canonical PNG копируется существующим build script, используются штатные manifest/vsce и уже имеющиеся проверки. Новых runtime функций, abstractions, auth frameworks или зависимостей нет. Без дополнительных findings по сложности.

Lean already. Ship.
