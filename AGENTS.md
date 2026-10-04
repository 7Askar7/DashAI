# Работа над Agentboard

Для coding tasks применяй Ponytail full: `.agents/skills/ponytail/SKILL.md`. Перед завершением — отдельный review по `.agents/skills/ponytail-review/SKILL.md`. Upstream: https://github.com/DietrichGebert/ponytail, commit c982cd411abb53323c4baa1baa3c2f020b8d0b08, MIT. Не сокращай validation, data safety, security или accessibility ради размера кода.

Сначала прочитай `docs/architecture.md` и исследования `docs/research/`. Не добавляй runtime моделей, speculative abstractions и зависимости без конкретной необходимости. Domain behavior общий для UI и MCP. Изменение данных и audit event атомарны. Никогда не выдавай demo data или наличие конфига за реальное подключение агента.

Когда MCP `agentboard` доступен: найди проект через `list_projects`, прочитай `get_board`/`get_task`, создай задачу с rationale и acceptance criteria, возьми ее через `claim_task`. После существенной правки вызови `log_change`: summary, files, reason, diff/commit и verification; решения объясни note/decision. Приложи evidence проверки; переведи в review, затем done после проверки. Перед update перечитай version. На conflict перечитай состояние, не повторяй старый overwrite. Reason — описание причины, не скрытые рассуждения модели. Не помещай ключи, пароли и личные данные в историю.

Для новой задачи укажи `project_id` и `task_type`: `research`, `development`, `testing`, `bugfix`, `documentation` или `other`. Создавать раздел не требуется. Все карточки проекта находятся на общей доске по статусам; тип работы не заменяет статус. Старые section-инструменты сохранены для совместимости.

Запуск и проверки смотри в README.md. `data/` и локальные credentials не коммитить. Коннектор обращается к HTTP API; ему запрещено создавать отдельную копию project store.
