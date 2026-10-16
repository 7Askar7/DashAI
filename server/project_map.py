"""Versioned project descriptions published by external agents through the shared API."""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Prose = Annotated[str, StringConstraints(max_length=20000)]
Notation = Literal['c4_context', 'c4_containers', 'c4_components', 'sequence', 'state', 'erd', 'flowchart']
BLOCKED = {'.git', 'node_modules', '.venv', '.venv-build', '__pycache__', 'dist', 'build', 'data', '.ssh', '.aws', '.codex', 'credentials', 'secrets'}


def safe_path(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (not value or len(value) > 1024 or '\\' in value or ':' in value or value.startswith('/')
            or any(c < ' ' for c in value) or any(p in {'', '.', '..'} for p in value.split('/'))
            or any(p.lower() in BLOCKED for p in parts)
            or any(p.lower().startswith('.env') for p in parts)
            or any(re.search(r'(secret|credential|private.?key|token)', p, re.I) for p in parts)
            or PurePosixPath(value).name.lower() in {'.mcp.json', 'id_rsa', 'id_ed25519'}
            or PurePosixPath(value).suffix.lower() in {'.pem', '.key', '.pfx', '.p12', '.sqlite3', '.db'}):
        raise ValueError('Нужен безопасный относительный путь без секретов, данных и результатов сборки')
    return value


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class FileDescription(Model):
    title: Short
    summary: Prose
    purpose: Prose
    workflow: list[Annotated[str, StringConstraints(min_length=1, max_length=4000)]] = Field(default_factory=list, max_length=30)
    related_paths: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('related_paths')
    @classmethod
    def paths(cls, values):
        return [safe_path(p) for p in values]


class MapFile(Model):
    path: str
    kind: Literal['file', 'directory'] = 'file'
    sha256: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')] | None = None
    description: FileDescription | None = None

    _path = field_validator('path')(safe_path)

    @model_validator(mode='after')
    def file_hash(self):
        if self.kind == 'file' and self.sha256 is None:
            raise ValueError('Для файла нужен SHA-256 анализированного содержимого')
        if self.kind == 'directory' and self.sha256 is not None:
            raise ValueError('Для папки используется снимок вложенных файлов')
        return self


class MapDiagram(Model):
    id: Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9_-]{1,80}$')]
    title: Short
    notation: Notation
    scope: Prose
    explanation: Prose
    legend: Prose
    source: Annotated[str, StringConstraints(min_length=1, max_length=30000)]
    related_paths: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('related_paths')
    @classmethod
    def paths(cls, values):
        return [safe_path(p) for p in values]

    @model_validator(mode='after')
    def safe_source(self):
        header = {'sequence': 'sequenceDiagram', 'state': 'stateDiagram-v2', 'erd': 'erDiagram'}.get(self.notation, 'flowchart')
        if not re.match(r'^\s*' + header + r'\b', self.source):
            raise ValueError('Mermaid-исходник не соответствует выбранной нотации')
        if re.search(r'%%\{|\b(?:click|href|image|classDef)\b|https?://|javascript:|data:|file:|<\s*(?:script|iframe|img|svg)|@\{', self.source, re.I):
            raise ValueError('Схемы не могут содержать директивы, внешние ресурсы или действия')
        return self


class MapDocument(Model):
    title: Short = 'Документация проекта'
    context: Prose = ''
    sections: list[Literal['intro', 'diagrams', 'files', 'decisions', 'verification']] = Field(default_factory=lambda: ['intro', 'diagrams', 'files', 'decisions', 'verification'], max_length=5)
    diagram_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.sections)) != len(self.sections) or len(set(self.diagram_ids)) != len(self.diagram_ids):
            raise ValueError('Разделы и схемы не должны повторяться')
        return self


class MapWrite(Model):
    expected_version: int = Field(ge=0)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None


