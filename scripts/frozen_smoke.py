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
            assert {"create_project", "get_board", "create_task", "log_change", "connector_status"} <= tools

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
            section = await call("create_section", {"project_id": project["id"], "title": "Installer verification",
                                                      "reason": "Verify hierarchy", "idempotency_key": "frozen-section"})
            task = await call("create_task", {"project_id": project["id"], "section_id": section["id"],
                                               "title": "Frozen protocol works", "rationale": "Check distributed executable",
                                               "acceptance_criteria": "Shared API and stdio tools operate",
                                               "reason": "Verify task schema", "idempotency_key": "frozen-task"})
            assert (await call("get_task", {"task_id": task["id"]}))["task"]["title"] == "Frozen protocol works"


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
                assert b"<html" in response.read(1024)
            with opener.open(url + "/api/connectors", timeout=5) as response:
                metadata = json.load(response)
            assert metadata["credentials_file"] == str(data / "connector-secrets.json")
            setup = subprocess.run([str(companion), "--setup-connectors", "--project-root", str(repository),
                                    "--data-dir", str(data)], capture_output=True, text=True, timeout=30)
            assert setup.returncode == 0, setup.stderr
            claude = json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
            codex = tomllib.loads((repository / ".codex" / "config.toml").read_text(encoding="utf-8"))
            for entry in (claude["mcpServers"]["agentboard"], codex["mcp_servers"]["agentboard"]):
                assert entry["command"] == str(companion)
                assert entry["args"][0] == "--mcp"
                assert str(data) in entry["args"]
                assert "--url" not in entry["args"]
            asyncio.run(protocol(str(companion), data))
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
    print("Frozen smoke passed: version, isolated data, bundled UI/API, project configs, real stdio MCP hierarchy.")


if __name__ == "__main__":
    main()
