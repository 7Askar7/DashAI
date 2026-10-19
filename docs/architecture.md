# DashAI — контракт реализации

## Чтение документации

Вкладка документации открывается в режиме чтения: оглавление переключает разделы без изменения URL/history, на узком экране используется закреплённый native select. Файлы представлены раскрываемыми строками по 30 на страницу; поиск включает путь, название, описание назначения и шаги работы. Фильтр и страница влияют только на чтение. Настройки состава и сведения о ревизии раскрываются отдельно; сохранение состава остаётся прежней атомарной HTTP-операцией с версией и причиной.

`src/markdown.ts` использует отдельные экземпляры уже поставляемых Marked/DOMPurify; версии закреплены как прямые зависимости. Один renderer применяется в просмотре и HTML/PDF: Markdown получает семантическую разметку, исходный HTML остаётся видимым текстом, изображения заменены alt-текстом, разрешены ссылки HTTP(S)/mailto. Относительные пути и fragment-ссылки остаются текстом до появления разрешения путей внутри документов. Скрипты и внешние загрузки из документов не допускаются. Mermaid сохраняет strict/sandbox/CSP.

HTML и кнопка «Печать / PDF» подготавливают все выбранные схемы самостоятельно и включают полный состав независимо от открытого раздела, фильтра и страницы. Печать получает отдельное представление с целыми SVG вместо ограниченных по высоте iframe. Ошибка схемы или загрузки дополнительных документов не выдаётся за успешный полный экспорт. Исторический снимок по-прежнему исключает текущие модули документов. Проверки: `scripts/documentation_reader_smoke.py`, `scripts/large_project_map_smoke.py`, `scripts/ui_smoke.py`.

## Возврат к работе и ссылки на задачи

`?task=<UUID>` открывает существующую задачу и выбирает её фактический проект. Явная ссылка имеет приоритет над сохранённой карточкой. Ошибка ссылки остаётся видимой до закрытия или повторной попытки. Копирование убирает параметры webview/runtime и fragment; адрес относится к текущему локальному серверу и порту, не является облачной ссылкой.

Навигационные настройки версии 1 хранятся под ключом `dashai.workspace.v1`: текущие проект, вкладка и открытая задача; для каждого проекта — его вкладка, доска/список, поиск и фильтры. Браузер использует localStorage своего origin, VS Code — `context.globalState` расширения без Settings Sync. Чтение завершается до монтирования App; ошибки хранилища видимы, при недоступном host используется локальный fallback. Старый `agentboard.project` читается как начальное значение при отсутствии нового состояния. Формы, тексты заметок и credentials не входят в снимок навигации.

Клиент нормализует версию, enum и идентификаторы; наличие исполнителя/подпроекта проверяет после загрузки соответствующих данных. Host принимает только фиксированную схему и ключ, JSON до 100 КБ. Записи в host последовательны. Открытие/закрытие задачи использует History API; Back/Forward проверяет актуальные черновики и блокирует переход при сохранении. Отказ возвращает прежнюю запись истории вместе с URL; индекс сохраняется при reload. Чтение ссылок и изменение настроек не создают domain/audit events. Проверка: `scripts/workspace_navigation_smoke.py` и тесты расширения.

## UX-аудит 18.10.2026

Доска и список применяют одни и те же фильтры статуса, исполнителя, типа, подпроекта и приоритета. Быстрые выборки используют эти же поля, не создают отдельные доски и не меняют данные. Поиск ограничен текущим проектом и включает критерии готовности; на узком экране новый запрос открывает колонку с совпадением. Новая задача получает выбранный подпроект как редактируемое начальное значение; после сохранения фильтры сбрасываются, чтобы задача оставалась видна.

Формы проекта, подпроекта, задачи, заметки и причины перемещения защищают фактически изменённые поля при закрытии и уходе со страницы. Во время сохранения закрытие и поля заблокированы. Смена типа заметки предупреждает о потере дополнительных полей правки кода. Ошибки не очищают черновик; API/version/idempotency и атомарный audit сохраняются.

