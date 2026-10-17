import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from server import create_app

BROWSER = {'X-Dashboard-Client': 'browser'}


def test_large_project_snapshot_preserves_all_paths_and_rejects_overflow(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1:4242') as client:
        project = client.post('/api/projects', json={'name': 'Large repository', 'reason': 'Check large snapshot'}, headers=BROWSER).json()
        url = f"/api/projects/{project['id']}/map"
        files = [{'path': f'packages/area-{index // 100}/file-{index}.ts', 'sha256': '1' * 64,
                  'description': {'title': f'Module {index}', 'summary': 'Describe a large source snapshot', 'purpose': 'Keep every file reachable'}} for index in range(10000)]
        payload = {'expected_version': 0, 'source_revision': 'large-source', 'files': files, 'reason': 'Publish full permitted snapshot'}
        response = client.put(url, headers=BROWSER, json=payload)
        assert response.status_code == 200, response.text
        saved = client.get(url).json()
        assert len(saved['files']) == 10000 and saved['files'][-1]['path'] == files[-1]['path']
        events = len(client.get(f"/api/projects/{project['id']}/export").json()['events'])
        overflow = {**payload, 'expected_version': 1, 'files': files + [{'path': 'overflow.ts', 'sha256': '2' * 64}]}
        assert client.put(url, headers=BROWSER, json=overflow).status_code == 422
        assert client.get(url).json()['version'] == 1
        assert len(client.get(f"/api/projects/{project['id']}/export").json()['events']) == events


def test_project_map_shared_versions_safety_audit_and_restart(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:4242') as client:
        token = json.loads((tmp_path / 'connector-secrets.json').read_text())['agents']['codex']['token']
        agent = {'Authorization': 'Bearer ' + token}
        project = client.post('/api/projects', json={'name': 'Documentation', 'reason': 'Test'}, headers=BROWSER).json()
        url = f"/api/projects/{project['id']}/map"
        assert client.get(url).json()['version'] == 0
        description = {'title': 'HTTP API', 'summary': 'Shared rules', 'purpose': 'Preserve data', 'workflow': ['Validate', 'Save atomically'], 'related_paths': ['src/App.tsx']}
        files = [{'path': 'server/app.py', 'sha256': '1' * 64, 'description': description}, {'path': 'src/App.tsx', 'sha256': '2' * 64}]
        diagram = {'id': 'containers', 'title': 'Containers', 'notation': 'c4_containers', 'scope': 'API', 'explanation': 'Shared server', 'legend': 'Arrow: request', 'source': 'flowchart LR\n UI --> API', 'related_paths': ['server/app.py']}
        payload = {'expected_version': 0, 'source_revision': 'snapshot-1', 'files': files, 'diagrams': [diagram], 'reason': 'Publish analysis', 'idempotency_key': 'first'}
        def put(value, expected=200):
            response = client.put(url, json=value, headers=agent)
            assert response.status_code == expected, response.text
            return response.json()
        assert put(payload)['version'] == 1
        assert put(payload)['version'] == 1
        value = client.get(url).json()
        assert value['files'][0]['author_name'] == 'Codex' and value['files'][0]['status'] == 'draft'
        assert client.post(url + '/review', json={'expected_version': 1, 'path': files[0]['path'], 'reason': 'Checked'}, headers=agent).status_code == 403
        assert client.post(url + '/review', json={'expected_version': 1, 'path': files[0]['path'], 'reason': 'Compared source'}, headers=BROWSER).json()['version'] == 2
        changed = {'expected_version': 2, 'source_revision': 'snapshot-2', 'files': [{'path': 'server/app.py', 'sha256': '3'*64}, files[1]], 'reason': 'Changed source'}
        assert put(changed)['version'] == 3
        value = client.get(url).json()
        assert value['files'][0]['description'] == description
        assert value['files'][0]['status'] == value['diagrams'][0]['status'] == 'stale'
        assert value['files'][0]['described_sha256'] == '1'*64
        assert client.post(url + '/review', json={'expected_version': 3, 'path': files[0]['path'], 'reason': 'Cannot check stale'}, headers=BROWSER).status_code == 409
        put(changed, 409)
        assert client.get(url + '?version=2').json()['files'][0]['status'] == 'reviewed'
        # Related file changes and directory-scoped diagrams invalidate prior review too.
        other = client.post('/api/projects', json={'name': 'Related source changes', 'reason': 'Regression'}, headers=BROWSER).json()
        related_url = f"/api/projects/{other['id']}/map"
        related_files = [files[0], {'path': 'src', 'kind': 'directory'}, files[1]]
        published = client.put(related_url, json={**payload, 'files': related_files, 'diagrams': [{**diagram, 'related_paths': ['src']}]}, headers=agent)
        assert published.status_code == 200, published.text
        for version, target in [(1, {'path': files[0]['path']}), (2, {'diagram_id': diagram['id']})]:
            assert client.post(related_url+'/review', json={'expected_version':version, **target, 'reason':'Reviewed'},headers=BROWSER).status_code == 200
        related_files = [{k:v for k,v in f.items() if k != 'description'} for f in related_files]
        related_files[-1]['sha256'] = '4'*64
        assert client.put(related_url,json={'expected_version':3,'source_revision':'related-change','files':related_files,'reason':'Related source changed'},headers=agent).status_code == 200
        related = client.get(related_url).json()
        assert related['files'][0]['status'] == related['diagrams'][0]['status'] == 'stale'
        assert client.put(related_url,json={'expected_version':4,'source_revision':'related-removed','files':related_files[:-1],'reason':'Source removed'},headers=agent).status_code == 200
        assert client.get(related_url).json()['files'][0]['status'] == 'stale'
        config = {'title': 'Project documentation', 'sections': ['intro', 'diagrams'], 'diagram_ids': ['containers']}
        response = client.patch(url + '/document', json={'expected_version': 3, 'document': config, 'reason': 'Compose'}, headers=BROWSER)
        assert response.status_code == 200, response.text
        assert response.json()['version'] == 4
        assert client.get(url).json()['document']['diagram_ids'] == ['containers']
        for path in ['../secret', '/etc/passwd', 'C:/private', 'a\\b', '.env', 'data/state.json', '.git/config', 'a//b', 'a/./b', 'connector-secrets.json']:
            put({**changed, 'expected_version': 4, 'files': [{'path': path, 'sha256': '1'*64}]}, 422)
        for source in ['flowchart LR\n click A "https://example.org"', '%%{init:{}}%%\nflowchart LR\n A-->B', 'sequenceDiagram\n A->>B:Hi', 'flowchart LR\n A["<img src=x>"]']:
            put({**changed, 'expected_version': 4, 'diagrams': [{**diagram, 'source': source}]}, 422)
        put({**changed, 'expected_version': 4, 'files': [files[0]]}, 422)
        assert client.put(url, json=payload, headers={'Authorization': 'Bearer invalid'}).status_code == 401
        barrier = Barrier(2)
        def race(index):
            barrier.wait()
            return client.put(url, json={**changed, 'expected_version': 4, 'source_revision': f'race-{index}'}, headers=agent).status_code
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(race, [1, 2])) == [200, 409]
        assert client.get(url).json()['version'] == 5
        with monkeypatch.context() as context:
            context.setattr(app.state.store, 'record', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('audit failed')))
            with pytest.raises(RuntimeError, match='audit failed'):
                put({**changed, 'expected_version': 5})
        assert client.get(url).json()['version'] == 5
        assert client.get(url + '?version=6').status_code == 404
        exported = client.get(f"/api/projects/{project['id']}/export").json()
        assert exported['project_map']['version'] == 5 and len(exported['project_map_revisions']) == 5
        assert len([e for e in exported['events'] if e['entity_type'] == 'project_map']) == 5
        assert all('files' not in (e['after'] or {}) for e in exported['events'] if e['entity_type'] == 'project_map')
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1:4242') as restarted:
        assert restarted.get(url).json()['version'] == 5
        assert restarted.get(url + '?version=1').json()['files'][0]['description'] == description
