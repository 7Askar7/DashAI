"""One-way, explicitly scoped Atlassian documentation sync; no model runtime."""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs, quote, urlsplit
from uuid import uuid4

import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA = '''
CREATE TABLE IF NOT EXISTS integrations (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), provider TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(project_id,provider));
CREATE TABLE IF NOT EXISTS integration_outbox (integration_id TEXT NOT NULL REFERENCES integrations(id), local_id TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0, error TEXT, PRIMARY KEY(integration_id,local_id));
CREATE TABLE IF NOT EXISTS integration_mappings (integration_id TEXT NOT NULL REFERENCES integrations(id), local_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(integration_id,local_id));
CREATE TABLE IF NOT EXISTS integration_attempts (integration_id TEXT NOT NULL REFERENCES integrations(id), local_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(integration_id,local_id));
'''
Provider = Literal['confluence', 'jira']
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Write(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_version: int = Field(ge=0)
    reason: Short


class Configure(Write):
    url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2048)]
    deployment: Literal['cloud', 'data_center']
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=320)] = ''
    token: Annotated[str, StringConstraints(max_length=4096)] = ''
    personal_cloud_token: bool = False
    enabled: bool = True
    auto_sync: bool = True
    issue_type_id: Annotated[str, StringConstraints(pattern=r'^\d{1,30}$')] | None = None


class Sync(Write):
    overwrite_remote: bool = False


class Resolve(Write):
    local_id: Annotated[str, StringConstraints(min_length=1, max_length=1100)]
    confirm_remote_absent: bool