Обзор задачи показывает наличие критериев, незавершённые зависимости и последнюю evidence-запись с автором и временем. Это сообщение автора, а не независимое подтверждение или запуск тестов DashAI. Номера версий записей и общий каталог агентов убраны из основной шапки проекта. Свежесть доски и обновление истории обозначены отдельно. [Исследование и приоритеты](research/08-user-needs-ux-audit.md).

## Версии и исполнители 1.7

`server/releases.py` хранит записи выпусков в `project_releases` общей SQLite. Модуль `releases` выключен по умолчанию; его отключение сохраняет данные, чтение и export, но запрещает новые записи и правки. UI и MCP используют один HTTP-контракт с optimistic version, idempotency и атомарным audit. Summaries и обычное polling не загружают полные changelog. Состояние записи задаёт человек или агент; это не доказательство реального развёртывания. [Контракт](project-releases.md).

Исполнители используют существующий общий каталог `agents`. Ввод имени из формы задачи вызывает `POST /api/agents` с `kind=custom, issue_token=false`: идентичность сохраняется для всех проектов без token/hash и без ложного признака подключения. Прежний `issue_token=true` остаётся значением по умолчанию для выдачи credentials через человеческий UI коннекторов. Добавление и audit атомарны; произвольное имя не меняет авторизацию.

## Модульное пространство 1.6

Поддерживаются внешние MCP-клиенты со свободными именами идентичностей (`kind=custom`) и стандартные Codex/Claude для совместимости. Формат клиентского конфига независим от имени модели. Автор определяется сервером по токену, не по названию клиента.

`server/modules.py` хранит повторно используемые документные шаблоны и состояние возможностей каждого проекта в общей SQLite. Карта/архитектура/документация включены для прежних проектов; интеграции выключены. Отключение не удаляет текст, истории и внешние записи. Обычное обновление доски получает только краткие флаги, без тел документов. UI скрывает ненужные вкладки; MCP читает и пишет тот же контракт с версиями и idempotency. [Контракт модулей](modules.md).

`server/integrations.py` обслуживает личные Confluence/Jira Cloud и Data Center подключения. HTTP API и MCP по-прежнему не запускают модели. Корень внешней записи проверяется реальным GET и закрепляется; Confluence создаёт только непосредственных детей страницы, Jira — задачи в проверенном проекте. Credentials хранятся отдельно от SQLite/audit/export. Знания, audit и постановка outbox атомарны локально; сетевые изменения не могут быть одной транзакцией с SQLite. Статусы ожидания, неизвестного результата и конфликта видны пользователю. Выключение интеграционного модуля проверяется перед каждым новым внешним запросом. [Подробности и границы](integrations.md).

Карта проекта использует индекс дерева и окно видимых строк, а не рендер всех путей. Поиск работает по путям и описаниям, раскрытие пути и активная строка сохраняются при навигации. Клавиатурная семантика — tree/treeitem. Контент карты и diagram sandbox сохраняют прежние правила безопасности и актуальности снимка.

## Обновление интерфейса 1.5.2

URL iframe включает проверенные `runtime.version` и `instance_id`: новая версия или экземпляр получает отдельный ключ HTTP-кэша. Общий HTTP frontend отдаёт HTML entry point и SPA fallback с `Cache-Control: no-cache`; hash-ресурсы JS/CSS не меняют политику. При активном MCP новый webview может открыть существующий совместимый runtime 1.5.0 без его остановки. Самопроизвольной перезагрузки страницы нет: несохранённый состав документа продолжает защищаться существующим UI.

## Нативное расширение macOS 1.5.2

Один Python runtime собирается PyInstaller на Windows x64, macOS arm64 и macOS x64. Общий упаковщик проверяет соответствие хоста target и внедряет точные `os`/`cpu` в каждый VSIX. macOS использует `~/Library/Application Support/Agentboard`, бинарники без `.exe`, исполняемые права и безопасную копию runtime в постоянную личную папку. Windows сохраняет существующие пути и named mutex. На macOS stdlib `fcntl.flock` обеспечивает эксклюзивный desktop lock и shared MCP lock на одну папку данных; shared acquisition ожидает краткую эксклюзивную проверку активности, чтобы сессия не стартовала без защиты. Коннектор по-прежнему обращается только к общему HTTP API. Mac-пакеты обновляются через Marketplace; PowerShell/Inno Setup updater остаётся Windows-only.

