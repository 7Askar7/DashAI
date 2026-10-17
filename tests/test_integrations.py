"""Mocked real REST contracts: personal Cloud + Data Center, pinned scope and outbox."""
import base64
import copy
import json
import socket

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import create_app
from server import integrations as integration

BROWSER = {'X-Dashboard-Client': 'browser', 'Origin': 'http://127.0.0.1:8000'}
REASON = 'Публикация документации только в выбранном личном проекте'
TOKEN = 'test-token-never-in-audit-57293'
EMAIL = 'personal@example.test'


class Remote:
    def __init__(self, provider, cloud):
        self.provider, self.cloud = provider, cloud
        self.pages, self.issues, self.requests = {}, {}, []
        self.posts = 0
        self.move_outside = False
        self.timeout_after_create = False
        self.hide_search = False
        self.reject = None

    def page(self, ident, title, body, version=1, parent='100'):
        if self.cloud:
            return {'id': ident, 'spaceId': '7', 'parentId': parent, 'title': title,
                    'status': 'current', 'version': {'number': version}, 'body': {'storage': {'value': body}}}
        return {'id': ident, 'space': {'id': '7', 'key': 'DOC'}, 'ancestors': [{'id': parent}],
                'title': title, 'type': 'page', 'status': 'current', 'version': {'number': version}, 'body': {'storage': {'value': body}}}

    def __call__(self, request):
        expected = 'Basic ' + base64.b64encode(f'{EMAIL}:{TOKEN}'.encode()).decode() if self.cloud else 'Bearer ' + TOKEN
        assert request.headers['authorization'] == expected
        assert request.url.scheme == 'https'
        self.requests.append((request.method, str(request.url)))
        if self.reject:
            return httpx.Response(self.reject, json={'error': 'private remote error ' + TOKEN})
        path, method = request.url.path, request.method
        if self.provider == 'confluence':
            endpoint = '/api/v2/pages' if self.cloud else '/rest/api/content'
            prefix = '/wiki' if self.cloud else '/confluence'
            assert path.startswith(prefix + endpoint)
            suffix = path[len(prefix + endpoint):]
            if method == 'GET' and suffix == '/100':
                return httpx.Response(200, json=self.page('100', 'Pinned root', '', parent='1'))
            if method == 'GET' and not suffix:
                assert request.url.params.get('space-id' if self.cloud else 'spaceKey') == ('7' if self.cloud else 'DOC')
                values = [page for page in self.pages.values() if page['title'] == request.url.params['title']]
                return httpx.Response(200, json={'results': [] if self.hide_search else values})
            if method == 'GET':
                page = copy.deepcopy(self.pages[suffix[1:]])
                if self.move_outside:
                    page.update(parentId='999', ancestors=[{'id': '999'}])
                return httpx.Response(200, json=page)
            body = json.loads(request.content)
            assert body.get('parentId') == '100' if self.cloud else body['ancestors'] == [{'id': '100'}]
            assert body.get('spaceId') == '7' if self.cloud else body['space'] == {'key': 'DOC'}
            content = body['body']['value'] if self.cloud else body['body']['storage']['value']
            if method == 'POST':
                self.posts += 1
                ident = str(1000 + self.posts)
                self.pages[ident] = self.page(ident, body['title'], content)
                if self.timeout_after_create:
                    self.timeout_after_create = False
                    raise httpx.ReadTimeout('private timeout ' + TOKEN, request=request)
                return httpx.Response(200, json=self.pages[ident])
            assert method == 'PUT'
            ident = suffix[1:]
            assert body['version']['number'] == self.pages[ident]['version']['number'] + 1
            self.pages[ident] = self.page(ident, body['title'], content, body['version']['number'])
            return httpx.Response(200, json=self.pages[ident])
        prefix = '/rest/api/3' if self.cloud else '/jira/rest/api/2'
        assert path.startswith(prefix)
        suffix = path[len(prefix):]
        if method == 'GET' and suffix.startswith('/project/'):
            assert suffix in {'/project/TEST', '/project/9'}
            return httpx.Response(200, json={'id': '9', 'key': 'TEST', 'name': 'Pinned Jira', 'issueTypes': [{'id': '11', 'name': 'Subtask', 'subtask': True}, {'id': '12', 'name': 'Task', 'subtask': False}]})
        if method == 'GET' and suffix.startswith('/search'):
            assert 'project = 9 AND labels = "dashai-' in request.url.params['jql']
            marker = request.url.params['jql'].split('"')[1]
            return httpx.Response(200, json={'issues': [] if self.hide_search else [issue for issue in self.issues.values() if marker in issue['fields']['labels']]})
        if method == 'GET':
            issue = copy.deepcopy(self.issues[suffix.split('/')[-1]])
            if self.move_outside:
                issue['fields']['project'] = {'id': '999'}
            return httpx.Response(200, json=issue)
        fields = json.loads(request.content)['fields']
        assert isinstance(fields['description'], dict if self.cloud else str)
        if method == 'POST':
            assert suffix == '/issue' and fields['project'] == {'id': '9'} and fields['issuetype'] == {'id': '12'}
            self.posts += 1
            ident = str(2000 + self.posts)
            self.issues[ident] = {'id': ident, 'key': 'TEST-' + str(self.posts), 'fields': fields}
            if self.timeout_after_create:
                self.timeout_after_create = False
                raise httpx.ReadTimeout('private timeout ' + TOKEN, request=request)
            return httpx.Response(201, json={'id': ident, 'key': 'TEST-' + str(self.posts)})
        assert method == 'PUT' and 'project' not in fields and 'parent' not in fields
        self.issues[suffix.split('/')[-1]]['fields'].update(fields)
        return httpx.Response(204)


