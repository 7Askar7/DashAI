"""Provider-independent identity, safe presets, and non-destructive setup."""

import json
import tomllib

import pytest
from fastapi.testclient import TestClient

from connectors.presets import client_profiles, render_config
from connectors.setup import setup
from server import create_app

BROWSER = {"X-Dashboard-Client": "browser", "Origin": "http://127.0.0.1:8000"}


def test_custom_identity_and_configuration_generator(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1:8000") as client:
        issued = client.post("/api/agents", headers=BROWSER, json={"name": "DeepSeek локальный / модель v2", "reason": "Distinct author"}).json()
        agent = issued["agent"]
        assert agent["kind"] == "custom" and agent["last_seen"] is None
        headers = {"Authorization": "Bearer " + issued["token"]}
        assert client.post("/api/agents", headers=headers, json={"name": "Unauthorized", "reason": "No credential minting"}).status_code == 403
        request = {"client": "cursor", "agent_id": agent["id"]}
        assert client.post("/api/connectors/config", headers=BROWSER, json=request).status_code == 422
        assert client.post("/api/connectors/config", headers=BROWSER, json={**request, "token_file": "relative/token.json"}).status_code == 422
        assert client.post("/api/connectors/config", headers=headers, json={**request, "token_file": str(tmp_path / "token.json")}).status_code == 403
        profiles = client.get("/api/connectors").json()["client_profiles"]
        assert {p["id"] for p in profiles} == {"codex", "claude", "cursor", "vscode", "cline", "generic"}
        for profile in profiles:
            response = client.post("/api/connectors/config", headers=BROWSER, json={**request, "client": profile["id"], "token_file": str(tmp_path / "not-read.json")})
            assert response.status_code == 200, response.text
            result = response.json()
            parsed = tomllib.loads(result["content"]) if result["format"] == "toml" else json.loads(result["content"])
            assert parsed and issued["token"] not in result["content"]
            assert agent["id"] in result["content"] and "--token-file" in result["content"]
        assert client.post("/api/connectors/config", headers=BROWSER, json={"client": "claude", "agent_id": "claude"}).status_code == 200
        assert client.post("/api/connectors/config", headers=BROWSER, json={"client": "generic", "agent_id": "human"}).status_code == 404
        # Rendering does not claim a client connected or create more identities/events.
        agents = client.get("/api/bootstrap").json()["agents"]
        assert len(agents) == 4


def test_profiles_preserve_existing_settings_and_external_token(tmp_path):
    credentials = tmp_path / "credentials.json"
    token_file = tmp_path / "issued.json"
    identity = "third-party-identity"
    token_file.write_text(json.dumps({"token": "test-only-secret", "agent": {"id": identity}}), encoding="utf-8")
    entry = {"command": "C:/program with spaces/python.exe", "args": ["C:/repo/сервер.py", "--agent", identity, "--token-file", str(token_file)]}
    assert tomllib.loads(render_config("codex", entry)["content"])["mcp_servers"]["agentboard"] == entry
    for profile in client_profiles():
        project = tmp_path / profile["id"]
        destination = project / (".dashai" if profile["scope"] == "manual" else "") / profile["filename"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if profile["id"] == "codex":
            destination.write_text('model="unchanged"\n[mcp_servers.other]\ncommand="keep"\n', encoding="utf-8")
        elif profile["id"] != "generic":
            key = "servers" if profile["id"] == "vscode" else "mcpServers"
            destination.write_text(json.dumps({key: {"other": {"command": "keep"}}, "otherSetting": True}), encoding="utf-8")
        for _ in range(2):
            paths = setup(project, credentials, "http://127.0.0.1:4242", agent_kind="custom", client=profile["id"], agent_id=identity, token_file=token_file)
            assert paths == (destination,)
        content = destination.read_text(encoding="utf-8")
        assert "test-only-secret" not in content and "--token-file" in content
        if profile["id"] == "codex":
            config = tomllib.loads(content)
            assert config["model"] == "unchanged" and config["mcp_servers"]["other"]["command"] == "keep"
        elif profile["id"] != "generic":
            config = json.loads(content)
            assert config["otherSetting"] and config[key]["other"]["command"] == "keep"
        original = destination.read_bytes()
        destination.write_text("invalid configuration", encoding="utf-8")
        with pytest.raises(ValueError):
            setup(project, credentials, "http://127.0.0.1:4242", agent_name="Must not be issued", agent_kind="custom", client=profile["id"])
        assert destination.read_text(encoding="utf-8") == "invalid configuration"
        destination.write_bytes(original)
