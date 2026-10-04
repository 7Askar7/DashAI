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
from uuid import uuid4
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


def test_frozen_mcp_forwarding_checks_version_paths_and_live_proof(tmp_path, monkeypatch):
    from desktop import runtime as desktop_runtime
    data = tmp_path / "personal data"
    old = data / "vscode-runtime" / "1.4.0" / "AgentboardMCP.exe"
    old.parent.mkdir(parents=True)
    old.touch()
    directory = data / "vscode-runtime" / "1.5.0"
    (directory / "_internal").mkdir(parents=True)
    target = directory / "AgentboardMCP.exe"
    target.touch()
    (directory / "Agentboard.exe").touch()
    marker = directory / "_internal" / "package.json"
    marker.write_text('{"version":"1.5.0"}', encoding="utf-8")
    descriptor = {"schema_version": 1, "mode": "vscode", "version": "1.5.0", "data_dir": str(data),
                  "executable": str(target), "base_url": "http://127.0.0.1:4242", "pid": 1234, "instance_id": str(uuid4())}
    runtime_file = data / "runtime.json"
    def write(value):
        runtime_file.write_text(json.dumps(value), encoding="utf-8")
    write(descriptor)
    health = {"status": "ok", "mcp_running": True, **{field: descriptor[field] for field in ("mode", "version", "pid", "instance_id")}}
    probes = []
    body = [json.dumps(health).encode()]
    class RuntimeApi:
        def open(self, request, timeout):
            assert request.full_url == "http://127.0.0.1:4242/api/health" and timeout == 5
            assert request.get_header("Authorization") is None and request.get_header("X-agentboard-instance") is None
            probes.append(request)
            return io.BytesIO(body[0])
    def opener(*handlers):
        assert handlers[0].proxies == {} and isinstance(handlers[1], mcp_server.NoRedirect)
        return RuntimeApi()
    monkeypatch.setattr(mcp_server, "build_opener", opener)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(old))
    monkeypatch.setattr(desktop_runtime, "VERSION", "1.4.0")
    assert mcp_server.forwarding_target(data, None) == target.resolve()
    assert len(probes) == 1
    for version in ["1.4.0", "1.3.9"]:
        write({**descriptor, "version": version})
        assert mcp_server.forwarding_target(data, None) is None
    write({**descriptor, "mode": "desktop"})
    assert mcp_server.forwarding_target(data, None) is None
    write(descriptor)
    assert mcp_server.forwarding_target(data, "http://127.0.0.1:4242") is None
    assert mcp_server.forwarding_target(None, None) is None
    with monkeypatch.context() as external:
        external.setattr(sys, "executable", str(tmp_path / "other" / "AgentboardMCP.exe"))
        assert mcp_server.forwarding_target(data, None) is None
    with monkeypatch.context() as source:
        source.setattr(sys, "frozen", False)
        assert mcp_server.forwarding_target(data, None) is None
    assert len(probes) == 1
    for changes in [{"schema_version": True}, {"data_dir": str(tmp_path / "other")},
                    {"executable": str(tmp_path / "unexpected.exe")}, {"instance_id": "not-a-uuid"},
                    {"pid": True}, {"pid": -1}, {"base_url": "http://attacker.example"},
                    {"base_url": "http://127.0.0.1"}, {"base_url": 123}, {"version": "../../other"}]:
        write({**descriptor, **changes})
        with pytest.raises(ValueError):
            mcp_server.forwarding_target(data, None)
    assert len(probes) == 1
    write(descriptor)
    marker.write_text('{"version":"1.4.0"}', encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server.forwarding_target(data, None)
    marker.write_text('{"version":"1.5.0"}', encoding="utf-8")
    for changes in [{"instance_id": str(uuid4())}, {"pid": 5678}, {"mode": "desktop"},
                    {"version": "1.4.0"}, {"status": "other"}, {"mcp_running": "true"}]:
        body[0] = json.dumps({**health, **changes}).encode()
        with pytest.raises(ValueError):
            mcp_server.forwarding_target(data, None)
    body[0] = b" " * 16385
    with pytest.raises(ValueError, match="размер"):
        mcp_server.forwarding_target(data, None)
    write({**descriptor, "pid": 1})
    body[0] = json.dumps({**health, "pid": True}).encode()
    with pytest.raises(ValueError):
        mcp_server.forwarding_target(data, None)
    write(descriptor)
    class UnreachableApi:
        def open(self, *_args, **_kwargs):
            raise URLError("test-only unavailable runtime")
    with monkeypatch.context() as offline:
        offline.setattr(mcp_server, "build_opener", lambda *_handlers: UnreachableApi())
        with pytest.raises(URLError):
            mcp_server.forwarding_target(data, None)
    body[0] = json.dumps(health).encode()
    # The new companion sees its own version and stops forwarding, even with the same descriptor.
    with monkeypatch.context() as updated:
        updated.setattr(desktop_runtime, "VERSION", "1.5.0")
        updated.setattr(sys, "executable", str(target))
        assert mcp_server.forwarding_target(data, None) is None


def test_frozen_mcp_handoff_keeps_stdio_arguments_session_and_exit_code(tmp_path, monkeypatch):
    from desktop import runtime as desktop_runtime
    target = tmp_path / "new runtime" / "AgentboardMCP.exe"
    target.parent.mkdir()
    target.touch()
    monkeypatch.setattr(mcp_server, "forwarding_target", lambda data, url: target)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Old companion must not load credentials, open its API or create a store")
    monkeypatch.setattr(mcp_server, "connection_options", forbidden)
    monkeypatch.setattr(mcp_server, "load_token", forbidden)
    monkeypatch.setattr(mcp_server, "build_server", forbidden)
    resets = []
    monkeypatch.setattr(desktop_runtime, "external_program_environment", lambda: resets.append(True))
    commands = []
    def native_call(command, **options):
        commands.append((command, options))
        assert "cwd" not in options and options["shell"] is False
        assert options["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
        assert options["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        assert options["stdin"] is sys.stdin and options["stdout"] is sys.stdout and options["stderr"] is sys.stderr
        assert "capture_output" not in options
        return 7
    monkeypatch.setattr(mcp_server.subprocess, "call", native_call)
    original = ["--agent", "claude", "--data-dir", str(tmp_path), "--token-file", "relative-identity.json",
                "--session-id", "existing-chat"]
    with pytest.raises(SystemExit) as stopped:
        mcp_server.main(original)
    assert stopped.value.code == 7 and resets == [True]
    assert commands[0][0] == [str(target), "--mcp", *original, "--session-id", "existing-chat"]
    with pytest.raises(SystemExit):
        mcp_server.main(["--agent", "codex", "--data-dir", str(tmp_path)])
    assert commands[1][0][-2] == "--session-id" and commands[1][0][-1].startswith("mcp-")


def test_mcp_collection_pages_stay_bounded(monkeypatch):
    """Large API collections cannot overflow a requested MCP page or hide continuation."""
    sections = [{"id": f"section-{index}", "project_id": "project", "title": "Section " + str(index),
                 "version": 1, "description": "x" * 50000} for index in range(500)]
    subprojects = [{"id": f"subproject-{index}", "project_id": "project", "title": "Workstream " + str(index),
                    "version": 1, "parent_id": None, "description": "y" * 50000} for index in range(500)]
    agents = [{"id": f"agent-{index}", "name": "Agent " + str(index), "kind": "codex"}
              for index in range(500)]

    class LargeApi:
        def open(self, request, timeout):
            data = {"projects": [], "agents": agents} if request.full_url.endswith("/bootstrap") else {
                "project": {"id": "project", "name": "Large board"}, "sections": sections, "subprojects": subprojects,
                "tasks": [], "activity": [],
            }
            return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(mcp_server, "build_opener", lambda *_: LargeApi())
    server = mcp_server.build_server("http://127.0.0.1:4242", "test-only", "codex", "test-page")

    async def read_pages():
        text, first = await server.call_tool("get_board", {"project_id": "project", "limit": 1, "section_limit": 1, "subproject_limit": 1})
        assert len(first["sections"]) == 1 and first["total_sections"] == 500
        assert first["next_section_offset"] == 1 and "description" not in first["sections"][0]
        assert len(text[0].text) + len(json.dumps(first)) < 5000
        assert len(first["subprojects"]) == 1 and first["total_subprojects"] == 500 and first["next_subproject_offset"] == 1
        assert "description" not in first["subprojects"][0]
        _, second = await server.call_tool("get_board", {"project_id": "project", "section_limit": 1, "section_offset": 1})
        assert second["sections"][0]["id"] != first["sections"][0]["id"]
        _, maximum = await server.call_tool("get_board", {"project_id": "project", "section_limit": 100, "section_offset": 400})
        assert len(maximum["sections"]) == 100 and maximum["next_section_offset"] is None
        _, context = await server.call_tool("get_board", {"project_id": "project", "section_id": "section-499", "section_limit": 1})
        assert context["section_context"]["id"] == "section-499"
        assert context["section_context"]["description"].startswith("x" * 2000)
        assert len(context["section_context"]["description"]) < 2100
        _, subcontext = await server.call_tool("get_board", {"project_id": "project", "subproject_id": "subproject-499",
            "subproject_limit": 1, "subproject_offset": 499})
        assert subcontext["subproject_context"]["id"] == "subproject-499" and subcontext["next_subproject_offset"] is None
        assert len(subcontext["subproject_context"]["description"]) < 2100
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
                        assert {"create_task", "claim_task", "log_change", "ready_tasks", "get_history", "create_subproject", "update_subproject"} <= tools.keys()
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
                        group_args = {"project_id": direct_project["id"], "title": "Website", "reason": "Group parallel work", "idempotency_key": "subproject-root"}
                        root_group = await call(codex_client, "create_subproject", group_args)
                        assert await call(codex_client, "create_subproject", group_args) == root_group
                        child_group = await call(claude_client, "create_subproject", {**group_args, "title": "Payments",
                            "parent_id": root_group["id"], "idempotency_key": "subproject-child"})
                        assert "HTTP_422" in await call(codex_client, "update_subproject", {"subproject_id": root_group["id"],
                            "expected_version": 1, "changes": {"parent_id": child_group["id"]}, "reason": "Reject cycle", "idempotency_key": "subproject-cycle"}, error=True)
                        root_task = await call(codex_client, "create_task", {**direct_args, "subproject_id": root_group["id"],
                            "title": "Website chat", "idempotency_key": "root-chat-task"})
                        child_task = await call(claude_client, "create_task", {**direct_args, "subproject_id": child_group["id"],
                            "title": "Payments chat", "idempotency_key": "child-chat-task"})
                        filtered = await call(claude_client, "get_board", {"project_id": direct_project["id"], "subproject_id": root_group["id"]})
                        assert {item["id"] for item in filtered["tasks"]} == {root_task["id"], child_task["id"]}
                        exact = await call(codex_client, "ready_tasks", {"project_id": direct_project["id"], "subproject_id": root_group["id"], "include_descendants": False})
                        assert [item["id"] for item in exact["tasks"]] == [root_task["id"]]
                        claims = await asyncio.gather(*[
                            call(agent, "claim_task", {"task_id": item["id"], "expected_version": 1,
                                 "reason": "Independent parallel chat", "idempotency_key": "parallel-claim"})
                            for agent, item in [(codex_client, root_task), (claude_client, child_task)]])
                        assert [item["claim_owner_id"] for item in claims] == ["codex", "claude"]
                        ready_group = await call(codex_client, "ready_tasks", {"project_id": direct_project["id"], "subproject_id": root_group["id"]})
                        assert ready_group["tasks"] == []
                        assert "VALIDATION_ERROR" in await call(codex_client, "get_board", {"project_id": project["id"], "subproject_id": root_group["id"]}, error=True)
                        detached = await call(claude_client, "update_subproject", {"subproject_id": child_group["id"],
                            "expected_version": child_group["version"], "changes": {"parent_id": None},
                            "reason": "Promote independent workstream", "idempotency_key": "detach-subproject"})
                        assert detached["parent_id"] is None and detached["version"] == 2
                        assert "HTTP_409" in await call(codex_client, "update_subproject", {"subproject_id": child_group["id"],
                            "expected_version": 1, "changes": {"title": "Stale"}, "reason": "Reject stale write", "idempotency_key": "stale-subproject"}, error=True)
                        unassigned = await call(claude_client, "update_task", {"task_id": child_task["id"], "expected_version": claims[1]["version"],
                            "changes": {"subproject_id": None}, "reason": "Return task to project", "idempotency_key": "unassign-subproject"})
                        assert unassigned["subproject_id"] is None and unassigned["task_type"] == "research"
                        group_history = await call(codex_client, "get_history", {"project_id": direct_project["id"]})
                        assert any(item["action"] == "subproject.updated" and item["session_id"] == "test-claude" for item in group_history["events"])
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
