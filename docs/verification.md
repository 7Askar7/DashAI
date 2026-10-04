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

## Windows-поставка 1.1.0

Проверена отдельная установка без Python, Node.js, checkout и административных прав. Локальная сборка `Agentboard-Setup-1.1.0.exe` использует Python 3.14.3; опубликованная CI-сборка — Python 3.14.7. Пользовательская SQLite/credentials хранится отдельно от программы. В installer встроены публичный ключ издателя и HTTPS feed DashAI; private key, рабочая база и project connector configs в bundle отсутствуют.

- **17 тестов PASS** в изолированной production build-среде: 9 API, 5 MCP/launcher, 2 desktop security/resource checks и 1 release contract.
- **Frozen smoke PASS**: windowed EXE поднимает настоящий UI/API, console companion через официальный SDK создает проект, раздел и карточку; project configs используют установленный EXE. Stdio shutdown завершается без traceback.
- **9 групп browser integration PASS** после изменения connector metadata; реальные forms/API/SQLite, конфликт, export и mobile navigation.
- Независимые **19 adversarial checks PASS**: подпись/ключ/подмена, replay и downgrade, HTTPS, размер и SHA-256, потоковые лимиты, WAL backup и native PowerShell отказ поврежденному installer.
- Независимый **реальный lifecycle 7/7 PASS**: fresh Inno install; запись задач/notes/code changes через MCP; запрет установки при работающей программе; signed handoff → PowerShell → Inno → новая QA-версия 1.1.1; точное сохранение всех persisted экспортных полей и credentials; запрет downgrade; uninstall сохраняет SQLite и удаляет собственный автозапуск.

Lifecycle использует отдельную папку и временную тестовую регистрацию установщика. Итог: `artifacts/qa/desktop-lifecycle-20261004-172146/result.json`; тестовая регистрация Windows восстановлена, рабочая база пользователя не использовалась. Из сравнения экспорта исключалось только динамическое время самого export-запроса, а не данные или timestamps истории.

Все замечания независимого [desktop-review](reviews/desktop-review.md) исправлены и перепроверены; отдельный Ponytail-review — **Lean already. Ship.** Границы: Windows 10/11 x64; браузерный UI; pinned Ed25519 channel key; начальный installer без платного Authenticode сертификата. Это не полная реализация TUF и не тест всех будущих миграций схемы. [Процесс установки и выпуска](release.md).

## Опубликованный релиз и настоящий канал