def configuration(provider, cloud):
    if provider == 'confluence':
        url = 'https://team.atlassian.net/wiki/spaces/DOC/pages/100/Root' if cloud else 'https://docs.example.internal:8443/confluence/pages/viewpage.action?pageId=100'
    else:
        url = 'https://team.atlassian.net/jira/software/c/projects/TEST/boards/1' if cloud else 'https://jira.example.internal/jira/projects/TEST'
    return {'url': url, 'deployment': 'cloud' if cloud else 'data_center', 'email': EMAIL if cloud else '',
            'token': TOKEN, 'personal_cloud_token': cloud, 'expected_version': 0, 'reason': REASON}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(integration, 'validate_host', lambda _: None)
    app = create_app(tmp_path)
    # Background threads are exercised separately; deterministic tests run one batch explicitly.
    app.router.on_startup = [handler for handler in app.router.on_startup if getattr(handler, '__self__', None) is not app.state.integrations]
    with TestClient(app, base_url='http://127.0.0.1:8000') as client:
        app.state.integrations.stop_event.clear()
        project = client.post('/api/projects', json={'name': 'Project', 'description': 'Local explanation', 'reason': REASON}, headers=BROWSER).json()
        response = client.put(f"/api/projects/{project['id']}/modules/integrations", json={'expected_version': 0, 'enabled': True, 'reason': REASON}, headers=BROWSER)
        assert response.status_code == 200, response.text
        yield app, client, project


