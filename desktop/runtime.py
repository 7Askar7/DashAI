from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def personal_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Agentboard"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def mutex_name(kind: str = "Desktop") -> str:
    return f"Local\\Agentboard{kind}-{os.environ.get('USERNAME', 'user')}"


def acquire_mutex(kind: str = "Desktop") -> int | None:
    """Keep the handle until process exit; Inno Setup checks these exact names."""
    if os.name != "nt":
        return 1
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


def release_mutex(handle: int | None) -> None:
    if os.name == "nt" and handle:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)


def mcp_running() -> bool:
    if os.name != "nt":
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
        return [str(Path(sys.executable).with_name("AgentboardMCP.exe"))]
    return [sys.executable, "-m", "desktop.mcp_entry"]


def external_program_environment() -> None:
    # PyInstaller sets a DLL directory for its bundled runtime. External installers
    # and installed CLI clients must resolve their own Windows libraries.
    if os.name == "nt" and getattr(sys, "frozen", False):
        ctypes.windll.kernel32.SetDllDirectoryW(None)
