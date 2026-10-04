import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from server import create_app

BROWSER = {"X-Dashboard-Client": "browser", "Origin": "http://127.0.0.1:8000"}
REASON = "Проверяем общий рабочий процесс человека и агентов"


@pytest.fixture
def workspace(tmp_path):
    app = create_app(tmp_path)
    credentials = json.loads((tmp_path / "connector-secrets.json").read_text(encoding="utf-8"))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield app, client, {kind: {"Authorization": "Bearer " + record["token"], "X-Session-ID": "test-" + kind} for kind, record in credentials["agents"].items()}


def post(client, url, payload, headers=BROWSER, expected=200):
    response = client.post(url, json={"reason": REASON, **payload}, headers=headers)
    assert response.status_code == expected, response.text
    return response.json()


def project_and_section(client, headers=BROWSER):
    project = post(client, "/api/projects", {"name": "Общий dashboard"}, headers)
    section = post(client, f"/api/projects/{project['id']}/sections", {"title": "Коннекторы"}, headers)
    return project, section


def task(client, project, section, title="Реализовать MCP", headers=BROWSER, **extra):
    return post(client, "/api/tasks", {"project_id": project["id"], "section_id": section["id"], "title": title, "rationale": "Общий источник состояния для Codex и Claude Code", "acceptance_criteria": "Реальный MCP запрос создает задачу и читает историю", **extra}, headers)


def patch(client, item, changes, headers=BROWSER, expected=200):
    response = client.patch(f"/api/tasks/{item['id']}", json={"expected_version": item["version"], "changes": changes, "reason": REASON}, headers=headers)
    assert response.status_code == expected, response.text
    return response.json()


def test_full_workflow_history_and_restart(workspace):
    app, client, agents = workspace
    empty = client.get("/api/bootstrap").json()
    assert empty["projects"] == [] and empty["activity"] == []
    assert all(agent["last_seen"] is None for agent in empty["agents"])
    project, section = project_and_section(client, agents["codex"])
    item = task(client, project, section, headers=agents["codex"])
    assert item["status"] == "backlog" and item["short_id"] == "AD-001"
    claimed = post(client, f"/api/tasks/{item['id']}/claim", {"expected_version": item["version"]}, agents["claude"])
    assert claimed["claim_owner_id"] == "claude" and claimed["assignee_id"] == "claude"
    post(client, f"/api/tasks/{item['id']}/notes", {"kind": "decision", "body": "Используем официальный SDK и общий HTTP API"}, agents["claude"])
    change = post(client, f"/api/tasks/{item['id']}/changes", {"summary": "Добавлен MCP коннектор", "files": ["connectors/mcp_server.py"], "diff": "+ create_task", "commit": "abc123", "verification": "ClientSession smoke"}, agents["claude"])
    assert change["kind"] == "change" and change["metadata"]["files"] == ["connectors/mcp_server.py"]
    post(client, f"/api/tasks/{item['id']}/notes", {"kind": "evidence", "body": "pytest: полный workflow и конкурентный claim прошли"}, agents["claude"])
    reviewing = patch(client, claimed, {"status": "review"}, agents["claude"])
    assert reviewing["claim_owner_id"] is None
    completed = patch(client, reviewing, {"status": "done"})
    assert completed["status"] == "done"
    details = client.get(f"/api/tasks/{item['id']}").json()
    assert len(details["notes"]) == 3
    assert {event["actor_id"] for event in details["events"]} == {"codex", "claude", "human"}
    updates = [event for event in details["events"] if event["action"] == "task.updated"]
    assert updates[0]["before"]["status"] == "review" and updates[0]["after"]["status"] == "done"
    assert all(event["reason"] and event["created_at"].endswith("Z") for event in details["events"])
    old_credentials = app.state.store.credentials_file.read_bytes()
    restarted = create_app(app.state.store.data_dir)
    assert restarted.state.store.credentials_file.read_bytes() == old_credentials
    with TestClient(restarted, base_url="http://127.0.0.1:8000") as reconnected:
        restored = reconnected.get(f"/api/tasks/{item['id']}", headers=agents["codex"]).json()
        assert restored == details
        exported = reconnected.get(f"/api/projects/{project['id']}/export").json()
        assert exported["tasks"][0] == completed and len(exported["notes"]) == 3
        assert exported["events"][0]["action"] == "project.created"
        assert "token_hash" not in json.dumps(exported)