@pytest.mark.parametrize('provider', ['confluence', 'jira'])
@pytest.mark.parametrize('cloud', [False, True])
def test_personal_cloud_and_dc_scope_retry_and_secret_isolation(workspace, provider, cloud):
    app, client, project = workspace
    service = app.state.integrations
    remote = Remote(provider, cloud)
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/{provider}"
    response = client.put(endpoint, json=configuration(provider, cloud), headers=BROWSER)
    assert response.status_code == 200, response.text
    config = response.json()
    assert config['credential_present'] and config['verified_at'] and config['root_title'].startswith('Pinned')
    assert config['root_id'] == ('100' if provider == 'confluence' else '9')
    assert config['counts'] == {'pending': 1}
    assert service.process_once() == 1 and remote.posts == 1
    with service.store.connect() as db:
        assert db.execute('SELECT status FROM integration_outbox').fetchone()[0] == 'synced'
        assert db.execute('SELECT count(*) FROM integration_mappings').fetchone()[0] == 1
    # Repeating a send does not create a duplicate or an unnecessary remote revision.
    assert client.post(endpoint + '/sync', json={'expected_version': 1, 'reason': REASON}, headers=BROWSER).status_code == 200
    assert service.process_once() == 0 and remote.posts == 1
    # Updating metadata does a real GET, keeps immutable scope and never returns email/token.
    changed = configuration(provider, cloud) | {'expected_version': 1, 'token': '', 'auto_sync': False}
    response = client.put(endpoint, json=changed, headers=BROWSER)
    assert response.status_code == 200, response.text
    assert response.json()['version'] == 2
    assert client.put(endpoint, json=changed, headers=BROWSER).status_code == 409
    read = client.get(f"/api/projects/{project['id']}/integrations").text
    history = client.get(f"/api/history?project_id={project['id']}").text
    exported = client.get(f"/api/projects/{project['id']}/export").text
    assert all(TOKEN not in value and EMAIL not in value for value in (read, history, exported))
    with service.store.connect() as db:
        assert TOKEN not in '\n'.join(str(tuple(row)) for row in db.execute('SELECT * FROM idempotency'))
    # New descriptions stay local while auto-sync is disabled; manual sync sends the new revision.
    patch = client.patch(f"/api/projects/{project['id']}", json={'expected_version': project['version'], 'changes': {'description': 'Revised description'}, 'reason': REASON}, headers=BROWSER)
    assert patch.status_code == 200, patch.text
    assert service.process_once() == 0
    assert client.post(endpoint + '/sync', json={'expected_version': 2, 'reason': REASON}, headers=BROWSER).status_code == 200
    assert service.process_once() == 1 and remote.posts == 1
    # A moved page/issue is read but never updated outside the pinned root/project.
    remote.move_outside = True
    with service.store.transaction() as db:
        db.execute("UPDATE integration_outbox SET status='pending',retry_at=0")
    before_writes = sum(method == 'PUT' for method, _ in remote.requests)
    service.process_once()
    assert sum(method == 'PUT' for method, _ in remote.requests) == before_writes
    public = client.get(f"/api/projects/{project['id']}/integrations").json()['integrations'][0]
    assert public['counts']['failed'] == 1 and 'запрещена' in public['errors'][0]['error']
    # Disconnect keeps mappings/data and removes credentials; disabled means no network traffic.
    response = client.post(endpoint + '/disconnect', json={'expected_version': 2, 'reason': REASON}, headers=BROWSER)
    assert response.status_code == 200 and not response.json()['credential_present']
    requests = len(remote.requests)
    assert service.process_once() == 0 and len(remote.requests) == requests


@pytest.mark.parametrize('provider', ['confluence', 'jira'])
def test_ambiguous_create_recovers_without_duplicate_and_survives_local_edit(workspace, provider):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote(provider, True)
    remote.timeout_after_create = True
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/{provider}"
    assert client.put(endpoint, json=configuration(provider, True), headers=BROWSER).status_code == 200
    service.process_once()
    with service.store.connect() as db:
        assert db.execute('SELECT status FROM integration_outbox').fetchone()[0] == 'uncertain'
    # Rename while POST result is uncertain: the old intended title remains a recovery key.
    response = client.patch(f"/api/projects/{project['id']}", json={'expected_version': 1, 'changes': {'name': 'New name'}, 'reason': REASON}, headers=BROWSER)
    assert response.status_code == 200
    service.process_once()
    assert remote.posts == 1
    public = client.get(f"/api/projects/{project['id']}/integrations").json()['integrations'][0]
    assert public['counts']['synced'] == 1 and not public['errors']
    assert TOKEN not in json.dumps(public)


