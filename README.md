# Agentboard

Локальное рабочее пространство для человека, Codex и Claude Code: **проект → раздел большой задачи → карточки**. Доска показывает ход работы; журнал сохраняет автора, причину и изменения «было → стало». Отдельные записи кодовых правок содержат файлы, diff, commit и результат проверки.

## Открыть

Для обычного пользователя Windows 10/11 x64: **[скачать Agentboard-Setup-1.1.0.exe](https://github.com/7Askar7/DashAI/releases/download/v1.1.0/Agentboard-Setup-1.1.0.exe)**. Установка для текущего пользователя, без прав администратора, Python и Node.js. Ярлык запускает локальный dashboard; кнопка лаунчера подключает агентов к выбранной папке проекта. Каждая установка хранит свою базу в `%LOCALAPPDATA%\Agentboard`.

Обновления приходят через [DashAI Releases](https://github.com/7Askar7/DashAI/releases): приложение проверяет канал при запуске и каждый час, пока оно открыто. Автообновление включено по умолчанию; приложение проверяет подпись издателя, сохраняет SQLite backup и обновляет программу после закрытия подключений агентов. Проекты, история и credentials сохраняются. [Установка и выпуск версий](docs/release.md) описывает готовый установщик, канал, настройки издателя и workflow релизов.

Следующие команды нужны для разработки и сборки из исходников.

После запуска: **http://127.0.0.1:4242**.

```powershell
# В этой рабочей папке среда и зависимости уже установлены.
npm start
```

Один процесс отдает production UI и API. Данные сохраняются в `data/agentboard.sqlite3`, стандартные connector credentials — в `data/connector-secrets.json`. Перезапуск не удаляет проекты и историю. Первый запуск на новой базе создает пустое пространство и идентичности клиентов, без выдуманной активности. В текущей базе проект Agent Dashboard создан через MCP; записи отражают реально выполненное исследование и реализацию.

## Установка с чистого checkout

Нужны Python 3.11+ и Node.js 20.12+; проект проверен на Windows. PowerShell:

```powershell
./scripts/setup.ps1
npm start
```

Или вручную:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-lock.txt
npm ci
npm run build
npm start
```

`requirements-lock.txt` фиксирует проверенную Python-среду Windows. Для другой ОС установите `requirements-dev.txt`, где платформенные зависимости выбирает pip. Npm scripts используют именно `.venv`, а не несовместимые глобальные библиотеки. Порт 4242 выбран после проверки занятых портов этой машины; чужие сервисы не изменялись.

Для разработки в двух терминалах:

```powershell
npm run server
npm run dev
```

Dev UI: http://127.0.0.1:5173; `/api` проксируется на 4242. Другой production port: `npm start -- --port 4250`. В dev при смене API port обновите proxy в `vite.config.ts`.

## Подключить Codex и Claude Code

При запущенном API выполните:

```powershell
npm run connectors:setup
```

Setup создает project-scoped `.codex/config.toml` и `.mcp.json` с абсолютными путями. Остальные настройки сохраняются; глобальные настройки пользователя не изменяются. В этом workspace конфиги уже созданы. Начните новую сессию Codex/Claude Code в доверенном проекте и проверьте `agentboard` в `/mcp`. Claude Code может запросить стандартное разрешение project MCP.

Установленный здесь Codex CLI 0.154.0 не читает настройки недоверенного проекта. Подготовлен совместимый запуск, который передает только конфигурацию `agentboard` через явные CLI overrides и не меняет глобальный config:

```powershell
npm run codex
# Проверить загрузку конфига без запуска модели:
npm run codex -- mcp get agentboard --json
```

После доверия проекту подойдет и обычный `codex`. Установленный Claude Code уже видит project connector; его состояние — `Pending approval`, до разрешения MCP в новой сессии.

Для другого репозитория:

```powershell
npm run connectors:setup -- --project-root "C:/path/to/project"
```

Для нескольких экземпляров используйте отдельную идентичность, чтобы различать авторов истории:

```powershell
npm run connectors:setup -- --project-root "C:/path/to/project" --agent-name "Codex — backend" --agent-kind codex
```

Отдельного агента также можно создать в UI «Коннекторы». Его токен выдается один раз. Сервер определяет автора по токену; имя в произвольном payload не дает права действовать от чужого лица.

MCP tools: `list_projects`, `create_project`, `get_board`, `ready_tasks`, `create_section`, `create_task`, `get_task`, `update_task`, `claim_task`, `add_note`, `log_change`, `get_history`, `connector_status`.

Рабочий цикл агента:

1. Найти проект и прочитать контекст доски/задачи.
2. Создать карточку с целью, rationale и критериями; взять ее через atomic claim.
3. После существенных изменений вызвать `log_change` с файлами, причиной и diff/commit; сохранить решения и progress.
4. Добавить evidence: точная проверка и фактический результат.
5. Перевести в review, после проверки — в done. На conflict перечитать version; при retry использовать тот же idempotency key с тем же payload.

Подробные команды, форматы токенов и contracts: [docs/connectors.md](docs/connectors.md). Правила работы агентов: [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md). Подключение соответствует официальным инструкциям [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) и [Claude Code MCP](https://code.claude.com/docs/en/mcp).

## Что работает

- Отдельные проекты и их доски; разделы крупных задач; создание и редактирование карточек, проектов и разделов.
- Пять статусов, приоритеты, исполнители, зависимости, поиск и комбинированные фильтры, доска и список.
- Подробности: что делаем, зачем, критерии, записи, правки кода и хронология; журнал проекта и всего пространства.
- Транзакционный append-only audit, optimistic version conflicts, atomic claim с продлением/истечением, idempotency и запрет циклов зависимостей.
- Done требует критериев и evidence; ручное вмешательство человека сохраняет причину. История показывает записанное подтверждение, не автоматическую независимую сертификацию результата.
- Экспорт полного проекта и истории без credentials; native modal dialogs, клавиатура, responsive UI на 390/320 px и reduced motion.
- Один store для browser и двух MCP-клиентов. Коннекторы не создают отдельные базы и не наследуют HTTP proxy для локальных bearer-запросов.

Dashboard — учет работы внешних агентов. Он не запускает модели и не следит за filesystem автоматически: агент явно вызывает `log_change`. Метка последнего запроса отражает контакт с API, а не доказательство работающей сессии. Это локальное пространство одного пользователя ОС, не публичный multi-user сервис. Записанное evidence — сообщение автора; dashboard не запускает команды из заметок.

## Исследование до реализации

Пользователь запросил глубокий анализ. Все три исследования закончены до начала кода; использованы первичные источники и отдельная критика результатов:

| Отчет | Объем | Содержание |
| --- | --- | --- |
| [Аналоги](docs/research/01-products.md) | 38 самостоятельных продуктов и проектов | Механизмы, компромиссы, сравнительные группы и решения |
| [Потребности агентов](docs/research/02-agent-needs.md) | 38 первичных источников | Контекст, concurrency, audit, evidence, MCP и надежность |
| [UX/UI](docs/research/03-ux-ui.md) | 26 первичных источников | Иерархия, взаимодействия, визуальная система, доступность |

[Архитектурный контракт](docs/architecture.md) связывает исследование с поведением API/UI. [Независимый review исследований](docs/reviews/research-review.md) проверяет источники и отделяет наблюдения от обещаний реализации. Документы фиксируют дату исследования 03.10.2026; проверки реализации завершены 04.10.2026 по Москве.

## Ponytail действительно используется

Прочитаны и применены upstream skills [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail): `ponytail` (full) и `ponytail-review`. Их оригинальные файлы и MIT license находятся в `.agents/skills/` для Codex и `.claude/skills/` для Claude Code. Источник закреплен на commit `c982cd411abb53323c4baa1baa3c2f020b8d0b08`; глобальные plugins/hooks не устанавливались.

Конкретные результаты подхода: sqlite3/backup/UUID/JSON из stdlib; native inputs/select/dialog; CSS responsive вместо отдельного mobile framework; небольшой stdio proxy поверх общего API. Критик проверяет лишние абстракции и зависимости отдельно от correctness; обязательные проверки и сохранность истории не сокращаются.

## Проверить

```powershell
npm run build
npm test
npm run test:ui
```

`npm test` проверяет API и настоящие stdio MCP ClientSession на отдельной временной базе. Browser integration использует изолированный backend, реальные формы и SQLite, включая конфликт одновременных правок, evidence gate, code-change metadata, reload, export и mobile reflow. Для UI нужен Chromium: `node scripts/python.mjs -m playwright install chromium`; на этой машине автоматически используется уже установленный Chromium. Можно задать `AGENTBOARD_BROWSER` с абсолютным путем к browser executable.

Независимые отчеты: [engineering](docs/reviews/engineering-review.md), [backend](docs/reviews/backend-review.md), [UX](docs/reviews/ux-review.md). Фактические результаты и screenshots: `artifacts/qa/`. Общий итог: [docs/verification.md](docs/verification.md).

## Экспорт и backup

Кнопка «Экспорт» сохраняет JSON проекта со всеми его events и notes. Для согласованного полного backup SQLite при работающем сервере:

```powershell
npm run backup -- "C:/backups/agentboard-2026-10-04.sqlite3"
```

Backup не перезаписывает существующий файл и проверяет `integrity_check`. Он содержит credential hashes, поэтому храните его приватно. Стандартные реальные tokens находятся отдельно в `data/connector-secrets.json`; для восстановления действующих коннекторов сохраните этот файл приватно вместе с backup. Для восстановления остановите **свой** Agentboard process, сохраните текущую `data/` отдельно, восстановите проверенный backup как `data/agentboard.sqlite3` в чистую data directory и верните соответствующий secrets-файл. Не копируйте только живой SQLite файл с незавершенным WAL: используйте backup API.

Локальные `.mcp.json`, `.codex/config.toml`, `data/`, `.venv/`, `dist/` и QA outputs исключены из git. Исходники, lockfiles, исследования, инструкции, tests и reports остаются в проекте.