def test_versions_idempotency_and_input_boundaries(workspace):
    _app, client, agents = workspace
    payload = {"name": "Повторяемый проект", "idempotency_key": "create-1"}
    project = post(client, "/api/projects", payload, agents["codex"])
    assert post(client, "/api/projects", payload, agents["codex"]) == project
    post(client, "/api/projects", {**payload, "name": "Другое намерение"}, agents["codex"], expected=409)
    # Same key on another actor and another route is independent.
    other = post(client, "/api/projects", payload, agents["claude"])
    assert other["id"] != project["id"]
    section = post(client, f"/api/projects/{project['id']}/sections", {"title": "Раздел", "idempotency_key": "create-1"}, agents["codex"])
    item = task(client, project, section)
    updated = patch(client, item, {"title": "Новое имя"})
    patch(client, item, {"description": "Попытка затереть чужую правку"}, expected=409)
    assert client.get(f"/api/tasks/{item['id']}").json()["task"] == updated
    response = client.patch(f"/api/projects/{project['id']}", json={"expected_version": 1, "changes": {"name": "Переименовано"}, "reason": REASON}, headers=BROWSER)
    assert response.status_code == 200 and response.json()["version"] == 2
    response = client.patch(f"/api/sections/{section['id']}", json={"expected_version": 1, "changes": {"title": "Подключения"}, "reason": REASON}, headers=BROWSER)
    assert response.status_code == 200 and response.json()["version"] == 2
    before = len(client.get("/api/history?limit=500").json()["events"])
    for invalid in [{"name": "X"}, {"name": "X", "reason": "  "}, {"name": "X", "reason": REASON, "actor_id": "codex"}, {"name": 123, "reason": REASON}, {"name": "X", "reason": REASON, "color": "javascript:x"}]:
        response = client.post("/api/projects", json=invalid, headers=BROWSER)
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    patch(client, updated, {"title": None}, expected=422)
    patch(client, updated, {"status": "invented"}, expected=422)
    patch(client, updated, {}, expected=422)
    patch(client, updated, {"version": 999}, expected=422)
    assert len(client.get("/api/history?limit=500").json()["events"]) == before


def test_concurrent_claim_lease_ownership_and_human_override(workspace):
    app, client, agents = workspace
    project, section = project_and_section(client)
    item = task(client, project, section)
    barrier = Barrier(2)
    def claim(kind):
        barrier.wait()
        return kind, client.post(f"/api/tasks/{item['id']}/claim", json={"expected_version": 1, "reason": "Берем доступную работу"}, headers=agents[kind])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["codex", "claude"]))
    assert sorted(response.status_code for _, response in results) == [200, 409]
    winner, success = next(pair for pair in results if pair[1].status_code == 200)
    loser = "claude" if winner == "codex" else "codex"
    claimed = success.json()
    patch(client, claimed, {"description": "Чужая правка"}, agents[loser], expected=409)
    post(client, f"/api/tasks/{item['id']}/notes", {"kind": "evidence", "body": "Чужое свидетельство"}, agents[loser], expected=409)
    post(client, f"/api/tasks/{item['id']}/changes", {"summary": "Чужое изменение", "files": ["file.py"]}, agents[loser], expected=409)
    renewed = post(client, f"/api/tasks/{item['id']}/claim", {"expected_version": claimed["version"], "lease_seconds": 7200}, agents[winner])
    assert renewed["claim_expires_at"] > claimed["claim_expires_at"]
    human_change = patch(client, renewed, {"description": "Человек уточнил задачу"})
    assert human_change["claim_owner_id"] == winner
    with app.state.store.transaction() as db:
        expired = {**human_change, "claim_expires_at": "2000-01-01T00:00:00.000Z"}
        db.execute("UPDATE tasks SET payload=? WHERE id=?", (json.dumps(expired), item["id"]))
    takeover = post(client, f"/api/tasks/{item['id']}/claim", {"expected_version": human_change["version"]}, agents[loser])
    assert takeover["claim_owner_id"] == loser
    released = patch(client, takeover, {"status": "blocked"}, agents[loser])
    assert released["claim_owner_id"] is None and released["claim_expires_at"] is None
    assert len([event for event in client.get(f"/api/tasks/{item['id']}").json()["events"] if event["action"] == "task.claimed"]) == 3


