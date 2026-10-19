import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from server import create_app

BROWSER = {"X-Dashboard-Client": "browser"}


def test_modules_isolate_projects_preserve_content_and_audit(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:4242") as client:
        first, other = [client.post("/api/projects", headers=BROWSER, json={"name": name, "reason": "Module test"}).json()["id"] for name in ("One", "Two")]
        root = f"/api/projects/{first}/modules"
        modules = {m["id"]: m for m in client.get(root).json()["modules"]}
        assert modules["map"]["enabled"] and not modules["integrations"]["enabled"]
        token = json.loads((tmp_path / "connector-secrets.json").read_text())["agents"]["codex"]["token"]
        agent = {"Authorization": "Bearer " + token}
        body = {"expected_version": 0, "enabled": True, "content": "## Decision\nChosen SQLite", "reason": "Capture decision", "idempotency_key": "decision"}
        saved = client.put(root + "/decisions", headers=agent, json=body).json()
        assert saved["version"] == 1 and saved["enabled"]
        assert client.put(root + "/decisions", headers=agent, json=body).json() == saved
        assert client.put(root + "/decisions", headers=agent, json={**body, "content": "Different"}).status_code == 409
        assert client.put(root + "/decisions", headers=BROWSER, json={"expected_version": 1, "enabled": False, "reason": "Hide module"}).json()["content"] == body["content"]
        reenabled = client.put(root + "/decisions", headers=BROWSER, json={"expected_version": 2, "enabled": True, "reason": "Use again"}).json()
        assert reenabled["content"] == body["content"] and reenabled["version"] == 3
        assert not next(m for m in client.get(f"/api/projects/{other}/modules").json()["modules"] if m["id"] == "decisions")["enabled"]
        assert client.put(root + "/no-such-module", headers=BROWSER, json={"expected_version": 0, "enabled": True, "reason": "Invalid module"}).status_code == 404
        assert client.put(root + "/map", headers=BROWSER, json={"expected_version": 0, "enabled": True, "content": "No", "reason": "Invalid content"}).status_code == 422
        # Project polling carries flags, never full document bodies.
        flags = client.get(f"/api/projects/{first}").json()["modules"]
        assert all("content" not in item and "template" not in item for item in flags)
        export = client.get(f"/api/projects/{first}/export").json()
        decision = next(m for m in export["modules"] if m["id"] == "decisions")
        assert decision["content"] == body["content"]
        events = [event for event in export["events"] if event["action"] == "project_module.updated"]
        assert len(events) == 3 and events[0]["actor_id"] == "codex"
        assert events[0]["after"]["content"] == body["content"]
        template = client.post("/api/modules", headers=BROWSER, json={"name": "Release checklist", "template": "## Release\n- [ ] Smoke", "reason": "Reusable module", "idempotency_key": "template"}).json()
        assert template["kind"] == "document"
        for project in (first, other):
            instance = next(m for m in client.get(f"/api/projects/{project}/modules").json()["modules"] if m["id"] == template["id"])
            assert not instance["enabled"] and instance["content"] == template["template"]
        # Two independent writers cannot overwrite each other's draft silently.
        update = {"expected_version": 0, "enabled": True, "reason": "Concurrent edit"}
        with ThreadPoolExecutor(2) as pool:
            codes = list(pool.map(lambda value: client.put(root + "/" + template["id"], headers=BROWSER, json={**update, "content": value}).status_code, ("A", "B")))
        assert sorted(codes) == [200, 409]
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1:4242") as client:
        state = client.get(root).json()["modules"]
        assert next(m for m in state if m["id"] == "decisions")["content"] == body["content"]


def test_polling_omits_large_module_snapshots_before_python_parsing_without_losing_audit(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:4242") as client:
        project = client.post("/api/projects", headers=BROWSER, json={"name": "Large documentation", "reason": "Polling regression"}).json()
        root = f"/api/projects/{project['id']}"
        first, second = "first revision\n" + "a" * 190000, "second revision\n" + "b" * 190000
        for version, content in enumerate((first, second)):
            response = client.put(root + "/modules/decisions", headers=BROWSER, json={"expected_version": version, "enabled": True, "content": content, "reason": "Record large document"})
            assert response.status_code == 200, response.text
        store = app.state.store
        with store.connect() as db:
            original_rows = [tuple(row) for row in db.execute("SELECT * FROM events ORDER BY id")]
        decode_event, projected_ids = type(store).event, []

        def inspect_projection(row):
            if row["entity_type"] == "project_module":
                # Assert the SQLite result is already small, before Store.event calls json.loads.
                for field in ("before_json", "after_json"):
                    assert "content" not in json.loads(row[field])
                    assert len(row[field]) < 1000
                projected_ids.append(row["id"])
            return decode_event(row)

        with monkeypatch.context() as polling:
            polling.setattr(type(store), "event", staticmethod(inspect_projection))
            for endpoint in ("/api/bootstrap", root):
                response = client.get(endpoint)
                assert response.status_code == 200 and len(response.content) < 10000
                events = response.json()["activity"]
                assert len([event for event in events if event["entity_type"] == "project_module"]) == 2
                assert next(event for event in events if event["action"] == "project.created")["after"]["name"] == project["name"]
        assert len(projected_ids) == 4
        history = client.get("/api/history", params={"project_id": project["id"]}).json()["events"]
        exported = client.get(root + "/export").json()
        assert exported["events"] == history
        changes = [event for event in history if event["entity_type"] == "project_module"]
        assert changes[0]["after"]["content"] == first
        assert changes[1]["before"]["content"] == first and changes[1]["after"]["content"] == second
        assert next(module for module in exported["modules"] if module["id"] == "decisions")["content"] == second
        with store.connect() as db:
            assert [tuple(row) for row in db.execute("SELECT * FROM events ORDER BY id")] == original_rows
