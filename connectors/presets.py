"""Client configuration formats, independent from the credential's display name."""

from __future__ import annotations

import json

PROFILES = (
    {"id": "codex", "label": "Codex", "filename": ".codex/config.toml", "format": "toml", "scope": "project"},
    {"id": "claude", "label": "Claude Code", "filename": ".mcp.json", "format": "json", "scope": "project"},
    {"id": "cursor", "label": "Cursor", "filename": ".cursor/mcp.json", "format": "json", "scope": "project"},
    {"id": "vscode", "label": "VS Code / Copilot", "filename": ".vscode/mcp.json", "format": "json", "scope": "project"},
    {"id": "cline", "label": "Cline", "filename": "cline_mcp_settings.json", "format": "json", "scope": "manual"},
    {"id": "generic", "label": "Другой MCP-клиент", "filename": "mcp-server.json", "format": "json", "scope": "manual"},
)


def client_profiles() -> list[dict[str, str]]:
    return [dict(profile) for profile in PROFILES]


def render_config(client: str, entry: dict, cwd: str | None = None) -> dict[str, str]:
    profile = next((p for p in PROFILES if p["id"] == client), None)
    if profile is None:
        raise ValueError("Unknown MCP client profile")
    command, args = entry.get("command"), entry.get("args")
    if not isinstance(command, str) or not command or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("MCP command and string-array args are required")
    server = {"command": command, "args": args}
    if client == "codex":
        if cwd is not None:
            server["cwd"] = cwd
        content = "[mcp_servers.agentboard]\n" + "\n".join(
            f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in server.items()) + "\n"
    else:
        if client in {"claude", "vscode"}:
            server = {"type": "stdio", **server}
        if client == "cline":
            server.update(disabled=False, autoApprove=[])
        config = server if client == "generic" else {"servers" if client == "vscode" else "mcpServers": {"agentboard": server}}
        content = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    return {"filename": profile["filename"], "format": profile["format"], "content": content}
