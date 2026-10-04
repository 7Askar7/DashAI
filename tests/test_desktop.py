"""Security boundaries and resource lifetime for personal desktop updates."""
import base64
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from desktop import updates
from desktop import main as desktop_main
from server.app import create_app


def test_signed_update_rejects_tampering_rollback_and_bounded_download(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    installer = b"signed installer bytes"
    payload = {"schema_version": 1, "version": "1.1.1", "installer_url": "https://example.com/setup.exe",
               "sha256": hashlib.sha256(installer).hexdigest(), "size": len(installer),
               "published_at": "2026-10-04T00:00:00+00:00"}

    def envelope(value):
        raw = json.dumps(value).encode()
        return json.dumps({"payload": base64.b64encode(raw).decode(),
                           "signature": base64.b64encode(key.sign(raw)).decode()}).encode()

    encoded = envelope(payload)
    assert updates.verify_manifest(encoded, public, "1.1.0") == payload
    wrong_key = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()
    with pytest.raises(ValueError):
        updates.verify_manifest(encoded, wrong_key, "1.1.0")
    tampered = json.loads(encoded)
    tampered["payload"] = base64.b64encode(json.dumps({**payload, "version": "9.9.9"}).encode()).decode()
    with pytest.raises(ValueError):
        updates.verify_manifest(json.dumps(tampered).encode(), public, "1.1.0")
    for changes in ({"installer_url": "http://example.com/setup.exe"}, {"size": True},
                    {"size": updates.MAX_INSTALLER + 1}, {"size": -1}, {"version": "1.1.1-beta"},
                    {"sha256": "abc"}, {"published_at": "2026-10-04T00:00:00"}):
        with pytest.raises(ValueError):
            updates.verify_manifest(envelope({**payload, **changes}), public, "1.1.0")
    for version in ("1.1.0", "1.0.9"):
        assert updates.verify_manifest(envelope({**payload, "version": version}), public, "1.1.0") is None
    with pytest.raises(ValueError):
        updates.verify_manifest(b" " * (updates.MAX_MANIFEST + 1), public, "1.1.0")
    with pytest.raises(ValueError):
        updates.HTTPSRedirect().redirect_request(None, None, 302, None, None, "http://example.com/setup.exe")

    # Mock HTTPS bodies, preserving real streaming, verification and filesystem writes.
    for corrupt in (installer + b"excess", b"x" * len(installer)):
        monkeypatch.setattr(updates, "open_https", lambda _, body=corrupt: io.BytesIO(body))
        with pytest.raises(ValueError):
            updates.download_update(payload, encoded, tmp_path)
        assert not list((tmp_path / "updates").glob("*.exe"))
        assert not list((tmp_path / "updates").glob("*.part"))
    monkeypatch.setattr(updates, "open_https", lambda _: io.BytesIO(installer))
    exe, signed = updates.download_update(payload, encoded, tmp_path)
    assert exe.read_bytes() == installer
    assert updates.verify_manifest(signed.read_bytes(), public, "1.1.0") == payload
    exe.write_bytes(b"x" * len(installer))
    with pytest.raises(ValueError):
        updates.verify_installer(exe, payload)


def test_live_wal_backup_closes_handles_and_native_handoff_rechecks_hash(tmp_path):
    database = tmp_path / "agentboard.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, note TEXT)")
        db.execute("INSERT INTO audit VALUES (1, 'still in WAL')")
        db.commit()
        credentials = tmp_path / "connector-secrets.json"
        credentials.write_text('{"token":"test-only-stable"}', encoding="utf-8")
        copied = updates.backup_before_update(tmp_path, "1.1.1")
        with closing(sqlite3.connect(copied)) as verification:
            assert verification.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert verification.execute("SELECT note FROM audit").fetchone()[0] == "still in WAL"
        assert credentials.read_text(encoding="utf-8") == '{"token":"test-only-stable"}'
    # Windows immediately refuses deletion if backup() left a connection alive.
    database.unlink()
    copied.unlink()

    if os.name == "nt":
        native_dir = tmp_path / "literal [test] path"
        native_dir.mkdir()
        fake_installer = native_dir / "setup.exe"
        fake_installer.write_bytes(b"must not execute")
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-File", str(updates.ROOT / "desktop" / "install-update.ps1"),
                                 "-Installer", str(fake_installer), "-ExpectedHash", "0" * 64,
                                 "-ExpectedSize", str(fake_installer.stat().st_size),
                                 "-ParentPid", "2147483646", "-HelperPid", "2147483645",
                                 "-McpMutex", "Local\\AgentboardTestNeverCreated",
                                 "-AppPath", str(native_dir / "missing-app.exe")],
                                capture_output=True, text=True, timeout=10,
                                env={**os.environ, "PSModulePath": str(tmp_path / "missing-modules")})
        assert result.returncode == 1, result.stdout + result.stderr
        log = native_dir / "install-update.log"
        assert log.is_file(), result.stdout + result.stderr
        assert "Installer hash changed" in log.read_text(encoding="utf-8-sig")


