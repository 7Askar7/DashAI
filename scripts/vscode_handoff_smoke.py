"""Exercise future VS Code MCP forwarding with explicitly labeled version metadata fixtures.

Both binaries are the current build. The newer copy changes only its bundled package
version to verify dispatch; this does not claim a future product version was built.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
HTTP = build_opener(ProxyHandler({}))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def get(url):
    with HTTP.open(url, timeout=5) as response:
        return json.load(response)


async def protocol(directory, old, newer, runtime, environment):
    parameters = StdioServerParameters(command=str(old), args=["--mcp", "--agent", "codex",
        "--data-dir", runtime["data_dir"], "--session-id", "vscode-handoff-fixture"], env=environment)
    with (directory / "mcp-stderr.log").open("w", encoding="utf-8") as error_log:
        async with stdio_client(parameters, errlog=error_log) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as session:
                await session.initialize()
                async def call(name, arguments):
                    result = await session.call_tool(name, arguments)
                    assert not result.isError, result.content
                    assert result.structuredContent is not None
                    return result.structuredContent

                # Native Windows inventory is restricted to our two exact fixture EXE paths.
                inventory = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -ieq $env:DASHAI_QA_OLD -or $_.ExecutablePath -ieq $env:DASHAI_QA_NEW } | Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json -Compress"],
                    env=dict(environment, DASHAI_QA_OLD=str(old), DASHAI_QA_NEW=str(newer)),
                    capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
                assert inventory.returncode == 0, inventory.stderr
                processes = json.loads(inventory.stdout)
                if isinstance(processes, dict):
                    processes = [processes]
                old_process = next(item for item in processes if Path(item["ExecutablePath"]).samefile(old))
                child = next(item for item in processes if Path(item["ExecutablePath"]).samefile(newer)
                    and item["ParentProcessId"] == old_process["ProcessId"])
                assert child["ProcessId"] != old_process["ProcessId"]
                assert get(runtime["base_url"] + "/api/health")["mcp_running"] is True
                assert (await call("list_projects", {}))["projects"] == []
                project = await call("create_project", {"name": "MCP version forwarding fixture",
                    "reason": "Verify durable connector path after a future runtime update", "idempotency_key": "handoff-project"})
                group = await call("create_subproject", {"project_id": project["id"], "title": "Parallel chat",
                    "reason": "Verify forwarded schema", "idempotency_key": "handoff-group"})
                task = await call("create_task", {"project_id": project["id"], "subproject_id": group["id"],
                    "title": "Forwarded MCP task", "task_type": "testing", "rationale": "Use the active shared API",
                    "acceptance_criteria": "One task and audit entry use the same store and session",
                    "reason": "Verify actual stdio delegation", "idempotency_key": "handoff-task"})
                board = get(runtime["base_url"] + "/api/projects/" + project["id"])
                assert any(item["id"] == task["id"] and item["subproject_id"] == group["id"] for item in board["tasks"])
                history = get(runtime["base_url"] + "/api/history?project_id=" + project["id"])["events"]
                assert any(event["task_id"] == task["id"] and event["session_id"] == "vscode-handoff-fixture"
                    and event["actor_id"] == "codex" for event in history)
                assert not list(old.parent.rglob("agentboard.sqlite3"))
                assert not list(newer.parent.rglob("agentboard.sqlite3"))
                return processes


def main():
    current = read_json(ROOT / "package.json")["version"]
    major, minor, _patch = map(int, current.split("."))
    future_fixture = f"{major}.{minor + 1}.0"
    directory = ROOT / "artifacts" / "qa" / ("vscode-handoff-" + uuid4().hex[:10])
    data = directory / "personal data"
    old_dir = data / "vscode-runtime" / current
    new_dir = data / "vscode-runtime" / future_fixture
    bundle = ROOT / "artifacts" / "desktop" / "Agentboard"
    assert read_json(bundle / "_internal" / "package.json")["version"] == current, "Build current frozen runtime first"
    shutil.copytree(bundle, old_dir)
    shutil.copytree(bundle, new_dir)
    metadata = new_dir / "_internal" / "package.json"
    package = read_json(metadata)
    package["version"] = future_fixture
    metadata.write_text(json.dumps(package), encoding="utf-8")
    environment = dict(os.environ, LOCALAPPDATA=str(directory / "local"), USERNAME="DashAI-Handoff-" + uuid4().hex)
    environment.pop("AGENTBOARD_TOKEN", None)
    environment.pop("ELECTRON_RUN_AS_NODE", None)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    process = subprocess.Popen([str(new_dir / "Agentboard.exe"), "--vscode", "--data-dir", str(data)],
        env=environment, startupinfo=startup)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert process.poll() is None, "Fixture server exited before health"
            try:
                runtime = read_json(data / "runtime.json")
                health = get(runtime["base_url"] + "/api/health")
                if health["version"] == future_fixture and health["instance_id"] == runtime["instance_id"]:
                    break
            except (OSError, URLError, ValueError):
                pass
            time.sleep(.2)
        else:
            raise AssertionError("Fixture server did not become healthy")
        old = old_dir / "AgentboardMCP.exe"
        newer = new_dir / "AgentboardMCP.exe"
        processes = asyncio.run(protocol(directory, old, newer, runtime, environment))
        for _attempt in range(50):
            if not get(runtime["base_url"] + "/api/health")["mcp_running"]:
                break
            time.sleep(.1)
        else:
            raise AssertionError("Forwarded MCP child did not release its handle on stdio close")
        result = {"status": "passed", "current_build": current, "metadata_only_newer_fixture": future_fixture,
            "same_binary_build": True, "processes": processes, "checks": ["old companion launches verified active newer companion",
                "real stdio/MCP protocol", "task and subproject in one shared API store", "session/actor preserved in history",
                "no connector store copies", "child exits and releases MCP handle"]}
        (directory / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"directory": str(directory), **result}, indent=2))
    finally:
        try:
            runtime = read_json(data / "runtime.json")
            HTTP.open(Request(runtime["base_url"] + "/api/desktop/stop", method="POST",
                headers={"X-Agentboard-Instance": runtime["instance_id"]}), timeout=5).close()
            process.wait(timeout=15)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
