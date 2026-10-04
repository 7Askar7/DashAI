"""Real stdio MCP clients talking to one separately running HTTP/SQLite server."""

import asyncio
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from connectors.setup import codex_config, setup
from connectors import mcp_server
from connectors import codex as codex_launcher

ROOT = Path(__file__).resolve().parents[1]


def test_codex_launcher_explicit_config(tmp_path, monkeypatch):
    (tmp_path / ".codex").mkdir()
    entry = {"command": "C:/Python/python.exe", "args": ["C:/project with space/mcp.py", "--agent", "codex"], "cwd": "C:/board"}
    (tmp_path / ".codex" / "config.toml").write_text(codex_config("", entry), encoding="utf-8")
    with monkeypatch.context() as command:
        command.setattr(codex_launcher, "codex_command", lambda: ["codex-native"])
        arguments = codex_launcher.invocation(tmp_path, ["mcp", "get", "agentboard", "--json"])
    assert arguments[0] == "codex-native" and arguments[-4:] == ["mcp", "get", "agentboard", "--json"]
    for index, (key, value) in enumerate(entry.items()):
        assert arguments[1 + 2 * index] == "-c"
        assert tomllib.loads(arguments[2 + 2 * index])["mcp_servers"]["agentboard"][key] == value
    if shutil.which("codex"):
        result = subprocess.run([sys.executable, str(ROOT / "connectors" / "codex.py"), "--project-root", str(tmp_path),
                                 "mcp", "get", "agentboard", "--json"], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        registered = json.loads(result.stdout)
        assert registered["enabled"] is True and registered["transport"]["command"] == entry["command"]
        assert registered["transport"]["args"] == entry["args"]


def test_desktop_connector_config_and_runtime_discovery(tmp_path, monkeypatch):
    """Installed configs survive upgrades/port changes and do not use bundled personal data."""
    project = tmp_path / "repo with spaces"
    project.mkdir()
    (project / ".codex").mkdir()
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "keep"}}}), encoding="utf-8")
    (project / ".codex" / "config.toml").write_text('model="keep"\n[mcp_servers.other]\ncommand="keep"\n', encoding="utf-8")
    install = tmp_path / "Programs" / "Agentboard"
    install.mkdir(parents=True)
    executable = install / "AgentboardMCP.exe"
    executable.touch()
    local = tmp_path / "Local"
    data = local / "Agentboard"
    data.mkdir(parents=True)
    credentials = data / "connector-secrets.json"
    credentials.write_text(json.dumps({"schema_version": 1, "agents": {
        kind: {"id": kind, "token": "test-" + kind} for kind in ("codex", "claude")
    }}), encoding="utf-8")
    runtime_path = data / "runtime.json"
    runtime_path.write_text(json.dumps({"schema_version": 1, "base_url": "http://127.0.0.1:4251"}), encoding="utf-8")
    with monkeypatch.context() as frozen:
        frozen.setattr(sys, "frozen", True, raising=False)
        frozen.setattr(sys, "executable", str(executable))
        frozen.setenv("LOCALAPPDATA", str(local))
        paths = setup(project)
        setup(project)  # Re-running after an upgrade preserves other settings.
        assert mcp_server.connection_options() == (credentials, "http://127.0.0.1:4251")
    claude = json.loads(paths[0].read_text(encoding="utf-8"))
    codex = tomllib.loads(paths[1].read_text(encoding="utf-8"))
    assert claude["mcpServers"]["other"]["command"] == "keep"
    assert codex["model"] == "keep" and codex["mcp_servers"]["other"]["command"] == "keep"
    for entry in (claude["mcpServers"]["agentboard"], codex["mcp_servers"]["agentboard"]):
        assert entry["command"] == str(executable)
        assert entry["args"] == ["--mcp", "--agent", "claude" if "type" in entry else "codex",
                                 "--credentials", str(credentials), "--data-dir", str(data)]
        assert "test-codex" not in json.dumps(entry) and "test-claude" not in json.dumps(entry)
    assert codex["mcp_servers"]["agentboard"]["cwd"] == str(project)
    runtime_path.write_text(json.dumps({"base_url": "http://127.0.0.1:4252"}), encoding="utf-8")
    assert mcp_server.connection_options(data_dir=data)[1] == "http://127.0.0.1:4252"
    runtime_path.write_text(json.dumps({"base_url": "http://example.com:4252"}), encoding="utf-8")
    with pytest.raises(ValueError, match="loopback"):
        mcp_server.connection_options(data_dir=data)
    assert mcp_server.connection_options(data_dir=data, url="http://127.0.0.1:4253")[1].endswith(":4253")
    runtime_path.unlink()
    with pytest.raises(FileNotFoundError):
        mcp_server.connection_options(data_dir=data)