class SyncError(Exception):
    def __init__(self, message, *, uncertain=False):
        self.uncertain = uncertain
        super().__init__(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def module_enabled(db, project_id):
    from .modules import enabled
    return enabled(db, project_id, 'integrations')


def target(url: str, provider: str, deployment: str):
    """Extract an immutable root from an ordinary project/page link, never an API URL."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.fragment or parsed.port == 0 or any(c.isspace() for c in url)
                or '\\' in url or '%' in parsed.netloc or '..' in parsed.path.split('/')):
            raise ValueError()
        hostname = parsed.hostname.encode('idna').decode('ascii').lower()
        if hostname in {'localhost', 'localhost.localdomain'} or hostname.endswith('.localhost'):
            raise ValueError()
        if deployment == 'cloud' and (not hostname.endswith('.atlassian.net') or parsed.port not in (None, 443)):
            raise ValueError()
        origin = 'https://' + (f'[{hostname}]' if ':' in hostname else hostname) + (f':{parsed.port}' if parsed.port and parsed.port != 443 else '')
        if provider == 'confluence':
            match = re.search(r'/(?:spaces/[^/]+/pages|pages)/(\d+)(?:/|$)', parsed.path)
            query = parse_qs(parsed.query)
            if set(query) - {'pageId'} or any(len(v) != 1 for v in query.values()):
                raise ValueError()
            root = match[1] if match else query.get('pageId', [''])[0]
            if not re.fullmatch(r'\d{1,30}', root):
                raise ValueError()
            marker = '/spaces/' if '/spaces/' in parsed.path else '/pages/'
            context = parsed.path.split(marker, 1)[0] if marker in parsed.path else ''
            if deployment == 'cloud':
                context = '/wiki'
        else:
            match = re.search(r'/projects/([A-Za-z][A-Za-z0-9_]{0,49})(?:/|$)', parsed.path)
            if not match or parsed.query:
                raise ValueError()
            root = match[1].upper()
            context = '' if deployment == 'cloud' else parsed.path.split('/projects/', 1)[0]
        if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*', context):
            raise ValueError()
        return {'base_url': origin + context, 'root_id': root, 'url': url}
    except (ValueError, UnicodeError):
        raise HTTPException(422, 'Нужна HTTPS-ссылка на страницу Confluence с pageId или на /projects/KEY в Jira') from None


def validate_host(base_url):
    hostname = urlsplit(base_url).hostname
    try:
        addresses = socket.getaddrinfo(hostname, urlsplit(base_url).port or 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError()
        for record in addresses:
            address = ipaddress.ip_address(record[4][0])
            address = address.ipv4_mapped or address if isinstance(address, ipaddress.IPv6Address) else address
            if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
                raise SyncError('Локальные, link-local и служебные адреса запрещены')
    except (OSError, ValueError):
        raise SyncError('Не удалось безопасно разрешить адрес сервера') from None


class Atlassian:
    def __init__(self, config, credential, *, transport=None, guard=lambda: None):
        self.config, self.guard = config, guard
        self.cloud = config['deployment'] == 'cloud'
        self.api = '/api/v2/pages' if self.cloud and config['provider'] == 'confluence' else '/rest/api/content'
        self.jira = '/rest/api/3' if self.cloud else '/rest/api/2'
        auth = httpx.BasicAuth(credential['email'], credential['token']) if self.cloud else None
        headers = {'Accept': 'application/json'}
        if not self.cloud:
            headers['Authorization'] = 'Bearer ' + credential['token']
        self.client = httpx.Client(base_url=config['base_url'] + '/', auth=auth, headers=headers,
                                   timeout=15, follow_redirects=False, trust_env=False, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def request(self, method, path, *, params=None, body=None):
        self.guard()
        validate_host(self.config['base_url'])
        try:
            with self.client.stream(method, self.config['base_url'] + path, params=params, json=body) as response:
                if response.status_code >= 300:
                    labels = {401: 'Проверьте учётные данные', 403: 'Недостаточно прав в выбранном проекте',
                              404: 'Страница или проект недоступны', 409: 'Удалённая версия изменилась',
                              429: 'Лимит Atlassian: повтор будет отложен'}
                    raise SyncError(labels.get(response.status_code, 'Atlassian отклонил запрос') + f' (HTTP {response.status_code})', uncertain=method == 'POST' and response.status_code >= 500)
                raw = bytearray()
                deadline = time.monotonic() + 20
                for part in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise SyncError('Ответ Atlassian занял слишком много времени', uncertain=method == 'POST')
                    raw.extend(part)
                    if len(raw) > 4_000_000:
                        raise SyncError('Ответ Atlassian превышает 4 MB', uncertain=method == 'POST')
                value = json.loads(raw) if raw else {}
                if not isinstance(value, dict):
                    raise SyncError('Atlassian вернул некорректный ответ', uncertain=method == 'POST')
                return value
        except (httpx.HTTPError, json.JSONDecodeError):
            raise SyncError('Нет подтверждённого ответа Atlassian; проверьте сеть и TLS', uncertain=method == 'POST') from None

    @staticmethod
    def identifier(value):
        if not re.fullmatch(r'\d{1,30}', str(value or '')):
            raise SyncError('Atlassian вернул некорректный идентификатор')
        return str(value)

    def verify_root(self):
        config = self.config
        if config['provider'] == 'confluence':
            root = self.request('GET', self.api + '/' + config['root_id'], params={} if self.cloud else {'expand': 'space,version,ancestors'})
            if str(root.get('id')) != config['root_id'] or root.get('status') != 'current' or not self.cloud and root.get('type') != 'page':
                raise SyncError('Корневая страница недоступна или не опубликована')
            space = self.identifier(root.get('spaceId') if self.cloud else root.get('space', {}).get('id'))
            if config.get('space_id') and space != config['space_id']:
                raise SyncError('Корневая страница перемещена в другое пространство; синхронизация остановлена')
            if not self.cloud and config.get('space_key') and root.get('space', {}).get('key') != config['space_key']:
                raise SyncError('Ключ пространства изменился; синхронизация остановлена')
            return {'space_id': space, 'space_key': root.get('space', {}).get('key', ''), 'root_title': str(root.get('title', ''))[:255]}
        project = self.request('GET', self.jira + '/project/' + quote(config['root_id'], safe=''))
        project_id = self.identifier(project.get('id'))
        if not config.get('project_key') and project.get('key') != config['root_id']:
            raise SyncError('Jira вернула другой проект; подключение остановлено')
        if config.get('project_key') and (project_id != config['root_id'] or project.get('key') != config['project_key']):
            raise SyncError('Идентичность Jira-проекта изменилась; синхронизация остановлена')
        types = [item for item in project.get('issueTypes', []) if not item.get('subtask') and re.fullmatch(r'\d{1,30}', str(item.get('id', '')))]
        requested = config.get('issue_type_id')
        chosen = next((item for item in types if item['id'] == requested), None) if requested else next(iter(types), None)
        if not chosen:
            raise SyncError('В Jira нужен доступный тип обычной задачи; настройте права или тип задачи')
        return {'root_id': project_id, 'project_key': project['key'], 'root_title': str(project.get('name', ''))[:255],
                'issue_type_id': chosen['id'], 'issue_types': [{'id': t['id'], 'name': t['name']} for t in types]}

    def marker(self, local_id):
        return 'dashai-' + self.config['id'] + '-' + hashlib.sha256(local_id.encode()).hexdigest()[:24]

    def title(self, item):
        return item['title'][:170] + ' [' + self.marker(item['local_id']) + ']'

    def managed(self, item):
        if self.config['provider'] == 'confluence':
            return {'title': self.title(item), 'body': '<p>' + html.escape(self.marker(item['local_id'])) + '</p><pre>' + html.escape(item['text']) + '</pre>'}
        description = item['text']
        if self.cloud:
            description = {'type': 'doc', 'version': 1, 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': line}]} for line in (item['text'].splitlines() or [' ']) if line]}
        return {'summary': self.title(item), 'description': description}

    def confluence_page(self, remote_id):
        page = self.request('GET', self.api + '/' + self.identifier(remote_id), params={'body-format': 'storage'} if self.cloud else {'expand': 'ancestors,space,version,body.storage'})
        parent = str(page.get('parentId', '')) if self.cloud else str((page.get('ancestors') or [{}])[-1].get('id', ''))
        space = str(page.get('spaceId', '')) if self.cloud else str(page.get('space', {}).get('id', ''))
        if str(page.get('id')) != remote_id or parent != self.config['root_id'] or space != self.config['space_id']:
            raise SyncError('Страница вышла за разрешённую корневую страницу; запись запрещена')
        return page

    def jira_issue(self, remote_id):
        issue = self.request('GET', self.jira + '/issue/' + self.identifier(remote_id), params={'fields': 'project,summary,description,labels'})
        if str(issue.get('id')) != remote_id or str(issue.get('fields', {}).get('project', {}).get('id')) != self.config['root_id']:
            raise SyncError('Задача вышла за разрешённый Jira-проект; запись запрещена')
        return issue

    def recover(self, item, *, overwrite=False):
        marker = self.marker(item['local_id'])
        if self.config['provider'] == 'confluence':
            title = item.get('recovery_title', self.title(item))
            params = {'space-id': self.config['space_id'], 'title': title, 'limit': 2} if self.cloud else {'spaceKey': self.config['space_key'], 'title': title, 'type': 'page', 'limit': 2}
            values = self.request('GET', self.api, params=params).get('results', [])
            if len(values) > 1:
                raise SyncError('Найдено несколько страниц с идентификатором DashAI; требуется проверка')
            if not values:
                return None
            page = self.confluence_page(self.identifier(values[0].get('id')))
            if marker not in page.get('body', {}).get('storage', {}).get('value', ''):
                raise SyncError('Заголовок занят чужой страницей; запись запрещена')
            actual = {'title': page.get('title'), 'body': page.get('body', {}).get('storage', {}).get('value')}
            if actual != self.managed(item) and not overwrite:
                raise SyncError('Страница изменена после неопределённой отправки. Сверьте изменения перед явной перезаписью', uncertain=True)
            return {'remote_id': self.identifier(page['id']), 'version': page['version']['number']}
        path = '/search/jql' if self.cloud else '/search'
        values = self.request('GET', self.jira + path, params={'jql': f'project = {self.config["root_id"]} AND labels = "{marker}"', 'maxResults': 2, 'fields': 'project,summary,description,labels'}).get('issues', [])
        if len(values) > 1:
            raise SyncError('Найдено несколько задач с идентификатором DashAI; требуется проверка')
        if not values:
            return None
        issue = self.jira_issue(self.identifier(values[0].get('id')))
        if marker not in issue['fields'].get('labels', []):
            raise SyncError('Идентификатор DashAI отсутствует; запись запрещена')
        actual = {k: issue['fields'].get(k) for k in ('summary', 'description')}
        if actual != self.managed(item) and not overwrite:
            raise SyncError('Задача изменена после неопределённой отправки. Сверьте изменения перед явной перезаписью', uncertain=True)
        return {'remote_id': self.identifier(issue['id']), 'fingerprint': digest(actual)}

    def publish(self, item, mapping, *, uncertain=False, overwrite=False, recovery_item=None):
        marker = self.marker(item['local_id'])
        if mapping is None:
            mapping = self.recover(recovery_item or item, overwrite=overwrite)
            if mapping is None and uncertain:
                raise SyncError('Результат создания неизвестен. Проверьте удалённый проект перед разрешением повторного создания', uncertain=True)
        title = self.title(item)
        if self.config['provider'] == 'confluence':
            content = self.managed(item)['body']
            body = {'title': title, 'status': 'current'}
            if self.cloud:
                body.update(spaceId=self.config['space_id'], parentId=self.config['root_id'], body={'representation': 'storage', 'value': content})
            else:
                body.update(type='page', space={'key': self.config['space_key']}, ancestors=[{'id': self.config['root_id']}], body={'storage': {'value': content, 'representation': 'storage'}})
            if mapping:
                page = self.confluence_page(mapping['remote_id'])
                version = page['version']['number']
                if marker not in page.get('body', {}).get('storage', {}).get('value', ''):
                    raise SyncError('Удалённая страница больше не принадлежит DashAI; запись запрещена')
                if version != mapping['version'] and not overwrite:
                    raise SyncError('Страница изменена в Confluence. Сверьте изменения перед явной перезаписью')
                body.update(id=mapping['remote_id'], version={'number': version + 1})
                self.request('PUT', self.api + '/' + mapping['remote_id'], body=body)
                return {'remote_id': mapping['remote_id'], 'version': version + 1}
            result = self.request('POST', self.api, body=body)
            try:
                return {'remote_id': self.identifier(result.get('id')), 'version': result.get('version', {}).get('number', 1)}
            except SyncError:
                raise SyncError('Создание отправлено, но идентификатор страницы не подтверждён', uncertain=True) from None
        if len(item['text']) > 30000:
            raise SyncError('Описание превышает лимит Jira 30000 символов; сократите этот документ')
        fields = self.managed(item)
        description = fields['description']
        if mapping:
            issue = self.jira_issue(mapping['remote_id'])
            if marker not in issue['fields'].get('labels', []):
                raise SyncError('Удалённая задача больше не принадлежит DashAI; запись запрещена')
            if digest({k: issue['fields'].get(k) for k in fields}) != mapping['fingerprint'] and not overwrite:
                raise SyncError('Описание изменено в Jira. Сверьте изменения перед явной перезаписью')
            self.request('PUT', self.jira + '/issue/' + mapping['remote_id'], body={'fields': fields})
            remote_id = mapping['remote_id']
        else:
            fields.update(project={'id': self.config['root_id']}, issuetype={'id': self.config['issue_type_id']}, labels=[marker])
            result = self.request('POST', self.jira + '/issue', body={'fields': fields})
            try:
                remote_id = self.identifier(result.get('id'))
            except SyncError:
                raise SyncError('Создание отправлено, но идентификатор задачи не подтверждён', uncertain=True) from None
        return {'remote_id': remote_id, 'fingerprint': digest({'summary': title, 'description': description})}


def documents(db, project_id):
    project = json.loads(db.execute('SELECT payload FROM projects WHERE id=?', (project_id,)).fetchone()['payload'])
    row = db.execute('SELECT payload FROM project_maps WHERE id=?', (project_id,)).fetchone()
    project_map = json.loads(row['payload']) if row else {'files': [], 'diagrams': [], 'document': {}}
    from .modules import enabled, project_modules
    document = project_map.get('document', {}) if enabled(db, project_id, 'documentation') else {}
    intro = f"{project['name']}\n\n{project.get('description', '')}\n\n{document.get('title', '')}\n{document.get('context', '')}\nСостав документа: {', '.join(document.get('sections', []))}\nРевизия исходников: {project_map.get('source_revision', '')}"
    result = [{'local_id': 'project', 'title': project['name'] + ' — документация', 'text': intro}]
    for item in project_map['files'] if enabled(db, project_id, 'map') else []:
        description = item.get('description')
        if description:
            text = '\n\n'.join([item['path'], description['title'], description.get('summary', ''), description.get('purpose', ''), '\n'.join(description.get('workflow', [])), 'Связанные файлы: ' + ', '.join(description.get('related_paths', [])), 'Актуальность: ' + str(item.get('status', 'draft'))])
            result.append({'local_id': 'file:' + item['path'], 'title': item['path'], 'text': text})
    for item in project_map['diagrams'] if enabled(db, project_id, 'architecture') else []:
        text = '\n\n'.join([item['title'], 'Нотация: ' + item['notation'], item.get('scope', ''), item.get('explanation', ''), item.get('legend', ''), '```mermaid\n' + item['source'] + '\n```', 'Актуальность: ' + str(item.get('status', 'draft'))])
        result.append({'local_id': 'diagram:' + item['id'], 'title': item['title'], 'text': text})
    # Modules are stored beside projects; disabled content remains local and is not published.
    for item in project_modules(db, project_id):
        if item.get('enabled') and item.get('content'):
            result.append({'local_id': 'module:' + item['module_id'], 'title': item.get('title', item['module_id']), 'text': item['content']})
    return result


def enqueue(db, project_id, *, force=False, overwrite=False, provider=None):
    """Call inside the originating project's transaction, alongside its audit event."""
    if not module_enabled(db, project_id):
        return
    items = None
    for row in db.execute('SELECT payload FROM integrations WHERE project_id=?', (project_id,)):
        config = json.loads(row['payload'])
        if not config['enabled'] or provider is not None and config['provider'] != provider or (not force and not config['auto_sync']):
            continue
        items = documents(db, project_id) if items is None else items
        for item in items:
            old = db.execute('SELECT digest,status,payload FROM integration_outbox WHERE integration_id=? AND local_id=?', (config['id'], item['local_id'])).fetchone()
            recovery_title = (json.loads(old['payload']).get('recovery_title') if old else None) or (item['title'][:170] + ' [dashai-' + config['id'] + '-' + hashlib.sha256(item['local_id'].encode()).hexdigest()[:24] + ']')
            item = item | {'overwrite_remote': overwrite, 'recovery_title': recovery_title}
            checksum = digest(item)
            if old and old['digest'] == checksum and old['status'] not in {'removed', 'removed_uncertain'} and (not force or old['status'] in {'synced', 'processing', 'uncertain'}):
                continue
            # An ambiguous POST is never blindly re-created after a local revision changes.
            status = 'uncertain' if old and old['status'] in {'uncertain', 'processing', 'removed_uncertain'} else 'pending'
            db.execute('INSERT INTO integration_outbox VALUES (?,?,?,?,?,0,0,NULL) ON CONFLICT(integration_id,local_id) DO UPDATE SET digest=excluded.digest,payload=excluded.payload,status=excluded.status,retry_at=0,error=NULL', (config['id'], item['local_id'], checksum, encode(item), status))
        live = {item['local_id'] for item in items}
        for old in db.execute('SELECT local_id,status FROM integration_outbox WHERE integration_id=?', (config['id'],)).fetchall():
            if old['local_id'] not in live:
                state = 'removed_uncertain' if old['status'] in {'uncertain', 'processing', 'removed_uncertain'} else 'removed'
                db.execute("UPDATE integration_outbox SET status=?,error=CASE WHEN ?='removed' THEN NULL ELSE error END WHERE integration_id=? AND local_id=?", (state, state, config['id'], old['local_id']))


class Integrations:
    def __init__(self, store):
        self.store, self.locks, self.stop_event = store, {}, threading.Event()
        self.thread = None
        self.transport = None  # Tests supply httpx.MockTransport; production always uses verified TLS.
        self.secrets_dir = store.data_dir / 'integration-secrets'

    def lock_for(self, project_id, provider):
        return self.locks.setdefault((project_id, provider), threading.RLock())

    def credential_path(self, integration_id):
        return self.secrets_dir / (integration_id + '.json')

    def credential(self, integration_id):
        try:
            return json.loads(self.credential_path(integration_id).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise SyncError('Локальные учётные данные недоступны; подключите интеграцию заново') from None

    def save_credential(self, integration_id, value):
        self.secrets_dir.mkdir(mode=0o700, exist_ok=True)
        path = self.credential_path(integration_id)
        temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
        try:
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
                stream.write(encode(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def config(self, db, project_id, provider):
        self.store.entity(db, 'projects', project_id)
        row = db.execute('SELECT payload FROM integrations WHERE project_id=? AND provider=?', (project_id, provider)).fetchone()
        return json.loads(row['payload']) if row else None

    def public(self, db, config):
        counts = {row['status']: row['n'] for row in db.execute('SELECT status,count(*) AS n FROM integration_outbox WHERE integration_id=? GROUP BY status', (config['id'],))}
        paused_uncertain = counts.pop('removed_uncertain', 0)
        if paused_uncertain:
            counts['uncertain'] = counts.get('uncertain', 0) + paused_uncertain
        errors = [dict(row) for row in db.execute('SELECT local_id,status,error FROM integration_outbox WHERE integration_id=? AND error IS NOT NULL ORDER BY retry_at DESC LIMIT 20', (config['id'],))]
        for error in errors:
            if error['status'] == 'removed_uncertain':
                error.update(status='uncertain', paused=True)
        return config | {'credential_present': self.credential_path(config['id']).is_file(), 'counts': counts, 'errors': errors, 'paused_uncertain_count': paused_uncertain}

    def require_enabled(self, project_id):
        if self.stop_event.is_set():
            raise SyncError('Синхронизация остановлена при завершении приложения')
        with self.store.connect() as db:
            if not module_enabled(db, project_id):
                raise SyncError('Модуль интеграций выключен; отправка остановлена')

    def process_once(self, limit=10):
        processed = 0
        with self.store.connect() as db:
            # Filter paused projects before LIMIT: an inactive queue must never starve active work.
            rows = db.execute("""SELECT o.*,i.project_id,i.provider FROM integration_outbox o
                JOIN integrations i ON i.id=o.integration_id
                JOIN project_modules m ON m.project_id=i.project_id AND m.module_id='integrations'
                WHERE o.status IN ('pending','failed','uncertain') AND o.retry_at<=?
                AND json_extract(i.payload,'$.enabled')=1 AND json_extract(m.payload,'$.enabled')=1
                ORDER BY o.retry_at,o.rowid LIMIT ?""", (time.time(), limit)).fetchall()
        for row in rows:
            if self.stop_event.is_set():
                break
            with self.lock_for(row['project_id'], row['provider']):
                with self.store.transaction() as db:
                    config = self.config(db, row['project_id'], row['provider'])
                    if not config or not config['enabled'] or not module_enabled(db, config['project_id']):
                        continue
                    current = db.execute('SELECT digest,status FROM integration_outbox WHERE integration_id=? AND local_id=?', (config['id'], row['local_id'])).fetchone()
                    if current['digest'] != row['digest'] or current['status'] not in {'pending', 'failed', 'uncertain'}:
                        continue
                    state = current['status']
                    db.execute("UPDATE integration_outbox SET status='processing',attempts=attempts+1 WHERE integration_id=? AND local_id=?", (config['id'], row['local_id']))
                    saved = db.execute('SELECT payload FROM integration_mappings WHERE integration_id=? AND local_id=?', (config['id'], row['local_id'])).fetchone()
                    mapping = json.loads(saved['payload']) if saved else None
                    attempt = db.execute('SELECT payload FROM integration_attempts WHERE integration_id=? AND local_id=?', (config['id'], row['local_id'])).fetchone()
                    recovery_item = json.loads(attempt['payload']) if attempt else None
                    if mapping is None and state != 'uncertain':
                        recovery_item = json.loads(row['payload'])
                        db.execute('INSERT INTO integration_attempts VALUES (?,?,?) ON CONFLICT(integration_id,local_id) DO UPDATE SET payload=excluded.payload', (config['id'], row['local_id'], row['payload']))
                try:
                    with Atlassian(config, self.credential(config['id']), transport=self.transport, guard=lambda: self.require_enabled(config['project_id'])) as client:
                        client.verify_root()
                        item = json.loads(row['payload'])
                        result = client.publish(item, mapping, uncertain=state == 'uncertain', overwrite=item.get('overwrite_remote', False), recovery_item=recovery_item)
                    status, error, retry = 'synced', None, 0
                except SyncError as failure:
                    result = None
                    status = 'uncertain' if failure.uncertain or state == 'uncertain' else 'failed'
                    error, retry = str(failure), time.time() + min(3600, 30 * 2 ** min(row['attempts'], 7))
                except Exception:
                    result = None
                    status = 'uncertain' if mapping is None else 'failed'
                    error, retry = 'Формат ответа Atlassian не подтверждён; проверьте удалённый результат', time.time() + 60
                with self.store.transaction() as db:
                    if result:
                        db.execute('INSERT INTO integration_mappings VALUES (?,?,?) ON CONFLICT(integration_id,local_id) DO UPDATE SET payload=excluded.payload', (config['id'], row['local_id'], encode(result)))
                        db.execute('DELETE FROM integration_attempts WHERE integration_id=? AND local_id=?', (config['id'], row['local_id']))
                    # A newer local revision keeps its own pending state; retain recovered remote ID.
                    db.execute("UPDATE integration_outbox SET status=?,error=?,retry_at=? WHERE integration_id=? AND local_id=? AND digest=? AND status='processing'", (status, error, retry, config['id'], row['local_id'], row['digest']))
                    actor = dict(db.execute("SELECT id,name,kind FROM agents WHERE id='human'").fetchone())
                    self.store.record(db, actor, 'Результат настроенной односторонней синхронизации документации', 'integration', config['id'], 'integration.sync_' + status, None, {'provider': config['provider'], 'local_id': row['local_id'], 'status': status}, project_id=config['project_id'])
                processed += 1
        return processed

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        with self.store.transaction() as db:
            db.execute("UPDATE integration_outbox SET status='uncertain',error='Отправка была прервана; сначала проверяется удалённый результат' WHERE status='processing'")
        self.stop_event.clear()

        def run():
            while not self.stop_event.wait(5):
                try:
                    self.process_once()
                except Exception:
                    # No raw exception, URL, credentials or remote response is ever logged.
                    continue
        self.thread = threading.Thread(target=run, name='dashai-document-sync', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=20)


def install_routes(app, store, actor, authenticated_read, session):
    from .app import now
    service = Integrations(store)
    app.state.integrations = service
    app.add_event_handler('startup', service.start)
    app.add_event_handler('shutdown', service.stop)

    def human(who):
        if who['kind'] != 'human':
            raise HTTPException(403, 'Настройку внешней отправки и учётных данных выполняет человек')

    def version(config, expected):
        if (config['version'] if config else 0) != expected:
            raise HTTPException(409, 'Настройка уже изменена; перечитайте её и подтвердите намерение заново')

    def available(db, project_id):
        store.entity(db, 'projects', project_id)
        if not module_enabled(db, project_id):
            raise HTTPException(409, 'Сначала включите модуль интеграций в этом проекте')

    @app.get('/api/projects/{project_id}/integrations', dependencies=[Depends(authenticated_read)])
    def read_integrations(project_id: str):
        with store.connect() as db:
            store.entity(db, 'projects', project_id)
            values = [service.public(db, json.loads(row['payload'])) for row in db.execute('SELECT payload FROM integrations WHERE project_id=?', (project_id,))]
            return {'integrations': values, 'pending_count': sum(sum(item['counts'].get(status, 0) for status in ('pending', 'processing', 'uncertain', 'failed')) for item in values)}

    @app.put('/api/projects/{project_id}/integrations/{provider}')
    def configure(project_id: str, provider: Provider, body: Configure, request: Request, who=Depends(actor)):
        human(who)
        with service.lock_for(project_id, provider):
            with store.connect() as db:
                available(db, project_id)
                before = service.config(db, project_id, provider)
                version(before, body.expected_version)
            parsed = target(body.url, provider, body.deployment)
            if before and (parsed['base_url'] != before['base_url'] or parsed['root_id'] not in {before['root_id'], before.get('project_key')} or body.deployment != before['deployment']):
                raise HTTPException(409, 'Корень подключения закреплён. Используйте отдельный локальный проект для другого назначения')
            config = (before or {'id': uuid4().hex, 'project_id': project_id, 'provider': provider}) | parsed | {'deployment': body.deployment, 'issue_type_id': body.issue_type_id or (before or {}).get('issue_type_id')}
            if before and provider == 'jira':
                config['root_id'] = before['root_id']
            if body.deployment == 'cloud' and not (body.personal_cloud_token or before and before.get('personal_cloud_token')):
                raise HTTPException(422, 'Cloud API token доступен только в явно выбранном личном режиме. Для публичной интеграции нужен зарегистрированный OAuth 3LO broker')
            try:
                credential = {'email': body.email, 'token': body.token} if body.token else service.credential(config['id'])
            except SyncError as error:
                raise HTTPException(422, str(error)) from None
            if not credential['token'] or any(ord(c) < 33 or ord(c) > 126 for c in credential['token']) or body.deployment == 'cloud' and ('@' not in credential['email'] or ':' in credential['email'] or any(c.isspace() for c in credential['email'])):
                raise HTTPException(422, 'Нужен токен, а для личного Cloud-подключения — email')
            try:
                with Atlassian(config, credential, transport=service.transport, guard=lambda: service.require_enabled(project_id)) as client:
                    config.update(client.verify_root())
            except SyncError as error:
                raise HTTPException(422, str(error)) from None
            config.update(version=(before['version'] if before else 0) + 1, enabled=body.enabled, auto_sync=body.auto_sync,
                          personal_cloud_token=body.deployment == 'cloud', verified_at=now())
            # A random per-connection file is outside DB/audit/idempotency/export. Failed DB
            # writes may leave an unused credential, never an integration without its secret.
            previous = service.credential(config['id']) if before and service.credential_path(config['id']).is_file() else None
            service.save_credential(config['id'], credential)
            try:
                with store.transaction() as db:
                    available(db, project_id)
                    version(service.config(db, project_id, provider), body.expected_version)
                    db.execute('INSERT INTO integrations VALUES (?,?,?,?) ON CONFLICT(project_id,provider) DO UPDATE SET payload=excluded.payload', (config['id'], project_id, provider, encode(config)))
                    enqueue(db, project_id)
                    store.record(db, who, body.reason, 'integration', config['id'], 'integration.configured', before, config, project_id=project_id, session_id=session(request))
                    return service.public(db, config)
            except BaseException:
                if previous:
                    service.save_credential(config['id'], previous)
                else:
                    service.credential_path(config['id']).unlink(missing_ok=True)
                raise

    @app.post('/api/projects/{project_id}/integrations/{provider}/sync')
    def sync(project_id: str, provider: Provider, body: Sync, request: Request, who=Depends(actor)):
        human(who)
        with store.transaction() as db:
            available(db, project_id)
            config = service.config(db, project_id, provider)
            version(config, body.expected_version)
            if not config or not config['enabled']:
                raise HTTPException(409, 'Сначала подключите и включите интеграцию')
            enqueue(db, project_id, force=True, overwrite=body.overwrite_remote, provider=provider)
            store.record(db, who, body.reason, 'integration', config['id'], 'integration.sync_requested', None, {'provider': provider, 'overwrite_remote': body.overwrite_remote}, project_id=project_id, session_id=session(request))
            return service.public(db, config)

    @app.post('/api/projects/{project_id}/integrations/{provider}/disconnect')
    def disconnect(project_id: str, provider: Provider, body: Write, request: Request, who=Depends(actor)):
        human(who)
        with service.lock_for(project_id, provider):
            with store.transaction() as db:
                before = service.config(db, project_id, provider)
                version(before, body.expected_version)
                if not before:
                    raise HTTPException(404, 'Подключение не найдено')
                after = before | {'enabled': False, 'version': before['version'] + 1}
                db.execute('UPDATE integrations SET payload=? WHERE id=?', (encode(after), before['id']))
                store.record(db, who, body.reason, 'integration', before['id'], 'integration.disconnected', before, after, project_id=project_id, session_id=session(request))
            service.credential_path(before['id']).unlink(missing_ok=True)
            with store.connect() as db:
                return service.public(db, after)

    @app.post('/api/projects/{project_id}/integrations/{provider}/resolve')
    def resolve(project_id: str, provider: Provider, body: Resolve, request: Request, who=Depends(actor)):
        human(who)
        with service.lock_for(project_id, provider), store.transaction() as db:
            available(db, project_id)
            config = service.config(db, project_id, provider)
            version(config, body.expected_version)
            if not config or not body.confirm_remote_absent:
                raise HTTPException(422, 'Нужно явно подтвердить проверенное отсутствие удалённого документа')
            result = db.execute("UPDATE integration_outbox SET status='pending',error=NULL,retry_at=0 WHERE integration_id=? AND local_id=? AND status='uncertain'", (config['id'], body.local_id))
            if result.rowcount != 1:
                raise HTTPException(409, 'Неопределённая отправка не найдена; перечитайте состояние')
            store.record(db, who, body.reason, 'integration', config['id'], 'integration.remote_absence_confirmed', None, {'local_id': body.local_id}, project_id=project_id, session_id=session(request))
            return service.public(db, config)
    return service
