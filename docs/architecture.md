# DashAI — контракт реализации

Дата решения: 03.10.2026. Исследования: `research/01-products.md`, `research/02-agent-needs.md`, `research/03-ux-ui.md`. Реализация начинается после завершения этих исследований.

## Граница продукта

Локальный общий dashboard, а не среда исполнения моделей. Человек, Codex и Claude Code создают проекты и карточки на общей доске проекта, выбирают тип работы, читают контекст и сохраняют действия с причинами. Продукт не запускает модели и не требует ключей OpenAI/Anthropic. Интерфейс на русском. Статусы: `backlog`, `in_progress`, `review`, `done`, `blocked`.

React + TypeScript + Vite; FastAPI + Python stdlib SQLite; официальный Python MCP SDK со stdio transport. MCP процессы обращаются к единому HTTP API и не открывают SQLite. Production FastAPI отдает собранный `dist/`; dev Vite проксирует `/api`. Сервер слушает только `127.0.0.1:4242`.

## Данные

- Project: `id`, `name`, `description`, `repository`, `color`, `version`, `created_at`, `updated_at`.
- Section: `id`, `project_id`, `title`, `description`, `position`, `version`, `created_at`.
- Task: `id`, `short_id` (AD-001), `project_id`, `section_id` (совместимость хранения), `task_type` (`research/development/testing/bugfix/documentation/other`), `title`, `description`, `rationale`, `acceptance_criteria` (текст), `status`, `priority` (`urgent/high/medium/low`), `assignee_id` (nullable), `depends_on` (список task IDs), `version`, `claim_owner_id`, `claim_expires_at`, `created_at`, `updated_at`.
- Agent: `id`, `name`, `kind` (`human/codex/claude`), `last_seen` (nullable), `created_at`. Не выдавать token hash.
- Event: `id` (монотонный integer), `project_id`, `task_id` (nullable), `entity_type`, `entity_id`, `action`, `actor_id`, `actor_name`, `actor_kind`, `reason`, `before`, `after`, `created_at`, `session_id` (nullable). Event append-only; создание/изменение и event в одной транзакции.
- Note: `id`, `task_id`, `kind` (`progress/decision/evidence/comment/change`), `body`, `actor_id`, `created_at`, `metadata` (JSON). Для `change` metadata содержит files, diff, commit и verification. Добавление note порождает event.

## HTTP API

Все даты ISO-8601 UTC. В UI `Europe/Moscow`. Ошибки: HTTP 400/401/403/404/409/422 с `{detail: string}`; при 409 клиент перечитывает состояние и показывает конфликт, не повторяет изменение молча. У каждого write body обязательный `reason`. Не принимать actor от клиента — его определяет credential.

- `GET /api/health` → `{status: 'ok'}`.
- `GET /api/bootstrap` → `{projects: Project[], agents: Agent[], activity: Event[]}`.
- `GET /api/projects/{id}` → `{project: Project, sections: Section[], tasks: Task[], activity: Event[]}`.
- `POST /api/projects` body `{name, description?, repository?, color?, reason, idempotency_key?}` → Project.
- `PATCH /api/projects/{id}` body `{expected_version, changes: {name?, description?, repository?, color?}, reason}` → Project.
- `POST /api/projects/{id}/sections` body `{title, description?, reason, idempotency_key?}` → Section.
- `PATCH /api/sections/{id}` body `{expected_version, changes: {title?, description?}, reason}` → Section.
- `POST /api/tasks` body `{project_id, section_id?, task_type?: 'other', title, description?, rationale, acceptance_criteria?, priority?, assignee_id?, depends_on?, reason, idempotency_key?}` → Task. Без section_id задача создается сразу в проекте.
- `GET /api/tasks/{id}` → `{task: Task, events: Event[], notes: Note[]}`.
- `PATCH /api/tasks/{id}` body `{expected_version, changes: {...}, reason, idempotency_key?}` → Task. Разрешенные fields: title, description, rationale, acceptance_criteria, status, priority, task_type, assignee_id, section_id, depends_on. `task_type: null` запрещен; пропущенное поле не изменяется. `done` требует критерии и хотя бы одну evidence note; unfinished dependencies запрещают in_progress/review/done. Граф dependencies ацикличный и внутри проекта.
- `POST /api/tasks/{id}/claim` body `{expected_version, reason, lease_seconds?: 3600, idempotency_key?}` → Task. Атомарно резервирует исполнение за authenticated agent, выставляет in_progress/assignee. Живая чужая аренда запрещает агенту писать задачу. Человек может вмешаться с обязательной причиной.
- `POST /api/tasks/{id}/notes` body `{kind, body, reason, idempotency_key?}` → Note.
- `POST /api/tasks/{id}/changes` body `{summary, files: string[], diff?, commit?, verification?, reason, idempotency_key?}` → Note(kind=change). Это явная запись code change от агента: файлы, diff/commit и что проверено. Tracker не наблюдает filesystem автоматически и не утверждает, что проверки запущены самим dashboard. Агент должен вызвать log_change после существенного изменения; реальные checks дополнительно сохраняет как evidence.
- `GET /api/history?project_id=&task_id=&after=0&limit=100` → `{events: Event[], next_cursor: number}`. Возвращает по возрастанию ID для delta sync.
- `GET /api/projects/{id}/export` → JSON snapshot проекта, разделов, задач, notes, всей истории без credentials. Экспорт не заменяет backup.
- `GET /api/connectors` → `{base_url, python_command, mcp_script, credentials_file, agents: Agent[]}` без секретов.
- `POST /api/agents` body `{name, kind: codex|claude, reason}` → `{agent: Agent, token: string}` (одноразовая выдача). Нужен для отдельных экземпляров агентов; только human credential может выпускать токены.

