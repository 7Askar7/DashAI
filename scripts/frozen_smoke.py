"""Exercise the real frozen GUI server and MCP companion with an isolated personal store."""
import asyncio
import json
import socket
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "artifacts" / "desktop" / "Agentboard"


async def protocol(command: str, data: Path) -> None:
    parameters = StdioServerParameters(command=command, args=["--mcp", "--agent", "codex",
                                                              "--data-dir", str(data)])
    with (data.parent / "mcp-stderr.log").open("w", encoding="utf-8") as errlog:
        await protocol_session(parameters, errlog)
    errors = (data.parent / "mcp-stderr.log").read_text(encoding="utf-8")
    assert "Traceback" not in errors, errors


async def protocol_session(parameters, errlog) -> None:
    async with stdio_client(parameters, errlog=errlog) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            assert {"create_project", "get_board", "create_task", "log_change", "connector_status", "create_subproject", "update_subproject"} <= tools

            async def call(name: str, arguments: dict) -> dict:
                result = await session.call_tool(name, arguments)
                assert not result.isError, f"Frozen MCP {name} failed: {result.content}"
                assert result.structuredContent is not None
                return result.structuredContent

            assert (await call("list_projects", {}))["projects"] == []
            status = await call("connector_status", {})
            assert status["api"]["status"] == "ok"
            project = await call("create_project", {"name": "Frozen smoke", "reason": "Verify bundled MCP",
                                                       "idempotency_key": "frozen-project"})
            task = await call("create_task", {"project_id": project["id"], "task_type": "testing",
                                               "title": "Frozen protocol works", "rationale": "Check distributed executable",
                                               "acceptance_criteria": "Shared API and stdio tools operate",
                                               "reason": "Verify task schema", "idempotency_key": "frozen-task"})
            detail = (await call("get_task", {"task_id": task["id"]}))["task"]
            assert detail["title"] == "Frozen protocol works" and detail["task_type"] == "testing"
            board = await call("get_board", {"project_id": project["id"]})
            assert next(item for item in board["tasks"] if item["id"] == task["id"])["task_type"] == "testing"
            parent = None
            groups = []
            for index, title in enumerate(["Website", "Payments", "Testing"]):
                args = {"project_id": project["id"], "title": title, "parent_id": parent,
                        "reason": "Verify bundled nested subprojects", "idempotency_key": "frozen-subproject-" + str(index)}
                group = await call("create_subproject", args)
                assert await call("create_subproject", args) == group
                groups.append(group)
                parent = group["id"]
            grouped = await call("create_task", {"project_id": project["id"], "subproject_id": groups[-1]["id"],
                "task_type": "testing", "title": "Nested frozen task", "rationale": "Track a separate agent workstream",
                "reason": "Verify subproject assignment", "idempotency_key": "frozen-nested-task"})
            assigned = await call("update_task", {"task_id": task["id"], "expected_version": task["version"],
                "changes": {"subproject_id": groups[0]["id"]}, "reason": "Move task into workstream", "idempotency_key": "frozen-assign"})
            blocked = await call("update_task", {"task_id": task["id"], "expected_version": assigned["version"],
                "changes": {"status": "blocked"}, "reason": "Verify grouping survives status change", "idempotency_key": "frozen-block"})
            assert blocked["subproject_id"] == groups[0]["id"] and blocked["task_type"] == "testing"
            subtree = await call("get_board", {"project_id": project["id"], "subproject_id": groups[0]["id"]})
            assert {item["id"] for item in subtree["tasks"]} == {task["id"], grouped["id"]}
            assert len(subtree["subprojects"]) == 3 and subtree["subproject_context"]["id"] == groups[0]["id"]
            exact = await call("get_board", {"project_id": project["id"], "subproject_id": groups[0]["id"], "include_descendants": False})
            assert [item["id"] for item in exact["tasks"]] == [task["id"]]
            ready = await call("ready_tasks", {"project_id": project["id"], "subproject_id": groups[0]["id"]})
            assert [item["id"] for item in ready["tasks"]] == [grouped["id"]]
            cycle = await session.call_tool("update_subproject", {"subproject_id": groups[0]["id"], "expected_version": 1,
                "changes": {"parent_id": groups[-1]["id"]}, "reason": "Reject frozen hierarchy cycle", "idempotency_key": "frozen-cycle"})
            assert cycle.isError and "HTTP_422" in " ".join(item.text for item in cycle.content if item.type == "text")
            cleared = await call("update_task", {"task_id": grouped["id"], "expected_version": grouped["version"],
                "changes": {"subproject_id": None}, "reason": "Return task to project", "idempotency_key": "frozen-clear"})
            assert cleared["subproject_id"] is None and cleared["task_type"] == "testing"
            detached = await call("update_subproject", {"subproject_id": groups[-1]["id"], "expected_version": 1,
                "changes": {"parent_id": None}, "reason": "Promote independent subproject", "idempotency_key": "frozen-detach"})
            assert detached["parent_id"] is None and detached["version"] == 2
            history = await call("get_history", {"project_id": project["id"]})
            assert sum(item["action"] == "subproject.created" for item in history["events"]) == 3
            assert any(item["action"] == "subproject.updated" for item in history["events"])
            section = await call("create_section", {"project_id": project["id"], "title": "Legacy compatibility",
                                                      "reason": "Verify existing clients", "idempotency_key": "frozen-section"})
            legacy = await call("create_task", {"project_id": project["id"], "section_id": section["id"],
                                                 "title": "Legacy section task", "rationale": "Keep existing clients compatible",
                                                 "reason": "Verify legacy defaults", "idempotency_key": "frozen-legacy-task"})
            assert legacy["section_id"] == section["id"] and legacy["task_type"] == "other"


