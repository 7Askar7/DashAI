# Отдельный Ponytail и UI review типов задач 1.3

Дата: 04.10.2026. Reviewer: агент `desktop_connectors`. Новый UI diff написан другим агентом; backend и MCP этого изменения написал reviewer, поэтому их проверка ниже — **самопроверка, не независимая критика**. Независимый backend review и отдельные исполнения зафиксированы в [task-types-review.md](task-types-review.md).

Прочитаны AGENTS.md, architecture/research и `.agents/skills/ponytail-review/SKILL.md`. Scope: общая доска без пользовательских разделов, native dropdown типа, сохранение старых данных и cached retries, package/frozen smoke/documentation diff. Код reviewer в этом проходе не менял; замечания переданы владельцу.

## Ponytail review

Первоначальная находка:

`src/styles.css:L931: delete: четыре блока .task-rationale остались после удаления единственного JSX потребителя. Удалить; замена не нужна.`

Автор удалил эти блоки. Новые формы используют существующий native `Select`, значения и русские подписи находятся в `src/api.ts`, а API/MCP используют существующие literal enums и общую HTTP модель. Удалены section-формы, состояние группировки, section-ограничение создания задач и прежние стили. Registry типов, миграционный framework, другая база или новые dependencies не появились. Служебный FK container и legacy tools нужны существующим данным и клиентам и не считаются избыточностью.

Остальных обоснованных удалений в проверенном diff нет. **Lean already. Ship.**

## Независимая проверка нового UI diff

В Chromium выполнен read-only проход при ширинах **1440, 390 и 320 px**. Запросы POST/PATCH к задачам отслеживались; их не было. Проверено настоящее клавиатурное взаимодействие с native select, а не только программный `select_option`:

- В форме создания `Alt+ArrowDown → Escape` закрывает dropdown, сохраняет dialog и фокус на `task_type`.
- `ArrowDown` выбирает `testing`; последующий Tab переходит к описанию внутри формы.
- Закрытие формы возвращает фокус на «Новая задача».
- В редактировании `Alt+ArrowDown → Escape` сохраняет drawer/select; Tab остаётся внутри drawer.

Найдена **F1, P2**: кнопка «Отмена» внутри edit-form удалялась вместе с формой, оставляя `document.activeElement = BODY` вне открытого dialog. Подтверждено на всех трёх ширинах. Минимальное исправление владельца — stable ref существующей кнопки редактирования в заголовке и общий `finishEdit()` для отмены и успешного сохранения; перед удалением формы фокус возвращается на живую кнопку. Нативный dropdown не заменяется собственным popup или focus framework.

Статус F1: **закрыто, PASS**. На финальном build `index-Dl1U-MLW.js` / `index-BNxrRaU7.css` весь native-dropdown проход повторён при 1440/390/320 px. После «Отмена» активна существующая кнопка «Редактировать задачу» внутри открытого drawer; фокус больше не падает на BODY. Остальные dropdown/Tab/возврат focus проверки также прошли; POST/PATCH не было. Retained regression кнопок отмены/сохранения согласована с владельцем `scripts/ui_smoke.py`; успешное сохранение проверяется его изолированным сценарием, а не записью в рабочую базу этого reviewer.

Артефакт воспроизведения и повторной проверки: `artifacts/qa/task-types-native-focus.json`.

## Самопроверка backend/MCP и сохранности данных

В авторском проходе **16 API/MCP тестов PASS**. Две сохранённые feature-проверки находятся в `tests/test_api.py`: `test_project_board_task_types_without_sections` и `test_legacy_task_projection_and_cached_retries_preserve_database`. Настоящий STDIO workflow обоих SDK clients находится в `tests/test_mcp.py`.

Read projection добавляет `other` только в возвращаемые текущие task payloads; raw events/notes не меняются. Golden legacy fixture сохраняет IDs, section FK, credentials и содержимое всех семи таблиц после restart, чтения, экспорта и прежних cached create/patch retries. Кэш сравнивается с недостающим default-полем без перезаписи сохранённого запроса; повтор возвращает прежний ID/version без второго события. Другой тип с прежним key даёт conflict; явный null отвергается перед cached response. Обычная смена статуса сохраняет тип. Служебный container, первая задача и их достоверные audit events создаются в одной SQLite transaction; провал валидации откатывает всё, concurrent requests получают один container.

Отдельный reviewer независимо запустил эти два API tests и настоящий MCP workflow: **3 PASS**; его результат не выдаётся за независимость авторских 16 тестов.

## Read-only packaging review

`scripts/frozen_smoke.py` сначала создаёт `testing` задачу без `section_id` и проверяет тип через `get_task` и `get_board`; отдельная explicit-section задача проверяет legacy default `other`. README, connector/release docs и package/lock согласованы с версией **1.3.0**, UI default `development` и API/legacy default `other`. Дополнительного runtime слоя нет.

Полные 19 тестов и реальный frozen smoke выполнены packager; этот reviewer их повторно не запускал и не выдаёт read-only просмотр diff за новое исполнение installer/CI. После focus fix итоговый выпуск должен собираться из commit с исправлением; SHA прежнего локального артефакта относится к прежней сборке.
