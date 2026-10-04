# Независимая проверка типов задач 1.3

Reviewer: отдельный агент `desktop_critic`. Прочитаны architecture, исследования, Ponytail full и отдельный Ponytail-review. Проверены UI/API/MCP diff, browser flow, старые payloads и пользовательская документация. Frontend/backend/package этим reviewer не изменялись; все исполнения используют временные базы и отдельные порты, не рабочий сервис 4242.

## Результат

**PASS: 11 browser integration групп + 10 Kanban групп + 3 независимых API/MCP tests.** Итоговый production build: `index-Dl1U-MLW.js` / `index-BNxrRaU7.css`. Открытых correctness замечаний по проверенному scope нет.

Свежий проект сразу показывает пять колонок и позволяет создать карточку без создания раздела. Native select «Тип задачи» содержит research/development/testing/bugfix/documentation/other; UI default — «Разработка». Тип показан в карточке и подробностях, доступен в фильтре и редактируется с причиной. История показывает перевод поля и значений «Исследование → Исправление»; тип и событие сохраняются после reload и в полном экспорте.

Kanban smoke сохраняет все прежние проверки: одна карточка в текущей колонке, native drag с подтверждением причины, отмена/обязательная причина, evidence gate, потеря настоящего успешного ответа и повтор того же idempotency key без дублирования, реальный stale conflict с сохранением черновика и чужих полей, busy Escape, клавиатура и восстановление фокуса, мобильные статусы и переносы. Фильтр типа сохраняет пять колонок; список плоский, его фильтр статуса не скрывает задачи доски.

Просмотрены desktop/mobile скриншоты. При 1440 px все пять колонок помещаются в рабочую ширину 1138 px; при 390/320 px видна одна выбранная колонка, нет горизонтального переполнения страницы. Полный кадр снимается после scroll-to-top и исчезновения toast, поэтому offscreen fixed skip-link не попадает в снимок.

## Совместимость и сохранность

В Kanban smoke до запуска нового сервера подготовлен изолированный payload прежней формы: проект, section FK, task без `task_type`, заметка и audit events. Новая UI показывает «Другое» и после reload; export сохраняет прежние IDs и содержимое. Прямое сравнение исходных SQLite task/note/event rows подтверждает, что чтение не переписало эти строки.

Независимо выполнены `test_project_board_task_types_without_sections`, `test_legacy_task_projection_and_cached_retries_preserve_database` и `test_mcp_workflow_and_project_setup`. Они проверяют enum и null validation, atomic default container + rollback + concurrent first tasks, read-time fallback, снимок семи таблиц и credentials после повторного запуска, старые cached create/patch retries, сохранение старых событий после новой типизации, настоящий stdio MCP create/read/update без `create_section` и сохранение типа при смене статуса.

## Замечания review, закрытые до приемки

1. Добавление default-поля могло изменить сериализованный запрос прежнего idempotency key и вызвать ложный конфликт. Нормализация отсутствующих default fields применяется только к сравнению старых cached task requests и возвращаемому результату; сохраненная запись не переписывается. Retained legacy tests подтверждают тот же ID/version и отсутствие повторного события; иной тип с прежним key корректно отклоняется.
2. Первый task создает внутренний FK container и достоверное `section.created` событие в той же транзакции. Чтобы новый пользовательский flow снова не предлагал разделы, UI показывает такой служебный event как «подготовил доску проекта». Реальный browser assert подтверждает эту подпись и отсутствие «создал раздел» для свежего проекта; старые настоящие section events остаются неизменными.
3. Второй критик нашел потерю фокуса при отмене формы редактирования: focused footer button удалялся и фокус переходил в BODY. Исправлено использованием стабильной кнопки в заголовке и общей `finishEdit` для отмены и успешного сохранения. Retained browser assert подтверждает возврат на эту кнопку при cancel на 1440/390/320 px и после успешного сохранения типа. Native Alt+ArrowDown → Escape в select оставляет диалог открытым и фокус на поле; отмена не меняет task/history. После исправления обе browser проверки повторно прошли на итоговом build.

Один QA selector был исправлен: accessible name проектного h1 включает вложенную кнопку редактирования, поэтому точное совпадение только названия проекта было неверным. Это ошибка теста; приложение не менялось ради нее.

## Воспроизведение

```powershell
npm run build
node scripts/python.mjs scripts/ui_smoke.py
node scripts/python.mjs scripts/kanban_smoke.py
node scripts/python.mjs -m pytest tests/test_api.py::test_project_board_task_types_without_sections tests/test_api.py::test_legacy_task_projection_and_cached_retries_preserve_database tests/test_mcp.py::test_mcp_workflow_and_project_setup -q
```

Артефакты: `artifacts/qa/ui-results.json`, `kanban-results.json`, `ui-smoke-desktop.png`, `ui-smoke-mobile-320.png`, `kanban-desktop.png`, `kanban-mobile-320.png`. Необработанных browser page errors нет. `py_compile` и `git diff --check` проходят.

## Отдельный Ponytail-review

Проверены server/MCP, UI, удаление прежнего section-flow и CSS, оба browser smoke, frozen smoke, package/lock и README/release/connector docs. Используются literal enum, JSON `setdefault`, существующая SQLite transaction и native select. Сохранение FK и legacy tools нужно для существующих данных и клиентов; массовая миграция, другая база, registry типов и новые зависимости не добавлены. Удалены старые формы, grouping state и стили разделов. Документы правильно различают UI default development, API/legacy default other и optional section compatibility.

**Lean already. Ship.**

Дополнительный независимый [Ponytail/native review](task-types-ponytail-review.md) фиксирует найденную и закрытую проблему фокуса.

## Публичный релиз 1.3.0

**PASS, независимая read-only проверка после публикации.** [Release v1.3.0](https://github.com/7Askar7/DashAI/releases/tag/v1.3.0) и успешный [CI 37223585980](https://github.com/7Askar7/DashAI/actions/runs/37223585980) указывают на commit `8dcf0bd03d1401c67bde95ebf2ca411ac1cda61b`. Публичный HTTPS `latest.json` проверен штатным updater со старым pinned Ed25519 key, совпадающим с bundled channel; предлагается версия 1.3.0, для установленной 1.3.0 результат — `None`. URL и версия установщика совпадают с release asset `Agentboard-Setup-1.3.0.exe`; подписанные size `24,137,640` и SHA256 `66f9bd88879c0abbce993286025da43358369df48cb44d35190d1e392bd86865` точно совпадают с публичными GitHub asset metadata. Размер и digest самого feed также совпадают. Результат: `artifacts/qa/public-release-1.3.0-critic/result.json`.

## Границы проверки

Проверены production web UI, реальные API, stdio MCP и публичный подписанный канал релиза 1.3.0. Install/update lifecycle повторно не выполнялся: reviewer не скачивал и не запускал EXE, не запускал CI. Legacy fixture представляет прежнюю форму сохраненных данных; рабочие проекты пользователя не использовались.