def test_unknown_remote_result_never_blindly_retries_create(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', True)
    remote.timeout_after_create = True
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/jira"
    assert client.put(endpoint, json=configuration('jira', True), headers=BROWSER).status_code == 200
    service.process_once()
    remote.hide_search = True
    with service.store.transaction() as db:
        db.execute('UPDATE integration_outbox SET retry_at=0')
    service.process_once()
    assert remote.posts == 1
    response = client.post(endpoint + '/sync', json={'expected_version': 1, 'reason': REASON}, headers=BROWSER)
    assert response.json()['counts']['uncertain'] == 1
    assert client.post(endpoint + '/resolve', json={'expected_version': 1, 'reason': REASON, 'local_id': 'project', 'confirm_remote_absent': False}, headers=BROWSER).status_code == 422


@pytest.mark.parametrize('provider', ['confluence', 'jira'])
def test_remote_manual_edits_require_explicit_versioned_overwrite(workspace, provider):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote(provider, True)
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/{provider}"
    assert client.put(endpoint, json=configuration(provider, True), headers=BROWSER).status_code == 200
    service.process_once()
    if provider == 'confluence':
        remote.pages['1001']['version']['number'] += 1
    else:
        remote.issues['2001']['fields']['description'] = {'type': 'doc', 'version': 1, 'content': []}
    patch = client.patch(f"/api/projects/{project['id']}", json={'expected_version': 1, 'changes': {'description': 'New local text'}, 'reason': REASON}, headers=BROWSER)
    assert patch.status_code == 200
    writes = sum(method == 'PUT' for method, _ in remote.requests)
    service.process_once()
    assert sum(method == 'PUT' for method, _ in remote.requests) == writes
    public = client.get(f"/api/projects/{project['id']}/integrations").json()['integrations'][0]
    assert public['counts']['failed'] == 1 and 'изменен' in public['errors'][0]['error'].replace('ё', 'е')
    response = client.post(endpoint + '/sync', json={'expected_version': 1, 'overwrite_remote': True, 'reason': REASON}, headers=BROWSER)
    assert response.status_code == 200
    assert service.process_once() == 1 and remote.posts == 1
    assert client.get(f"/api/projects/{project['id']}/integrations").json()['integrations'][0]['counts']['synced'] == 1


def test_permissions_authentication_and_personal_cloud_opt_in(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', True)
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/jira"
    config = configuration('jira', True)
    response = client.put(endpoint, json=config | {'personal_cloud_token': False}, headers=BROWSER)
    assert response.status_code == 422 and len(remote.requests) == 0
    response = client.put(endpoint, json=config | {'token': 'non-ascii-ключ'}, headers=BROWSER)
    assert response.status_code == 422 and len(remote.requests) == 0
    secrets = json.loads(service.store.credentials_file.read_text(encoding='utf-8'))
    agent_token = secrets['agents']['codex']['token']
    response = client.put(endpoint, json=config, headers={'Authorization': 'Bearer ' + agent_token})
    assert response.status_code == 403 and len(remote.requests) == 0
    assert client.put(endpoint, json=config, headers=BROWSER).status_code == 200
    raw_db = service.store.path.read_bytes()
    # WAL may contain commits; both storage files must exclude external credentials.
    wal = service.store.path.with_suffix('.sqlite3-wal')
    assert TOKEN.encode() not in raw_db and (not wal.exists() or TOKEN.encode() not in wal.read_bytes())


def test_interrupted_worker_recovers_outbox_without_destroying_configuration(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', False)
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/jira"
    assert client.put(endpoint, json=configuration('jira', False), headers=BROWSER).status_code == 200
    with service.store.transaction() as db:
        db.execute("UPDATE integration_outbox SET status='processing'")
    service.start()
    service.stop()
    with service.store.connect() as db:
        assert db.execute('SELECT status FROM integration_outbox').fetchone()[0] == 'uncertain'
        assert db.execute('SELECT count(*) FROM integrations').fetchone()[0] == 1
    assert service.credential_path(client.get(f"/api/projects/{project['id']}/integrations").json()['integrations'][0]['id']).is_file()


def test_paused_queues_do_not_starve_later_active_projects(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', False)
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/jira"
    response = client.put(endpoint, json=configuration('jira', False), headers=BROWSER)
    assert response.status_code == 200
    active = response.json()
    with service.store.transaction() as db:
        queued = dict(db.execute('SELECT * FROM integration_outbox').fetchone())
        db.execute('DELETE FROM integration_outbox')
        for index in range(12):
            paused_id = 'paused-' + str(index)
            paused_project = project | {'id': paused_id}
            db.execute('INSERT INTO projects VALUES (?,?)', (paused_id, json.dumps(paused_project)))
            db.execute('INSERT INTO project_modules VALUES (?,?,?)', (paused_id, 'integrations', json.dumps({'enabled': index % 2 == 0, 'version': 1})))
            config = {key: value for key, value in active.items() if key not in {'counts', 'errors', 'credential_present'}}
            config.update(id=paused_id, project_id=paused_id, enabled=index % 2 != 0)
            db.execute('INSERT INTO integrations VALUES (?,?,?,?)', (paused_id, paused_id, 'jira', json.dumps(config)))
            db.execute('INSERT INTO integration_outbox VALUES (?,?,?,?,?,0,0,NULL)', (paused_id, 'project', queued['digest'], queued['payload'], 'pending'))
        integration.enqueue(db, project['id'], force=True)
    assert service.process_once(limit=10) == 1
    assert remote.posts == 1
    with service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM integration_outbox WHERE status='pending'").fetchone()[0] == 12
        assert db.execute("SELECT status FROM integration_outbox WHERE integration_id=?", (active['id'],)).fetchone()[0] == 'synced'


def test_edit_during_remote_request_keeps_new_revision_and_recovered_mapping(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', True)
    changed = False
    def transport(request):
        nonlocal changed
        response = remote(request)
        if request.method == 'POST' and not changed:
            changed = True
            patch = client.patch(f"/api/projects/{project['id']}", json={'expected_version': 1, 'changes': {'description': 'Edited while publishing'}, 'reason': REASON}, headers=BROWSER)
            assert patch.status_code == 200
        return response
    service.transport = httpx.MockTransport(transport)
    endpoint = f"/api/projects/{project['id']}/integrations/jira"
    assert client.put(endpoint, json=configuration('jira', True), headers=BROWSER).status_code == 200
    service.process_once()
    with service.store.connect() as db:
        assert 'Edited while publishing' in db.execute('SELECT payload FROM integration_outbox').fetchone()[0]
        assert db.execute('SELECT status FROM integration_outbox').fetchone()[0] != 'synced'
        assert db.execute('SELECT count(*) FROM integration_mappings').fetchone()[0] == 1
    service.process_once()
    assert remote.posts == 1
    assert 'Edited while publishing' in json.dumps(remote.issues, ensure_ascii=False)


@pytest.mark.parametrize('new_content', [False, True])
def test_unknown_post_survives_module_removal_and_same_or_revised_reenable(workspace, new_content):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', True)
    service.transport = httpx.MockTransport(remote)
    module = f"/api/projects/{project['id']}/modules/decisions"
    assert client.put(module, json={'expected_version': 0, 'enabled': True, 'content': 'Original ADR', 'reason': REASON}, headers=BROWSER).status_code == 200
    endpoint = f"/api/projects/{project['id']}/integrations/jira"
    assert client.put(endpoint, json=configuration('jira', True), headers=BROWSER).status_code == 200
    service.process_once(limit=1)  # Project intro succeeds.
    remote.timeout_after_create = True
    service.process_once(limit=1)  # ADR creation succeeds remotely but response is lost.
    assert remote.posts == 2
    assert client.put(module, json={'expected_version': 1, 'enabled': False, 'reason': REASON}, headers=BROWSER).status_code == 200
    with service.store.connect() as db:
        assert db.execute("SELECT status FROM integration_outbox WHERE local_id='module:decisions'").fetchone()[0] == 'removed_uncertain'
    assert client.put(module, json={'expected_version': 2, 'enabled': True, 'content': 'Revised ADR' if new_content else 'Original ADR', 'reason': REASON}, headers=BROWSER).status_code == 200
    remote.hide_search = True
    service.process_once()
    assert remote.posts == 2
    with service.store.connect() as db:
        assert db.execute("SELECT status FROM integration_outbox WHERE local_id='module:decisions'").fetchone()[0] == 'uncertain'
    remote.hide_search = False
    with service.store.transaction() as db:
        db.execute('UPDATE integration_outbox SET retry_at=0')
    service.process_once()
    assert remote.posts == 2
    with service.store.connect() as db:
        assert db.execute("SELECT status FROM integration_outbox WHERE local_id='module:decisions'").fetchone()[0] == 'synced'


def test_synced_module_reenabled_with_unchanged_text_resumes_automatically(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('jira', True)
    service.transport = httpx.MockTransport(remote)
    module = f"/api/projects/{project['id']}/modules/decisions"
    assert client.put(module, json={'expected_version': 0, 'enabled': True, 'content': 'ADR', 'reason': REASON}, headers=BROWSER).status_code == 200
    assert client.put(f"/api/projects/{project['id']}/integrations/jira", json=configuration('jira', True), headers=BROWSER).status_code == 200
    service.process_once()
    assert client.put(module, json={'expected_version': 1, 'enabled': False, 'reason': REASON}, headers=BROWSER).status_code == 200
    assert client.put(module, json={'expected_version': 2, 'enabled': True, 'reason': REASON}, headers=BROWSER).status_code == 200
    assert service.process_once() == 1 and remote.posts == 2


@pytest.mark.parametrize('provider', ['confluence', 'jira'])
def test_recovered_unknown_creation_never_approves_remote_human_edit(workspace, provider):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote(provider, True)
    service.transport = httpx.MockTransport(remote)
    remote.timeout_after_create = True
    endpoint = f"/api/projects/{project['id']}/integrations/{provider}"
    assert client.put(endpoint, json=configuration(provider, True), headers=BROWSER).status_code == 200
    service.process_once()
    human_text = 'Human addition that must survive'
    if provider == 'confluence':
        remote.pages['1001']['body']['storage']['value'] += '<p>' + human_text + '</p>'
        remote.pages['1001']['version']['number'] += 1
    else:
        remote.issues['2001']['fields']['description']['content'].append({'type': 'paragraph', 'content': [{'type': 'text', 'text': human_text}]})
    with service.store.transaction() as db:
        db.execute('UPDATE integration_outbox SET retry_at=0')
    service.process_once()
    assert not any(method == 'PUT' for method, _ in remote.requests)
    assert remote.posts == 1 and human_text in json.dumps(remote.pages if provider == 'confluence' else remote.issues)
    public = client.get(f"/api/projects/{project['id']}/integrations").json()['integrations'][0]
    assert public['counts']['uncertain'] == 1


def test_module_off_no_network_root_retarget_rejected_and_remote_errors_sanitized(workspace):
    app, client, project = workspace
    service, remote = app.state.integrations, Remote('confluence', False)
    service.transport = httpx.MockTransport(remote)
    endpoint = f"/api/projects/{project['id']}/integrations/confluence"
    config = configuration('confluence', False)
    assert client.put(endpoint, json=config, headers=BROWSER).status_code == 200
    retarget = config | {'expected_version': 1, 'url': config['url'].replace('pageId=100', 'pageId=999')}
    assert client.put(endpoint, json=retarget, headers=BROWSER).status_code == 409
    remote.reject = 403
    service.process_once()
    response = client.get(f"/api/projects/{project['id']}/integrations")
    assert TOKEN not in response.text and 'HTTP 403' in response.text
    assert client.put(f"/api/projects/{project['id']}/modules/integrations", json={'expected_version': 1, 'enabled': False, 'reason': REASON}, headers=BROWSER).status_code == 200
    requests = len(remote.requests)
    assert client.post(endpoint + '/sync', json={'expected_version': 1, 'reason': REASON}, headers=BROWSER).status_code == 409
    assert service.process_once() == 0 and len(remote.requests) == requests


def test_document_material_includes_diagrams_and_enabled_custom_modules(workspace):
    app, client, project = workspace
    service = app.state.integrations
    with service.store.transaction() as db:
        project_map = {'files': [{'path': 'src/app.py', 'description': {'title': 'Entry', 'summary': '<script>text</script>', 'purpose': 'Run API'}}],
                       'diagrams': [{'id': 'system', 'title': 'Architecture', 'notation': 'flowchart', 'source': 'flowchart LR\nA-->B'}],
                       'document': {'title': 'Overview', 'context': 'Technical context', 'sections': ['intro', 'files', 'diagrams']}}
        db.execute('INSERT INTO project_maps VALUES (?,?)', (project['id'], json.dumps(project_map)))
        db.execute('INSERT INTO project_modules VALUES (?,?,?)', (project['id'], 'decisions', json.dumps({'enabled': True, 'content': '# Decision\nLocal reason', 'version': 1})))
        values = integration.documents(db, project['id'])
        assert {item['local_id'] for item in values} == {'project', 'file:src/app.py', 'diagram:system', 'module:decisions'}
        assert any('```mermaid\nflowchart' in item['text'] for item in values)
        db.execute('INSERT INTO project_modules VALUES (?,?,?)', (project['id'], 'map', json.dumps({'enabled': False, 'version': 1})))
        assert 'file:src/app.py' not in {item['local_id'] for item in integration.documents(db, project['id'])}


@pytest.mark.parametrize('url,provider,deployment', [
    ('http://host/projects/TEST', 'jira', 'data_center'),
    ('https://user:secret@host/projects/TEST', 'jira', 'data_center'),
    ('https://localhost/projects/TEST', 'jira', 'data_center'),
    ('https://evil.example/projects/TEST', 'jira', 'cloud'),
    ('https://team.atlassian.net/projects/TEST?token=private', 'jira', 'cloud'),
    ('https://host/pages/viewpage.action?pageId=123&token=private', 'confluence', 'data_center'),
])
def test_untrusted_links_rejected(url, provider, deployment):
    with pytest.raises(HTTPException):
        integration.target(url, provider, deployment)


@pytest.mark.parametrize('address', ['127.0.0.1', '::1', '169.254.169.254', 'fe80::1', '0.0.0.0', '224.0.0.1'])
def test_metadata_and_loopback_hosts_rejected(monkeypatch, address):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *_args, **_kw: [(None, None, None, '', (address, 443))])
    with pytest.raises(integration.SyncError):
        integration.validate_host('https://internal.example')


@pytest.mark.parametrize('address', ['10.1.2.3', '192.168.0.4', 'fd00::10'])
def test_private_data_center_https_allowed(monkeypatch, address):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *_args, **_kw: [(None, None, None, '', (address, 8443))])
    integration.validate_host('https://internal.example:8443/confluence')


def test_redirect_does_not_leak_authorization(monkeypatch):
    monkeypatch.setattr(integration, 'validate_host', lambda _: None)
    seen = []
    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'https://evil.example/credentials'})
    config = {'id': 'id', 'provider': 'jira', 'deployment': 'data_center', 'base_url': 'https://jira.example', 'root_id': 'TEST'}
    with integration.Atlassian(config, {'token': TOKEN}, transport=httpx.MockTransport(redirect)) as client:
        with pytest.raises(integration.SyncError):
            client.verify_root()
    assert seen == ['https://jira.example/rest/api/2/project/TEST']
