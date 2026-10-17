"""Optional project features and reusable Markdown modules; no executable plugins."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA = """
CREATE TABLE IF NOT EXISTS module_templates (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_modules (project_id TEXT NOT NULL REFERENCES projects(id), module_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id,module_id));
"""

BUILTINS = [
    {"id": "map", "name": "Карта проекта", "description": "Дерево файлов с описаниями, поиском и проверкой актуальности.", "kind": "feature", "default_enabled": True},
    {"id": "architecture", "name": "Архитектура", "description": "Схемы системы в разных нотациях и связи с исходниками.", "kind": "feature", "default_enabled": True},
    {"id": "documentation", "name": "Документация", "description": "Сборка и экспорт описаний проекта в единый документ.", "kind": "feature", "default_enabled": True},
    {"id": "integrations", "name": "Confluence и Jira", "description": "Публикация знаний в выбранный внешний проект. Требует подключения.", "kind": "feature", "default_enabled": False},
    {"id": "decisions", "name": "Архитектурные решения", "description": "Контекст, варианты и последствия принятых решений (ADR).", "kind": "document", "default_enabled": False, "template": "# Архитектурные решения\n\n## Решение\n\nСтатус: предложено\n\n### Контекст\n\n### Рассмотренные варианты\n\n### Выбранное решение и причина\n\n### Последствия\n\n### Проверка и связанные задачи\n"},
    {"id": "risks", "name": "Риски и ограничения", "description": "Что может помешать проекту, кто отвечает и как проверить снижение риска.", "kind": "document", "default_enabled": False, "template": "# Риски и ограничения\n\n## Риск\n\n### Вероятность и влияние\n\n### Причина и признаки\n\n### Действия и ответственный\n\n### Срок и проверка результата\n"},
    {"id": "runbook", "name": "Запуск и эксплуатация", "description": "Подготовка окружения, запуск, проверки и восстановление.", "kind": "document", "default_enabled": False, "template": "# Запуск и эксплуатация\n\n## Требования и подготовка\n\n## Запуск\n\n## Проверка работоспособности\n\n## Диагностика\n\n## Восстановление и откат\n"},
]


def catalog(db, summary=False):
    column = "json_remove(payload,'$.template')" if summary else "payload"
    builtins = [{key: value for key, value in item.items() if not summary or key != "template"} for item in BUILTINS]
    return builtins + [json.loads(row[0]) for row in db.execute(f"SELECT {column} FROM module_templates ORDER BY rowid")]


def project_modules(db, project_id, summary=False):
    column = "json_remove(payload,'$.content')" if summary else "payload"
    stored = {row[0]: json.loads(row[1]) for row in db.execute(f"SELECT module_id,{column} FROM project_modules WHERE project_id=?", (project_id,))}
    return [{**definition, "module_id": definition["id"], "title": definition["name"],
             "enabled": definition["default_enabled"], "version": 0,
             **({} if summary else {"content": definition.get("template", "")}),
             **stored.get(definition["id"], {})} for definition in catalog(db, summary)]


def enabled(db, project_id, module_id):
    row = db.execute("SELECT payload FROM project_modules WHERE project_id=? AND module_id=?", (project_id, module_id)).fetchone()
    if row:
        return json.loads(row[0])["enabled"]
    return next((item["default_enabled"] for item in BUILTINS if item["id"] == module_id), False)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Write(Model):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None


class TemplateWrite(Write):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: Annotated[str, StringConstraints(max_length=3000)] = ""
    template: Annotated[str, StringConstraints(max_length=100000)] = ""


class ModuleWrite(Write):
    expected_version: int = Field(ge=0)
    enabled: bool
    content: Annotated[str, StringConstraints(max_length=200000)] | None = None


def install_routes(app, store, actor, authenticated_read, session):
    @app.get("/api/modules", dependencies=[Depends(authenticated_read)])
    def get_catalog():
        with store.connect() as db:
            return {"modules": catalog(db)}

    @app.post("/api/modules")
    def create_template(body: TemplateWrite, request: Request, who=Depends(actor)):
        def operation(db):
            if db.execute("SELECT COUNT(*) FROM module_templates").fetchone()[0] >= 100:
                raise HTTPException(422, "В каталоге уже 100 пользовательских модулей")
            item = {"id": str(uuid4()), "name": body.name, "description": body.description,
                    "template": body.template, "kind": "document", "default_enabled": False,
                    "created_at": datetime.now(timezone.utc).isoformat()}
            db.execute("INSERT INTO module_templates VALUES (?,?)", (item["id"], json.dumps(item, ensure_ascii=False)))
            store.record(db, who, body.reason, "module_template", item["id"], "module_template.created", None,
                         {key: value for key, value in item.items() if key != "template"}, session_id=session(request))
            return item
        return store.write(who, "/api/modules", body, operation)

    @app.get("/api/projects/{project_id}/modules", dependencies=[Depends(authenticated_read)])
    def get_modules(project_id: str):
        with store.connect() as db:
            db.execute("BEGIN")
            store.entity(db, "projects", project_id)
            return {"modules": project_modules(db, project_id)}

    @app.put("/api/projects/{project_id}/modules/{module_id}")
    def configure(project_id: str, module_id: str, body: ModuleWrite, request: Request, who=Depends(actor)):
        def operation(db):
            store.entity(db, "projects", project_id)
            before = next((item for item in project_modules(db, project_id) if item["id"] == module_id), None)
            if before is None:
                raise HTTPException(404, "Модуль не найден в каталоге")
            if body.expected_version != before["version"]:
                raise HTTPException(409, "Модуль изменён. Перечитайте его и подтвердите действие снова")
            if before["kind"] == "feature" and body.content is not None:
                raise HTTPException(422, "Текст доступен только документным модулям")
            after = {"enabled": body.enabled, "version": before["version"] + 1,
                     "content": before["content"] if body.content is None else body.content,
                     "updated_at": datetime.now(timezone.utc).isoformat()}
            db.execute("INSERT INTO project_modules VALUES (?,?,?) ON CONFLICT(project_id,module_id) DO UPDATE SET payload=excluded.payload",
                       (project_id, module_id, json.dumps(after, ensure_ascii=False)))
            # The content is local project data; audit records exactly what was saved.
            old = {key: before[key] for key in ("enabled", "version", "content")}
            store.record(db, who, body.reason, "project_module", module_id, "project_module.updated", old, after,
                         project_id=project_id, session_id=session(request))
            return {**before, **after}
        return store.write(who, f"/api/projects/{project_id}/modules/{module_id}", body, operation)
