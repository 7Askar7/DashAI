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