def test_mcp_collection_pages_stay_bounded(monkeypatch):
    """Large API collections cannot overflow a requested MCP page or hide continuation."""
    sections = [{"id": f"section-{index}", "project_id": "project", "title": "Section " + str(index),
                 "version": 1, "description": "x" * 50000} for index in range(500)]
    agents = [{"id": f"agent-{index}", "name": "Agent " + str(index), "kind": "codex"}
              for index in range(500)]

    class LargeApi:
        def open(self, request, timeout):
            data = {"projects": [], "agents": agents} if request.full_url.endswith("/bootstrap") else {
                "project": {"id": "project", "name": "Large board"}, "sections": sections,
                "tasks": [], "activity": [],
            }
            return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(mcp_server, "build_opener", lambda *_: LargeApi())
    server = mcp_server.build_server("http://127.0.0.1:4242", "test-only", "codex", "test-page")

    async def read_pages():
        text, first = await server.call_tool("get_board", {"project_id": "project", "limit": 1, "section_limit": 1})
        assert len(first["sections"]) == 1 and first["total_sections"] == 500
        assert first["next_section_offset"] == 1 and "description" not in first["sections"][0]
        assert len(text[0].text) + len(json.dumps(first)) < 5000
        _, second = await server.call_tool("get_board", {"project_id": "project", "section_limit": 1, "section_offset": 1})
        assert second["sections"][0]["id"] != first["sections"][0]["id"]
        _, maximum = await server.call_tool("get_board", {"project_id": "project", "section_limit": 100, "section_offset": 400})
        assert len(maximum["sections"]) == 100 and maximum["next_section_offset"] is None
        _, context = await server.call_tool("get_board", {"project_id": "project", "section_id": "section-499", "section_limit": 1})
        assert context["section_context"]["id"] == "section-499"
        assert context["section_context"]["description"].startswith("x" * 2000)
        assert len(context["section_context"]["description"]) < 2100
        _, identities = await server.call_tool("list_projects", {"agent_limit": 1, "agent_offset": 499})
        assert identities["agents"][0]["id"] == "agent-499"
        assert len(identities["agents"]) == 1 and identities["total_agents"] == 500
        assert identities["next_agent_offset"] is None

    asyncio.run(read_pages())


def test_mcp_nested_history_and_notes_are_summaries(monkeypatch):
    """Maximum-sized file lists/diffs cannot repeat full snapshots into agent context."""
    note = {"id": "note", "task_id": "task", "kind": "change", "body": "b" * 200000,
            "actor_id": "codex", "metadata": {"files": ["f" * 2048 for _ in range(200)],
                                                "diff": "d" * 200000, "verification": "v" * 50000}}
    event = {"id": 1, "entity_type": "note", "action": "change.logged", "actor_id": "codex",
             "reason": "r" * 4000, "before": None, "after": note}
    task = {"id": "task", "depends_on": [f"dependency-{index}" for index in range(128)]}

    class LargeHistoryApi:
        def open(self, request, timeout):
            if "/history?" in request.full_url:
                data = {"events": [event] * 50, "next_cursor": 50}
            elif "/tasks/" in request.full_url:
                data = {"task": task, "notes": [note] * 10, "events": [event] * 10}
            else:
                data = {"project": {}, "sections": [], "tasks": [task], "activity": [event] * 10}
            return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(mcp_server, "build_opener", lambda *_: LargeHistoryApi())
    server = mcp_server.build_server("http://127.0.0.1:4242", "test-only", "codex", "test-history")

    async def read_context():
        content, history = await server.call_tool("get_history", {})
        assert len(history["events"]) == 50 and history["next_cursor"] == 50
        assert len(content[0].text) + len(json.dumps(history)) < 500000
        preview = history["events"][0]["after"]
        assert preview["summary_only"] and history["events"][0]["snapshots_are_summaries"]
        assert len(preview["metadata"]["files"]) == 5
        assert preview["metadata"]["files_total"] == 200 and preview["metadata"]["files_truncated"]
        assert "truncated" in preview["metadata"]["diff"]
        _, board = await server.call_tool("get_board", {"project_id": "project"})
        assert board["tasks"][0]["task_type"] == "other"
        assert len(board["tasks"][0]["depends_on"]) == 10
        assert board["tasks"][0]["depends_on_count"] == 128 and board["tasks"][0]["depends_on_truncated"]
        assert len(json.dumps(board)) < 50000
        _, detailed = await server.call_tool("get_task", {"task_id": "task"})
        assert len(detailed["task"]["depends_on"]) == 128
        assert len(detailed["notes"][0]["metadata"]["files"]) == 5
        assert len(json.dumps(detailed)) < 100000

    asyncio.run(read_context())