## Карта проекта и документация 1.5

Рабочие вкладки дерева описаний, архитектуры и сборки документов используют общие HTTP/MCP-операции. Текущая карта и неизменяемые ревизии хранятся в `project_maps`/`project_map_revisions` той же SQLite-базы. Публикация, ревизия и audit атомарны; optimistic version и idempotency сохраняются. Внешний агент публикует разрешённый манифест путей/SHA-256 и структурированные объяснения, не передавая код/секреты. Смена hashes собственного или связанного исходника снимает подтверждение актуальности. UI не утверждает, что следит за файловой системой или запускает модель. Mermaid — конкретно необходимая UI-зависимость для отрисовки исходников; strict-режим дополнен sandbox/CSP. API, лимиты, версии и сценарии: [project-map.md](project-map.md).

Исходное решение: 03.10.2026; исследования: `research/01-products.md`, `research/02-agent-needs.md`, `research/03-ux-ui.md`. Расширение 1.6 опирается также на исследования MCP-клиентов, личной синхронизации Atlassian и проектных модулей в `research/`.

## Граница продукта

Локальный общий dashboard, а не среда исполнения моделей. Человек и внешние coding agents с поддержкой локального stdio MCP создают проекты и карточки на общей доске проекта, выбирают тип работы, читают контекст и сохраняют действия с причинами. Имя агента задаётся пользователем; Codex и Claude Code сохраняются как стандартные идентичности для совместимости. Продукт не запускает модели и не требует ключей их поставщиков. Интерфейс на русском. Статусы: `backlog`, `in_progress`, `review`, `done`, `blocked`.

React + TypeScript + Vite; FastAPI + Python stdlib SQLite; официальный Python MCP SDK со stdio transport. MCP процессы обращаются к единому HTTP API и не открывают SQLite. Production FastAPI отдает собранный `dist/`; dev Vite проксирует `/api`. Сервер слушает только `127.0.0.1:4242`.

## Данные

- Project: `id`, `name`, `description`, `repository`, `color`, `version`, `created_at`, `updated_at`.
- Section: `id`, `project_id`, `title`, `description`, `position`, `version`, `created_at`.
- Task: `id`, `short_id` (AD-001), `project_id`, `section_id` (совместимость хранения), `task_type` (`research/development/testing/bugfix/documentation/other`), `title`, `description`, `rationale`, `acceptance_criteria` (текст), `status`, `priority` (`urgent/high/medium/low`), `assignee_id` (nullable), `depends_on` (список task IDs), `version`, `claim_owner_id`, `claim_expires_at`, `created_at`, `updated_at`.
- Agent: `id`, `name`, `kind` (`human/codex/claude/custom`), `last_seen` (nullable), `created_at`. `custom` — произвольная пользовательская идентичность, не проверка производителя модели. Не выдавать token hash.
- Event: `id` (монотонный integer), `project_id`, `task_id` (nullable), `entity_type`, `entity_id`, `action`, `actor_id`, `actor_name`, `actor_kind`, `reason`, `before`, `after`, `created_at`, `session_id` (nullable). Event append-only; создание/изменение и event в одной транзакции.
- Note: `id`, `task_id`, `kind` (`progress/decision/evidence/comment/change`), `body`, `actor_id`, `created_at`, `metadata` (JSON). Для `change` metadata содержит files, diff, commit и verification. Добавление note порождает event.

## HTTP API

Все даты ISO-8601 UTC. В UI `Europe/Moscow`. Ошибки: HTTP 400/401/403/404/409/422 с `{detail: string}`; при 409 клиент перечитывает состояние и показывает конфликт, не повторяет изменение молча. У каждого write body обязательный `reason`. Не принимать actor от клиента — его определяет credential.

