# Подключение Codex и Claude Code

Оба клиента работают с одной доской через **локальный MCP server**. Коннектор предоставляет инструменты работы с проектами, задачами и журналом; он обращается к общему HTTP API и не открывает SQLite. Dashboard не запускает модели и не требует ключей OpenAI или Anthropic.

## Установленная Windows версия

После установки запустите Agentboard и выберите папку репозитория через действие подключения агентов. Для CLI доступна та же операция:

```powershell
& "$env:LOCALAPPDATA\Programs\Agentboard\AgentboardMCP.exe" --setup-connectors --project-root "C:\path\to\project"
```

Python и Node для работы самого установленного Agentboard и его MCP не нужны. Codex/Claude Code устанавливаются отдельно. Приложение и console companion `AgentboardMCP.exe` находятся в `%LOCALAPPDATA%\Programs\Agentboard`, а личная база, credentials и `runtime.json` — в `%LOCALAPPDATA%\Agentboard`. У каждого пользователя Windows своя база; обновление приложения не переносит ее другим людям.

Конфиги проекта запускают стабильный `AgentboardMCP.exe --mcp`, передают каталог личных данных и путь к credentials. Они не содержат token, Python пути или путь временной распаковки приложения. При каждом запуске MCP текущий localhost URL читается из `runtime.json`: приложение может выбрать свободный порт в диапазоне 4242–4262. Если после перезапуска приложения порт изменился, перезапустите MCP в клиенте; уже открытый MCP процесс использует прежний URL. При выключенном Agentboard коннектор сообщает ошибку доступности, а не создает вторую базу.

После настройки перезапустите клиент и выполните `list_projects` / `connector_status`. Claude Code может запросить обычное разрешение project MCP. Codex можно запустить с явной конфигурацией проекта:

```powershell
& "$env:LOCALAPPDATA\Programs\Agentboard\AgentboardMCP.exe" --codex --project-root "C:\path\to\project"
& "$env:LOCALAPPDATA\Programs\Agentboard\AgentboardMCP.exe" --codex --project-root "C:\path\to\project" mcp get agentboard --json
```

Вторая команда проверяет видимость конфигурации без модельного запроса. Обновление Agentboard сохраняет путь executable и личные credentials, поэтому пересоздавать MCP конфиги после каждого выпуска не требуется. Глобальные настройки клиентов setup не меняет. Наличие конфига не считается реальным подключением.

## Быстрый запуск на Windows

Из корня этого репозитория установите зависимости и запустите dashboard согласно README. После первого запуска API создаст `data/connector-secrets.json` с отдельными локальными credentials для Codex и Claude Code. Сервер должен оставаться запущенным на `http://127.0.0.1:4242`.

Сгенерируйте конфигурацию **в репозитории, над которым работают агенты**:

```powershell
.venv/Scripts/python.exe connectors/setup.py --project-root C:/path/to/your/project
```

Если агенты работают в самом Agentboard, `--project-root` можно опустить. С другим портом добавьте `--url http://127.0.0.1:8001`; при другом каталоге данных — `--credentials C:/path/to/data/connector-secrets.json`.

Скрипт создает/обновляет `.mcp.json` для Claude Code и `.codex/config.toml` для Codex. Используются абсолютные пути и Python интерпретатор, которым запущен setup. Другие server entries и settings сохраняются; некорректный или неоднозначный существующий TOML не переписывается. Глобальные пользовательские настройки не изменяются. Token находится в отдельном файле, а не в конфигурации MCP.

Перезапустите соответствующий клиент и проверьте `agentboard` в `/mcp`. Для Codex проект должен быть доверенным; Claude Code может запросить доверие к проектной `.mcp.json`. Затем попросите агента вызвать `list_projects` и `connector_status`.

**Конфигурация не доказывает подключение.** Реальный вызов API обновляет `last_seen` идентичности. Это время последнего запроса, а не индикатор работающего процесса/активной сессии. Smoke test ниже доказывает MCP совместимость и shared state без запуска платной модельной сессии; он не выдает себя за live run установленного Codex/Claude Code.

## Совместимый запуск установленного Codex CLI

