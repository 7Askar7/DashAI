# Ссылки на задачи и восстановление пространства — 18.10.2026

Реализован пункт 9 [UX-исследования](../research/08-user-needs-ux-audit.md): при возвращении пользователю не нужно заново выбирать проект, вкладку, доску/список и фильтры. Открытая карточка также восстанавливается. В карточке появилась кнопка копирования ссылки; явный `?task=<UUID>` имеет приоритет над сохранённой задачей и выбирает её настоящий проект. Неверная или отсутствующая задача показывает закрываемую ошибку с повторной попыткой.

## Реализация и границы

- `src/workspace.ts`, `src/main.tsx`, `src/App.tsx`, `src/styles.css`: проверяемый снимок навигации, загрузка до монтирования App, настройки каждого проекта, ссылки и обратимая навигация через History API. Нет новых зависимостей или router framework.
- `src/host.ts`, `vscode-extension/extension.cjs`: существующий origin-checked bridge читает/пишет фиксированный `dashai.workspace.v1` в globalState; строгая схема, до 100 КБ, без Settings Sync. Browser fallback использует localStorage с видимым сообщением об ошибке.
- `scripts/workspace_navigation_smoke.py`, тесты расширения и документация фиксируют проверяемый контракт. Тексты форм, заметки, credentials и данные задач не входят в настройки. Навигация не пишет domain/audit events.
- Скопированная ссылка относится к текущему локальному серверу и порту. Browser storage принадлежит origin; хранилище расширения переживает смену порта. Именованные виды, облачные ссылки и синхронизация между устройствами не реализованы.

## Проверка

- `npm run build`: PASS, TypeScript и Vite. Финальная браузерная сборка `index-n9d-F9rG.js`. Прежние предупреждения lucide `use client` и крупных Mermaid/ELK chunks остаются.
- `node scripts/python.mjs scripts/workspace_navigation_smoke.py`: PASS, 8 групп, `page_errors: []`. Все фильтры и открытая задача после reload; разные вкладки/настройки проектов; приоритет ссылки; настоящий clipboard без host/query/hash-параметров; ошибки ссылок; Back/Forward; отклонённый Back после reload; Back во время сохранения заметки; повреждённое и недоступное хранилище.
- Финальные `scripts/task_draft_smoke.py`: 6 групп PASS; `npm run test:ui`: 13 проверок PASS. `scripts/ux_board_smoke.py`: 6 групп PASS на предыдущей сборке этой итерации, до исправления двух выявленных гонок восстановления; эти гонки отдельно покрыты финальным navigation smoke.
- `npm --prefix vscode-extension test`: 15/15 PASS, включая схему/размер JSON, roundtrip, отсутствие overwrite при ошибке, сбой storage и прежнюю проверку origin/source/CSP.
- Реальный VS Code 1.142.0, изолированные installation/profile/data: PASS для origin, начального `null`, object/boolean roundtrip через `host.ts`, отклонения неверной версии без overwrite и сохранения после закрытия/повторного создания панели. Проверены свежие `extension.cjs` и транспилированный `src/host.ts` внутри настоящего iframe; native bundle и остальной UI взяты из прежнего Marketplace 1.7.0 VSIX. Полный новый UI подтверждён браузерными тестами, не этой проверкой расширения. Профиль и clipboard пользователя не затрагивались. Evidence: `artifacts/qa/vscode-actual-8df9e7c184/results.json`; `actual-driver.cjs` дополнен изолированным режимом и командой повторного открытия панели.
- Desktop 1440 px и mobile 390 px снимки новой кнопки просмотрены; переполнений и перекрытий не обнаружено. Draft regression дополнительно проверяет 320 px. Это не тест на физическом телефоне.

Все browser-сценарии работают на временной SQLite, изолированном API и production UI. Задержка bootstrap/записи, запрещённый storage и один ответ 503 в draft regression — намеренные fault injections. Личные данные не используются. Артефакты: `artifacts/qa/workspace-navigation/results.json`, `task-link-{1440,390}.png`, `artifacts/qa/task-drafts/evidence.json`, `artifacts/qa/ui-results.json`.

Локальный runner настоящего VS Code: `node scripts/python.mjs artifacts/qa/host-persistence-run.py`; требует установленный VS Code и существующий `DashAI-Marketplace-1.7.0-win32-x64.vsix`. Runner и изолированные профили находятся в игнорируемых QA-артефактах, не входят в поставку. Финальные `git diff --check` и синтаксическая проверка driver проходят.

## Отдельный review

Независимый correctness review выявил две ошибки: сброс индекса History при reload приводил к неверному возврату после отменённого Back; ранняя карточка при задержанном bootstrap очищала сохранённого исполнителя. Обе исправлены и воспроизведены отдельными regression-сценариями. После исправления блокирующих замечаний не осталось. Отдельный Ponytail-review: **Lean already. Ship.**

Рабочее дерево содержит более ранние изменения; они сохранены. Backend/domain в этой итерации не менялись. MCP agentboard возвращал HTTP 401 (`invalid agent token`), поэтому задача и evidence не записаны в реальную доску; credentials для обхода ошибки не читались. Публикация и обновление установленного пользовательского расширения не выполнялись.
