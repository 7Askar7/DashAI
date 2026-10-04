"""Launch installed Codex with this project's explicit Agentboard MCP configuration."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def codex_command() -> list[str]:
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is not installed or not on PATH")
    if Path(executable).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        # Invoke the npm JavaScript entry directly; pass arguments without a shell.
        entry = Path(executable).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if not node or not entry.is_file():
            raise ValueError("Cannot resolve Codex npm launcher; add codex.exe to PATH")
        return [node, str(entry)]
    return [executable]


def invocation(project_root: Path, arguments: list[str]) -> list[str]:
    config = tomllib.loads((project_root / ".codex" / "config.toml").read_text(encoding="utf-8-sig"))
    entry = config.get("mcp_servers", {}).get("agentboard", {})
    if not isinstance(entry.get("command"), str) or not entry["command"]:
        raise ValueError("Run connectors/setup.py for this project before launching Codex")
    if not isinstance(entry.get("args"), list) or not all(isinstance(arg, str) for arg in entry["args"]):
        raise ValueError("Agentboard MCP args must be a string array")
    cwd = entry.get("cwd", str(project_root))
    if not isinstance(cwd, str):
        raise ValueError("Agentboard MCP cwd must be a string")
    command = codex_command()
    for key, value in {"command": entry["command"], "args": entry["args"], "cwd": cwd}.items():
        command.extend(["-c", f"mcp_servers.agentboard.{key}={json.dumps(value, ensure_ascii=False)}"])
    return [*command, *arguments]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    options, arguments = parser.parse_known_args(argv)
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    try:
        project_root = options.project_root.resolve()
        raise SystemExit(subprocess.call(invocation(project_root, arguments), cwd=project_root))
    except (OSError, ValueError) as error:
        print(f"Agentboard Codex launcher: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
