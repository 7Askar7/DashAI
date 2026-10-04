"""Console companion: stdio MCP must retain stdin/stdout in a frozen build."""
import logging
import os
import subprocess
import sys
from pathlib import Path

from desktop.runtime import (ROOT, VERSION, acquire_mutex, external_program_environment,
                             mutex_name, release_mutex)


def apply_update(argv: list[str]) -> None:
    import argparse
    from desktop.updates import channel_config, verify_installer, verify_manifest

    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--wait-pid", type=int, required=True)
    args = parser.parse_args(argv)
    config = channel_config()
    manifest = verify_manifest(args.manifest.read_bytes(), config["public_key"], VERSION)
    if manifest is None:
        raise ValueError("Версия обновления уже установлена")
    verify_installer(args.installer, manifest)
    if args.wait_pid <= 0 or os.name != "nt" or not getattr(sys, "frozen", False):
        raise ValueError("Установку обновлений выполняет установленная Windows-версия")
    script = args.installer.parent / "install-update.ps1"
    script.write_bytes((ROOT / "desktop" / "install-update.ps1").read_bytes())
    external_program_environment()
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.Popen([
        str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", str(script), "-Installer", str(args.installer), "-ExpectedHash", manifest["sha256"],
        "-ExpectedSize", str(manifest["size"]), "-ParentPid", str(args.wait_pid), "-HelperPid", str(os.getpid()),
        "-McpMutex", mutex_name("MCP"), "-AppPath", str(Path(sys.executable).with_name("Agentboard.exe")),
    ], shell=False, creationflags=subprocess.CREATE_NO_WINDOW)


def main() -> None:
    if sys.argv[1:] == ["--version"]:
        print(VERSION)
        return
    if len(sys.argv) < 2:
        raise SystemExit("Use --mcp, --setup-connectors or --codex")
    mode, *argv = sys.argv[1:]
    if mode == "--mcp":
        from connectors.mcp_server import main as run
        handle = acquire_mutex("MCP")
        try:
            run(argv)
        finally:
            release_mutex(handle)
            # The MCP SDK owns a TextIOWrapper of stdout.buffer and closes it on
            # shutdown. PyInstaller flushes stdout again after this entrypoint.
            if getattr(sys, "frozen", False) or sys.stdout.closed:
                sys.stdout = sys.__stdout__ = open(os.devnull, "w", encoding="utf-8")
    elif mode == "--setup-connectors":
        from connectors.setup import main as run
        run(argv)
    elif mode == "--codex":
        from connectors.codex import main as run
        external_program_environment()
        run(argv)
    elif mode == "--apply-update":
        # Only the signed, hash-checked installer is ever launched. A failed
        # upgrade restarts the current app and leaves its personal store intact.
        log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Agentboard" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=log_dir / "updates.log", level=logging.INFO)
        try:
            apply_update(argv)
        except Exception:
            logging.exception("Automatic update failed")
            if getattr(sys, "frozen", False):
                external_program_environment()
                subprocess.Popen([str(Path(sys.executable).with_name("Agentboard.exe"))], shell=False)
            raise SystemExit(1)
    else:
        raise SystemExit("Use --mcp, --setup-connectors, --codex or --apply-update")


if __name__ == "__main__":
    main()