def test_mcp_workflow_and_project_setup(tmp_path, monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    data_dir = tmp_path / "data"
    server_log = tmp_path / "server.log"
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "server", "--port", str(port), "--data-dir", str(data_dir)],
            cwd=ROOT, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urlopen(url + "/api/health", timeout=1) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except (URLError, TimeoutError):
                    assert process.poll() is None, server_log.read_text(encoding="utf-8")
                    assert time.monotonic() < deadline, "HTTP server startup timed out"
                    time.sleep(0.1)
            credentials = data_dir / "connector-secrets.json"
            (data_dir / "runtime.json").write_text(json.dumps({"schema_version": 1, "base_url": url}), encoding="utf-8")
            secret = json.loads(credentials.read_text(encoding="utf-8"))
            project_root = tmp_path / "client repo"
            project_root.mkdir()
            (project_root / ".codex").mkdir()
            (project_root / ".mcp.json").write_text(json.dumps({
                "mcpServers": {"existing": {"command": "keep-me"}}, "custom": True,
            }), encoding="utf-8")
            prior_toml = 'model = "unchanged"\n[mcp_servers.other]\ncommand = "keep-me"\n'
            (project_root / ".codex" / "config.toml").write_text(prior_toml, encoding="utf-8")
            setup(project_root, credentials, url)
            setup(project_root, credentials, url)
            claude = json.loads((project_root / ".mcp.json").read_text(encoding="utf-8"))
            codex = tomllib.loads((project_root / ".codex" / "config.toml").read_text(encoding="utf-8"))
            assert claude["custom"] is True and claude["mcpServers"]["existing"]["command"] == "keep-me"
            assert codex["model"] == "unchanged" and codex["mcp_servers"]["other"]["command"] == "keep-me"
            assert codex["mcp_servers"]["agentboard"]["command"] == sys.executable
            assert all(value["token"] not in json.dumps(claude) + json.dumps(codex) for value in secret["agents"].values())
            # Quoted table names and nested env are replaced, unrelated entries survive.
            quoted = '[mcp_servers."agentboard"]\ncommand="old"\n[mcp_servers.agentboard.env]\nOLD="x"\n[mcp_servers.keep]\ncommand="kept"\n'
            replaced = tomllib.loads(codex_config(quoted, {"command": "new"}))
            assert replaced["mcp_servers"] == {"agentboard": {"command": "new"}, "keep": {"command": "kept"}}
            rejected = subprocess.run([sys.executable, str(ROOT / "connectors" / "mcp_server.py"), "--agent", "codex",
                                       "--credentials", str(credentials), "--session-id", "x" * 201],
                                      capture_output=True, text=True, timeout=10)
            assert rejected.returncode == 1 and "Invalid session ID" in rejected.stderr and not rejected.stdout
            invalid_project = tmp_path / "invalid config"
            (invalid_project / ".codex").mkdir(parents=True)
            (invalid_project / ".codex" / "config.toml").write_text("[unfinished", encoding="utf-8")
            with urlopen(url + "/api/bootstrap", timeout=5) as response:
                before_agents = len(json.load(response)["agents"])
            with pytest.raises(ValueError):
                setup(invalid_project, credentials, url, agent_name="Should not be issued")
            with urlopen(url + "/api/bootstrap", timeout=5) as response:
                assert len(json.load(response)["agents"]) == before_agents
            # A loopback connector must bypass inherited proxy settings, including provisioning.
            proxy_env = {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9",
                         "NO_PROXY": "", "no_proxy": ""}
            with monkeypatch.context() as environment:
                for name, value in proxy_env.items():
                    environment.setenv(name, value)
                custom_paths = setup(tmp_path / "custom client", credentials, url, agent_name="Proxy-safe instance")
            custom = tomllib.loads(custom_paths[1].read_text(encoding="utf-8"))
            custom_args = custom["mcp_servers"]["agentboard"]["args"]
            assert "--token-file" in custom_args
            assert Path(custom_args[custom_args.index("--token-file") + 1]).read_text(encoding="utf-8").strip()

            async def workflow():
                def params(kind):
                    return StdioServerParameters(command=sys.executable, args=[
                        str(ROOT / "connectors" / "mcp_server.py"), "--agent", kind,
                        "--credentials", str(credentials),
                        *(["--data-dir", str(data_dir)] if kind == "codex" else ["--url", url]),
                        "--session-id", "test-" + kind,
                    ], env={**os.environ, **proxy_env})

                async with stdio_client(params("codex")) as (cr, cw), stdio_client(params("claude")) as (ar, aw):
                    async with ClientSession(cr, cw) as codex_client, ClientSession(ar, aw) as claude_client:
                        await codex_client.initialize()
                        await claude_client.initialize()
                        listed = await codex_client.list_tools()
                        tools = {tool.name: tool for tool in listed.tools}
                        assert {"create_task", "claim_task", "log_change", "ready_tasks", "get_history"} <= tools.keys()
                        assert tools["get_task"].annotations.readOnlyHint is True
                        assert tools["log_change"].annotations.readOnlyHint is False
                        assert "idempotency_key" in tools["create_task"].inputSchema["required"]
                        assert "section_id" not in tools["create_task"].inputSchema["required"]
                        assert tools["create_task"].inputSchema["properties"]["task_type"]["enum"] == [
                            "research", "development", "testing", "bugfix", "documentation", "other",
                        ]

                        async def call(client, name, args, error=False):
                            result = await client.call_tool(name, args)
                            assert bool(result.isError) == error, result.content
                            if error:
                                return " ".join(item.text for item in result.content if item.type == "text")
                            assert isinstance(result.structuredContent, dict)
                            return result.structuredContent

                        project_args = {"name": "MCP integration", "reason": "Test shared state", "idempotency_key": "project-1"}
                        project = await call(codex_client, "create_project", project_args)
                        retry = await call(codex_client, "create_project", project_args)
                        assert project["id"] == retry["id"]
                        assert "HTTP_409" in await call(codex_client, "create_project", {**project_args, "name": "Different"}, error=True)
                        shared = await call(claude_client, "list_projects", {})
                        assert len(shared["projects"]) == 1 and shared["projects"][0]["id"] == project["id"]
                        direct_project = await call(codex_client, "create_project", {
                            "name": "Direct project board", "reason": "No section setup needed", "idempotency_key": "direct-project",
                        })
                        direct_args = {"project_id": direct_project["id"], "title": "Typed direct task", "task_type": "research",
                                       "rationale": "Task creation must not require section provisioning", "reason": "Test direct board",
                                       "idempotency_key": "direct-task"}
                        direct_task = await call(codex_client, "create_task", direct_args)
                        assert direct_task["task_type"] == "research"
                        assert (await call(codex_client, "create_task", direct_args))["id"] == direct_task["id"]
                        direct_board = await call(claude_client, "get_board", {"project_id": direct_project["id"]})
                        assert len(direct_board["sections"]) == 1 and direct_board["tasks"][0]["task_type"] == "research"
                        direct_retyped = await call(codex_client, "update_task", {"task_id": direct_task["id"],
                            "expected_version": direct_task["version"], "changes": {"task_type": "development"},
                            "reason": "Start implementation", "idempotency_key": "direct-retype"})
                        direct_blocked = await call(codex_client, "update_task", {"task_id": direct_task["id"],
                            "expected_version": direct_retyped["version"], "changes": {"status": "blocked"},
                            "reason": "Waiting for input", "idempotency_key": "direct-status"})
                        assert direct_blocked["task_type"] == "development"
                        assert "HTTP_422" in await call(codex_client, "update_task", {"task_id": direct_task["id"],
                            "expected_version": direct_blocked["version"], "changes": {"task_type": None},
                            "reason": "Verify no null work type", "idempotency_key": "direct-null"}, error=True)
                        await call(codex_client, "create_task", {**direct_args, "task_type": "unknown"}, error=True)
                        section = await call(codex_client, "create_section", {
                            "project_id": project["id"], "title": "Connector", "reason": "Group protocol work", "idempotency_key": "section-1",
                        })
                        task_args = {"project_id": project["id"], "section_id": section["id"], "title": "Verify tools",
                                     "rationale": "Both clients need shared task state", "acceptance_criteria": "MCP calls and HTTP agree",
                                     "reason": "Test protocol workflow", "idempotency_key": "task-1"}
                        task = await call(codex_client, "create_task", task_args)
                        dependent = await call(codex_client, "create_task", {**task_args, "title": "Follow-up", "depends_on": [task["id"]], "idempotency_key": "task-2"})
                        ready = await call(claude_client, "ready_tasks", {"project_id": project["id"]})
                        assert [entry["id"] for entry in ready["tasks"]] == [task["id"]]
                        assert "HTTP_409" in await call(claude_client, "claim_task", {
                            "task_id": dependent["id"], "expected_version": 1, "reason": "Dependency guard", "idempotency_key": "claim-blocked",
                        }, error=True)
                        claimed = await call(codex_client, "claim_task", {
                            "task_id": task["id"], "expected_version": task["version"], "reason": "Start verification", "idempotency_key": "claim-1",
                        })
                        assert claimed["claim_owner_id"] == "codex"
                        assert "HTTP_409" in await call(claude_client, "claim_task", {
                            "task_id": task["id"], "expected_version": claimed["version"], "reason": "Try competing claim", "idempotency_key": "claim-other",
                        }, error=True)
                        await call(claude_client, "add_note", {"task_id": task["id"], "kind": "comment", "body": "Competing write",
                                   "reason": "Test ownership", "idempotency_key": "other-note"}, error=True)
                        change_args = {"task_id": task["id"], "summary": "Added MCP tools", "files": ["connectors/mcp_server.py"],
                                       "verification": "Real SDK client protocol calls", "reason": "Allow shared work", "idempotency_key": "change-1"}
                        change = await call(codex_client, "log_change", change_args)
                        assert change["kind"] == "change" and change["metadata"]["files"] == change_args["files"]
                        repeated_change = await call(codex_client, "log_change", change_args)
                        assert repeated_change["id"] == change["id"]
                        await call(codex_client, "add_note", {"task_id": task["id"], "kind": "evidence", "body": "initialize/list_tools/call_tool passed",
                                   "reason": "Document observed checks", "idempotency_key": "evidence-1"})
                        review = await call(codex_client, "update_task", {"task_id": task["id"], "expected_version": claimed["version"],
                                      "changes": {"status": "review"}, "reason": "Request independent review", "idempotency_key": "review-1"})
                        await call(claude_client, "add_note", {"task_id": task["id"], "kind": "comment", "body": "Shared data verified from second MCP client",
                                   "reason": "Independent protocol review", "idempotency_key": "review-note"})
                        finished = await call(claude_client, "update_task", {"task_id": task["id"], "expected_version": review["version"],
                                      "changes": {"status": "done"}, "reason": "Review passed", "idempotency_key": "done-1"})
                        assert finished["status"] == "done"
                        stale = await call(codex_client, "update_task", {"task_id": task["id"], "expected_version": 1,
                                           "changes": {"title": "stale overwrite"}, "reason": "Test optimistic lock", "idempotency_key": "stale-1"}, error=True)
                        assert "HTTP_409" in stale
                        ready = await call(claude_client, "ready_tasks", {"project_id": project["id"]})
                        assert ready["tasks"][0]["id"] == dependent["id"]
                        history = await call(claude_client, "get_history", {"project_id": project["id"], "limit": 2})
                        assert len(history["events"]) == 2 and history["next_cursor"] > 0
                        remainder = await call(claude_client, "get_history", {"project_id": project["id"], "after": history["next_cursor"]})
                        assert all(event["id"] > history["next_cursor"] for event in remainder["events"])
                        assert any(event["actor_id"] == "claude" for event in remainder["events"])
                        assert any(event["session_id"] == "test-codex" for event in remainder["events"])
                        request = Request(url + "/api/tasks/" + task["id"], headers={"Authorization": "Bearer " + secret["agents"]["codex"]["token"]})
                        with urlopen(request, timeout=5) as response:
                            direct = json.load(response)
                        assert direct["task"]["status"] == "done"
                        assert sum(note["kind"] == "change" for note in direct["notes"]) == 1
                        assert direct["task"]["title"] == "Verify tools"
                        recent = await call(claude_client, "get_task", {"task_id": task["id"], "event_limit": 1})
                        assert recent["events"][0]["id"] == max(event["id"] for event in direct["events"])

            asyncio.run(workflow())
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
