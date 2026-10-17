"""Release records remain shared, bounded and auditable without deploying anything."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from server import create_app

BROWSER = {"X-Dashboard-Client": "browser"}
ROOT = Path(__file__).resolve().parents[1]


def project(client, name="Release test"):
    response = client.post("/api/projects", headers=BROWSER, json={"name": name, "reason": "Verify release history"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def configure(client, project_id, enabled, version):
    response = client.put(f"/api/projects/{project_id}/modules/releases", headers=BROWSER,
                          json={"expected_version": version, "enabled": enabled, "reason": "Choose project features"})
    assert response.status_code == 200, response.text


def test_release_history_isolation_versions_pagination_and_nondestructive_disable(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1:4242") as client:
        first, other = project(client), project(client, "Other project")
        root = f"/api/projects/{first}/releases"
        body = {"version_name": "1.2.0", "title": "Новая архитектура", "changelog": "Обновили карту\n" + "a" * 40000,
                "reason": "Record the shipped scope", "idempotency_key": "first-release"}
        assert client.post(root, headers=BROWSER, json=body).status_code == 409
        configure(client, first, True, 0)
        token = json.loads((tmp_path / "connector-secrets.json").read_text())["agents"]["codex"]["token"]
        agent = {"Authorization": "Bearer " + token, "X-Session-ID": "release-test"}
        response = client.post(root, headers=agent, json=body)
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["version"] == 1 and record["status"] == "draft" and record["author_id"] == "codex"
        assert record["environment"] == "production" and record["released_at"] is None
        assert client.post(root, headers=agent, json=body).json() == record
        assert client.post(root, headers=agent, json={**body, "title": "Different"}).status_code == 409
        path = root + "/" + record["id"]
        patch = {"expected_version": 1, "changes": {"status": "released", "released_at": "2026-10-17"},
                 "reason": "Record production release", "idempotency_key": "publish-release"}
        published = client.patch(path, headers=BROWSER, json=patch).json()
        assert published["version"] == 2 and published["changelog"] == body["changelog"]
        assert client.patch(path, headers=BROWSER, json=patch).json() == published
        assert client.patch(path, headers=BROWSER, json={**patch, "idempotency_key": "stale"}).status_code == 409
        assert client.get(f"/api/projects/{other}/releases/{record['id']}").status_code == 404
        assert client.patch(f"/api/projects/{other}/releases/{record['id']}", headers=BROWSER,
                            json={**patch, "expected_version": 2}).status_code == 404
        page = client.get(root, params={"q": "НОВАЯ", "status": "released", "environment": "production", "limit": 1}).json()
        assert page["total"] == 1 and not page["has_more"] and page["offset"] == 0
        summary = page["releases"][0]
        assert "changelog" not in summary and summary["changelog_preview"] == body["changelog"][:300]
        assert summary["summary_only"] and summary["version_name"] == "1.2.0"
        assert client.get(root, params={"q": "ОБНОВИЛИ"}).json()["total"] == 1
        assert client.get(root, params={"q": "PRODUCTION"}).json()["total"] == 1
        assert client.get(root, params={"environment": "staging"}).json()["total"] == 0
        assert client.get(root, params={"limit": 101}).status_code == 422
        second = client.post(root, headers=BROWSER, json={**body, "version_name": "2.0.0", "changelog": "Next changes", "idempotency_key": "next"}).json()
        page = client.get(root, params={"limit": 1}).json()
        last = client.get(root, params={"limit": 1, "offset": 1}).json()
        assert page["total"] == 2 and page["has_more"] and not last["has_more"]
        assert {page["releases"][0]["id"], last["releases"][0]["id"]} == {record["id"], second["id"]}
        # Large changelogs remain out of board/bootstrap polling, including audit snapshots.
        for endpoint in ("/api/bootstrap", f"/api/projects/{first}"):
            polled = client.get(endpoint)
            assert len(polled.content) < 20000 and "a" * 1000 not in polled.text
        configure(client, first, False, 1)
        assert client.get(path).json() == published
        assert client.get(root).json()["total"] == 2
        assert client.patch(path, headers=BROWSER, json={"expected_version": 2, "changes": {"title": "Paused"}, "reason": "Module hidden"}).status_code == 409
        exported = client.get(f"/api/projects/{first}/export").json()
        assert next(item for item in exported["releases"] if item["id"] == record["id"]) == published
        events = [event for event in exported["events"] if event["entity_type"] == "project_release"]
        assert len(events) == 3 and events[0]["after"]["changelog"] == body["changelog"]
        assert events[0]["session_id"] == "release-test" and events[1]["before"] == record
        assert not client.get(f"/api/projects/{other}/releases").json()["releases"]
        configure(client, first, True, 2)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1:4242") as client:
        assert client.get(path).json() == published


def test_release_validation_concurrency_idempotency_and_atomic_audit(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:4242") as client:
        project_id = project(client)
        configure(client, project_id, True, 0)
        root = f"/api/projects/{project_id}/releases"
        body = {"version_name": "1.0", "changelog": "Recorded changes", "reason": "Validate release records"}
        for invalid in ({"status": "released"}, {"status": "rolled_back"}, {"released_at": "2026-02-30"},
                        {"released_at": "20261017"}, {"released_at": "2026-W01-1"}, {"released_at": "2026-10-17T00:00:00Z"},
                        {"link": "javascript:alert(1)"}, {"link": "https://user:password@example.com"},
                        {"link": "https://example.com/a b"}, {"version_name": " "}, {"changelog": " "}):
            rejected = client.post(root, headers=BROWSER, json={**body, **invalid})
            assert rejected.status_code == 422, (invalid, rejected.text)
        record = client.post(root, headers=BROWSER, json={**body, "released_at": "2026-10-17", "link": "https://example.com/releases/1.0"}).json()
        path = root + "/" + record["id"]
        for changes in ({}, {"title": None}, {"version_name": None}, {"status": "released", "released_at": None},
                        {"released_at": "2026-02-30"}, {"unknown": "no"}):
            assert client.patch(path, headers=BROWSER, json={"expected_version": 1, "changes": changes, "reason": "Reject invalid edits"}).status_code == 422
        clear = {"expected_version": 1, "changes": {"released_at": None, "title": "Clear date"}, "reason": "Clear draft date", "idempotency_key": "clear"}
        saved = client.patch(path, headers=BROWSER, json=clear).json()
        assert saved["released_at"] is None and saved["version"] == 2
        assert client.patch(path, headers=BROWSER, json=clear).json() == saved
        # Omission and explicit null are different operations for a draft's date.
        assert client.patch(path, headers=BROWSER, json={**clear, "changes": {"title": "Clear date"}}).status_code == 409
        competing = {"expected_version": 2, "reason": "Concurrent writers"}
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda name: client.patch(path, headers=BROWSER, json={**competing, "changes": {"title": name}}), ("One", "Two")))
        assert sorted(response.status_code for response in responses) == [200, 409]
        before = client.get(path).json()
        store, original_record = app.state.store, app.state.store.record
        before_events = client.get("/api/history", params={"project_id": project_id}).json()["events"]

        def abort(*args, **kwargs):
            original_record(*args, **kwargs)
            raise RuntimeError("Injected failure after audit insert")

        with monkeypatch.context() as failure:
            failure.setattr(store, "record", abort)
            with pytest.raises(RuntimeError, match="Injected failure"):
                client.post(root, headers=BROWSER, json={**body, "idempotency_key": "atomic-create"})
            with pytest.raises(RuntimeError, match="Injected failure"):
                client.patch(path, headers=BROWSER, json={"expected_version": before["version"], "changes": {"title": "Must roll back"},
                                                         "reason": "Check atomicity", "idempotency_key": "atomic-update"})
        assert client.get(path).json() == before and client.get(root).json()["total"] == 1
        assert client.get("/api/history", params={"project_id": project_id}).json()["events"] == before_events
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM idempotency WHERE key LIKE 'atomic-%'").fetchone()[0] == 0


def test_release_real_stdio_mcp_uses_same_http_store(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url, data = f"http://127.0.0.1:{port}", tmp_path / "data"
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "server", "--port", str(port), "--data-dir", str(data)], cwd=ROOT,
                                   stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urlopen(url + "/api/health", timeout=1) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except (URLError, TimeoutError):
                    assert process.poll() is None, (tmp_path / "server.log").read_text(encoding="utf-8")
                    assert time.monotonic() < deadline, "HTTP server startup timed out"
                    time.sleep(0.1)

            async def workflow():
                params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "connectors/mcp_server.py"), "--agent", "codex",
                    "--credentials", str(data / "connector-secrets.json"), "--url", url, "--session-id", "release-stdio"])
                async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as client:
                    await client.initialize()
                    listed = {tool.name: tool for tool in (await client.list_tools()).tools}
                    assert {"list_project_releases", "get_project_release", "create_project_release", "update_project_release"} <= listed.keys()
                    assert listed["list_project_releases"].annotations.readOnlyHint
                    assert "idempotency_key" in listed["create_project_release"].inputSchema["required"]

                    async def call(name, arguments, error=False):
                        result = await client.call_tool(name, arguments)
                        assert bool(result.isError) == error, result.content
                        return result.structuredContent if not error else " ".join(item.text for item in result.content if item.type == "text")

                    project = await call("create_project", {"name": "Release stdio", "reason": "Verify shared releases", "idempotency_key": "stdio-project"})
                    base = {"project_id": project["id"]}
                    await call("configure_project_module", {**base, "module_id": "releases", "expected_version": 0, "enabled": True,
                                                           "reason": "Enable history", "idempotency_key": "stdio-module"})
                    create = {**base, "version_name": "2.1.0", "status": "released", "released_at": "2026-10-17",
                              "changelog": "Real stdio release\n" + "x" * 4500, "reason": "Record delivered change", "idempotency_key": "stdio-release"}
                    released = await call("create_project_release", create)
                    assert released == await call("create_project_release", create)
                    assert released["author_id"] == "codex" and len(released["changelog"]) > 4000
                    detail = await call("get_project_release", {**base, "release_id": released["id"]})
                    assert detail == released
                    page = await call("list_project_releases", {**base, "q": "REAL STDIO", "limit": 1})
                    assert page["total"] == 1 and "changelog" not in page["releases"][0]
                    assert len(page["releases"][0]["changelog_preview"]) == 300
                    update = {**base, "release_id": released["id"], "expected_version": 1, "changes": {"status": "rolled_back"},
                              "reason": "Record production rollback", "idempotency_key": "stdio-rollback"}
                    rolled_back = await call("update_project_release", update)
                    assert rolled_back["version"] == 2 and rolled_back["status"] == "rolled_back"
                    assert "HTTP_409" in await call("update_project_release", {**update, "idempotency_key": "stale"}, error=True)
                    await call("configure_project_module", {**base, "module_id": "releases", "expected_version": 1, "enabled": False,
                                                           "reason": "Hide module", "idempotency_key": "stdio-hide"})
                    assert (await call("get_project_release", {**base, "release_id": released["id"]})) == rolled_back
                    with urlopen(url + f"/api/projects/{project['id']}/export", timeout=5) as response:
                        exported = json.load(response)
                    assert exported["releases"] == [rolled_back]
                    events = [event for event in exported["events"] if event["entity_type"] == "project_release"]
                    assert len(events) == 2 and all(event["session_id"] == "release-stdio" for event in events)

            asyncio.run(workflow())
        finally:
            process.terminate()
            process.wait(timeout=15)