def test_vscode_stop_requires_instance_proof_and_preserves_data(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    with closing(sqlite3.connect(tmp_path / "agentboard.sqlite3")) as db:
        before = tuple(db.iterdump())
    credentials = (tmp_path / "connector-secrets.json").read_bytes()
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.post("/api/desktop/stop").status_code == 404

    metadata = {"instance_id": str(uuid4()), "mode": "desktop", "version": "test", "pid": os.getpid()}
    app.state.desktop = metadata
    app.state.last_activity = 0
    app.state.shutdown_requested = False
    active_mcp = [False]
    app.state.mcp_running = lambda: active_mcp[0]
    proof = {"X-Agentboard-Instance": metadata["instance_id"]}
    assert client.get("/api/health").json() == {"status": "ok", **metadata, "mcp_running": False}
    assert client.post("/api/desktop/stop", headers=proof).status_code == 404

    metadata["mode"] = "vscode"
    for bad_headers in ({"Host": "example.com"}, {"Origin": "http://example.com:8000"},
                        {"Origin": "http://127.0.0.1:9999"}):
        app.state.last_activity = 0
        assert client.post("/api/desktop/stop", headers={**proof, **bad_headers}).status_code == 403
        assert app.state.last_activity == 0
        assert not app.state.shutdown_requested
    for invalid_proof in ({}, {"X-Agentboard-Instance": str(uuid4())}):
        assert client.post("/api/desktop/stop", headers=invalid_proof).status_code == 403
        assert not app.state.shutdown_requested

    active_mcp[0] = True
    assert client.get("/api/health").json()["mcp_running"] is True
    assert client.post("/api/desktop/stop", headers=proof).status_code == 409
    assert not app.state.shutdown_requested
    active_mcp[0] = False
    app.state.last_activity = 0
    client.get("/not-api")
    assert app.state.last_activity == 0
    sent_at = time.monotonic()
    assert client.get("/api/bootstrap").status_code == 200
    assert app.state.last_activity >= sent_at
    response = client.post("/api/desktop/stop", headers=proof)
    assert response.status_code == 200 and response.json() == {"status": "stopping"}
    assert app.state.shutdown_requested
    with closing(sqlite3.connect(tmp_path / "agentboard.sqlite3")) as db:
        assert tuple(db.iterdump()) == before
    assert (tmp_path / "connector-secrets.json").read_bytes() == credentials


def test_vscode_runtime_health_matches_reserved_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_main, "mcp_running", lambda: False)
    server, thread, base_url = desktop_main.start_server(tmp_path, 0, vscode_mode=True)
    try:
        runtime = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
        with urlopen(base_url + "/api/health", timeout=5) as response:
            health = json.load(response)
        assert UUID(runtime["instance_id"]).version == 4
        assert runtime["schema_version"] == 1
        assert runtime["base_url"] == base_url
        assert runtime["data_dir"] == str(tmp_path)
        assert runtime["executable"] == desktop_main.companion_command()[0]
        assert health == {"status": "ok", "instance_id": runtime["instance_id"], "mode": "vscode",
                          "version": desktop_main.VERSION, "pid": os.getpid(), "mcp_running": False}
        assert runtime["version"] == health["version"] and runtime["pid"] == health["pid"]
        request = Request(base_url + "/api/desktop/stop", data=b"", method="POST",
                          headers={"X-Agentboard-Instance": runtime["instance_id"]})
        with urlopen(request, timeout=5) as response:
            assert json.load(response) == {"status": "stopping"}
        assert desktop_main.should_stop_vscode(server.config.app.state)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_vscode_idle_and_headless_lifetime(tmp_path, monkeypatch):
    state = SimpleNamespace(desktop={"mode": "vscode"}, last_activity=100,
                            shutdown_requested=False, mcp_running=lambda: False)
    assert not desktop_main.should_stop_vscode(SimpleNamespace(), 1000)
    assert not desktop_main.should_stop_vscode(state, 189.99)
    assert desktop_main.should_stop_vscode(state, 190)
    state.last_activity = 1000
    assert not desktop_main.should_stop_vscode(state, 1000)
    state.shutdown_requested = True
    assert desktop_main.should_stop_vscode(state, 1000)
    state.mcp_running = lambda: True
    assert not desktop_main.should_stop_vscode(state, 2000)
    state.mcp_running = lambda: False
    state.desktop["mode"] = "desktop"
    assert not desktop_main.should_stop_vscode(state, 2000)

    calls = []
    expected_mode = [True]
    server = SimpleNamespace(config=SimpleNamespace(app=SimpleNamespace(state=state)), should_exit=False)
    thread = SimpleNamespace(is_alive=lambda: not server.should_exit, join=lambda **_: calls.append("joined"))

    def start(data_dir, port, *, vscode_mode=False):
        assert data_dir == tmp_path.resolve() and port is None
        assert vscode_mode == expected_mode[0]
        state.desktop["mode"] = "vscode" if vscode_mode else "desktop"
        return server, thread, "http://127.0.0.1:4242"

    monkeypatch.setattr(sys, "argv", ["Agentboard", "--vscode", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(desktop_main, "start_server", start)
    monkeypatch.setattr(desktop_main, "acquire_mutex", lambda: "owned-test-mutex")
    monkeypatch.setattr(desktop_main, "release_mutex", lambda handle: calls.append(handle))
    monkeypatch.setattr(desktop_main.time, "sleep", lambda _: None)
    monkeypatch.setattr(desktop_main.webbrowser, "open", lambda _: pytest.fail("VS Code opened a browser"))
    monkeypatch.setattr(desktop_main, "Launcher", lambda *_: pytest.fail("VS Code opened a launcher"))
    desktop_main.main()
    assert server.should_exit and calls == ["joined", "owned-test-mutex"]
    monkeypatch.setattr(desktop_main, "acquire_mutex", lambda: None)
    desktop_main.main()
    expected_mode[0] = False
    calls.clear()
    server.should_exit = False
    running = iter([True, False])
    thread.is_alive = lambda: next(running)
    monkeypatch.setattr(sys, "argv", ["Agentboard", "--headless", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(desktop_main, "acquire_mutex", lambda: "owned-test-mutex")
    monkeypatch.setattr(desktop_main, "should_stop_vscode", lambda _: pytest.fail("Diagnostic mode used idle shutdown"))
    desktop_main.main()
    assert calls == ["joined", "owned-test-mutex"]