class MapPublish(MapWrite):
    source_revision: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    files: list[MapFile] = Field(max_length=2000)
    diagrams: list[MapDiagram] | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def references(self):
        by_path = {f.path: f for f in self.files}
        paths = set(by_path)
        if len(paths) != len(self.files) or len({p.casefold() for p in paths}) != len(paths):
            raise ValueError('Пути файлов должны быть уникальны, включая регистр Windows')
        for f in self.files:
            if any(parent in paths and by_path[parent].kind != 'directory'
                   for parent in (str(p) for p in PurePosixPath(f.path).parents) if parent != '.'):
                raise ValueError('Родитель файла должен быть папкой')
        refs = [p for f in self.files if f.description for p in f.description.related_paths]
        if self.diagrams is not None:
            if len({d.id for d in self.diagrams}) != len(self.diagrams):
                raise ValueError('ID схем должны быть уникальны')
            refs += [p for d in self.diagrams for p in d.related_paths]
        if any(p not in paths for p in refs):
            raise ValueError('Связанные пути должны присутствовать в том же снимке')
        if len(self.model_dump_json().encode()) > 2_000_000:
            raise ValueError('Снимок превышает 2 MB; сократите область анализа')
        return self


class MapDocumentWrite(MapWrite):
    document: MapDocument


class MapReview(MapWrite):
    path: str | None = None
    diagram_id: str | None = None

    @model_validator(mode='after')
    def target(self):
        if (self.path is None) == (self.diagram_id is None):
            raise ValueError('Выберите один файл или одну схему')
        if self.path is not None:
            safe_path(self.path)
        return self


SCHEMA = '''
CREATE TABLE IF NOT EXISTS project_maps (id TEXT PRIMARY KEY REFERENCES projects(id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_map_revisions (project_id TEXT NOT NULL REFERENCES projects(id), version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id,version));
CREATE TRIGGER IF NOT EXISTS map_revisions_no_update BEFORE UPDATE ON project_map_revisions BEGIN SELECT RAISE(ABORT, 'Map revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS map_revisions_no_delete BEFORE DELETE ON project_map_revisions BEGIN SELECT RAISE(ABORT, 'Map revisions are immutable'); END;
'''