def test_dependencies_cycles_and_evidence_gate(workspace):
    _app, client, agents = workspace
    project, section = project_and_section(client)
    other_project, other_section = project_and_section(client)
    root = task(client, project, section, title="Блокер")
    dependent = task(client, project, section, title="Зависимая работа", depends_on=[root["id"]])
    foreign = task(client, other_project, other_section)
    post(client, "/api/tasks", {"project_id": project["id"], "section_id": other_section["id"], "title": "Неверная иерархия", "rationale": REASON}, expected=422)
    patch(client, dependent, {"status": "in_progress"}, expected=409)
    post(client, f"/api/tasks/{dependent['id']}/claim", {"expected_version": 1}, agents["codex"], expected=409)
    patch(client, root, {"depends_on": [dependent["id"]]}, expected=422)
    patch(client, root, {"depends_on": [root["id"]]}, expected=422)
    patch(client, root, {"depends_on": [foreign["id"]]}, expected=422)
    patch(client, root, {"depends_on": ["missing"]}, expected=422)
    patch(client, dependent, {"depends_on": [root["id"], root["id"]]}, expected=422)
    patch(client, root, {"status": "done"}, expected=422)
    post(client, f"/api/tasks/{root['id']}/notes", {"kind": "evidence", "body": "Проверка блокера прошла"})
    no_criteria = patch(client, root, {"acceptance_criteria": ""})
    patch(client, no_criteria, {"status": "done"}, expected=422)
    finished = patch(client, no_criteria, {"status": "done", "acceptance_criteria": "Проверка прошла"})
    working = patch(client, dependent, {"status": "in_progress"})
    patch(client, finished, {"status": "backlog"}, expected=409)
    post(client, f"/api/tasks/{finished['id']}/claim", {"expected_version": finished["version"]}, agents["codex"], expected=409)
    patch(client, working, {"status": "blocked"})
    assert patch(client, finished, {"status": "backlog"})["status"] == "backlog"


