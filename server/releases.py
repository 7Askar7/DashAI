"""Project release records share the API store; they do not perform deployments."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Depends, HTTPException, Query, Request
from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from .modules import Model, Write, enabled

SCHEMA = """
CREATE TABLE IF NOT EXISTS project_releases (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS releases_project ON project_releases(project_id);
"""

VersionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Changelog = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50000)]
Link = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Revision = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
ReleaseDate = Annotated[str, StringConstraints(min_length=10, max_length=10)]
ReleaseStatus = Literal["draft", "released", "rolled_back"]


class ReleaseContent(Model):
    version_name: VersionName
    title: Title = ""
    status: ReleaseStatus = "draft"
    environment: VersionName = "production"
    released_at: ReleaseDate | None = None
    changelog: Changelog
    link: Link = ""
    source_revision: Revision = ""

    @field_validator("released_at")
    @classmethod
    def release_date(cls, value):
        if value is not None:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                raise ValueError("Дата выпуска должна иметь формат YYYY-MM-DD и существовать в календаре") from None
        return value

    @field_validator("link")
    @classmethod
    def release_link(cls, value):
        if value:
            try:
                parsed = urlsplit(value)
                parsed.port
                if (parsed.scheme not in {"https", "http"} or not parsed.hostname
                        or parsed.username or parsed.password or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)):
                    raise ValueError
            except ValueError:
                raise ValueError("Нужна HTTP(S)-ссылка без логина, пароля и управляющих символов") from None
        return value

    @model_validator(mode="after")
    def dated_release(self):
        if self.status != "draft" and self.released_at is None:
            raise ValueError("Для выпущенной или отозванной версии нужна дата выпуска")
        return self


class ReleaseCreate(ReleaseContent, Write):
    pass


class ReleaseChanges(Model):
    version_name: VersionName | None = None
    title: Title | None = None
    status: ReleaseStatus | None = None
    environment: VersionName | None = None
    released_at: ReleaseDate | None = None
    changelog: Changelog | None = None
    link: Link | None = None
    source_revision: Revision | None = None

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно изменение")
        if any(getattr(self, key) is None for key in self.model_fields_set if key != "released_at"):
            raise ValueError("Только дату черновика можно очистить значением null")
        return self


class ReleasePatch(Write):
    expected_version: int = Field(ge=1)
    changes: ReleaseChanges


def install_routes(app, store, actor, authenticated_read, session):
    def project_release(db, project_id, release_id):
        store.entity(db, "projects", project_id)
        item = store.entity(db, "project_releases", release_id)
        if item["project_id"] != project_id:
            raise HTTPException(404, "Версия не найдена в этом проекте")
        return item

    def require_enabled(db, project_id):
        store.entity(db, "projects", project_id)
        if not enabled(db, project_id, "releases"):
            raise HTTPException(409, "Сначала включите модуль «Версии проекта». История сохранена")

    @app.get("/api/projects/{project_id}/releases", dependencies=[Depends(authenticated_read)])
    def list_releases(project_id: str, q: str = Query(default="", max_length=200),
                      status: ReleaseStatus | None = None, environment: str | None = Query(default=None, max_length=100),
                      offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100)):
        with store.connect() as db:
            db.execute("BEGIN")
            store.entity(db, "projects", project_id)
            where, args = ["project_id=?"], [project_id]
            if status is not None:
                where.append("json_extract(payload,'$.status')=?")
                args.append(status)
            if environment is not None:
                where.append("json_extract(payload,'$.environment')=?")
                args.append(environment)
            if q.strip():
                # SQLite lower() covers ASCII only; preserve Russian search without decoding full records in Python.
                db.create_function("casefold", 1, str.casefold, deterministic=True)
                where.append("instr(casefold(json_extract(payload,'$.version_name') || ' ' || json_extract(payload,'$.title') || ' ' || json_extract(payload,'$.environment') || ' ' || json_extract(payload,'$.changelog')),?)>0")
                args.append(q.strip().casefold())
            predicate = " AND ".join(where)
            total = db.execute("SELECT COUNT(*) FROM project_releases WHERE " + predicate, args).fetchone()[0]
            projection = "json_set(json_remove(payload,'$.changelog'),'$.changelog_preview',substr(json_extract(payload,'$.changelog'),1,300),'$.summary_only',json('true'))"
            rows = db.execute(f"SELECT {projection} FROM project_releases WHERE {predicate} ORDER BY COALESCE(json_extract(payload,'$.released_at'),json_extract(payload,'$.created_at')) DESC,id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
            return {"releases": [json.loads(row[0]) for row in rows], "total": total, "offset": offset,
                    "limit": limit, "has_more": offset + limit < total}

    @app.get("/api/projects/{project_id}/releases/{release_id}", dependencies=[Depends(authenticated_read)])
    def get_release(project_id: str, release_id: str):
        with store.connect() as db:
            db.execute("BEGIN")
            return project_release(db, project_id, release_id)

    @app.post("/api/projects/{project_id}/releases")
    def create_release(project_id: str, body: ReleaseCreate, request: Request, who=Depends(actor)):
        def operation(db):
            require_enabled(db, project_id)
            timestamp = datetime.now(timezone.utc).isoformat()
            item = {**body.model_dump(exclude={"reason", "idempotency_key"}), "id": str(uuid4()),
                    "project_id": project_id, "version": 1, "created_at": timestamp, "updated_at": timestamp,
                    "author_id": who["id"], "author_name": who["name"]}
            db.execute("INSERT INTO project_releases VALUES (?,?,?)", (item["id"], project_id, json.dumps(item, ensure_ascii=False)))
            store.record(db, who, body.reason, "project_release", item["id"], "project_release.created", None, item,
                         project_id=project_id, session_id=session(request))
            return item
        return store.write(who, f"/api/projects/{project_id}/releases", body, operation)

    @app.patch("/api/projects/{project_id}/releases/{release_id}")
    def update_release(project_id: str, release_id: str, body: ReleasePatch, request: Request, who=Depends(actor)):
        def operation(db):
            before = project_release(db, project_id, release_id)
            require_enabled(db, project_id)
            if body.expected_version != before["version"]:
                raise HTTPException(409, "Версия проекта изменена. Перечитайте запись и подтвердите изменение снова")
            values = {key: before[key] for key in ReleaseContent.model_fields}
            values.update(body.changes.model_dump(exclude_unset=True))
            try:
                content = ReleaseContent.model_validate(values).model_dump()
            except ValidationError as error:
                raise HTTPException(422, str(error)) from None
            after = {**before, **content, "version": before["version"] + 1,
                     "updated_at": datetime.now(timezone.utc).isoformat()}
            db.execute("UPDATE project_releases SET payload=? WHERE id=?", (json.dumps(after, ensure_ascii=False), release_id))
            store.record(db, who, body.reason, "project_release", release_id, "project_release.updated", before, after,
                         project_id=project_id, session_id=session(request))
            return after
        return store.write(who, f"/api/projects/{project_id}/releases/{release_id}", body, operation)