Для агентных запросов `Authorization: Bearer <token>`, опциональный `X-Session-ID`. Browser writes посылают `X-Dashboard-Client: browser`; сервер проверяет localhost Host и допустимый Origin. Никакого permissive CORS. Доверенная граница — один пользователь ОС на локальном компьютере. Это не multi-user public SaaS.

## Коннектор

`python connectors/mcp_server.py --agent codex|claude --credentials <absolute file> --url http://127.0.0.1:4242` поднимает stdio server. Секреты в `data/connector-secrets.json` (gitignored); `--token-file` для дополнительных credential. Стандартные идентичности Codex и Claude Code создаются сервером, но last_seen пуст до настоящего запроса. MCP `instructions` описывают workflow list/get → create/claim → log_change/notes → evidence → review/done. Tools имеют явные schemas, readOnly annotations, bounded output, обработку transport ошибок без stdout логов. Минимальные tools: list_projects, create_project, get_board, create_section, create_task, get_task, update_task, claim_task, add_note, log_change, get_history. Повтор write с одинаковым idempotency_key и payload возвращает прежний результат; другой payload с тем же ключом → 409.

Конфиги project-scoped `.mcp.json` и `.codex/config.toml` генерируются setup script с абсолютными путями; без изменений глобальных пользовательских настроек. `AGENTS.md` и `CLAUDE.md` объясняют использование dashboard и Ponytail.

## Проверка

Один интеграционный тест domain/API: hierarchy, reason, optimistic conflict, реальная конкуренция claim, idempotency, dependencies/cycle, append-only audit, evidence gate, persistence/restart, token isolation. MCP smoke через официальный ClientSession: initialize/list_tools + создание/взятие/изменение/история. Browser QA: real create/search/filter/drawer/note/status/export/connector, клавиатура, desktop/mobile screenshots. Отдельные critics: correctness/security, interoperability, UX/accessibility, Ponytail review. Findings и исправления сохраняются в `docs/reviews/`.

## Ponytail

Используется upstream `DietrichGebert/ponytail`, commit `c982cd411abb53323c4baa1baa3c2f020b8d0b08`, MIT. Применяем `skills/ponytail/SKILL.md` (full) и `skills/ponytail-review/SKILL.md`. Правила сокращают лишние зависимости и абстракции; validation, сохранность данных, accessibility и явные требования пользователя остаются обязательными.

## Установленная Windows-версия 1.1

`Agentboard.exe` содержит Python runtime, API, native Tk launcher и production UI; `AgentboardMCP.exe` сохраняет console stdio для обоих клиентов. Установщик Inno Setup работает без администратора, устанавливает программу в `%LOCALAPPDATA%\Programs\Agentboard`, а личные данные остаются в `%LOCALAPPDATA%\Agentboard`. Эта папка не является ресурсом сборки и не удаляется установщиком. Общего облачного store и передачи содержимого проектов нет.

Desktop резервирует собственный socket на 127.0.0.1, начиная с 4242 и заканчивая 4262, не подключаясь к уже запущенным чужим сервисам. Активный endpoint сохраняется в личном `runtime.json`; новые MCP-сессии читают его через `--data-dir`. Разные компьютеры и Windows-профили получают разные базы и credentials. Это разделение хранения; HTTP API сохраняет доверенную границу локального компьютера, а не защиту от враждебных локальных учетных записей.

