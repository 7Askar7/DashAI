# Что действительно нужно coding agents и их оператору

Дата исследования: **3 октября 2026 года**. Материал подготовлен до реализации. Изучены **38 отдельных первичных источников**: официальная документация Codex, Claude Code и MCP, инженерные публикации Anthropic, документация агентных систем и инфраструктуры, исходные репозитории и исследование SWE-bench. Страницы открывались непосредственно; выводы не построены только на результатах поиска. Редиректы официальных документов учтены. Повторное открытие страницы или другая версия того же README не считается дополнительным источником.

Это кабинет наблюдения и совместной работы человека и coding agents. Его главный результат — сохраненный ответ на вопросы **«что изменили, кто, зачем, что проверили и что делать дальше»**. Доска должна быть общей для Codex и Claude Code и переживать остановку агентной сессии. Обычная колонка «готово» без доказательства и причины изменения этого результата не обеспечивает. Такой вывод следует из описанных проблем длинных сессий и проверяемых критериев завершения [A16](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), [A13](https://code.claude.com/docs/en/best-practices).

## Метод и ограничения

В таблице разделены **наблюдение из источника** и **наше проектное решение**. Официальный документ подтверждает поведение своей системы; он не является исследованием предпочтений всех пользователей. Наличие функции у продукта также не доказывает, что ее нужно полностью копировать. Исследование выделяет пересекающиеся потребности и переводит их в проверяемые требования.

Для MCP отдельно изучены SDK и протокол. Часть ссылок фиксирует спецификацию **2025-11-25** как совместимую основу для выбранного Python SDK `mcp==1.27.0`; она не называется последней спецификацией. Изучена и версия tools **2026-07-28**. Коннектор следует строить на SDK и проверять инициализацию настоящим MCP client, а не писать свою частичную JSON-RPC реализацию.

Исследование не обещает автоматического чтения всего внутреннего журнала Codex или Claude Code. MCP дает агенту инструменты dashboard; агент должен вызывать их по рабочему регламенту. Hooks могут дополнительно передавать технические события, но не объясняют мотив изменения и имеют ограничения [A11](https://code.claude.com/docs/en/hooks), [A14](https://code.claude.com/docs/en/checkpointing).

## Матрица первичных источников: наблюдение → потребность → решение

| ID | Первичный источник | Прочитанное наблюдение | Что из этого нужно в dashboard |
|---|---|---|---|
| A01 | [Codex: Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) | Codex поддерживает STDIO и Streamable HTTP; MCP configuration хранится в `config.toml`. Есть серверные instructions и параметры времени ожидания. | Один MCP connector для всех операций доски. Дать команды настройки и проверку подключения; явно показывать endpoint и требования к запущенному API. |
| A02 | [Codex: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Codex читает проектные инструкции с иерархией и ограничением размера. Близкие к рабочей директории инструкции имеют приоритет. | Поставить короткий регламент работы с доской в репозиторий. Длинную историю загружать инструментом по необходимости. |
| A03 | [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) | SDK запускает и возобновляет локальные threads. Документация сообщает об удалении `codex mcp-server`; для custom clients указан app server. | Dashboard MCP — сервер инструментов, **к которому подключается Codex**. Не использовать устаревшую команду запуска Codex как сервера и не смешивать connector с оркестратором. |
| A04 | [Codex: non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) | `codex exec` пригоден для скриптов и CI, различает stdout и stderr и имеет настройки sandbox. | У работы может не быть интерактивного окна. Сохранять внешний session/run ID, команды проверки и exit code; состояние держать на сервере. |
| A05 | [Codex: subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Отдельные агенты работают параллельно и возвращают результаты главному агенту; могут иметь разные инструкции и конфигурации. | Отделить родительскую задачу, подзадачу, исполнителя и критика. Показывать объединенный прогресс и источник каждого результата. |
| A06 | [OpenAI: Define tools](https://developers.openai.com/plugins/plan/tools) | Tools следует выводить из целей пользователя; для контракта нужны schema, side effects, authorization и output. Чтение и запись разделяются. | Именованные операции `create_task`, `claim_task`, `get_task_context`, `record_activity`. Явные side effects и предсказуемые ошибки. |
| A07 | [OpenAI: Build an MCP server](https://developers.openai.com/plugins/build/mcp-server) | Серверные instructions помогают общим workflows. Annotations должны соответствовать поведению и не заменяют authorization. Inspector проверяет schemas, invalid inputs и ошибки. | Серверные правила короткие: сначала прочитать контекст, затем claim, сообщить причину и доказательство. Валидировать на backend независимо от подсказок агенту. |
| A08 | [Claude Code: MCP](https://code.claude.com/docs/en/mcp) | STDIO сервер добавляется через `claude mcp add … -- command args`. Проектная конфигурация хранится в `.mcp.json`; HTTP entry требует type. Есть статусы подключения. | Реальный connector совместим с Claude Code. Поставить проектный пример конфигурации и диагностический read tool; избежать неоднозначного JSON с URL без type. |
| A09 | [Claude Code: custom subagents](https://code.claude.com/docs/en/sub-agents) | У subagents отдельный контекст, инструменты, permissions и возможный worktree; результат возвращается в основной разговор. | Подзадача должна быть самодостаточной: цель, границы, критерии, ссылки и результат. Не считать общую историю чата автоматически доступной каждому агенту. |
| A10 | [Claude Code: agent teams](https://code.claude.com/docs/en/agent-teams) | Команда использует общий task list, claim и dependencies. Нерешенные зависимости препятствуют claim. Есть ограничения и накладные расходы координации. | Атомарное занятие задачи, ready queue, явные блокирующие зависимости. Параллелить независимые задачи; отражать заблокированную работу. |
| A11 | [Claude Code: hooks reference](https://code.claude.com/docs/en/hooks) | `PostToolUse` содержит input, response, session ID и tool use ID после успешного вызова. Hook на Edit/Write не ловит запись через Bash. | Hooks — дополнительная телеметрия. Корреляцию хранить в журнале; смысловой reason передавать отдельно. Не заявлять, что connector автоматически поймает все файловые изменения. |
| A12 | [Claude Code: memory](https://code.claude.com/docs/en/memory) | Инструкции проекта и auto memory решают разные задачи; память может хранить решения и внешние ссылки. Поддержка AGENTS.md зависит от конфигурации/версии, доступен импорт из CLAUDE.md. | Общий durable context в dashboard и короткие инструкции обоим клиентам. Предоставить совместимый CLAUDE.md с импортом, если требуется; не полагаться только на память одного клиента. |
| A13 | [Claude Code: best practices](https://code.claude.com/docs/en/best-practices) | Явный проверяемый сигнал помогает агенту завершать работу; примеры включают tests, build и screenshots. Отдельный verification subagent дает второй взгляд. | Acceptance criteria на карточке, запись фактической проверки и независимый review. Статус «на проверке» отделен от принятой работы. |
| A14 | [Claude Code: checkpointing](https://code.claude.com/docs/en/checkpointing) | Checkpoints не покрывают Bash modifications, обычные subagent edits и внешние concurrent changes полностью. | Dashboard audit не равен rollback файлов. Хранить commit/PR/path references; для восстановления кода пользоваться Git. Не показывать фиктивную кнопку полного отката. |
| A15 | [Claude Code: programmatic runs](https://code.claude.com/docs/en/headless) | JSON и stream-json содержат session metadata. Bare mode требует явного MCP config. SIGTERM может оставить turn незавершенным. | Различать состояние задачи и жизнь процесса. Остановка клиента не должна переводить работу в done; нужна аренда claim и возможность продолжить после потери сессии. |
| A16 | [Anthropic: long-running agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Потеря контекста и преждевременное завершение возникают в длинных задачах; помогают список требований, progress artifacts, Git history и end-to-end verification. | Передавать сжатый текущий контекст и список оставшихся шагов. Сохранять описание результата и проверки каждой инкрементальной задачи. |
| A17 | [Anthropic: writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) | Избыточные и перекрывающиеся tools увеличивают ошибки; поиск и релевантные компактные ответы экономят context. Для оценки нужны реалистичные многошаговые задачи. | Умеренный список понятных tools. Фильтры project/section/status/agent, ограниченный объем ответов, ссылки на detail. Проверять полный рабочий сценарий. |
| A18 | [Anthropic: multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) | Неясное делегирование приводило к дублированию поиска; инструкции должны задавать разделение труда и ожидаемый результат. | В каждой подзадаче фиксировать scope и output; карточка должна объяснять, почему задача создана и чем она отличается от соседних. |
| A19 | [Anthropic: building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Авторы рекомендуют простую архитектуру, прозрачный план и тщательно документированный ACI; усложнение требует основания. | Сначала durable task board и надежные tool contracts. Не внедрять автоматически дорогостоящую оркестрацию, генерацию планов и скрытые фоновые агенты. |
| A20 | [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) | Официальный README различает v2 и поддерживаемую v1.x, содержит новый package/import shape. | Фиксировать поколение SDK в dependency lock и примерах. TS не нужен для выбранного Python connector; исследование проверяет протоколную совместимость, а не заставляет ставить второй SDK. |
| A21 | [MCP tools, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | Tool имеет input/output schema; `structuredContent` дает структурированный результат, а text block обеспечивает совместимость. Tool errors отличаются от protocol errors. | Возвращать стабильные ID, version и ссылки как JSON. Conflict/blocked/validation не представлять успешной мутацией; выдавать понятную дальнейшую операцию. |
| A22 | [MCP transports, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | STDIO stdout используется только для MCP сообщений. Для локального HTTP рекомендованы loopback и authentication; Origin должен проверяться. | Diagnostics отправлять в stderr. Локальный API привязать к loopback; connector не должен печатать banner в stdout. |
| A23 | [MCP lifecycle, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) | Initialization согласует protocolVersion и capabilities, после чего начинается работа. Клиент не может предполагать наличие необъявленных возможностей. | Проверять настоящий initialize/list_tools/call_tool. Не объявлять subscriptions, logging или task-augmentation, если они не реализованы. |
| A24 | [MCP resources, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) | Resource URI однозначно идентифицирует контекст; reading, templates и subscriptions — отдельные возможности. | Проектный brief и task context могут иметь stable URI. Для минимальной совместимости достаточно read tools; resources допустимы как дополнительный канал. |
| A25 | [MCP pagination, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/pagination) | List primitives используют opaque cursor, `nextCursor` и стабильный порядок. | Ограничивать историю и результаты. Различать протокольную пагинацию tools/resources и собственную пагинацию task-query. Не выдавать бесконечный журнал одним ответом. |
| A26 | [MCP cancellation, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation) | Cancel может прибыть после фактического выполнения; протокол требует корректно переживать гонки. | Состояние изменения определяет серверная транзакция. После timeout повторить запрос с тем же idempotency key или перечитать результат. |
| A27 | [MCP authorization, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) | HTTP authorization использует credentials для ресурса; STDIO должен получать credentials из environment. Token не должен попадать в URL. | Секреты хранить вне карточек и config примеров. Локальный stdio proxy использует environment token к общему API; произвольный actor label не должен давать повышенных прав. |
| A28 | [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpointer хранит state отдельного thread; store хранит данные между threads. | Общий журнал проекта должен жить вне отдельной сессии. Не выбирать browser memory или временный процесс в качестве источника истины. |
| A29 | [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | Возобновление может повторно запустить node и side effects; до interrupt нужны idempotent операции. | Idempotency — обязательная защита от повторного create/log после resume или retry. Один ключ с другим payload должен вызвать conflict. |
| A30 | [CrewAI tasks](https://docs.crewai.com/v1.15.23/en/concepts/tasks) | Description, expected_output и context явно задают работу; guardrails оценивают результат, async tasks учитывают dependencies. | Поля «цель», «критерии приемки», «результат» и links to dependencies. Карточка — контракт результата, а не только заголовок. |
| A31 | [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) | Trace/parent span IDs связывают операции из разных процессов; spans имеют время, events и status. | Корреляция project/task/session/run/request, timestamp и результат. Trace metadata дополняет смысловой audit, но не заменяет reason. |
| A32 | [Git worktree](https://git-scm.com/docs/git-worktree) | Один repository может иметь несколько рабочих деревьев и branch checkout. | Сохранять repository, branch, worktree и commit references по задаче. Claim карточки не заменяет изоляцию файлов. |
| A33 | [Stripe: idempotent requests](https://docs.stripe.com/api/idempotent_requests) | Повторный key воспроизводит сохраненный результат; несовпадающие параметры отвергаются. Это документированный API pattern, не специфичный для агентов. | Применить аналогичный pattern к записи в dashboard: unique key, canonical payload hash, сохраненный response, атомарная транзакция. |
| A34 | [Beads: agent issue graph](https://github.com/gastownhall/beads) | Проект предлагает persistent context, dependency-aware ready query, atomic claim, JSON output и иерархию epic/task/subtask. | Это прямой референс сочетания ready queue, claim, графа зависимостей и readable IDs; наличие функций не является независимым измерением потребностей всех агентов. Browser UI добавляет видимость человеку поверх общего task state. |
| A35 | [SWE-bench paper](https://arxiv.org/abs/2310.06770) | Реальные software issues требуют изменений в нескольких файлах и выполнения в окружении; benchmark оценивает разрешение issue. | У задачи может быть несколько артефактов и шагов. Подтверждать результат проверками, а не количеством написанного текста или tool calls. Не переносить старые benchmark scores на текущие модели. |
| A36 | [SWE-agent repository](https://github.com/SWE-agent/SWE-agent) | Агент работает с реальными issues; README направляет современную разработку к более простому mini-SWE-agent. | Dashboard должен принимать клиентов разной сложности через tools, не быть привязанным к одному harness. Не копировать полноразмерный runner без потребности. |
| A37 | [MCP Python SDK v1.27.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.27.0) | Версия SDK поддерживает стандартные transports, tools/resources/prompts; README использует `FastMCP` и typed functions. | Выбран `mcp==1.27.0`. Коннектор — Python STDIO proxy к общему HTTP backend; процессы клиентов не создают независимые базы данных. |
| A38 | [MCP Python SDK: server API v1.27.0](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.27.0/docs/server.md) | `@mcp.tool()` генерирует schemas из типов; поддерживает validated structured output, `ToolError` и явный `CallToolResult`. | Typed schemas, annotations и явные error results. Не смешивать `FastMCP` API этой версии с `MCPServer` из main/v2. |

## Приоритетные потребности и продуктовые решения

Это **наша синтезированная модель**, а не дословные рекомендации одного источника.

| Потребность | Поведение продукта | Проверяемое условие |
|---|---|---|
| Восстановить контекст | Проектный brief; краткое описание секции; карточка и ее последние решения/проверки | Новый клиент получает цель и актуальный next step без чтения полного чата |
| Разложить проект | Первая версия: проект → часть доски/направление → задача | Задача не может принадлежать чужой секции; зависимости остаются внутри проекта и не создают цикл |
| Понять «зачем» | Причина создания и значимых изменений обязательна | Пустой reason отвергается и в UI, и через API/MCP |
| Найти готовую работу | Ready query по приоритету с исключением unresolved dependencies и активных чужих claims | Заблокированная или занятая задача не выдается как доступная |
| Избежать дублей работы | Atomic claim с владельцем и сроком аренды | При двух одновременных claim ровно один выигрывает |
| Не потерять чужую правку | Version/expectedVersion | Stale update возвращает conflict и актуальную version |
| Пережить retry | Idempotency key и payload hash | Повтор create дает тот же task ID без второго audit event |
| Сохранить правки | Durable task state и append-only business audit | Перезапуск API сохраняет карточку и все успешные события |
| Проверить результат | Criteria, evidence и отдельный review stage | Done имеет результат и основание проверки; reviewer видим в истории |
| Сохранить свободу выбора клиента | Общий MCP protocol, project config examples, backend API | Codex/Claude используют одну доску и один domain validation |
| Помочь человеку | Board overview, blockers, detail, activity timeline, searchable history | По карточке понятно, кто занят, почему blocked и что проверялось |
| Не раздувать контекст | Bounded query, фильтры, краткий task context | Tool response не возвращает весь проектный журнал без запроса |

### Иерархия и границы

«Часть доски под каждую задачу» интерпретируется как отдельное направление/крупная задача с собственными карточками. В UI это секция внутри проекта. Первая версия по [architecture.md](../architecture.md) ограничена тремя уровнями; детализация карточки хранится в критериях и самостоятельных задачах секции. Отдельные parent/subtask entities — возможное расширение при подтверждённой необходимости. Статус — свойство конкретной карточки; секция не должна автоматически считать все дочерние карточки закрытыми из-за своего названия.

Секции задают **структуру**, колонки задают **состояние**. Поэтому карточка сохраняет секцию при переходе из «запланировано» в «в работе». Dependencies задают порядок, parent-child задает принадлежность: это разные связи. Отдельное поле blocker reason нужно даже при отсутствии task dependency — например, когда ожидается ответ человека.

### Проверка, критика и завершение

Рабочий цикл: создать/прочитать карточку → claim → выполнять небольшие шаги → записывать progress и decisions → приложить evidence → отправить на review → независимая проверка → done либо return to work. Для результата указываются команда, фактический outcome и ссылки на артефакты. Формулировка «проверено» без того, что именно проверяли, не дает наблюдаемого результата.

Предпочтителен отдельный review event с verdict, проверенной version и именем критика. Простая самостоятельная отметка агента о завершении не должна выглядеть независимой проверкой. Dashboard может различать review и done даже если встроенная автоматическая политика приемки еще не реализована. Открытые подзадачи и unresolved dependencies необходимо проверять перед принятой завершенностью [A10](https://code.claude.com/docs/en/agent-teams), [A13](https://code.claude.com/docs/en/best-practices).

## Durable audit: какие данные хранить

Сохранять бизнес-событие при **каждой успешной мутации** в той же транзакции, что и изменение карточки. Event содержит `id`, серверное `timestamp`, проект/секцию/задачу, actor, client provider, optional session/run ID, action, summary, reason, before/after или field delta, version и correlation/idempotency key. Для проверки дополнительно сохраняются evidence, outcome и reviewer. Неуспешный запрос не должен создавать событие об успешной правке.

Нужен **краткий явный reason**, пригодный для пользователя: «добавлен claim token, чтобы два агента не начали один шаг». Не следует требовать скрытое рассуждение модели или внутреннюю chain-of-thought. История хранит объяснение решения и наблюдаемые действия.

Actor identity и отображаемое имя — разные вещи. В минимальном локальном приложении actor может быть идентификатором доверенного connector; название «Claude» само по себе не доказывает, что вызов сделан Claude Code. При общем token и свободно переданном имени аудит является **атрибуцией доверенных локальных клиентов**, а не криптографическим доказательством личности. Для усиленной атрибуции требуются отдельные credentials/scopes на коннектор или агент. UI не должен создавать более сильное впечатление, чем реализовано.

Append-only business history запрещает редактирование прошлых событий обычными tool calls. Это не гарантирует защиты от администратора с прямым доступом к SQLite файлу. Следующий уровень — backup/export, отдельные права на storage и внешнее неизменяемое хранение. Для локального single-user scope достаточно честно показать эту границу.

## Надежность: правила общего сервера

1. **Один источник состояния.** Browser и оба connectors обращаются к одному FastAPI backend; SQLite находится у backend, а не у каждого STDIO процесса. Проверки бизнес-правил должны быть одинаковыми независимо от caller.
2. **Атомарный claim.** В одной транзакции проверить статус, unresolved dependencies, свободный/просроченный claim, записать владельца и срок. Не использовать схему «GET, затем независимый UPDATE». Для долгой работы нужна renew/release операция; истекший claim можно занять снова с записью причины.
3. **Защита записи.** Операция редактирования использует version comparison. При conflict сохранить исходное состояние и предложить перечитать task; никаких тихих last-writer-wins.
4. **Idempotency.** Для мутаций caller передает key. Повтор одинакового payload возвращает исходный результат. Отличающийся payload с тем же key отвергается. Изменение, audit и сохранение idempotency response проходят одной транзакцией [A29](https://docs.langchain.com/oss/python/langgraph/interrupts), [A33](https://docs.stripe.com/api/idempotent_requests).
5. **Integrity.** Проверить существование project/section/parent/dependencies; запретить межпроектные связи, self-dependency, graph cycles, пустые названия/reasons и неизвестные enum values.
6. **Restart.** Состояние, история и claims должны быть доступны после restart. Browser storage может хранить тему/последний проект, но не быть единственным persistent task store.
7. **Ограниченный доступ.** Loopback по умолчанию; token к API из environment; секрет не выводится в audit. Произвольный `actor` в payload не дает право обходить claim или review.

## MCP contract и конфигурация клиентов

Названия ниже — **предлагаемый контракт**, финальные имена нужно сверить с реализованным connector.

Таблица включает рекомендации за пределами минимального выпуска. По [architecture.md](../architecture.md) контекст проекта предоставляет `get_board`, контекст задачи — `get_task`, записи — `add_note`/`log_change`, диагностику — `/api/connectors`. Отдельные `release_task`, renew и `review_task`, resource URI и ready endpoint не считаются реализованными до включения в API и проверки. В первой версии gate `done` подтверждает наличие criteria и evidence note; независимый reviewer verdict и достоверность приложенного evidence требуют отдельной проверки. `last_seen` означает время реального обращения, а не доказательство живого агентского процесса.

| Операция | Назначение | Обязательный смысл |
|---|---|---|
| `list_projects` / `get_project_context` | Выбрать проект и понять текущую работу | IDs, brief, sections, bounded active tasks |
| `create_project` / `create_section` | Создать проектную доску и часть доски | Название, описание/цель, reason |
| `list_tasks` / `get_task_context` | Найти работу и прочитать актуальную карточку | Фильтры, dependencies, version, recent activity |
| `create_task` | Создать задачу/подзадачу | Project/section, title, goal, criteria, reason, idempotency key |
| `claim_task` / `release_task` | Взять/передать работу | Atomic ownership, expiry/lease, reason |
| `update_task` | Изменить описание, состояние или связи | Expected version, reason, bounded validated payload |
| `record_activity` | Сохранить действие, решение, проверку | Type, summary, reason, evidence/outcome |
| `review_task` | Зафиксировать отдельный review | Verdict, reviewer, reviewed version, findings |
| `get_history` | Ответить «что, зачем, когда» | Project/task filters, stable ordering, bounded page |
| `connector_status` | Диагностика | Реальное доступное API, version, capabilities без секретов |

Read tools маркируются read-only; append-only activity не объявляется read-only. `idempotentHint` уместен только там, где повторная операция действительно защищена ключом. Ошибка `CLAIM_CONFLICT`, `VERSION_CONFLICT`, `UNRESOLVED_DEPENDENCY`, `VALIDATION_ERROR` или `UNAUTHORIZED` должна быть machine-readable и понятной человеку. Ошибки выполнения tool возвращаются как ошибки, а не обычный JSON с успешным текстом [A07](https://developers.openai.com/plugins/build/mcp-server), [A21](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

Используется **official Python SDK v1.27.0**: `from mcp.server.fastmcp import FastMCP`, typed tool functions, запуск `mcp.run(transport="stdio")`. При явном `CallToolResult` вернуть text JSON и `structuredContent`; при ожидаемом business error использовать `ToolError` либо `isError=True`. Все human-readable diagnostics идут в stderr. Основание: [версионный server API](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.27.0/docs/server.md). SDK main уже показывает другое поколение API; нельзя брать из него imports без миграции.

Codex хранит MCP entries в `~/.codex/config.toml` или trusted project `.codex/config.toml`. У STDIO нужны command/args, можно задать cwd и environment. Claude Code использует `.mcp.json` с wrapper `mcpServers` и `type: "stdio"`; CLI форма — `claude mcp add --transport stdio agentboard -- <python> <absolute_connector_script>`. В shipped примерах должны быть реальные путь/команда выбранного проекта, а не фальшивый hosted URL [A01](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [A08](https://code.claude.com/docs/en/mcp).

Instructions обязаны объяснять порядок работы и side effects, но они не принуждают агента вызывать инструменты и не заменяют validation. Полезный минимальный регламент: «Перед работой прочитай project/task context. Создай карточки для новых шагов, возьми claim. Для изменения добавь краткий reason. После работы запиши outcome/evidence и передай на review. При conflict перечитай task, не перезаписывай чужую версию». Это должно появиться в проектном AGENTS.md/CLAUDE.md, server instructions и коротком разделе подключения.

## Проверяемые сценарии для отдельного критика

| Сценарий | Ожидаемое поведение |
|---|---|
| Codex connector создает проект, секцию, задачу; Claude connector читает ее | Совпадают ID и state; история видна в UI |
| Два клиента одновременно claim одну задачу | Один owner, второй получает conflict |
| Агент claim задачу с незавершенной dependency | Отказ с явным списком blockers |
| Повтор create после timeout с тем же key | Один task и одно событие создания |
| Тот же key, другие параметры | Conflict, состояние не меняется |
| Human и agent редактируют одну version | Второй stale write отвергается |
| Изменение без reason/в чужую секцию/с graph cycle | Validation error, без успешного audit event |
| Закрытие работы без evidence или с открытыми подзадачами | Применяется явная политика завершения; UI не называет ее проверенной |
| Перезапуск API и повторная загрузка browser | Данные и история сохранены |
| API выключен или token неверен | Connector дает объяснимую ошибку, не создает offline task |
| Независимый reviewer пишет замечание | Замечание, version и reviewer видны; состояние меняется только явной операцией |
| MCP subprocess стартует | Настоящие initialize, tools/list и tools/call проходят; stdout содержит только MCP |

Ограничение измерений: documentation research и protocol smoke tests подтверждают контракт и реализацию; они не заменяют user research, длительные concurrent workloads или authenticated live test через установленный Claude Code. Отчет проверки должен явно перечислить, какие из этих уровней реально пройдены.

## Принятое направление

Сначала реализовать общую durable иерархию, понятную доску, историю причин/результатов, защищенные мутации и работающий MCP connector. Из сложных агентных платформ брать необходимые contract patterns, а не воспроизводить все runner features. Это дает человеку понятную картину проекта, а Codex и Claude Code — одну доступную систему задач независимо от их внутренних чатов и памяти.
