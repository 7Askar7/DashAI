# Agentboard

Следуй `AGENTS.md` и `docs/architecture.md`. Используй локальные Ponytail skills `.claude/skills/ponytail/SKILL.md` и `.claude/skills/ponytail-review/SKILL.md`.

В проекте есть MCP `agentboard`: list_projects → get_board → create_task → claim_task → add_note (progress/decision/evidence) → update_task (review/done). Обязательны rationale, reason и актуальная version. Объясняй что изменено и почему, прикладывай подтверждение проверок. Не утверждай что результат проверен без evidence. При конфликте перечитай задачу. Не записывай секреты и скрытые рассуждения модели.