- `GET /api/health` → `{status: 'ok'}`.
- `GET /api/bootstrap` → `{projects: Project[], agents: Agent[], activity: Event[]}`.
- `GET /api/projects/{id}` → `{project: Project, sections: Section[], subprojects: Subproject[], tasks: Task[], activity: Event[], modules: ModuleSummary[]}`. Модули здесь содержат только `id/name/kind/enabled/version`, без текстов документов.
- `POST /api/projects` body `{name, description?, repository?, color?, reason, idempotency_key?}` → Project.
- `PATCH /api/projects/{id}` body `{expected_version, changes: {name?, description?, repository?, color?}, reason}` → Project.
- `POST /api/projects/{id}/sections` body `{title, description?, reason, idempotency_key?}` → Section.
- `PATCH /api/sections/{id}` body `{expected_version, changes: {title?, description?}, reason}` → Section.
- `POST /api/tasks` body `{project_id, section_id?, subproject_id?, task_type?: 'other', title, description?, rationale, acceptance_criteria?, priority?, assignee_id?, depends_on?, reason, idempotency_key?}` → Task. Без section_id задача создается сразу в проекте.
- `GET /api/tasks/{id}` → `{task: Task, events: Event[], notes: Note[]}`.
- `PATCH /api/tasks/{id}` body `{expected_version, changes: {...}, reason, idempotency_key?}` → Task. Разрешенные fields: title, description, rationale, acceptance_criteria, status, priority, task_type, assignee_id, section_id, subproject_id, depends_on. `task_type: null` запрещен; пропущенное поле не изменяется. `done` требует критерии и хотя бы одну evidence note; unfinished dependencies запрещают in_progress/review/done. Граф dependencies ацикличный и внутри проекта.
- `POST /api/tasks/{id}/claim` body `{expected_version, reason, lease_seconds?: 3600, idempotency_key?}` → Task. Атомарно резервирует исполнение за authenticated agent, выставляет in_progress/assignee. Живая чужая аренда запрещает агенту писать задачу. Человек может вмешаться с обязательной причиной.
- `POST /api/tasks/{id}/notes` body `{kind, body, reason, idempotency_key?}` → Note.
- `POST /api/tasks/{id}/changes` body `{summary, files: string[], diff?, commit?, verification?, reason, idempotency_key?}` → Note(kind=change). Это явная запись code change от агента: файлы, diff/commit и что проверено. Tracker не наблюдает filesystem автоматически и не утверждает, что проверки запущены самим dashboard. Агент должен вызвать log_change после существенного изменения; реальные checks дополнительно сохраняет как evidence.
- `GET /api/history?project_id=&task_id=&after=0&limit=100` → `{events: Event[], next_cursor: number}`. По умолчанию `order=asc`: возвращает по возрастанию ID для delta sync, продолжение — `after=next_cursor`. Для журнала UI `order=desc` возвращает последние события первыми; предыдущая страница — `before=next_cursor` (строго меньшие ID). Вставки новых событий между страницами не сдвигают старые страницы. Курсор — ID последней строки; при пустом результате сохраняется входной курсор, либо 0 для первого запроса. `before` допустим только с `order=desc`, ненулевой `after` — только с `order=asc`; несовместимые параметры возвращают 422. Фильтры проекта/задачи и лимит 1–500 действуют в обоих направлениях.
- `GET /api/projects/{id}/export` → JSON snapshot проекта, разделов, подпроектов, задач, notes, всей истории, карты и полных текстов модулей без credentials. Экспорт не заменяет backup.
- `GET /api/connectors` → `{base_url, python_command, mcp_script, credentials_file, data_dir, desktop, agents: Agent[], client_profiles: ClientProfile[]}` без секретов.
- `POST /api/agents` body `{name, kind?: custom|codex|claude, reason}` → `{agent: Agent, token: string}` (одноразовая выдача). Default `custom`; имя свободное. Нужен для отдельных экземпляров агентов; только human credential может выпускать токены.
- `POST /api/connectors/config` body `{client, agent_id, token_file?}` → `{filename, format, content}`. Только человек; формат клиента независим от идентичности. Для нестандартного `agent_id` обязателен абсолютный путь к локальному файлу ранее выданного токена; его содержимое сервер не читает и в конфигурацию не вставляет.