На этой машине проверен `codex-cli 0.154.0`. Обычный `codex mcp get agentboard --json` не видит project config, пока каталог не отмечен trusted. Причина подтверждена проверкой CLI с временным trust override; ограничение описано в [официальной MCP документации](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Для работы без изменения глобальных settings используйте launcher, который читает созданный project config и передает Codex только `command`, `args` и `cwd` данного MCP server через явные `-c` overrides:

```powershell
.venv/Scripts/python.exe connectors/codex.py mcp get agentboard --json
.venv/Scripts/python.exe connectors/codex.py
```

Первая команда проверяет видимость конфигурации без модельного запроса: на установленном CLI результат содержит `enabled: true` и правильный STDIO command. Вторая открывает интерактивный Codex по явному запуску пользователя. В Agentboard доступен короткий вариант `npm run codex`; `npm run codex -- mcp get agentboard --json` выполняет ту же проверку. Для другого репозитория укажите `--project-root C:/path/to/project`; остальные аргументы передаются Codex. MCP override не меняет trust, approval или sandbox policy проекта. Существующие глобальные settings и другие MCP servers сохраняются.

## Отдельные экземпляры агентов

Стандартные credentials отделяют Codex от Claude Code. Когда два экземпляра одного клиента работают одновременно, каждому лучше дать собственную идентичность:

```powershell
.venv/Scripts/python.exe connectors/setup.py --project-root C:/path/to/codex-worktree --agent codex --agent-name "Codex Backend"
.venv/Scripts/python.exe connectors/setup.py --project-root C:/path/to/claude-worktree --agent claude --agent-name "Claude Reviewer"
```

Setup вызывает локальный `POST /api/agents`, сохраняет одноразово выданный token рядом с credentials и добавляет `--token-file` только в профиль выбранного клиента. Другой клиент в этом проекте продолжает использовать свою стандартную идентичность. Повторная команда с `--agent-name` выпускает **новую** идентичность; обычный setup снова задает стандартные профили.

Новый экземпляр можно также создать на экране «Коннекторы» и скачать JSON с `token` и `agent`. Такой файл совместим с `--token-file`; поддерживается и простой UTF-8 файл с token. Отдельный session ID (`--session-id` или `AGENTBOARD_SESSION_ID`) добавляет корреляцию к событиям, но права и actor всегда определяет credential на сервере. Без explicit session ID коннектор создает UUID на время своего процесса.

Локальная доверенная граница — пользователь ОС. Agent name/provider — атрибуция выданного credential; dashboard не подтверждает производителя клиента криптографически. Не отправляйте token в prompt, reason, note или Git. Каталог `data/` исключен из Git. Для downloaded token выбирайте каталог вне репозитория или добавьте конкретный файл в `.gitignore`.

## Инструменты и рабочий цикл

| Tool | Что делает |
|---|---|
| `list_projects` | Проекты и известные identities; поиск и пагинация |
| `get_board` | Общая доска проекта, task summaries с типом задачи и последние события; фильтры и пагинация |
| `create_project` | Создать проектную доску |
| `create_task` | Создать карточку прямо в проекте с типом, rationale, критериями и dependencies |
| `ready_tasks` | Незаблокированные backlog/in-progress задачи без живой аренды |
| `get_task` | Актуальная version, описание, rationale, критерии, recent notes/events |
| `claim_task` | Атомарно занять задачу или продлить собственную аренду |
| `update_task` | Изменить поля, тип или статус по актуальной version |
| `add_note` | Progress, decision, evidence или comment |
| `log_change` | История кодовой правки: summary, files, reason, diff/commit, verification |
| `get_history` | События по возрастанию ID с cursor для продолжения |
| `connector_status` | Reachability общего API и конфигурация этого connector без секретов |

1. Найдите проект, прочитайте доску и актуальную карточку.
2. Создайте карточки прямо в проекте для новых шагов с типом задачи, целью и criteria. `rationale` — зачем существует задача; `reason` — почему выполняется конкретная запись.
3. Вызовите `claim_task` с прочитанной `expected_version`. Только сервер решает, свободна ли работа; результат `ready_tasks` может устареть.
4. После существенных правок вызовите `log_change`. Инструмент **записывает переданное описание**, не редактирует файлы, не читает Git и не запускает проверки автоматически. Реальные outcomes проверок добавьте `add_note(kind="evidence")`.
5. Переведите работу в `review`, пригласите независимого критика, сохраните его замечания. Затем явной операцией переведите в `done`; backend требует criteria, evidence и завершенные dependencies. Независимость review — рабочий регламент, а не встроенная автоматическая оценка модели.

Аренда по умолчанию — 3600 секунд (допустимо 30–86400). Продлите ее через `claim_task` с новой version и новым ключом. Чтобы освободить работу, владелец может `update_task` в `backlog`, `blocked` или `review` с конкретной причиной: backend очищает claim при уходе из `in_progress`. Человек может вмешаться в занятую карточку с обязательной причиной. Два агента с одним credential считаются одним actor; для изоляции выдайте разные credentials.

### Тип задачи и совместимость прежних проектов

`create_task` принимает `project_id`, название, rationale и остальные поля карточки; создавать раздел перед задачей не требуется. Поле `task_type` имеет следующие значения:

| `task_type` | В интерфейсе |
| --- | --- |
| `research` | Исследование |
| `development` | Разработка |
| `testing` | Тестирование |
| `bugfix` | Исправление |
| `documentation` | Документация |
| `other` | Другое |

Если MCP/API клиент не передает `task_type`, используется `other`. Прежние карточки также получают тип «Другое»; в UI новая карточка по умолчанию имеет тип «Разработка». Тип возвращается в карточке и ее summaries. Изменение через `update_task(changes={"task_type": "testing"}, ...)` требует актуальной `expected_version`, причины и нового idempotency key; оно записывается в историю. Тип сохраняется при смене статуса.

`section_id` при создании необязателен и сохранен для совместимости существующих клиентов. Прежние section IDs, данные и история остаются в базе и экспорте; `create_section` и section-параметры чтения доступны старым клиентам. Пользователь работает с одной доской проекта и типами карточек. Connector использует тот же store и тот же validation, что UI.

## Повторы, ошибки и объем контекста

Каждая MCP мутация требует `reason` и `idempotency_key`. Используйте новый уникальный key для нового намерения; после timeout повторите **тот же key и тот же payload**. Сервер возвращает исходный результат без второй карточки/записи. Другой payload с этим key возвращает `HTTP_409`.

`expected_version` защищает от перезаписи чужой правки. На `HTTP_409` прочитайте свежий `get_task`, затем выполните новое обоснованное намерение с новой version/key. Не изменяйте stale version автоматически и не выдавайте conflict за успех. Чужой живой claim блокирует PATCH, notes и changes. Зависимости не могут образовывать цикл или связывать разные проекты.

`API_UNREACHABLE` означает, что нужно запустить сервер/проверить URL. `HTTP_401` означает неверный credential. `HTTP_422` означает неподходящие поля или невыполненную политику валидации. Ошибки возвращаются MCP `isError`, а не успешным ответом. Диагностика subprocess идет только в stderr; stdout содержит только MCP protocol messages. HTTP redirects запрещены, чтобы credentials не переходили на другой origin. Connector принимает loopback HTTP origin и отключает наследуемые HTTP proxy settings для API и выпуска tokens.

Reads ограничены: каждая страница списка содержит до 100 entries, board содержит summaries задач с `task_type`, task detail содержит заданное число последних notes/events. Длинные строки обрезаются с явной меткой; сервер продолжает хранить полный текст. `get_history` продолжайте через `after=next_cursor`; проекты и задачи — через `offset=next_offset`. Identities имеют `agent_limit`, `agent_offset`, `total_agents` и `next_agent_offset`. Совместимые section-параметры: `section_limit`, `section_offset`, `total_sections`, `next_section_offset`; `get_board(section_id=...)` добавляет `section_context` с описанием прежнего раздела. Полный журнал и тексты можно открыть в dashboard и JSON export. Коннектор пока получает полный HTTP snapshot локальной доски перед выборкой страницы; объем ответа модели ограничен.

Notes и event snapshots возвращаются как previews с `summary_only` / `snapshots_are_summaries`: body, diff и verification до 500 символов, первые 5 файлов с `files_total` / `files_truncated`. История сохраняет список `changed_fields`, actor, action, reason и IDs. Task summaries показывают первые 10 зависимостей с `depends_on_count` / `depends_on_truncated`; `get_task` возвращает полный список IDs зависимостей одной задачи. Полные тексты, списки файлов и исторические before/after остаются в UI/export. Ответы `add_note`/`log_change` тоже краткие; сокращение ответа не изменяет сохраненные данные.

## Протокольная проверка

```powershell
.venv/Scripts/python.exe -m pytest tests/test_mcp.py -q
```

Тест запускает отдельный HTTP backend с временной SQLite базой и **два настоящих STDIO clients официального MCP SDK**. Проверяет initialize/list_tools/schema annotations, безопасные повторы, общие IDs/state, dependencies, конкурирующий claim, запрет чужой note, code-change metadata, review/done, stale write, пагинацию истории и согласованность с прямым HTTP чтением. Проверяет сохранение остальных settings при setup, включая quoted TOML tables. Постоянная рабочая база и реальные user-wide configs не затрагиваются.

Сам сервер MCP можно запустить напрямую; обычно это делает клиент:

```powershell
.venv/Scripts/python.exe connectors/mcp_server.py --agent codex --credentials C:/path/to/data/connector-secrets.json --url http://127.0.0.1:4242
```

Используется официальный Python SDK `mcp==1.27.0` с `FastMCP`. Версионное API проверено по [official SDK server docs](https://github.com/modelcontextprotocol/python-sdk/blob/v1.27.0/docs/server.md). Настройка клиентов основана на [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) и [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp). Код main/v2 SDK имеет другой API и не является примером для этой фиксированной версии.
