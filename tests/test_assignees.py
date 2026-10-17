import json

from fastapi.testclient import TestClient

from server import create_app


BROWSER = {"X-Dashboard-Client": "browser", "Origin": "http://127.0.0.1:8000"}
REASON = "Сохраняем исполнителя для повторного выбора в проектах"


def post(client, path, **payload):
    response = client.post(path, json={"reason": REASON, **payload}, headers=BROWSER)
    assert response.status_code == 200, response.text
    return response.json()


def test_global_assignee_without_credentials_survives_restart_and_reuses_id(tmp_path):
    app = create_app(tmp_path)
    credentials = app.state.store.credentials_file.read_bytes()
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        payload = {"name": "  Команда Qwen / Анна  ", "kind": "custom", "issue_token": False, "idempotency_key": "saved-assignee"}
        result = post(client, "/api/agents", **payload)
        agent = result["agent"]
        assert result["token"] is None and agent["name"] == "Команда Qwen / Анна"
        assert agent["kind"] == "custom" and agent["last_seen"] is None
        assert post(client, "/api/agents", **payload) == result
        assert client.post("/api/agents", json={**payload, "name": "Другой исполнитель", "reason": REASON}, headers=BROWSER).status_code == 409
        tasks = []
        for name in ("Первый проект", "Другой проект"):
            project = post(client, "/api/projects", name=name)
            task = post(client, "/api/tasks", project_id=project["id"], title="Общая команда", rationale=REASON, assignee_id=agent["id"])
            tasks.append(task)
            assert client.get(f"/api/projects/{project['id']}").json()["tasks"][0]["assignee_id"] == agent["id"]
        changed = client.patch(f"/api/tasks/{tasks[0]['id']}", json={"expected_version": 1, "changes": {"assignee_id": "codex"}, "reason": REASON}, headers=BROWSER)
        assert changed.status_code == 200
        restored = client.patch(f"/api/tasks/{tasks[0]['id']}", json={"expected_version": 2, "changes": {"assignee_id": agent["id"]}, "reason": REASON}, headers=BROWSER)
        assert restored.status_code == 200 and restored.json()["assignee_id"] == agent["id"]
        events = client.get("/api/history?limit=500").json()["events"]
        assert len([event for event in events if event["action"] == "agent.created"]) == 1
        assert "token_hash" not in json.dumps(events)
    with app.state.store.connect() as db:
        assert db.execute("SELECT token_hash FROM agents WHERE id=?", (agent["id"],)).fetchone()[0] is None
    restarted = create_app(tmp_path)
    assert restarted.state.store.credentials_file.read_bytes() == credentials
    with TestClient(restarted, base_url="http://127.0.0.1:8000") as client:
        saved = [item for item in client.get("/api/bootstrap").json()["agents"] if item["id"] == agent["id"]]
        assert saved == [agent]
        for task in tasks:
            assert client.get(f"/api/tasks/{task['id']}").json()["task"]["assignee_id"] == agent["id"]


def test_assignee_validation_human_authority_and_legacy_token_issuance(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        legacy = post(client, "/api/agents", name="Custom MCP identity")
        assert legacy["token"]
        auth = {"Authorization": "Bearer " + legacy["token"]}
        assert client.get("/api/bootstrap", headers=auth).status_code == 200
        assert client.post("/api/agents", json={"name": "Неавторизованный исполнитель", "issue_token": False, "reason": REASON}, headers=auth).status_code == 403
        before = client.get("/api/bootstrap").json()
        for invalid in ({"name": " "}, {"name": "x" * 256}, {"name": "X", "kind": "human"}, {"name": "X", "issue_token": "false"}, {"name": "X", "issue_token": False, "reason": " "}):
            response = client.post("/api/agents", json={"reason": REASON, "issue_token": False, **invalid}, headers=BROWSER)
            assert response.status_code == 422, response.text
        assert client.get("/api/bootstrap").json() == before
        project = post(client, "/api/projects", name="Проверка существования исполнителя")
        invalid_task = client.post("/api/tasks", json={"project_id": project["id"], "title": "Неверное назначение", "rationale": REASON, "assignee_id": "unknown", "reason": REASON}, headers=BROWSER)
        assert invalid_task.status_code == 422
        assert client.get(f"/api/projects/{project['id']}").json()["tasks"] == []


def test_assignee_creation_rolls_back_with_audit_failure(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False) as client:
        before = client.get("/api/bootstrap").json()
        def fail_audit(*args, **kwargs):
            raise RuntimeError("Injected audit failure")
        monkeypatch.setattr(app.state.store, "record", fail_audit)
        response = client.post("/api/agents", json={"name": "Не должно сохраниться", "issue_token": False, "idempotency_key": "rollback", "reason": REASON}, headers=BROWSER)
        assert response.status_code == 500
        assert client.get("/api/bootstrap").json() == before
        with app.state.store.connect() as db:
            assert not db.execute("SELECT 1 FROM idempotency WHERE key='rollback'").fetchone()
