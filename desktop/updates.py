from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from desktop.runtime import ROOT, write_json

MAX_MANIFEST = 65536
MAX_INSTALLER = 512 * 1024 * 1024


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})", value):
        raise ValueError("Некорректная версия обновления")
    return tuple(int(part) for part in value.split("."))


def https_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("Некорректный адрес обновления")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("Канал обновлений должен использовать HTTPS")
    return value


class HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_https(url: str):
    request = Request(https_url(url), headers={"User-Agent": "Agentboard-Updater", "Cache-Control": "no-cache"})
    response = build_opener(ProxyHandler({}), HTTPSRedirect()).open(request, timeout=30)
    https_url(response.url)
    return response


def channel_config() -> dict:
    path = ROOT / "release-channel.json"
    if not path.exists():
        return {"schema_version": 1, "manifest_url": None, "public_key": None, "channel": "stable"}
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Неподдерживаемый канал обновлений")
    if config.get("manifest_url") is not None:
        https_url(config["manifest_url"])
        Ed25519PublicKey.from_public_bytes(base64.b64decode(config["public_key"], validate=True))
    return config


def verify_manifest(envelope: bytes, public_key: str, current_version: str) -> dict | None:
    if len(envelope) > MAX_MANIFEST:
        raise ValueError("Манифест обновления слишком большой")
    message = json.loads(envelope)
    if not isinstance(message, dict) or set(message) != {"payload", "signature"}:
        raise ValueError("Некорректный манифест обновления")
    payload_bytes = base64.b64decode(message["payload"], validate=True)
    signature = base64.b64decode(message["signature"], validate=True)
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(signature, payload_bytes)
    except InvalidSignature:
        raise ValueError("Подпись обновления не совпадает с ключом издателя") from None
    payload = json.loads(payload_bytes)
    required = {"schema_version", "version", "installer_url", "sha256", "size", "published_at"}
    if not isinstance(payload, dict) or set(payload) != required or type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("Неподдерживаемый формат обновления")
    new_version = version_tuple(payload["version"])
    https_url(payload["installer_url"])
    if not isinstance(payload["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["sha256"]):
        raise ValueError("Некорректная контрольная сумма обновления")
    if type(payload["size"]) is not int or not 1 <= payload["size"] <= MAX_INSTALLER:
        raise ValueError("Некорректный размер обновления")
    timestamp = datetime.fromisoformat(payload["published_at"].replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("Некорректная дата обновления")
    if new_version <= version_tuple(current_version):
        return None
    return payload


def check_update(config: dict, current_version: str) -> tuple[dict, bytes] | None:
    if not config.get("manifest_url"):
        return None
    with open_https(config["manifest_url"]) as response:
        envelope = response.read(MAX_MANIFEST + 1)
    manifest = verify_manifest(envelope, config["public_key"], current_version)
    return (manifest, envelope) if manifest else None


def verify_installer(path: Path, manifest: dict) -> None:
    if path.stat().st_size != manifest["size"]:
        raise ValueError("Размер установщика не совпадает с подписанным манифестом")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != manifest["sha256"]:
        raise ValueError("Контрольная сумма установщика не совпадает")


def download_update(manifest: dict, envelope: bytes, data_dir: Path) -> tuple[Path, Path]:
    directory = data_dir / "updates"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"Agentboard-Setup-{manifest['version']}.exe"
    temporary = destination.with_suffix(".part")
    try:
        with open_https(manifest["installer_url"]) as response, temporary.open("wb") as output:
            count = 0
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > manifest["size"]:
                    raise ValueError("Установщик превысил подписанный размер")
                output.write(block)
        verify_installer(temporary, manifest)
        temporary.replace(destination)
        manifest_path = directory / f"manifest-{manifest['version']}.json"
        write_json(manifest_path, json.loads(envelope))
        return destination, manifest_path
    finally:
        temporary.unlink(missing_ok=True)


def backup_before_update(data_dir: Path, version: str) -> Path | None:
    database = data_dir / "agentboard.sqlite3"
    if not database.exists():
        return None
    directory = data_dir / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    destination = directory / f"before-{version}-{stamp}.sqlite3"
    with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Проверка резервной копии не пройдена; обновление отложено")
    return destination
