from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ROOT = Path(__file__).resolve().parents[1]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Description = Annotated[str, StringConstraints(max_length=50000)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200000)]
Key = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Status = Literal["backlog", "in_progress", "review", "done", "blocked"]
Priority = Literal["urgent", "high", "medium", "low"]
TaskType = Literal["research", "development", "testing", "bugfix", "documentation", "other"]
NoteKind = Literal["progress", "decision", "evidence", "comment"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Write(StrictModel):
    reason: Reason
    idempotency_key: Key | None = None


class ProjectCreate(Write):
    name: Text
    description: Description = ""
    repository: Annotated[str, StringConstraints(max_length=2048)] = ""
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")] = "#7c8aff"


class ProjectChanges(StrictModel):
    name: Text | None = None
    description: Description | None = None
    repository: Annotated[str, StringConstraints(max_length=2048)] | None = None
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None


class SectionCreate(Write):
    title: Text
    description: Description = ""


class SectionChanges(StrictModel):
    title: Text | None = None
    description: Description | None = None


class SubprojectCreate(SectionCreate):
    parent_id: Identifier | None = None


class SubprojectChanges(SectionChanges):
    parent_id: Identifier | None = None


class TaskCreate(Write):
    project_id: Identifier
    section_id: Identifier | None = None
    subproject_id: Identifier | None = None
    title: Text
    description: Description = ""
    rationale: Reason
    acceptance_criteria: Description = ""
    priority: Priority = "medium"
    task_type: TaskType = "other"
    assignee_id: Identifier | None = None
    depends_on: list[Identifier] = Field(default_factory=list, max_length=128)


class TaskChanges(StrictModel):
    title: Text | None = None
    description: Description | None = None
    rationale: Reason | None = None
    acceptance_criteria: Description | None = None
    status: Status | None = None
    priority: Priority | None = None
    task_type: TaskType | None = None
    assignee_id: Identifier | None = None
    section_id: Identifier | None = None
    subproject_id: Identifier | None = None
    depends_on: list[Identifier] | None = Field(default=None, max_length=128)


class Patch(Write):
    expected_version: int = Field(ge=1)


class ProjectPatch(Patch):
    changes: ProjectChanges


class SectionPatch(Patch):
    changes: SectionChanges


class SubprojectPatch(Patch):
    changes: SubprojectChanges


class TaskPatch(Patch):
    changes: TaskChanges


class Claim(Patch):
    lease_seconds: int = Field(default=3600, ge=30, le=86400)


class NoteCreate(Write):
    kind: NoteKind
    body: Body


class ChangeCreate(Write):
    summary: Body
    files: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]] = Field(min_length=1, max_length=200)
    diff: Annotated[str, StringConstraints(max_length=200000)] | None = None
    commit: Annotated[str, StringConstraints(max_length=2048)] | None = None
    verification: Annotated[str, StringConstraints(max_length=50000)] | None = None


