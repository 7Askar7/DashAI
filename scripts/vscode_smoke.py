"""Install the real VSIX into an isolated VS Code and exercise its actual Webview.

Requires installed Windows x64 VS Code and the repository's dev Python environment.
Uses Microsoft's extension-test entry point and Playwright's browser CDP support.
The native save-dialog selection is stubbed; its bridge and filesystem write are real.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import time
import tomllib
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
HTTP = build_opener(ProxyHandler({}))


def read_json(file: Path):
    return json.loads(file.read_text(encoding="utf-8"))


def api(url: str):
    with HTTP.open(url, timeout=5) as response:
        return json.load(response)


async def wait_file(file: Path, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return read_json(file)
        except (OSError, ValueError):
            await asyncio.sleep(.1)
    raise AssertionError(f"No QA result: {file.name}")


async def attach_iframe(connection, target_id):
    """Electron exposes these guests as iframe targets outside Playwright's page tree."""
    session = (await connection.send("Target.attachToTarget", {"targetId": target_id}))['sessionId']
    pending = {}
    counter = 0

    def receive(event):
        if event.get("sessionId") != session:
            return
        message = json.loads(event["message"])
        future = pending.pop(message.get("id"), None)
        if future:
            future.set_result(message)

    connection.on("Target.receivedMessageFromTarget", receive)

    async def evaluate(expression):
        nonlocal counter
        counter += 1
        future = asyncio.get_running_loop().create_future()
        pending[counter] = future
        await connection.send("Target.sendMessageToTarget", {"sessionId": session, "message": json.dumps({
            "id": counter, "method": "Runtime.evaluate", "params": {"expression": expression,
                "returnByValue": True, "awaitPromise": True, "userGesture": True}})})
        response = await asyncio.wait_for(future, 20)
        assert "error" not in response, response
        result = response["result"]
        assert "exceptionDetails" not in result, result
        return result["result"].get("value")

    return evaluate