def install_routes(app, store, actor, authenticated_read, session):
    # All changes, immutable revisions and business audit share Store.write's transaction.
    from .app import encode, now

    def read(db, project_id, version=None):
        store.entity(db, 'projects', project_id)
        row = (db.execute('SELECT payload FROM project_maps WHERE id=?', (project_id,)).fetchone() if version is None else
               db.execute('SELECT payload FROM project_map_revisions WHERE project_id=? AND version=?', (project_id, version)).fetchone())
        if row:
            import json
            return json.loads(row['payload'])
        if version is not None:
            raise HTTPException(404, 'Версия карты не найдена')
        return {'project_id': project_id, 'version': 0, 'source_revision': '', 'files': [], 'diagrams': [], 'document': MapDocument().model_dump(), 'updated_at': None, 'author_name': None}

    def summary(value):
        return {k: value.get(k) for k in ('project_id', 'version', 'source_revision', 'updated_at', 'author_name')} | {'files_count': len(value['files']), 'diagrams_count': len(value['diagrams'])}

    def save(db, project_id, before, after, body, who, request, action):
        after.update(version=before['version'] + 1, updated_at=now(), author_id=who['id'], author_name=who['name'])
        encoded = encode(after)
        if len(encoded.encode()) > 3_000_000:
            raise HTTPException(422, 'Сохранённая карта превышает 3 MB; сократите область анализа')
        db.execute('INSERT INTO project_maps VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (project_id, encoded))
        db.execute('INSERT INTO project_map_revisions VALUES (?,?,?)', (project_id, after['version'], encoded))
        store.record(db, who, body.reason, 'project_map', project_id, action, summary(before), summary(after), project_id=project_id, session_id=session(request))
        return summary(after)

    def current(db, project_id, body):
        value = read(db, project_id)
        if value['version'] != body.expected_version:
            raise HTTPException(409, 'Объект уже изменен. Перечитайте карту и подтвердите намерение заново')
        return value

    @app.get('/api/projects/{project_id}/map', dependencies=[Depends(authenticated_read)])
    def get_map(project_id: str, version: int | None = Query(default=None, ge=1)):
        with store.connect() as db:
            db.execute('BEGIN')
            return read(db, project_id, version)

    @app.put('/api/projects/{project_id}/map')
    def publish_map(project_id: str, body: MapPublish, request: Request, who=Depends(actor)):
        def operation(db):
            before = current(db, project_id, body)
            previous = {f['path']: f for f in before['files']}
            incoming = {f.path: f for f in body.files}
            changed = {p for p in set(previous) | set(incoming) if p not in previous or p not in incoming or previous[p]['sha256'] != incoming[p].sha256 or previous[p]['kind'] != incoming[p].kind}
            def touched(paths):
                return any(p in changed or any(c.startswith(p + '/') for c in changed) for p in paths)
            stamp = {'author_id': who['id'], 'author_name': who['name'], 'updated_at': now(), 'status': 'draft', 'reviewed_by': None}
            entries = []
            for f in body.files:
                old = previous.get(f.path, {})
                entry = f.model_dump() | {'status': None, 'reviewed_by': None}
                if f.description is not None:
                    entry.update(stamp, described_sha256=f.sha256)
                elif old.get('description'):
                    entry = {**old, **f.model_dump(exclude={'description'})}
                    if touched([f.path, *old['description']['related_paths']]):
                        entry.update(status='stale', reviewed_by=None)
                entries.append(entry)
            diagrams = before['diagrams']
            if body.diagrams is not None:
                diagrams = [d.model_dump() | stamp for d in body.diagrams]
            else:
                diagrams = [dict(d, status='stale', reviewed_by=None) if (not d['related_paths'] and changed) or touched(d['related_paths']) else d for d in diagrams]
            after = {**before, 'source_revision': body.source_revision, 'files': entries, 'diagrams': diagrams}
            valid_ids = {d['id'] for d in diagrams}
            after['document'] = {**before['document'], 'diagram_ids': [i for i in before['document']['diagram_ids'] if i in valid_ids]}
            return save(db, project_id, before, after, body, who, request, 'project_map.published')
        return store.write(who, f'/api/projects/{project_id}/map', body, operation)

    @app.patch('/api/projects/{project_id}/map/document')
    def save_document(project_id: str, body: MapDocumentWrite, request: Request, who=Depends(actor)):
        def operation(db):
            before = current(db, project_id, body)
            if not set(body.document.diagram_ids) <= {d['id'] for d in before['diagrams']}:
                raise HTTPException(422, 'Выбранная схема отсутствует в карте проекта')
            return save(db, project_id, before, {**before, 'document': body.document.model_dump()}, body, who, request, 'project_map.document_updated')
        return store.write(who, f'/api/projects/{project_id}/map/document', body, operation)

    @app.post('/api/projects/{project_id}/map/review')
    def review_map(project_id: str, body: MapReview, request: Request, who=Depends(actor)):
        if who['kind'] != 'human':
            raise HTTPException(403, 'Отметку проверки ставит человек после сверки с исходником')
        def operation(db):
            before = current(db, project_id, body)
            collection, key, target = ('files', 'path', body.path) if body.path else ('diagrams', 'id', body.diagram_id)
            entry = next((v for v in before[collection] if v[key] == target), None)
            if not entry or entry.get('status') is None:
                raise HTTPException(404, 'Описание не найдено')
            if entry['status'] == 'stale':
                raise HTTPException(409, 'Сначала обновите описание изменившегося исходника')
            after = {**before, collection: [dict(v, status='reviewed', reviewed_by=who['name']) if v[key] == target else v for v in before[collection]]}
            return save(db, project_id, before, after, body, who, request, 'project_map.reviewed')
        return store.write(who, f'/api/projects/{project_id}/map/review', body, operation)
