"""Generate a public release channel and signed installer manifest. Never bundles a private key."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def https_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Release URLs must be HTTPS, without credentials or fragments")
    return value


def raw_key(value: str, length: int) -> bytes:
    data = base64.b64decode(value.strip(), validate=True)
    if len(data) != length:
        raise ValueError(f"Expected a base64 key of {length} bytes")
    return data


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def channel(path: Path, url: str | None, public_key: str | None) -> None:
    if bool(url) != bool(public_key):
        raise ValueError("manifest-url and public-key must both be supplied, or both omitted")
    if public_key:
        public_key = public_key.strip()
        raw_key(public_key, 32)
    write_json(path, {"schema_version": 1, "manifest_url": https_url(url) if url else None,
                      "public_key": public_key, "channel": "stable"})


def manifest(path: Path, installer: Path, version: str, url: str, private_key: str,
             public_key: str | None = None) -> None:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("version must have three numeric SemVer components")
    if any(int(part) > 65535 for part in version.split(".")):
        raise ValueError("Windows file-version components must not exceed 65535")
    size = installer.stat().st_size
    if not 1 <= size <= 512 * 1024 * 1024:
        raise ValueError("The installer size must be 1 byte..512 MiB")
    digest = hashlib.sha256()
    with installer.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    payload = json.dumps({"schema_version": 1, "version": version, "installer_url": https_url(url),
                          "sha256": digest.hexdigest(), "size": size,
                          "published_at": datetime.now(timezone.utc).isoformat()},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    key = Ed25519PrivateKey.from_private_bytes(raw_key(private_key, 32))
    if public_key and key.public_key().public_bytes_raw() != raw_key(public_key, 32):
        raise ValueError("Signing key does not match the installer's public key")
    write_json(path, {"payload": base64.b64encode(payload).decode("ascii"),
                      "signature": base64.b64encode(key.sign(payload)).decode("ascii")})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    keys = commands.add_parser("keygen", help="Create a publisher key once. Output path must not exist.")
    keys.add_argument("--private-key-file", type=Path, required=True)
    config = commands.add_parser("channel")
    config.add_argument("--output", type=Path, required=True)
    config.add_argument("--manifest-url")
    config.add_argument("--public-key")
    signed = commands.add_parser("manifest")
    signed.add_argument("--output", type=Path, required=True)
    signed.add_argument("--installer", type=Path, required=True)
    signed.add_argument("--version", required=True)
    signed.add_argument("--installer-url", required=True)
    signed.add_argument("--private-key-file", type=Path)
    signed.add_argument("--public-key", required=True, help="Public key embedded in the installer; must match signing key")
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            key = Ed25519PrivateKey.generate()
            # Only the public key is printed; the private key stays in the explicitly chosen file.
            with args.private_key_file.open("x", encoding="ascii") as output:
                output.write(base64.b64encode(key.private_bytes_raw()).decode("ascii") + "\n")
            print(base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii"))
        elif args.command == "channel":
            channel(args.output, args.manifest_url, args.public_key)
        else:
            secret = (args.private_key_file.read_text(encoding="ascii") if args.private_key_file else
                      os.environ.get("AGENTBOARD_UPDATE_PRIVATE_KEY", ""))
            if not secret:
                raise ValueError("Use --private-key-file or AGENTBOARD_UPDATE_PRIVATE_KEY")
            manifest(args.output, args.installer, args.version, args.installer_url, secret, args.public_key)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Release: {error}\n")


if __name__ == "__main__":
    main()