async def check_ui(directory: Path, port: int, environment: dict):
    ready = await wait_file(directory / "ready.json")
    runtime = ready["runtime"]
    assert runtime["data_dir"] == str(directory / "local" / "Agentboard")
    repository = directory / "repo with spaces"
    companion = Path(runtime["executable"])
    assert companion.is_relative_to(directory / "local"), "MCP path is durable personal runtime"
    assert not companion.is_relative_to(Path(ready["extensionPath"])), "MCP does not depend on VSIX directory"
    claude = read_json(repository / ".mcp.json")["mcpServers"]["agentboard"]
    codex = tomllib.loads((repository / ".codex" / "config.toml").read_text(encoding="utf-8"))["mcp_servers"]["agentboard"]
    assert Path(claude["command"]).samefile(companion) and Path(codex["command"]).samefile(companion)
    assert "--url" not in claude["args"] and "--url" not in codex["args"]
    command_id = 0

    async def command(action, **fields):
        nonlocal command_id
        command_id += 1
        (directory / "command.json").write_text(json.dumps({"id": command_id, "action": action, **fields}), encoding="utf-8")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                reply = read_json(directory / "reply.json")
                if reply["id"] == command_id:
                    assert reply["status"] == "passed", reply
                    return
            except (OSError, ValueError):
                pass
            await asyncio.sleep(.1)
        raise AssertionError(f"VS Code API action timed out: {action}")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        connection = await browser.new_browser_cdp_session()
        target_data = await connection.send("Target.getTargets")
        (directory / "cdp-targets.json").write_text(json.dumps(target_data, indent=2), encoding="utf-8")
        local = next(item for item in target_data["targetInfos"] if item["url"].startswith(runtime["base_url"] + "/"))
        evaluate = await attach_iframe(connection, local["targetId"])
        outer = next(item for item in target_data["targetInfos"] if item["targetId"] == local["parentId"])
        parent_evaluate = await attach_iframe(connection, outer["targetId"])
        await parent_evaluate("document.getElementById('active-frame').contentWindow.addEventListener('message', event => { if(event.data?.kind==='agentboard-host-result') window.dashaiQAReply = {origin:event.origin,sourceIsWindow:event.source===document.getElementById('active-frame').contentWindow,sourceIsMaskedParent:event.source===document.getElementById('active-frame').contentWindow.parent}; })")
        async def wait_ui(expression, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                value = await evaluate(expression)
                if value:
                    return value
                await asyncio.sleep(.2)
            raise AssertionError(f"Editor UI condition failed: {expression}")

        async def click(name):
            await evaluate("(() => { const button=Array.from(document.querySelectorAll('button')).find(b => b.getAttribute('aria-label') === " + json.dumps(name) + " || b.textContent.trim() === " + json.dumps(name) + "); if(!button) throw new Error('Missing button: ' + " + json.dumps(name) + "); button.click(); })()")

        async def fill(name, value):
            await wait_ui("!!document.querySelector('dialog[open] [name=" + name + "]')")
            await evaluate("(() => { const input=document.querySelector('dialog[open] [name=" + name + "]'); if(!input) throw new Error('Missing field: " + name + "'); const prototype=input.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype : input.tagName==='SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype,'value').set.call(input," + json.dumps(value) + ");input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true})); })()")

        origins = await evaluate("({url:location.href, ancestors:Array.from(location.ancestorOrigins)})")
        (directory / "iframe-origins.json").write_text(json.dumps(origins, indent=2), encoding="utf-8")
        await click("Создать проект")
        await fill("name", "DashAI VSCode QA")
        await fill("description", "Verify real installed VSIX with isolated data")
        await click("Создать")
        await wait_ui("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Новая задача')")
        project = api(runtime["base_url"] + "/api/bootstrap")["projects"][0]
        await click("Новая задача")
        await fill("title", "VSCode UI task")
        await fill("task_type", "testing")
        await fill("rationale", "Validate the editor and shared API")
        await fill("acceptance_criteria", "MCP changes appear in the editor")
        await click("Создать")
        await wait_ui("!!document.querySelector('.drawer-body')")
        await click("Закрыть")
        assert await evaluate("document.querySelectorAll('.kanban-column').length") == 5
        session_parameters = StdioServerParameters(command=str(companion), args=["--mcp", "--agent", "codex",
            "--data-dir", runtime["data_dir"], "--session-id", "vscode-actual-qa"], env=environment)
        with (directory / "mcp-stderr.log").open("w", encoding="utf-8") as error_log:
            async with stdio_client(session_parameters, errlog=error_log) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    async def tool(name, arguments):
                        result = await session.call_tool(name, arguments)
                        assert not result.isError, result.content
                        assert result.structuredContent is not None
                        return result.structuredContent
                    task = await tool("create_task", {"project_id": project["id"], "title": "VSCode MCP parallel task",
                        "task_type": "research", "rationale": "Verify another chat shares the board",
                        "acceptance_criteria": "The real VSCode iframe polls and shows agent work",
                        "reason": "Actual VSIX integration test", "idempotency_key": "vscode-task"})
                    await tool("claim_task", {"task_id": task["id"], "expected_version": task["version"],
                        "reason": "Start integration check", "idempotency_key": "vscode-claim"})
                    await tool("log_change", {"task_id": task["id"], "summary": "Real MCP call from frozen companion",
                        "files": ["scripts/vscode_smoke.py"], "verification": "Task appeared in VSCode webview",
                        "reason": "Record check", "idempotency_key": "vscode-change"})
                    await wait_ui("Array.from(document.querySelectorAll('.kanban-card')).some(b=>b.textContent.includes(" + json.dumps(task["title"]) + "))")
                    await command("blocked-stop")
                    assert api(runtime["base_url"] + "/api/health")["mcp_running"] is True
        await evaluate("Array.from(document.querySelectorAll('.nav-item')).find(b=>b.textContent.startsWith('Коннекторы')).click()")
        config = await wait_ui("document.querySelector('.connector-card.codex pre')?.textContent")
        await click("Скопировать конфигурацию Codex")
        await wait_ui("document.querySelector('.connector-card.codex')?.textContent.includes('Скопировано')", timeout=10)
        await command("clipboard", expected=config)
        observed_reply = await parent_evaluate("window.dashaiQAReply")
        assert observed_reply["origin"] == origins["ancestors"][0] and observed_reply["sourceIsWindow"] is False
        (directory / "host-reply-source.json").write_text(json.dumps(observed_reply, indent=2), encoding="utf-8")
        await evaluate("Array.from(document.querySelectorAll('.nav-item')).find(b=>b.textContent.startsWith('Проекты')).click()")
        await click("Экспортировать проект")
        deadline = time.monotonic() + 15
        while not (directory / "project-export.json").is_file() and time.monotonic() < deadline:
            await asyncio.sleep(.1)
        assert (directory / "project-export.json").is_file(), "Actual webview-to-host export writes a file"
        await command("export", project_id=project["id"], task_title=task["title"])
        await browser.contexts[0].pages[0].screenshot(path=str(directory / "editor-board.png"))
        await command("restart")
        next_runtime = read_json(directory / "runtime-after-restart.json")
        stored = api(next_runtime["base_url"] + "/api/projects/" + project["id"])
        assert {task["title"], "VSCode UI task"} <= {item["title"] for item in stored["tasks"]}
        assert companion.is_file() and (repository / ".mcp.json").is_file()
        await command("finish")
        return {"status": "passed", "vscode": ready["vscode"], "extension_version": runtime["version"],
            "parent_origins": origins["ancestors"], "checks": ["actual VSIX install", "real editor iframe", "UI task creation",
                "five-column shared Kanban", "frozen MCP task/claim/change visible", "MCP shutdown guard", "VSCode clipboard bridge",
                "native export bridge (save-dialog selection stubbed)", "persistent data after runtime restart", "durable MCP configs"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vsix", type=Path)
    parser.add_argument("--code", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Microsoft VS Code" / "Code.exe")
    args = parser.parse_args()
    version = read_json(ROOT / "package.json")["version"]
    vsix = (args.vsix or ROOT / "artifacts" / "releases" / f"Agentboard-VSCode-{version}-win32-x64.vsix").resolve()
    assert args.code.is_file() and vsix.is_file(), "Install VS Code and build the VSIX before QA"
    directory = ROOT / "artifacts" / "qa" / ("vscode-actual-" + uuid4().hex[:10])
    repository = directory / "repo with spaces"
    repository.mkdir(parents=True)
    profile = directory / "profile"
    extensions = directory / "extensions"
    (profile / "User").mkdir(parents=True)
    (profile / "User" / "settings.json").write_text(json.dumps({"agentboard.automaticUpdates": False,
        "workbench.startupEditor": "none", "window.titleBarStyle": "custom"}), encoding="utf-8")
    driver = directory / "driver"
    driver.mkdir()
    (driver / "package.json").write_text(json.dumps({"name": "dashai-qa", "publisher": "local-qa", "version": "0.0.1",
        "engines": {"vscode": "^1.95.0"}, "main": "./index.cjs"}), encoding="utf-8")
    (driver / "index.cjs").write_text((ROOT / "vscode-extension" / "tests" / "actual-driver.cjs").read_text(encoding="utf-8"), encoding="utf-8")
    environment = dict(os.environ, LOCALAPPDATA=str(directory / "local"), USERNAME="DashAI-QA-" + uuid4().hex,
        DASHAI_VSCODE_QA=str(directory))
    environment.pop("ELECTRON_RUN_AS_NODE", None)
    environment.pop("AGENTBOARD_TOKEN", None)
    # The CLI is Microsoft's own installed launcher. No working editor profile is changed.
    cli_env = dict(environment, ELECTRON_RUN_AS_NODE="1")
    cli = args.code.parent / "resources" / "app" / "out" / "cli.js"
    if not cli.is_file():
        launcher = (args.code.parent / "bin" / "code.cmd").read_text(encoding="utf-8")
        relative = re.search(r'%~dp0\.\.\\([^"\r\n]+cli\.js)', launcher)
        assert relative, "Installed code.cmd must identify the current CLI"
        cli = args.code.parent / relative.group(1)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    install = subprocess.run([str(args.code), str(cli), "--user-data-dir", str(profile), "--extensions-dir", str(extensions),
        "--install-extension", str(vsix), "--force"], env=cli_env, capture_output=True, text=True, timeout=120, startupinfo=startup)
    (directory / "install.log").write_text(install.stdout + install.stderr, encoding="utf-8")
    assert install.returncode == 0, install.stdout + install.stderr
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    arguments = [str(args.code), str(repository), "--user-data-dir", str(profile), "--extensions-dir", str(extensions),
        "--extensionDevelopmentPath=" + str(driver), "--extensionTestsPath=" + str(driver / "index.cjs"),
        "--remote-debugging-port=" + str(port), "--disable-updates", "--skip-welcome", "--skip-release-notes",
        "--disable-workspace-trust", "--no-cached-data"]
    with (directory / "vscode.log").open("w", encoding="utf-8") as output:
        process = subprocess.Popen(arguments, env=environment, stdout=output, stderr=subprocess.STDOUT, startupinfo=startup)
        try:
            results = asyncio.run(check_ui(directory, port, environment))
            process.wait(timeout=30)
            assert process.returncode == 0, "VS Code extension tests returned failure"
            (directory / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps({"directory": str(directory), **results}, indent=2))
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
            try:
                runtime = read_json(directory / "local" / "Agentboard" / "runtime.json")
                from urllib.request import Request
                HTTP.open(Request(runtime["base_url"] + "/api/desktop/stop", method="POST",
                    headers={"X-Agentboard-Instance": runtime["instance_id"]}), timeout=5).close()
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    main()