[GitHub Actions 37210113381](https://github.com/7Askar7/DashAI/actions/runs/37210113381) успешно собрал commit `cbbb6ecc3a26537cf92e2ffda75125aa225c8cf6`, выполнил **17 tests PASS** и реальный frozen smoke, затем подписал manifest и опубликовал [Agentboard 1.1.0](https://github.com/7Askar7/DashAI/releases/tag/v1.1.0). Предыдущие два CI-запуска остановились до публикации; найденные PowerShell module-path и Windows path-alias ошибки исправлены и повторно проверены.

Штатный `desktop.updates` скачал публичный `latest.json` и весь опубликованный installer по настоящему HTTPS-каналу GitHub, без API credentials. Ed25519 signature, signed size и SHA-256 проверены; версия 1.1.0 предлагается для клиента 1.0.0, а для текущей 1.1.0 повторная установка не предлагается. Частичный `.part` файл после успешной загрузки отсутствует.

- Installer: `Agentboard-Setup-1.1.0.exe`, **24 124 234 bytes**.
- SHA-256: `a362c993df3ebfc5c5c9af5ed3a5cfea12c8548268509db99ca20b58771cbaae`.
- Результат сетевой проверки: `artifacts/qa/public-release-1.1.0/result.json`.

Локальный lifecycle проверял замену приложения QA-версией и сохранение данных; опубликованный installer отдельно прошёл frozen smoke на Windows runner. Сетевое скачивание здесь не выдаётся за повторную установку на рабочем профиле пользователя.

## Единый Kanban 1.2.0

Доска всего проекта теперь состоит из пяти самостоятельных колонок, а не рядов разделов с общей сеткой. Карточка находится только в колонке своего статуса; раздел указан меткой и доступен как фильтр. Подтверждено отдельным [Kanban review](reviews/kanban-review.md).

- Production build / TypeScript **PASS**, проверенный JS `index-CM5xKQTw.js`, CSS `index-9LvY9Z7e.css`.
- Общая browser regression: **9 групп PASS**, включая создание/правки/export/persistence и мобильный reflow; smoke адаптирован к новым карточкам и мобильной выбранной колонке.
- Независимый `node scripts/python.mjs scripts/kanban_smoke.py`: **9 групп PASS** на настоящем браузере и временной SQLite. Проверены whole-project grouping, section filter, list-only status filter, native drag, required reason/cancel, audit before/after/author/reload, evidence gate, настоящий concurrent PATCH, сохранение причины и чужих полей, потеря успешного ответа и idempotent retry с одной записью истории, клавиатура и mobile status navigation.
- Найденная потеря фокуса после перемещения закрыта: desktop фокусируется на поле перемещения новой карточки, mobile — на видимой кнопке выбранного статуса. Regression сохранен; one-shot animation frame был заменен эффектом после React commit.
- **17 API/MCP/desktop/release tests PASS** и настоящий **frozen smoke PASS** для runtime 1.2.0. Финальная frontend-правка не меняет backend, схему базы или процесс подписанного обновления.
- Отдельные Ponytail-reviews компонента, CSS и упаковки: **Lean already. Ship.** Новых зависимостей нет; старые swimlane CSS удалены.

Геометрия: при 1440 px все пять колонок помещаются (`clientWidth = scrollWidth = 1138`); при 390/320 px видна одна выбранная колонка, page overflow отсутствует. `page_errors = []`. Артефакты: `artifacts/qa/kanban-results.json`, `kanban-desktop.png`, `kanban-mobile-390.png`, `kanban-mobile-320.png`. Тестовые карточки не добавлялись в рабочую базу.

[CI 37220986415](https://github.com/7Askar7/DashAI/actions/runs/37220986415) успешно выпустил [Agentboard 1.2.0](https://github.com/7Askar7/DashAI/releases/tag/v1.2.0) из commit `2c1a235136c980dec7f56313d1166ea69e299650`: production build, **17 tests PASS**, настоящий frozen MCP smoke, подпись manifest и публикация завершены успешно. Штатный updater клиента 1.1.0 скачал публичный feed и весь installer, подтвердил прежний Ed25519 key, размер **24 131 177 bytes** и SHA-256 `b02d0f5241cc47686c08bbc0850f67442360300cec7c166db5d41cc3e7aaf31c`. Клиенту 1.2.0 повторное обновление не предлагается. Один transient ConnectTimeout при сетевой проверке разрешился повторной загрузкой; TLS и проверка подписи не ослаблялись. Результат: `artifacts/qa/public-release-1.2.0/result.json`.

Отдельный reviewer повторно подтвердил подпись реального manifest, версию, build commit, bundled key и соответствие size/SHA-256 GitHub asset metadata: **PASS**, `artifacts/qa/public-release-1.2.0-critic/result.json`. На рабочем профиле installer не запускался. Схема базы и updater runtime не изменялись; новая проверка не выдается за повторный install/update lifecycle.

После выпуска исправлена только съемка mobile QA: full-page capture после вертикальной прокрутки отображал fixed skip-link внутри полного кадра, хотя в реальном viewport он находился выше экрана и не имел фокуса. Перед screenshot выполняются scroll-to-top и ожидание завершения toast; геометрия и activeElement записываются. Повторные **9 Kanban groups PASS**; runtime, styles и опубликованный build не менялись.

## Общая доска и типы задач 1.3.0

Пользовательские разделы убраны из создания, редактирования, фильтров, карточек и списка. Новый проект сразу показывает пять колонок и кнопку создания задачи. Native select «Тип задачи» предлагает исследование, разработку, тестирование, исправление, документацию и другое. Тип виден на карточке, фильтруется, редактируется с причиной и экспортируется; HTTP/MCP позволяют создавать карточку без section_id.

- Production TypeScript/Vite build **PASS**, финальный frontend `index-Dl1U-MLW.js` / `index-BNxrRaU7.css`.
- **19 production tests PASS**: API, MCP, desktop и release contract. Новые проверки покрывают все шесть типов, optional section, запрет invalid/null, status-only сохранение типа, optimistic/idempotency и конкурентное создание одной служебной группы.
- Независимый general browser smoke **11 групп PASS**: fresh project → typed task без раздела, edit/type before-after, reload/export, прежние evidence/conflict/changes/mobile/keyboard/connectors, native dropdown и edit cancel/save focus.
- Независимый Kanban smoke **10 групп PASS**: type filter, native drag, доступное перемещение с причиной, cancel/evidence gate, потеря успешного ответа с одним audit при retry, concurrent PATCH с сохранением чужих полей, focus, mobile 390/320, legacy fixture. Page errors отсутствуют; desktop пять колонок помещаются без page overflow. Root дополнительно просмотрел desktop и mobile 320 screenshots.
- Legacy fixture без task_type отображается как «Другое» после reload; IDs, FK, notes и export сохранены. Сырые task/note/event строки SQLite побайтово прежние. Отдельный API test сохраняет все семь таблиц и credentials после restart/read/export и повторов старых cached create/patch запросов. Read fallback не меняет исторические payload.
- Исходная рабочая база перед restart 4242 сохранена через SQLite backup: `data/backups/task-types-before-2026-10-04.sqlite3`, integrity check **ok**. Другие сервисы не перезапускались.

Открытых runtime замечаний независимой проверки нет. Подробности: [task types review](reviews/task-types-review.md), [Ponytail review](reviews/task-types-ponytail-review.md). Новых dependencies и новой схемы SQLite нет; прежние section API/MCP оставлены для совместимости. Установщик и опубликованный канал проверяются отдельно ниже по фактическому выпуску.

Начальная локальная полная PyInstaller/Inno сборка **PASS**: `Agentboard-Setup-1.3.0.exe`, **22 428 683 bytes**, SHA-256 `1cef3056eebabba49efd871c823c722ff6422faa1410d797905e3142761bf213`. Windowed API EXE и console MCP EXE пересобраны; личные данные и настройки подключения не включены. Bundled HTTPS feed и public key прежние. Настоящий **frozen smoke PASS**: версия 1.3.0, отдельные personal data, HTTP UI/API, project configs для двух клиентов, реальный stdio MCP создает testing карточку без раздела и legacy-карточку с section_id/default other. Release signature/tamper/size/hash contract test **PASS**. Проверка не запускала installer на рабочем профиле пользователя.

Дополнительный независимый native-dropdown проход при 1440/390/320 px выявил потерю фокуса на BODY после отмены edit-form. Stable ref существующей кнопки заголовка и общий finishEdit возвращают фокус до удаления формы; отмена и успешное сохранение используют тот же путь. Повторный native проход на финальном frontend **PASS**: Alt+ArrowDown/Escape сохраняет dropdown/dialog, Tab остается внутри, отмена возвращает фокус на кнопку редактирования. Тестовая проверка не отправляла POST/PATCH в рабочую базу. Четыре неиспользуемых CSS-блока task-rationale удалены по Ponytail finding. Результат: `artifacts/qa/task-types-native-focus.json`.

После focus/CSS исправления выполнена финальная полная freeze/Inno сборка: **22 428 542 bytes**, SHA-256 `d6d325fcc437f25e3a4c8f0c4361f262c8236d0be852b25b284eb346fe8aeb76`. Ресурсы побайтово совпадают с финальным dist, лишних старых JS нет. Повторный **frozen smoke PASS** дополнительно сравнивает весь HTTP index с bundled index.html. Независимые **11 UI + 10 Kanban групп PASS** на финальном frontend, включая retained focus/cancel/save проверки при 1440/390/320; отмена не меняет task и audit. Backend suite не повторялся ради frontend-only исправления.