Обновления: встроенный HTTPS feed и public Ed25519 key → проверенный подписанный манифест → ограниченная загрузка → точные size/SHA-256 → согласованный SQLite backup → выход GUI и frozen helper → внешний PowerShell handoff → Inno Setup → новый запуск. Installer checks GUI/MCP mutex; активные MCP-сессии откладывают автоматическую установку. Принудительного завершения агентов или чужих процессов нет. Native helper повторно сверяет файл непосредственно перед запуском; downgrade отклоняется также установщиком.

Источник новых версий — GitHub Releases `7Askar7/DashAI`. Publisher private key находится отдельно от кода и передается GitHub Actions только как encrypted repository secret. Workflow собирает и проверяет EXE перед публикацией installer + `latest.json`; публичный ключ и адрес канала встроены в installer. Контракт выпуска и практические границы: `release.md`.

## Kanban 1.2

Основной вид — единая доска всего выбранного проекта: пять самостоятельных колонок статусов, одна карточка в колонке текущего статуса. В 1.3 пользовательские разделы удалены из UI; тип работы указан меткой на карточке и доступен как фильтр. Список всех задач остается отдельным переключаемым видом. Фильтр статуса используется только в списке; на Kanban статусы уже представлены колонками.

Desktop показывает колонки с отдельными вертикальными прокрутками; меньшая ширина допускает горизонтальную прокрутку внутри доски. На экранах до 760 px кнопки статусов со счетчиками показывают одну выбранную колонку, без превращения доски в общий плоский список. Все перемещения доступны через native select, в том числе без мыши; desktop дополнительно использует native HTML drag-and-drop.

Drop или выбор нового статуса открывает подтверждение с обязательной причиной. До успешного PATCH карточка остается на месте. Запрос меняет только `status`, передает исходную `expected_version` и стабильный ключ повторной попытки; domain checks, ownership, dependencies и evidence работают через тот же API, что и у MCP. При stale conflict нужно явно перечитать данные и подтвердить намерение снова; причина сохраняется, чужие поля не переписываются. Отмена не изменяет данные и не добавляет событий.

## Типы задач 1.3

UI create/edit предлагает native select «Тип задачи»: Исследование, Разработка, Тестирование, Исправление, Документация, Другое. Новая UI-карточка имеет default development; HTTP/MCP default other обеспечивает совместимость старых клиентов. Смена типа фиксируется обычным task.updated с причиной, before/after и version. Status-only PATCH сохраняет тип. Export, get_task, get_board и ready_tasks возвращают тип.

SQLite schema/FKs остаются прежними. Старые payload без task_type читаются как other; при чтении исходные строки задач, notes, events и cached idempotency не переписываются. Старый тип не угадывается по названию раздела. При новом create_task без section_id служебная группа project-board:<project_id> создается в той же транзакции, что task и audit; UI не требует настройки разделов. Ее truthful section.created с is_default показывается как «подготовил доску проекта». Прежние section API/MCP, IDs и export сохраняются для старых клиентов. Старые cached create/patch requests сравниваются с учетом default нового поля, а ответы получают read-time fallback; повтор успешного запроса до обновления не создает вторую задачу или audit.

## Подпроекты 1.4

У одного проекта остается одна доска по статусам. Необязательный `task.subproject_id` обозначает направление работы параллельных чатов; тип задачи и статус остаются отдельными полями. Подпроект имеет `id`, `project_id`, `title`, `description`, nullable `parent_id`, `version`, `created_at`, `updated_at`. Родитель и задача могут ссылаться только на подпроект того же проекта; циклы запрещены, включая конкурентное переподчинение.

`POST /api/projects/{id}/subprojects` принимает `{title, description?, parent_id?, reason, idempotency_key?}`; `PATCH /api/subprojects/{id}` — `{expected_version, changes: {title?, description?, parent_id?}, reason, idempotency_key?}`. Явный `parent_id: null` перемещает подпроект в корень, `subproject_id: null` отвязывает задачу; пропущенное поле сохраняется. Idempotency различает пропущенное поле и явное очищение. Изменения и `subproject.created/updated` записываются одной транзакцией.

Без миграции SQLite: подпроекты хранятся в существующей `sections` с `kind: "subproject"`; legacy-разделы не превращаются в подпроекты. Board/export возвращают отдельные `sections` и `subprojects`, старые задачи читаются с `subproject_id: null`, исходные строки и история не переписываются. `section_id` поддерживает прежние разделы и служебную группу; для новой принадлежности используется только `subproject_id`.

MCP `create_subproject/update_subproject` обращаются к общему HTTP API. `get_board/ready_tasks` поддерживают `subproject_id` и `include_descendants` (по умолчанию true), `get_board` отдельно ограничивает и страницы подпроектов. Источник события — авторизованный агент и `session_id`; наличие группы не создает и не запускает отдельного агента.
