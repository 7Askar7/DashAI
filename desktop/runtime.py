from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def personal_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Agentboard"
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Agentboard"


def binary_name(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def mutex_name(kind: str = "Desktop") -> str:
    return f"Local\\Agentboard{kind}-{os.environ.get('USERNAME', 'user')}"


def acquire_mutex(kind: str = "Desktop", data_dir: Path | None = None) -> int | BinaryIO | None:
    """Keep the handle until process exit; Inno Setup checks these exact names."""
    if os.name != "nt":
        import fcntl
        directory = data_dir or personal_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handle = (directory / f".{kind.lower()}.lock").open("a+b")
        try:
            # A shared MCP session must wait for the brief exclusive health probe.
            fcntl.flock(handle, fcntl.LOCK_SH if kind == "MCP" else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, mutex_name(kind))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if kind == "Desktop" and ctypes.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)
        return None
    return handle


def release_mutex(handle: int | BinaryIO | None) -> None:
    if os.name == "nt" and handle:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)
    elif handle:
        handle.close()


def mcp_running(data_dir: Path | None = None) -> bool:
    if os.name != "nt":
        import fcntl
        file = (data_dir or personal_dir()) / ".mcp.lock"
        if not file.exists():
            return False
        with file.open("a+b") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel.OpenMutexW(0x00100000, False, mutex_name("MCP"))
    if handle:
        release_mutex(handle)
        return True
    return False


def companion_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).with_name(binary_name("AgentboardMCP")))]
    return [sys.executable, "-m", "desktop.mcp_entry"]


def external_program_environment() -> None:
    # PyInstaller sets a DLL directory for its bundled runtime. External installers
    # and installed CLI clients must resolve their own Windows libraries.
    if os.name == "nt" and getattr(sys, "frozen", False):
        ctypes.windll.kernel32.SetDllDirectoryW(None)
