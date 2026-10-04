# Независимая критика коннектора

Дата: 04.10.2026. Reviewer: `research_products`; автор исправлений: `research_agents`, автор Codex launcher: root. Проверены `connectors/mcp_server.py`, `connectors/setup.py`, `connectors/codex.py`, `tests/test_mcp.py`. Полные воспроизведения и первоначальные последствия находятся в [engineering-review.md](engineering-review.md).

После исправлений открытых подтвержденных ошибок в проверенном connector scope не осталось. Это проверка протокола и shared-state workflow через официальный SDK; actual interactive Codex/Claude Code процессы reviewer не запускал.

| Найденная ошибка | Исправление | Независимая повторная проверка |
|---|---|---|
| Provisioning до проверки config терял одноразовый token при ошибке файла | Проверка JSON/TOML до POST | Невалидный JSON: agents 3→3; custom token сохранен и создает проект с HTTP 200; regression невалидного TOML |
| CLI session ID 255 против API 200 | Максимум 200 до запуска MCP | 201 символ: exit 1, диагностический stderr, пустой stdout |
| URL loopback мог передать Bearer системному HTTP proxy | `ProxyHandler({})` плюс запрет redirects | Dummy Bearer был пойман proxy до исправления; после исправления реальные две stdio sessions и provisioning работают при HTTP_PROXY на недоступный proxy и пустом NO_PROXY |
| get_board/list_projects отдавали все sections/agents независимо от page limit | Независимые limit/offset, totals/continuation | 500 sections/identities; разные страницы, конец списка, максимум 100, serialization первого элемента <5000 chars |
| Сокращение списка sections могло скрыть описание выбранного раздела | `section_context` при `section_id` | Контекст выбранной последней секции доступен и явно обрезан до 2000 символов |
| Вложенные files/diffs/events раздували даже небольшую страницу | Note/event summaries с markers/counts, files prefix, ограниченный текст; task summaries с dependency count; полный task сохраняет dependencies | 50 change events с 200 files по 2048 chars, diff 200k; serialized text+structured <500k chars; board <50k; get_task <100k; metadata totals/truncation и полные 128 dependency IDs проверены |

Фактически выполнена команда `.venv/Scripts/python.exe -m pytest tests/test_mcp.py -q`: **3 passed**, **8.18 s**, одно внешнее предупреждение Pydantic settings. Integration test поднимает изолированный настоящий HTTP server, соединяет две независимые stdio sessions, проверяет schema/annotations, создание и retry, конфликт ключа, shared read, dependencies, atomic claim, запрет чужих writes, code change/evidence/review/done, версию и actor/session history. Setup не меняет user-wide config и сохраняет unrelated project config.

Ограничение подтверждено явно: MCP возвращает summaries для управления контекстом агента. Полные notes/diffs/files остаются в HTTP API, dashboard и полном export. Counts/markers не дают принять preview за полный список. last_seen отражает реальный API request; успешная генерация config не считается proof of connection.

## Дополнительная проверка установленного Codex CLI

После основного review добавлен `connectors/codex.py` для установленного Codex 0.154, который может не загрузить MCP из проектного TOML до доверия workspace. Wrapper читает только `.codex/config.toml`, передает три явных process-scoped `-c` override (`command`, `args`, `cwd`) для Agentboard и сохраняет остальные аргументы CLI. JSON escaping проверяется TOML roundtrip в новом тесте, включая путь с пробелами. Запуск — argv list через `subprocess.call`, без shell; npm shim при необходимости заменяется прямым Node entry. Записи project/global config или изменения trust settings в коде отсутствуют. Подтвержденных ошибок wrapper в этом scope не найдено.

Reviewer лично выполнил только read metadata команду `npm.cmd run codex -- mcp get agentboard --json`: **exit 0**, **enabled: true**, **disabled_reason: null**, transport **stdio**, ожидаемые абсолютные Python/script/credentials пути, API **http://127.0.0.1:4242** и правильный **cwd**. Это подтверждает регистрацию MCP в реально установленном CLI через wrapper. Model run и interactive Codex/Claude sessions не запускались; эту проверку нельзя считать доказательством model-driven tool call. Новейший wrapper test прочитан; повторный запуск полной suite reviewer на этом этапе не выполнял.

Ponytail review коннектора и wrapper: `Lean already. Ship.` Stdlib HTTP/JSON/TOML/subprocess, один shared API и официальный MCP SDK; validation, paging, config-preservation и минимальные совместимые CLI overrides покрывают обязательные требования. Ненужных abstractions/dependencies для удаления не обнаружено.