class AgentCreate(Write):
    name: Text
    kind: Literal["codex", "claude"]


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sections (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), section_id TEXT NOT NULL REFERENCES sections(id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, token_hash TEXT UNIQUE, last_seen TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT REFERENCES projects(id), task_id TEXT REFERENCES tasks(id), entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES agents(id), actor_name TEXT NOT NULL, actor_kind TEXT NOT NULL, reason TEXT NOT NULL, before_json TEXT, after_json TEXT, created_at TEXT NOT NULL, session_id TEXT);
CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), project_id TEXT NOT NULL REFERENCES projects(id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency (actor_id TEXT NOT NULL REFERENCES agents(id), scope TEXT NOT NULL, key TEXT NOT NULL, request TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(actor_id,scope,key));
CREATE INDEX IF NOT EXISTS sections_project ON sections(project_id);
CREATE INDEX IF NOT EXISTS tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS notes_task ON notes(task_id);
CREATE INDEX IF NOT EXISTS events_project ON events(project_id,id);
CREATE INDEX IF NOT EXISTS events_task ON events(task_id,id);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END;
"""


class Store:
    """SQLite serializes writers; every write includes its audit event."""

    def __init__(self, data_dir: Path, base_url: str):
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "agentboard.sqlite3"
        self.credentials_file = self.data_dir / "connector-secrets.json"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        issued = {}
        with self.transaction() as db:
            for agent_id, name, kind in [("human", "Вы", "human"), ("codex", "Codex", "codex"), ("claude", "Claude Code", "claude")]:
                if not db.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
                    token = secrets.token_urlsafe(32) if kind != "human" else None
                    db.execute("INSERT INTO agents VALUES (?,?,?,?,?,?)", (agent_id, name, kind, self.hash(token) if token else None, None, now()))
                    if token:
                        issued[agent_id] = {"id": agent_id, "token": token}
            if issued or self.credentials_file.exists():
                # ponytail: local OS-user trust boundary; no hosted secret management.
                content = json.loads(self.credentials_file.read_text(encoding="utf-8")) if self.credentials_file.exists() else {"schema_version": 1, "agents": {}}
                if issued or content.get("base_url") != base_url:
                    content["base_url"] = base_url
                    content["agents"].update(issued)
                    temporary = self.credentials_file.with_suffix(".tmp")
                    temporary.write_text(encode(content) + "\n", encoding="utf-8")
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, self.credentials_file)

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def payload(table, value):
        result = json.loads(value)
        if table == "tasks":
            result.setdefault("task_type", "other")
            result.setdefault("subproject_id", None)
        return result

    @staticmethod
    def entity(db, table, entity_id):
        row = db.execute(f"SELECT payload FROM {table} WHERE id=?", (entity_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Объект не найден")
        return Store.payload(table, row["payload"])

    @staticmethod
    def entities(db, table, where="", args=()):
        return [Store.payload(table, row["payload"]) for row in db.execute(f"SELECT payload FROM {table} {where} ORDER BY rowid", args)]

    @staticmethod
    def agents(db):
        return [dict(row) for row in db.execute("SELECT id,name,kind,last_seen,created_at FROM agents ORDER BY created_at,id")]

    @staticmethod
    def event(row):
        event = dict(row)
        for field in ("before", "after"):
            value = event.pop(field + "_json")
            event[field] = json.loads(value) if value is not None else None
        return event

    @classmethod
    def events(cls, db, where="", args=(), tail: int | None = None):
        query = f"SELECT * FROM events {where} ORDER BY id DESC"
        if tail:
            query += " LIMIT ?"
            args = (*args, tail)
        return [cls.event(row) for row in db.execute(query, args)]

    @staticmethod
    def record(db, actor, reason, entity_type, entity_id, action, before, after, project_id=None, task_id=None, session_id=None):
        db.execute("INSERT INTO events(project_id,task_id,entity_type,entity_id,action,actor_id,actor_name,actor_kind,reason,before_json,after_json,created_at,session_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (project_id, task_id, entity_type, entity_id, action, actor["id"], actor["name"], actor["kind"], reason, encode(before) if before is not None else None, encode(after) if after is not None else None, now(), session_id))

    def write(self, actor, scope, model, operation):
        payload = model.model_dump(exclude={"idempotency_key"})
        if isinstance(model, TaskPatch) and "subproject_id" not in model.changes.model_fields_set:
            payload["changes"].pop("subproject_id", None)
        elif isinstance(model, SubprojectPatch):
            payload["changes"] = model.changes.model_dump(exclude_unset=True)
        with self.transaction() as db:
            if model.idempotency_key:
                old = db.execute("SELECT request,response FROM idempotency WHERE actor_id=? AND scope=? AND key=?", (actor["id"], scope, model.idempotency_key)).fetchone()
                if old:
                    previous = json.loads(old["request"])
                    if scope == "/api/tasks":
                        previous.setdefault("task_type", "other")
                        previous.setdefault("section_id", None)
                        previous.setdefault("subproject_id", None)
                    elif isinstance(model, TaskPatch):
                        previous["changes"].setdefault("task_type", None)
                    if encode(previous) != encode(payload):
                        raise HTTPException(409, "Этот idempotency_key уже использован с другим содержимым")
                    result = json.loads(old["response"])
                    if "section_id" in result and "status" in result:
                        result.setdefault("task_type", "other")
                        result.setdefault("subproject_id", None)
                    return result
            result = operation(db)
            if model.idempotency_key:
                db.execute("INSERT INTO idempotency VALUES (?,?,?,?,?)", (actor["id"], scope, model.idempotency_key, encode(payload), encode(result)))
            return result


def check_version(entity, version):
    if entity["version"] != version:
        raise HTTPException(409, "Объект уже изменен. Перечитайте актуальную версию и повторите намерение")


def check_claim(task, actor):
    owner = task["claim_owner_id"]
    if owner and task["claim_expires_at"] > now() and owner != actor["id"] and actor["kind"] != "human":
        raise HTTPException(409, "Задача занята другим агентом. Дождитесь завершения аренды или вмешательства человека")


def subproject_entity(db, subproject_id, project_id=None):
    item = Store.entity(db, "sections", subproject_id)
    if item.get("kind") != "subproject" or (project_id is not None and item["project_id"] != project_id):
        raise HTTPException(422, "Подпроект должен быть существующим подпроектом этого проекта")
    return item


def validate_subproject(db, item):
    visited = {item["id"]}
    parent_id = item["parent_id"]
    while parent_id is not None:
        if parent_id in visited:
            raise HTTPException(422, "Подпроекты не могут образовывать цикл")
        visited.add(parent_id)
        parent_id = subproject_entity(db, parent_id, item["project_id"])["parent_id"]


def validate_task(db, task):
    section = Store.entity(db, "sections", task["section_id"])
    if section["project_id"] != task["project_id"]:
        raise HTTPException(422, "Раздел должен принадлежать проекту задачи")
    if section.get("kind") == "subproject":
        raise HTTPException(422, "Для принадлежности подпроекту используйте subproject_id")
    if task.get("subproject_id") is not None:
        subproject_entity(db, task["subproject_id"], task["project_id"])
    if task["assignee_id"] and not db.execute("SELECT 1 FROM agents WHERE id=?", (task["assignee_id"],)).fetchone():
        raise HTTPException(422, "Исполнитель не найден")
    dependencies = task["depends_on"]
    if len(dependencies) != len(set(dependencies)):
        raise HTTPException(422, "Зависимости не должны повторяться")
    graph = {item["id"]: item for item in Store.entities(db, "tasks", "WHERE project_id=?", (task["project_id"],))}
    graph[task["id"]] = task
    for dependency in dependencies:
        if dependency not in graph:
            raise HTTPException(422, "Зависимость должна быть существующей задачей этого проекта")
        visited, pending = set(), [dependency]
        while pending:
            current = pending.pop()
            if current == task["id"]:
                raise HTTPException(422, "Зависимости не могут образовывать цикл")
            if current not in visited:
                visited.add(current)
                pending.extend(graph[current]["depends_on"])
    if task["status"] in {"in_progress", "review", "done"} and any(graph[dependency]["status"] != "done" for dependency in dependencies):
        raise HTTPException(409, "Сначала завершите блокирующие задачи")
    if task["status"] != "done" and any(task["id"] in item["depends_on"] and item["status"] in {"in_progress", "review", "done"} for item in graph.values() if item["id"] != task["id"]):
        raise HTTPException(409, "Сначала верните активные зависимые задачи в планирование или блокировку")
    if task["status"] == "done":
        if not task["acceptance_criteria"].strip():
            raise HTTPException(422, "Для завершения укажите критерии приемки")
        evidence = Store.entities(db, "notes", "WHERE task_id=?", (task["id"],))
        if not any(note["kind"] == "evidence" for note in evidence):
            raise HTTPException(422, "Для завершения добавьте свидетельство проверки (evidence)")


def changes_dict(model):
    changes = model.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Укажите хотя бы одно изменяемое поле")
    if any(value is None for key, value in changes.items() if key not in {"assignee_id", "subproject_id", "parent_id"}):
        raise HTTPException(422, "Пустое значение разрешено только для исполнителя, подпроекта или его родителя")
    return changes


def create_app(data_dir: str | Path = ROOT / "data", seed_demo: bool = False, base_url: str = "http://127.0.0.1:4242") -> FastAPI:
    store = Store(Path(data_dir), base_url)
    app = FastAPI(title="DashAI", version=json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"])
    app.state.store = store

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, error):
        locations = ", ".join(".".join(str(part) for part in item["loc"]) for item in error.errors())
        return JSONResponse(status_code=422, content={"detail": f"Некорректные поля запроса: {locations}"})

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        try:
            host = urlsplit("http://" + request.headers.get("host", ""))
            valid_host = host.hostname in {"127.0.0.1", "localhost", "::1"} and not host.username and not host.password and not host.path and not host.query and not host.fragment
            host_port = host.port
        except ValueError:
            valid_host = False
        if not valid_host:
            return JSONResponse(status_code=403, content={"detail": "Разрешен только локальный Host"})
        origin = request.headers.get("origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                same_port = parsed.port == host_port
                allowed = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and (same_port or parsed.port == 5173) and not parsed.username and not parsed.password and parsed.path == "" and not parsed.query and not parsed.fragment
            except ValueError:
                allowed = False
            if not allowed:
                return JSONResponse(status_code=403, content={"detail": "Этот Origin не имеет доступа к локальному dashboard"})
        if getattr(app.state, "desktop", None) and request.url.path.startswith("/api/"):
            app.state.last_activity = time.monotonic()
        return await call_next(request)

    def actor(request: Request):
        authorization = request.headers.get("authorization")
        with store.transaction() as db:
            if authorization:
                if not authorization.startswith("Bearer "):
                    raise HTTPException(401, "Требуется Bearer token")
                token = authorization[7:]
                record = db.execute("SELECT * FROM agents WHERE token_hash=?", (store.hash(token),)).fetchone()
                if not record:
                    raise HTTPException(401, "Неверный токен агента")
                record = dict(record)
                db.execute("UPDATE agents SET last_seen=? WHERE id=?", (now(), record["id"]))
            elif request.headers.get("x-dashboard-client") == "browser":
                record = dict(db.execute("SELECT * FROM agents WHERE id='human'").fetchone())
            else:
                raise HTTPException(401, "Для записи требуется коннектор агента или локальный dashboard")
        record.pop("token_hash", None)
        return record

    def authenticated_read(request: Request):
        if request.headers.get("authorization"):
            actor(request)

    def session(request: Request):
        value = request.headers.get("x-session-id")
        if value and len(value) > 200:
            raise HTTPException(422, "X-Session-ID не должен превышать 200 символов")
        return value

    @app.get("/api/health")
    def health():
        desktop = getattr(app.state, "desktop", None)
        return {"status": "ok", **desktop, "mcp_running": bool(app.state.mcp_running())} if desktop else {"status": "ok"}

    @app.post("/api/desktop/stop")
    def stop_desktop(request: Request):
        desktop = getattr(app.state, "desktop", None)
        if not desktop or desktop["mode"] != "vscode":
            raise HTTPException(404, "Остановка доступна только для режима VS Code")
        if request.headers.get("x-agentboard-instance") != desktop["instance_id"]:
            raise HTTPException(403, "Не совпадает экземпляр DashAI")
        if app.state.mcp_running():
            raise HTTPException(409, "Сначала закройте активные MCP-соединения")
        app.state.shutdown_requested = True
        return {"status": "stopping"}

    @app.get("/api/bootstrap", dependencies=[Depends(authenticated_read)])
    def bootstrap():
        with store.connect() as db:
            db.execute("BEGIN")
            return {"projects": store.entities(db, "projects"), "agents": store.agents(db), "activity": store.events(db, tail=50)}

    @app.get("/api/projects/{project_id}", dependencies=[Depends(authenticated_read)])
    def board(project_id: str):
        with store.connect() as db:
            db.execute("BEGIN")
            project = store.entity(db, "projects", project_id)
            sections = store.entities(db, "sections", "WHERE project_id=?", (project_id,))
            return {"project": project, "sections": [item for item in sections if item.get("kind") != "subproject"], "subprojects": [item for item in sections if item.get("kind") == "subproject"], "tasks": store.entities(db, "tasks", "WHERE project_id=?", (project_id,)), "activity": store.events(db, "WHERE project_id=?", (project_id,), tail=100)}

    @app.post("/api/projects")
    def create_project(body: ProjectCreate, request: Request, who=Depends(actor)):
        session_id = session(request)
        def operation(db):
            project = {"id": str(uuid4()), **body.model_dump(exclude={"reason", "idempotency_key"}), "version": 1, "created_at": now(), "updated_at": now()}
            db.execute("INSERT INTO projects VALUES (?,?)", (project["id"], encode(project)))
            store.record(db, who, body.reason, "project", project["id"], "project.created", None, project, project_id=project["id"], session_id=session_id)
            return project
        return store.write(who, "/api/projects", body, operation)

    def edit_container(table, entity_type, entity_id, body, who, session_id):
        changes = changes_dict(body.changes)
        def operation(db):
            before = store.entity(db, table, entity_id)
            if entity_type == "section" and before.get("kind") == "subproject":
                raise HTTPException(422, "Изменяйте подпроект через /api/subprojects")
            check_version(before, body.expected_version)
            after = {**before, **changes, "version": before["version"] + 1, "updated_at": now()}
            db.execute(f"UPDATE {table} SET payload=? WHERE id=?", (encode(after), entity_id))
            store.record(db, who, body.reason, entity_type, entity_id, entity_type + ".updated", before, after, project_id=before.get("project_id", entity_id), session_id=session_id)
            return after
        return store.write(who, f"/api/{table}/{entity_id}", body, operation)

    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, body: ProjectPatch, request: Request, who=Depends(actor)):
        return edit_container("projects", "project", project_id, body, who, session(request))

    @app.post("/api/projects/{project_id}/sections")
    def create_section(project_id: str, body: SectionCreate, request: Request, who=Depends(actor)):
        session_id = session(request)
        def operation(db):
            store.entity(db, "projects", project_id)
            position = db.execute("SELECT count(*) FROM sections WHERE project_id=?", (project_id,)).fetchone()[0]
            section = {"id": str(uuid4()), "project_id": project_id, "title": body.title, "description": body.description, "position": position, "version": 1, "created_at": now(), "updated_at": now()}
            db.execute("INSERT INTO sections VALUES (?,?,?)", (section["id"], project_id, encode(section)))
            store.record(db, who, body.reason, "section", section["id"], "section.created", None, section, project_id=project_id, session_id=session_id)
            return section
        return store.write(who, f"/api/projects/{project_id}/sections", body, operation)

    @app.patch("/api/sections/{section_id}")
    def update_section(section_id: str, body: SectionPatch, request: Request, who=Depends(actor)):
        return edit_container("sections", "section", section_id, body, who, session(request))


    @app.post("/api/projects/{project_id}/subprojects")
    def create_subproject(project_id: str, body: SubprojectCreate, request: Request, who=Depends(actor)):
        session_id = session(request)
        def operation(db):
            store.entity(db, "projects", project_id)
            item = {"id": str(uuid4()), "project_id": project_id, "kind": "subproject", **body.model_dump(exclude={"reason", "idempotency_key"}), "version": 1, "created_at": now(), "updated_at": now()}
            validate_subproject(db, item)
            db.execute("INSERT INTO sections VALUES (?,?,?)", (item["id"], project_id, encode(item)))
            store.record(db, who, body.reason, "subproject", item["id"], "subproject.created", None, item, project_id=project_id, session_id=session_id)
            return item
        return store.write(who, f"/api/projects/{project_id}/subprojects", body, operation)

    @app.patch("/api/subprojects/{subproject_id}")
    def update_subproject(subproject_id: str, body: SubprojectPatch, request: Request, who=Depends(actor)):
        session_id = session(request)
        changes = changes_dict(body.changes)
        def operation(db):
            before = subproject_entity(db, subproject_id)
            check_version(before, body.expected_version)
            after = {**before, **changes, "version": before["version"] + 1, "updated_at": now()}
            validate_subproject(db, after)
            db.execute("UPDATE sections SET payload=? WHERE id=?", (encode(after), subproject_id))
            store.record(db, who, body.reason, "subproject", subproject_id, "subproject.updated", before, after, project_id=before["project_id"], session_id=session_id)
            return after
        return store.write(who, f"/api/subprojects/{subproject_id}", body, operation)
    @app.post("/api/tasks")
    def create_task(body: TaskCreate, request: Request, who=Depends(actor)):
        session_id = session(request)
        def operation(db):
            store.entity(db, "projects", body.project_id)
            section_id = body.section_id
            if section_id is None:
                section_id = "project-board:" + body.project_id
                if not db.execute("SELECT 1 FROM sections WHERE id=?", (section_id,)).fetchone():
                    position = db.execute("SELECT count(*) FROM sections WHERE project_id=?", (body.project_id,)).fetchone()[0]
                    section = {"id": section_id, "project_id": body.project_id, "title": "Общая доска", "description": "Служебная группа задач общей доски проекта", "position": position, "version": 1, "is_default": True, "created_at": now(), "updated_at": now()}
                    db.execute("INSERT INTO sections VALUES (?,?,?)", (section_id, body.project_id, encode(section)))
                    store.record(db, who, body.reason, "section", section_id, "section.created", None, section, project_id=body.project_id, session_id=session_id)
            number = db.execute("SELECT count(*) FROM tasks").fetchone()[0] + 1
            task = {"id": str(uuid4()), "short_id": f"AD-{number:03d}", **body.model_dump(exclude={"reason", "idempotency_key"}), "section_id": section_id, "status": "backlog", "version": 1, "claim_owner_id": None, "claim_expires_at": None, "created_at": now(), "updated_at": now()}
            validate_task(db, task)
            db.execute("INSERT INTO tasks VALUES (?,?,?,?)", (task["id"], task["project_id"], task["section_id"], encode(task)))
            store.record(db, who, body.reason, "task", task["id"], "task.created", None, task, project_id=task["project_id"], task_id=task["id"], session_id=session_id)
            return task
        return store.write(who, "/api/tasks", body, operation)

    @app.get("/api/tasks/{task_id}", dependencies=[Depends(authenticated_read)])
    def task_details(task_id: str):
        with store.connect() as db:
            db.execute("BEGIN")
            return {"task": store.entity(db, "tasks", task_id), "notes": store.entities(db, "notes", "WHERE task_id=?", (task_id,)), "events": store.events(db, "WHERE task_id=?", (task_id,))}

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id: str, body: TaskPatch, request: Request, who=Depends(actor)):
        session_id = session(request)
        changes = changes_dict(body.changes)
        def operation(db):
            before = store.entity(db, "tasks", task_id)
            check_version(before, body.expected_version)
            check_claim(before, who)
            after = {**before, **changes, "version": before["version"] + 1, "updated_at": now()}
            if after["status"] != "in_progress" or ("assignee_id" in changes and after["assignee_id"] != after["claim_owner_id"]):
                after.update(claim_owner_id=None, claim_expires_at=None)
            validate_task(db, after)
            db.execute("UPDATE tasks SET section_id=?,payload=? WHERE id=?", (after["section_id"], encode(after), task_id))
            store.record(db, who, body.reason, "task", task_id, "task.updated", before, after, project_id=before["project_id"], task_id=task_id, session_id=session_id)
            return after
        return store.write(who, f"/api/tasks/{task_id}", body, operation)

    @app.post("/api/tasks/{task_id}/claim")
    def claim_task(task_id: str, body: Claim, request: Request, who=Depends(actor)):
        session_id = session(request)
        def operation(db):
            before = store.entity(db, "tasks", task_id)
            check_version(before, body.expected_version)
            check_claim(before, who)
            if before["status"] == "done":
                raise HTTPException(409, "Завершенную задачу сначала верните в планирование")
            expiry = (datetime.now(timezone.utc) + timedelta(seconds=body.lease_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            after = {**before, "status": "in_progress", "assignee_id": who["id"], "claim_owner_id": who["id"], "claim_expires_at": expiry, "version": before["version"] + 1, "updated_at": now()}
            validate_task(db, after)
            db.execute("UPDATE tasks SET payload=? WHERE id=?", (encode(after), task_id))
            store.record(db, who, body.reason, "task", task_id, "task.claimed", before, after, project_id=before["project_id"], task_id=task_id, session_id=session_id)
            return after
        return store.write(who, f"/api/tasks/{task_id}/claim", body, operation)

    def add_note(task_id, body, who, session_id, kind, note_body, metadata, scope):
        def operation(db):
            task = store.entity(db, "tasks", task_id)
            check_claim(task, who)
            note = {"id": str(uuid4()), "task_id": task_id, "kind": kind, "body": note_body, "actor_id": who["id"], "created_at": now(), "metadata": metadata}
            db.execute("INSERT INTO notes VALUES (?,?,?,?)", (note["id"], task_id, task["project_id"], encode(note)))
            store.record(db, who, body.reason, "note", note["id"], "change.logged" if kind == "change" else "note.created", None, note, project_id=task["project_id"], task_id=task_id, session_id=session_id)
            return note
        return store.write(who, f"/api/tasks/{task_id}/{scope}", body, operation)

    @app.post("/api/tasks/{task_id}/notes")
    def create_note(task_id: str, body: NoteCreate, request: Request, who=Depends(actor)):
        return add_note(task_id, body, who, session(request), body.kind, body.body, {}, "notes")

    @app.post("/api/tasks/{task_id}/changes")
    def log_change(task_id: str, body: ChangeCreate, request: Request, who=Depends(actor)):
        metadata = body.model_dump(include={"files", "diff", "commit", "verification"})
        return add_note(task_id, body, who, session(request), "change", body.summary, metadata, "changes")

    @app.get("/api/history", dependencies=[Depends(authenticated_read)])
    def history(project_id: str | None = None, task_id: str | None = None, after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)):
        where, args = ["id>?"], [after]
        with store.connect() as db:
            if project_id:
                store.entity(db, "projects", project_id)
                where.append("project_id=?")
                args.append(project_id)
            if task_id:
                task = store.entity(db, "tasks", task_id)
                if project_id and task["project_id"] != project_id:
                    raise HTTPException(422, "Задача не принадлежит указанному проекту")
                where.append("task_id=?")
                args.append(task_id)
            events = [store.event(row) for row in db.execute("SELECT * FROM events WHERE " + " AND ".join(where) + " ORDER BY id LIMIT ?", (*args, limit))]
            return {"events": events, "next_cursor": events[-1]["id"] if events else after}

    @app.get("/api/projects/{project_id}/export", dependencies=[Depends(authenticated_read)])
    def export(project_id: str):
        with store.connect() as db:
            # A read transaction gives one consistent snapshot while agents write.
            db.execute("BEGIN")
            result = {"schema_version": 1, "exported_at": now(), "project": store.entity(db, "projects", project_id), "sections": store.entities(db, "sections", "WHERE project_id=?", (project_id,)), "tasks": store.entities(db, "tasks", "WHERE project_id=?", (project_id,)), "notes": store.entities(db, "notes", "WHERE project_id=?", (project_id,)), "events": list(reversed(store.events(db, "WHERE project_id=?", (project_id,))))}
            result["subprojects"] = [item for item in result["sections"] if item.get("kind") == "subproject"]
            result["sections"] = [item for item in result["sections"] if item.get("kind") != "subproject"]
            return JSONResponse(result, headers={"Content-Disposition": f'attachment; filename="agentboard-{project_id}.json"'})

    @app.get("/api/connectors", dependencies=[Depends(authenticated_read)])
    def connectors():
        with store.connect() as db:
            installed = bool(getattr(sys, "frozen", False))
            command = Path(sys.executable).with_name("AgentboardMCP.exe") if installed else Path(sys.executable)
            return {"base_url": base_url, "python_command": str(command.resolve()), "mcp_script": "--mcp" if installed else str((ROOT / "connectors" / "mcp_server.py").resolve()), "data_dir": str(store.data_dir), "desktop": installed, "credentials_file": str(store.credentials_file), "agents": store.agents(db)}

    @app.post("/api/agents")
    def create_agent(body: AgentCreate, request: Request, who=Depends(actor)):
        if who["kind"] != "human":
            raise HTTPException(403, "Только человек может выпускать токены для агентов")
        if body.idempotency_key:
            raise HTTPException(422, "Выдача токена одноразовая: idempotency_key здесь не поддерживается")
        with store.transaction() as db:
            token, agent_id = secrets.token_urlsafe(32), str(uuid4())
            db.execute("INSERT INTO agents VALUES (?,?,?,?,?,?)", (agent_id, body.name, body.kind, store.hash(token), None, now()))
            agent = next(item for item in store.agents(db) if item["id"] == agent_id)
            store.record(db, who, body.reason, "agent", agent_id, "agent.created", None, agent, session_id=session(request))
            return {"agent": agent, "token": token}

    dist = ROOT / "dist"

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "API маршрут не найден")
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "Интерфейс еще не собран. Запустите npm run dev либо npm run build"})

    if seed_demo:
        with store.transaction() as db:
            if not db.execute("SELECT 1 FROM projects").fetchone():
                who = {"id": "human", "name": "Вы", "kind": "human"}
                demo = {"id": str(uuid4()), "name": "Демонстрационный проект", "description": "Пример структуры. Эти данные созданы явно с --demo и не являются выполненной работой агентов.", "repository": "", "color": "#7c8aff", "version": 1, "created_at": now(), "updated_at": now()}
                db.execute("INSERT INTO projects VALUES (?,?)", (demo["id"], encode(demo)))
                store.record(db, who, "Явно включен демонстрационный режим", "project", demo["id"], "project.created", None, demo, project_id=demo["id"])
    return app
