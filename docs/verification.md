# Проверка поставки

Дата: 04.10.2026, Москва. Локальный адрес: **http://127.0.0.1:4242**. Проверялся работающий UI и общий HTTP/MCP store, а не статический макет.

## Фактически выполненные проверки

| Проверка | Результат | Что она подтверждает |
| --- | --- | --- |
| `npm run build` | PASS | TypeScript без ошибок; production bundle Vite собран |
| `npm test` | **13 passed** | 9 API tests и 4 MCP/launcher tests |
| `npm run test:ui` | **9 групп browser assertions PASS** | Пустое пространство; create/reload; evidence gate; конфликт/черновик; code change; поиск/export; 390/320 reflow; mobile keyboard; configs |
| Независимая browser UX-проверка | **42 сценария + 6 keyboard checks PASS** | Реальные формы, network retry, зависимости, version conflict, clipboard, desktop/mobile; все найденные P1/P2 закрыты и перепроверены |
| `npm run codex -- mcp get agentboard --json` | `enabled: true`, exit 0 | Установленный Codex CLI 0.154.0 читает подготовленный connector при совместимом запуске |
| `claude mcp get agentboard` | project stdio config найден, Pending approval | Установленный Claude Code видит конфигурацию; штатное client разрешение еще не дано |
| `npm run backup -- data/backups/verified-2026-10-04.sqlite3` | PASS, integrity check `ok` | Согласованный backup настоящей SQLite базы |
| `npm run backup -- data/backups/delivery-2026-10-04.sqlite3` | PASS, integrity check `ok` | Финальная база после MCP-записи evidence и завершения семи задач текущего проекта |
| `pip check` | No broken requirements | Изолированная Python-среда совместима |
| `npm audit --omit=dev` | 0 vulnerabilities reported | Проверка известных advisory для runtime npm dependencies на момент запуска |

API tests проверяют иерархию, обязательную причину, неизвестные поля, optimistic conflicts, реальную конкурентную race claim, продление/истечение аренды, ownership notes/changes, human intervention, зависимости и циклы, evidence gate, idempotency, сохранение после restart, append-only SQL triggers, token isolation, Origin/Host и полный export более 100 событий. Параметризованный interleaving test подтверждает согласованный snapshot сущности и истории при параллельном commit.

MCP tests поднимают отдельный настоящий HTTP/SQLite сервер и **две независимые stdio ClientSession** официального SDK. Они читают одни task IDs, пишут задачи и code changes, проходят claim/review/done и получают одинаковую историю. Отдельно проверены inherited-proxy isolation, config preservation, одноразовая выдача credentials после validation, bounded nested output и Codex launcher с путями содержащими пробелы. Это проверка MCP транспорта/контракта, не запуск платных моделей внутри Codex/Claude.

Browser tests не мокируют API: работают реальные формы и временная SQLite база. Сценарий конфликта специально меняет description другим клиентом, оставляет старый textarea в черновике и проверяет, что последующее сохранение меняет только пользовательский priority, сохраняя новое чужое description. Console page errors отсутствуют.

## Независимые критики

- [Research review](reviews/research-review.md): проверка объема и качества источников, отделение рекомендаций от обещаний.
- [Engineering review](reviews/engineering-review.md): reproductions, исправления и browser rechecks конфликтов, истории, late responses и цвета.
- [Backend review](reviews/backend-review.md): обнаружена и исправлена несогласованность composite reads; повторная проверка 9 API tests.
- [Connector review](reviews/connector-review.md): credentials, proxy, config-preservation, nested budgets и установленный CLI.
- [UX review](reviews/ux-review.md): реальные сценарии, desktop/mobile, клавиатура и частичная проверка доступности. Это не сертификация WCAG.

Ponytail full применялся во время реализации. Отдельный Ponytail-review удалил неиспользуемый ref и не предложил сокращать необходимые проверки или обязательные функции.

## Артефакты

`artifacts/qa/ui-results.json`, `browser-export.json`, `ui-smoke-desktop.png`, `ui-smoke-mobile-390.png`, `ui-smoke-mobile-320.png`; дополнительные независимые screenshots и воспроизводители имеют prefix `ux-`. QA использует временные базы; реальные пользовательские проекты не загрязняются тестовыми карточками. Текущий проект в основной базе создан через MCP и содержит честно помеченные записи о реально выполненной работе.

Два предупреждения pytest поступают от установленных Starlette/AnyIO и MCP/Pydantic settings; failures отсутствуют. Vite предупреждает о неиспользуемой `use client` директиве в Lucide при сборке обычного browser app; сборка завершается успешно.

## Практические границы

Один пользователь ОС, loopback API, внешние agents. Dashboard не является runner моделей или filesystem watcher. Code changes записываются явным `log_change`; evidence хранит результат, сообщенный автором. Last seen — время последнего запроса, не живой heartbeat процесса. Наличие evidence не доказывает независимое принятие задачи. Экспорт сохраняет все данные; MCP previews маркируются как сокращенные.

Codex project config начинает действовать после доверия проекту либо при `npm run codex`, который передает только MCP параметры CLI overrides. Для Claude Code требуется обычное разрешение project MCP в новой сессии. Глобальные client settings и чужие сервисы не изменялись.