def test_export_pagination_append_only_and_token_isolation(workspace):
    app, client, agents = workspace
    project, section = project_and_section(client)
    item = task(client, project, section)
    for index in range(105):
        post(client, f"/api/tasks/{item['id']}/notes", {"kind": "progress", "body": f"Шаг {index}"}, agents["codex"])
    first = client.get(f"/api/history?project_id={project['id']}&limit=50").json()
    second = client.get(f"/api/history?project_id={project['id']}&limit=50&after={first['next_cursor']}").json()
    third = client.get(f"/api/history?project_id={project['id']}&limit=50&after={second['next_cursor']}").json()
    ids = [event["id"] for page in [first, second, third] for event in page["events"]]
    assert len(ids) == 108 and ids == sorted(set(ids))
    export = client.get(f"/api/projects/{project['id']}/export")
    assert "attachment" in export.headers["content-disposition"]
    assert len(export.json()["events"]) == 108 and len(export.json()["notes"]) == 105
    with sqlite3.connect(app.state.store.path) as db:
        for statement in ["UPDATE events SET reason='rewritten' WHERE id=1", "DELETE FROM events WHERE id=1"]:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                db.execute(statement)
        stored = db.execute("SELECT token_hash FROM agents WHERE id='codex'").fetchone()[0]
        assert stored != agents["codex"]["Authorization"][7:]
    issued = post(client, "/api/agents", {"name": "Еще один Codex", "kind": "codex"})
    assert issued["agent"]["last_seen"] is None and issued["token"]
    custom = {"Authorization": "Bearer " + issued["token"]}
    custom_item = task(client, project, section, headers=custom)
    event = client.get(f"/api/tasks/{custom_item['id']}").json()["events"][0]
    assert event["actor_id"] == issued["agent"]["id"]
    post(client, "/api/agents", {"name": "Недопустимое расширение прав", "kind": "claude"}, agents["codex"], expected=403)
    for endpoint in ["/api/bootstrap", "/api/connectors", "/api/history"]:
        output = client.get(endpoint).text
        assert issued["token"] not in output and "token_hash" not in output
    assert client.get("/api/bootstrap", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_loopback_origin_and_write_authentication(workspace):
    _app, client, _agents = workspace
    assert client.post("/api/projects", json={"name": "Unauthenticated", "reason": REASON}).status_code == 401
    assert client.post("/api/projects", json={"name": "Safe", "reason": REASON}, headers={**BROWSER, "Origin": "https://attacker.example"}).status_code == 403
    for host in ["attacker.example", "127.0.0.1:bad", "user@127.0.0.1", "[broken"]:
        assert client.get("/api/health", headers={"Host": host}).status_code == 403
    for origin in ["null", "https://127.0.0.1:8000", "http://127.0.0.1:9999", "http://127.0.0.1:8000/path"]:
        assert client.get("/api/bootstrap", headers={"Origin": origin}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert "access-control-allow-origin" not in client.get("/api/health").headers
    assert client.get("/api/history?limit=501").status_code == 422
    assert client.get("/api/missing").status_code == 404


@pytest.mark.parametrize("endpoint", ["bootstrap", "board", "task"])
def test_composite_reads_share_a_snapshot(workspace, monkeypatch, endpoint):
    app, client, _agents = workspace
    store = app.state.store
    project, section = project_and_section(client)
    item = task(client, project, section)
    original_entity, original_entities = store.entity, store.entities
    before = item if endpoint == "task" else project
    table = "tasks" if endpoint == "task" else "projects"
    wrote = False

    def concurrent_write():
        nonlocal wrote
        if wrote:
            return
        wrote = True
        after = {**before, "version": 2}
        with store.transaction() as db:
            db.execute(f"UPDATE {table} SET payload=? WHERE id=?", (json.dumps(after), before["id"]))
            human = next(actor for actor in store.agents(db) if actor["id"] == "human")
            store.record(db, human, REASON, "task" if endpoint == "task" else "project", before["id"],
                         "task.updated" if endpoint == "task" else "project.updated", before, after,
                         project_id=project["id"], task_id=item["id"] if endpoint == "task" else None)

    def entity_then_write(db, selected_table, entity_id):
        result = original_entity(db, selected_table, entity_id)
        if selected_table == table and entity_id == before["id"]:
            concurrent_write()
        return result

    def entities_then_write(db, selected_table, where="", args=()):
        result = original_entities(db, selected_table, where, args)
        if selected_table == "projects":
            concurrent_write()
        return result

    monkeypatch.setattr(store, "entities" if endpoint == "bootstrap" else "entity",
                        entities_then_write if endpoint == "bootstrap" else entity_then_write)
    url = "/api/bootstrap" if endpoint == "bootstrap" else f"/api/projects/{project['id']}" if endpoint == "board" else f"/api/tasks/{item['id']}"
    response = client.get(url).json()
    returned = response["projects"][0] if endpoint == "bootstrap" else response["project"] if endpoint == "board" else response["task"]
    events = response["events"] if endpoint == "task" else response["activity"]
    assert wrote and returned["version"] == 1
    assert not any(event["action"].endswith(".updated") for event in events)
    # The next request sees both committed entity and its audit event together.
    refreshed = client.get(url).json()
    current = refreshed["projects"][0] if endpoint == "bootstrap" else refreshed["project"] if endpoint == "board" else refreshed["task"]
    current_events = refreshed["events"] if endpoint == "task" else refreshed["activity"]
    assert current["version"] == 2 and current_events[0]["after"]["version"] == 2
