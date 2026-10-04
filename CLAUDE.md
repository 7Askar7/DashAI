# DashAI

Следуй `AGENTS.md` и `docs/architecture.md`. Используй локальные Ponytail skills `.claude/skills/ponytail/SKILL.md` и `.claude/skills/ponytail-review/SKILL.md`.

В проекте есть MCP `agentboard`: list_projects → get_board → create_task → claim_task → add_note (progress/decision/evidence) → update_task (review/done). Обязательны rationale, reason и актуальная version. Объясняй что изменено и почему, прикладывай подтверждение проверок. Не утверждай что результат проверен без evidence. При конфликте перечитай задачу. Не записывай секреты и скрытые рассуждения модели.

Создавай карточку сразу в проекте без section_id. Выбери task_type: research, development, testing, bugfix, documentation или other. Общая доска группируется по статусам; тип работы виден на карточке и меняется через update_task с reason.

Для параллельных чатов выбирай необязательный subproject_id из get_board. Создавай вложенные направления через create_subproject с parent_id; update_subproject требует свежую expected_version. Все подпроекты остаются на общей Kanban. Подробный контракт — docs/connectors.md.