Для агентных запросов `Authorization: Bearer <token>`, опциональный `X-Session-ID`. Browser writes посылают `X-Dashboard-Client: browser`; сервер проверяет localhost Host и допустимый Origin. Никакого permissive CORS. Доверенная граница — один пользователь ОС на локальном компьютере. Это не multi-user public SaaS.

## Коннектор

`python connectors/mcp_server.py --agent <credential alias or issued agent ID> --credentials <absolute file> --url http://127.0.0.1:4242` поднимает stdio server. `--agent` выбирает credential, не модель и не формат клиента. Стандартные aliases — `codex` и `claude`; для выданной пользовательской идентичности передаётся её ID и `--token-file <absolute file>`. Секреты остаются в `data/connector-secrets.json` или отдельном личном файле (вне Git). Стандартные идентичности создаются сервером, но last_seen пуст до настоящего запроса. MCP `instructions` описывают workflow list/get → create/claim → log_change/notes → evidence → review/done. Tools имеют явные schemas, readOnly annotations, bounded output, обработку transport ошибок без stdout логов. Минимальные tools: list_projects, create_project, get_board, create_section, create_task, get_task, update_task, claim_task, add_note, log_change, get_history. Дополнительные tools карты и модулей используют тот же HTTP domain. Повтор write с одинаковым idempotency_key и payload возвращает прежний результат; другой payload с тем же ключом → 409.

Генератор и setup предоставляют профили Codex, Claude Code, Cursor, VS Code/Copilot, Cline и общий `command/args`. Setup пишет project-scoped конфиги известных клиентов, а Cline/generic экспортирует в `.dashai/` для ручного объединения; глобальные пользовательские настройки не изменяются. `--client` выбирает формат; `--agent custom --agent-name "…"` в setup выпускает отдельную идентичность, а `--agent-id`/`--token-file` переиспользуют выданную. `AGENTS.md`, `CLAUDE.md` и repository skill `.agents/skills/dashai/` объясняют работу с общим dashboard. [Настройка MCP](connectors.md).

## Проверка

Domain/API проверки: hierarchy, reason, optimistic conflict, реальная конкуренция claim, idempotency, dependencies/cycle, append-only audit, evidence gate, persistence/restart, token isolation, custom identities, модули и транзакционная outbox. MCP smoke через официальный ClientSession: initialize/list_tools + создание/взятие/изменение/история. Browser QA: real create/search/filter/drawer/note/status/export/connector, большая карта, модули, клавиатура, desktop/mobile screenshots. Atlassian wire/scope/recovery проверяются изолированным MockTransport; без пользовательских credentials live-подключение не заявляется. Отдельные critics: correctness/security, interoperability, UX/accessibility, Ponytail review. Findings и исправления сохраняются в `docs/reviews/`.

## Ponytail

Используется upstream `DietrichGebert/ponytail`, commit `c982cd411abb53323c4baa1baa3c2f020b8d0b08`, MIT. Применяем `skills/ponytail/SKILL.md` (full) и `skills/ponytail-review/SKILL.md`. Правила сокращают лишние зависимости и абстракции; validation, сохранность данных, accessibility и явные требования пользователя остаются обязательными.

## Установленная Windows-версия 1.1

`Agentboard.exe` содержит Python runtime, API, native Tk launcher и production UI; `AgentboardMCP.exe` сохраняет console stdio для MCP-клиентов. Установщик Inno Setup работает без администратора, устанавливает программу в `%LOCALAPPDATA%\Programs\Agentboard`, а личные данные остаются в `%LOCALAPPDATA%\Agentboard`. Эта папка не является ресурсом сборки и не удаляется установщиком. Общего облачного store нет; в 1.6 внешняя передача знаний возможна только через явно настроенные личные интеграции.

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