def main() -> None:
    gui = BUNDLE / "Agentboard.exe"
    companion = BUNDLE / "AgentboardMCP.exe"
    assert gui.is_file() and companion.is_file(), "Build the desktop bundle first"
    expected_version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    version = subprocess.run([str(companion), "--version"], capture_output=True, text=True, timeout=30)
    assert version.returncode == 0 and version.stdout.strip() == expected_version, version.stderr
    with tempfile.TemporaryDirectory(prefix="agentboard-frozen-") as directory:
        data = Path(directory) / "personal data"
        repository = Path(directory) / "repo with spaces"
        repository.mkdir()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen([str(gui), "--headless", "--data-dir", str(data), "--port", str(port)])
        opener = build_opener(ProxyHandler({}))
        try:
            deadline = time.monotonic() + 45
            while True:
                assert process.poll() is None, "Frozen GUI server exited before health check"
                try:
                    with opener.open(url + "/api/health", timeout=2) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except (URLError, OSError):
                    if time.monotonic() >= deadline:
                        raise AssertionError("Frozen GUI server did not become healthy")
                    time.sleep(0.25)
            with opener.open(url, timeout=5) as response:
                page = response.read()
                assert page == (BUNDLE / "_internal" / "dist" / "index.html").read_bytes()
                assert b"<title>DashAI" in page
            cover = BUNDLE / "_internal" / "dist" / "brand" / "dashai-cover.png"
            assert cover.is_file() and cover.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            with opener.open(url + "/brand/dashai-cover.png", timeout=10) as response:
                assert response.read() == cover.read_bytes()
            with opener.open(url + "/api/connectors", timeout=5) as response:
                metadata = json.load(response)
            assert Path(metadata["credentials_file"]).samefile(data / "connector-secrets.json")
            assert Path(metadata["python_command"]).samefile(companion)
            assert Path(metadata["data_dir"]).samefile(data)
            assert metadata["desktop"] is True and metadata["mcp_script"] == "--mcp"
            setup = subprocess.run([str(companion), "--setup-connectors", "--project-root", str(repository),
                                    "--data-dir", str(data)], capture_output=True, text=True, timeout=30)
            assert setup.returncode == 0, setup.stderr
            claude = json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
            codex = tomllib.loads((repository / ".codex" / "config.toml").read_text(encoding="utf-8"))
            for entry in (claude["mcpServers"]["agentboard"], codex["mcp_servers"]["agentboard"]):
                assert Path(entry["command"]).samefile(companion)
                assert entry["args"][0] == "--mcp"
                assert Path(entry["args"][entry["args"].index("--data-dir") + 1]).samefile(data)
                assert Path(entry["args"][entry["args"].index("--credentials") + 1]).samefile(data / "connector-secrets.json")
                assert "--url" not in entry["args"]
            assert Path(codex["mcp_servers"]["agentboard"]["cwd"]).samefile(repository)
            asyncio.run(protocol(str(companion), data))
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
    print("Frozen smoke passed: version, isolated data, DashAI UI/cover, project configs, real MCP nested subprojects on one board, typed tasks and legacy compatibility.")


if __name__ == "__main__":
    main()
