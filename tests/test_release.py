import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.release import channel, manifest


def test_release_contract(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    private = base64.b64encode(key.private_bytes_raw()).decode("ascii")
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    config = tmp_path / "release-channel.json"
    channel(config, "https://example.com/latest.json", " " + public + "\n")
    assert json.loads(config.read_text(encoding="utf-8"))["public_key"] == public
    with pytest.raises(ValueError):
        channel(config, "http://example.com/latest.json", public)
    with pytest.raises(ValueError):
        channel(config, "https://example.com/latest.json", None)
    installer = tmp_path / "Agentboard-Setup-1.1.0.exe"
    installer.write_bytes(b"release installer fixture")
    output = tmp_path / "latest.json"
    manifest(output, installer, "1.1.0", "https://example.com/Agentboard-Setup-1.1.0.exe", private)
    envelope = json.loads(output.read_text(encoding="utf-8"))
    payload = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    key.public_key().verify(signature, payload)
    with pytest.raises(InvalidSignature):
        key.public_key().verify(signature, payload + b" ")
    data = json.loads(payload)
    assert data["version"] == "1.1.0"
    assert data["size"] == installer.stat().st_size
    assert data["sha256"] == hashlib.sha256(installer.read_bytes()).hexdigest()
    assert "private_key" not in envelope and private not in output.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        manifest(output, installer, "1.1.0-preview", "https://example.com/setup.exe", private)
    wrong = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode("ascii")
    with pytest.raises(ValueError, match="does not match"):
        manifest(output, installer, "1.1.0", "https://example.com/setup.exe", private, wrong)

    # CLI publisher key generation is explicit, does not overwrite, and prints only its public half.
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "release.py"),
               "keygen", "--private-key-file", str(tmp_path / "publisher-private.txt")]
    generated = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert generated.returncode == 0, generated.stderr
    saved = base64.b64decode((tmp_path / "publisher-private.txt").read_text(encoding="ascii"), validate=False)
    assert base64.b64decode(generated.stdout.strip(), validate=True) == Ed25519PrivateKey.from_private_bytes(saved).public_key().public_bytes_raw()
    assert subprocess.run(command, capture_output=True, timeout=10).returncode != 0


def test_vscode_release_signed_contract(tmp_path: Path) -> None:
    """The Python publisher's exact signed bytes are understood by the Node extension."""
    key = Ed25519PrivateKey.generate()
    private = base64.b64encode(key.private_bytes_raw()).decode("ascii")
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    vsix = tmp_path / "Agentboard-VSCode-1.4.0-win32-x64.vsix"
    vsix.write_bytes(b"VSIX release fixture")
    output = tmp_path / "vscode-latest.json"
    private_file = tmp_path / "publisher-private.txt"
    private_file.write_text(private, encoding="ascii")
    repository = Path(__file__).resolve().parents[1]
    url = "https://github.com/7Askar7/DashAI/releases/download/v1.4.0/Agentboard-VSCode-1.4.0-win32-x64.vsix"
    command = [sys.executable, str(repository / "scripts" / "release.py"), "vscode-manifest",
               "--vsix", str(vsix), "--version", "1.4.0", "--vsix-url", url,
               "--output", str(output), "--public-key", public, "--private-key-file", str(private_file)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    envelope = json.loads(output.read_text(encoding="utf-8"))
    payload = base64.b64decode(envelope["payload"], validate=True)
    key.public_key().verify(base64.b64decode(envelope["signature"], validate=True), payload)
    data = json.loads(payload)
    assert set(data) == {"schema_version", "version", "target", "vsix_url", "sha256", "size", "published_at"}
    assert data["target"] == "win32-x64" and data["vsix_url"] == url
    assert data["size"] == vsix.stat().st_size
    assert data["sha256"] == hashlib.sha256(vsix.read_bytes()).hexdigest()
    assert private not in output.read_text(encoding="utf-8")
    script = ("const fs=require('node:fs'); const u=require('./vscode-extension/updates.cjs'); "
              "const data=u.verifyManifest(fs.readFileSync(process.argv[1]),process.argv[2],'1.3.0'); "
              "if(data.version!=='1.4.0'||data.target!=='win32-x64')process.exit(1); "
              "if(u.verifyManifest(fs.readFileSync(process.argv[1]),process.argv[2],'1.4.0')!==null)process.exit(2)")
    verified = subprocess.run(["node", "-e", script, str(output), public], cwd=repository,
                              capture_output=True, text=True, timeout=10)
    assert verified.returncode == 0, verified.stderr
    with pytest.raises(ValueError, match="VSIX URL"):
        manifest(output, vsix, "1.4.0", url.replace("7Askar7", "untrusted"), private, public, vsix=True)
    with vsix.open("wb") as stream:
        stream.truncate(128 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="128 MiB"):
        manifest(output, vsix, "1.4.0", url, private, public, vsix=True)
