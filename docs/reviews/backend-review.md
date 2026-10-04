# Независимая проверка backend

Проверяющий: агент, который реализовывал MCP connector; автор backend — другой агент. Проверены `server/app.py` и `tests/test_api.py`: доменные правила, журнал, concurrency, credentials и persistence. Сервер при этой проверке самостоятельно не изменялся.

## Обнаружено: P2 — разные версии данных в одном ответе чтения

До исправления `bootstrap`, `board` и `task_details` выполняли несколько `SELECT` через соединение в autocommit, без явной read transaction. Параллельная запись между SELECT давала карточку старой version и историю уже новой version в одном ответе. Это мешало оператору сопоставить состояние с причиной последней правки.

Воспроизведение выполнено на временной SQLite базе через настоящий FastAPI `TestClient`. Контролируемый interleaving: сразу после чтения карточки независимая write transaction обновляет title/version и атомарно добавляет event; затем исходный GET читает события. Получен ответ:

```json
{
  "task_title": "before",
  "task_version": 1,
  "latest_event_after_title": "after",
  "latest_event_after_version": 2
}
```

Предлагаемое исправление: `db.execute("BEGIN")` перед первым SELECT в трех составных read handlers. SQLite WAL позволяет параллельному writer завершиться, а read transaction сохраняет один снимок для всей выдачи. Export уже реализован правильно с `BEGIN`. Нужен один deterministic regression test такого interleaving; обычные последовательные tests проблему не обнаруживают.

Статус: **исправлено автором backend и повторно проверено независимо**. Все три handlers начинают read transaction через `BEGIN`. Автор добавил параметризованный `test_composite_reads_share_a_snapshot` для bootstrap/board/task: concurrent writer коммитит между SELECT, исходный ответ сохраняет старые entity и audit вместе, следующий GET видит обе новые версии вместе. Независимый повторный запуск всех API tests: **9 passed**.

## Что проверено и подтверждено

- `.venv/Scripts/python.exe -m pytest tests/test_api.py -q`: **9 passed**. Единственное предупреждение — deprecated alias в установленной Starlette/AnyIO, не ошибка приложения.
- Domain writes проходят `BEGIN IMMEDIATE`; мутация, audit и idempotency result записываются одной транзакцией.
- `expected_version` и live claim проверяются перед task write; notes/changes также проверяют чужой claim.
- Dependency integrity покрывает same project, существование, duplicate/self/cycle, completion gate и reopen blocker.
- Reason/unknown fields/types проверяются shared schemas; caller не может передать actor и повысить права через payload.
- Token хранится в DB как hash; agent provisioning разрешен human boundary и не сохраняет plaintext token в business audit или idempotency cache.
- Host/Origin guards и loopback CLI соответствуют явно выбранной локальной доверенной границе.
- Events защищены от SQL UPDATE/DELETE; export содержит полную историю без credentials.
- Restart test сохраняет состояние и standard credentials; claim renewal/takeover/human override протестированы.

Дополнительно реальный MCP integration test из `tests/test_mcp.py` связывает два STDIO clients с одним HTTP backend: состояние, журнал, claim/conflict и code-change metadata совпадают с прямым HTTP чтением.

## Проверка сложности по Ponytail

Применен `.agents/skills/ponytail-review/SKILL.md` отдельно от correctness pass. SQLite, stdlib transactions и один shared validation path покрывают задачу без ORM, отдельного event bus или speculative repositories.

**Lean already. Ship.** Этот результат относится к сложности; найденная correctness issue исправлена и regression проверки прошли.
