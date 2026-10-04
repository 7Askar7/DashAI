"""Security boundaries and resource lifetime for personal desktop updates."""
import base64
import hashlib
import io
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from desktop import updates


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
