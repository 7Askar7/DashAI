from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from desktop.runtime import (ROOT, VERSION, acquire_mutex, companion_command,
                             mcp_running, personal_dir, release_mutex, write_json)
from desktop.updates import backup_before_update, channel_config, check_update, download_update
from server.app import create_app


def start_server(data_dir: Path, port: int | None = None):
    """Reserve our own socket; never adopt an existing service's health response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for candidate in [port] if port is not None else range(4242, 4263):
        try:
            sock.bind(("127.0.0.1", candidate))
            break
        except OSError:
            if port is not None or candidate == 4262:
                sock.close()
                raise OSError("Не удалось занять локальный порт Agentboard") from None
    base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    app = create_app(data_dir, base_url=base_url)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            server.should_exit = True
            sock.close()
            raise RuntimeError("Локальный сервер не запустился; подробности в журнале запуска")
        time.sleep(0.05)
    write_json(data_dir / "runtime.json", {
        "schema_version": 1, "base_url": base_url,
        "executable": companion_command()[0], "data_dir": str(data_dir),
        "version": VERSION, "pid": os.getpid(),
    })
    return server, thread, base_url


def open_previous(data_dir: Path) -> None:
    from connectors.mcp_server import validate_url
    try:
        runtime = json.loads((data_dir / "runtime.json").read_text(encoding="utf-8"))
        webbrowser.open(validate_url(runtime["base_url"]))
    except (OSError, ValueError, KeyError):
        logging.exception("Could not open existing launcher")


class Launcher:
    def __init__(self, window, data_dir: Path, base_url: str, server, thread):
        import tkinter as tk
        from tkinter import ttk

        self.window, self.data_dir, self.base_url = window, data_dir, base_url
        self.server, self.thread = server, thread
        self.messages = queue.Queue()
        self.pending = None
        self.checking = False
        self.closed = False
        self.settings_path = data_dir / "desktop-settings.json"
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(self.settings, dict):
                raise ValueError("Invalid desktop settings")
        except (OSError, ValueError):
            self.settings = {}
        self.channel = channel_config()
        window.title(f"Agentboard · {VERSION}")
        window.geometry("600x470")
        window.minsize(540, 470)
        window.configure(bg="#10161d")
        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure("TFrame", background="#10161d")
        style.configure("TLabel", background="#10161d", foreground="#d9e4ee", font=("Segoe UI", 11))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground="#b4f4a5")
        style.configure("TButton", font=("Segoe UI", 11), padding=(12, 8))
        style.configure("TCheckbutton", background="#10161d", foreground="#d9e4ee", font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", "#18232d")])
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="agentboard.", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Ваши проекты и история на этом компьютере.").pack(anchor="w", pady=(6, 18))
        ttk.Button(frame, text="Открыть доску", command=lambda: webbrowser.open(base_url)).pack(fill="x")
        ttk.Button(frame, text="Подключить Codex и Claude Code к проекту…", command=self.setup_project).pack(fill="x", pady=(8, 16))
        self.auto = tk.BooleanVar(value=self.settings.get("automatic_updates", True))
        ttk.Checkbutton(frame, text="Автоматически устанавливать обновления", variable=self.auto, command=self.save_settings).pack(anchor="w")
        self.startup = tk.BooleanVar(value=self.startup_enabled())
        ttk.Checkbutton(frame, text="Запускать при входе в Windows", variable=self.startup, command=self.set_startup).pack(anchor="w", pady=(4, 12))
        self.update_status = tk.StringVar(value="Канал обновлений подключён." if self.channel.get("manifest_url") else "Канал обновлений ещё не настроен издателем.")
        ttk.Label(frame, textvariable=self.update_status, wraplength=530).pack(anchor="w")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(12, 0))
        self.update_button = ttk.Button(actions, text="Проверить обновления", command=lambda: self.check_updates(manual=True))
        self.update_button.pack(side="left")
        ttk.Button(actions, text="Мои данные", command=self.open_data).pack(side="right")
        ttk.Label(frame, text="Закрытие этого окна остановит локальную доску.", font=("Segoe UI", 9)).pack(anchor="w", pady=(16, 0))
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(200, self.consume_messages)
        window.after(3000, self.check_updates)

    def save_settings(self):
        self.settings["automatic_updates"] = self.auto.get()
        write_json(self.settings_path, self.settings)

    def startup_enabled(self) -> bool:
        if os.name != "nt" or not getattr(sys, "frozen", False):
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                value, _ = winreg.QueryValueEx(key, "Agentboard")
                return value == f'"{sys.executable}"'
        except OSError:
            return False

    def set_startup(self):
        from tkinter import messagebox
        if os.name != "nt" or not getattr(sys, "frozen", False):
            self.startup.set(False)
            messagebox.showinfo("Agentboard", "Автозапуск доступен в установленной Windows-версии.", parent=self.window)
            return
        import winreg
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                if self.startup.get():
                    winreg.SetValueEx(key, "Agentboard", 0, winreg.REG_SZ, f'"{sys.executable}"')
                else:
                    try:
                        winreg.DeleteValue(key, "Agentboard")
                    except FileNotFoundError:
                        pass
        except OSError as error:
            self.startup.set(self.startup_enabled())
            messagebox.showerror("Автозапуск", str(error), parent=self.window)

    def open_data(self):
        if os.name == "nt":
            os.startfile(self.data_dir)

    def setup_project(self):
        from tkinter import filedialog, messagebox
        from connectors.setup import setup
        folder = filedialog.askdirectory(title="Выберите папку проекта для агентов", parent=self.window, mustexist=True)
        if not folder:
            return
        try:
            kwargs = {"data_dir": self.data_dir}
            if getattr(sys, "frozen", False):
                kwargs["executable"] = Path(companion_command()[0])
            setup(Path(folder), base_url=self.base_url, **kwargs)
            messagebox.showinfo("Подключение готово", "Конфигурации Codex и Claude Code сохранены в выбранном проекте.\n\nНачните новую сессию клиента и разрешите project MCP, если он запросит доступ.", parent=self.window)
        except Exception as error:
            logging.exception("Project connector setup failed")
            messagebox.showerror("Не удалось подключить проект", str(error), parent=self.window)

    def check_updates(self, manual=False):
        if self.closed:
            return
        if not manual:
            self.window.after(60 * 60 * 1000, self.check_updates)
        if self.checking or self.pending or not self.channel.get("manifest_url"):
            return
        if not manual and not self.auto.get():
            return
        self.checking = True
        self.update_status.set("Проверяем новую версию…")
        self.update_button.configure(state="disabled")

        def work():
            try:
                result = check_update(self.channel, VERSION)
                if not result:
                    self.messages.put(("current", None))
                else:
                    manifest, envelope = result
                    self.messages.put(("downloading", manifest["version"]))
                    paths = download_update(manifest, envelope, self.data_dir)
                    self.messages.put(("ready", (manifest, paths, manual)))
            except Exception as error:
                logging.exception("Update check/download failed")
                self.messages.put(("error", str(error)[:160]))
        threading.Thread(target=work, daemon=True).start()

    def consume_messages(self):
        if self.closed:
            return
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "downloading":
                self.update_status.set(f"Загружаем обновление {value}…")
                continue
            self.checking = False
            self.update_button.configure(state="normal")
            if kind == "current":
                self.update_status.set(f"Установлена последняя версия {VERSION}.")
            elif kind == "error":
                self.update_status.set(f"Обновление отложено: {value}. Доска продолжает работать.")
            elif kind == "ready":
                self.pending = value
                self.update_button.configure(text="Установить обновление", command=lambda: self.install_pending(manual=True))
        if self.pending:
            manifest, _, manual = self.pending
            if mcp_running():
                self.update_status.set(f"Версия {manifest['version']} готова. Обновится после закрытия подключений агентов.")
            elif self.auto.get() or manual:
                self.install_pending(manual=manual)
            else:
                self.update_status.set(f"Версия {manifest['version']} готова к установке.")
        if not self.closed:
            self.window.after(1000, self.consume_messages)

    def install_pending(self, manual=False):
        from tkinter import messagebox
        if not self.pending or mcp_running():
            return
        manifest, (installer, signed_manifest), _ = self.pending
        if not self.auto.get() and manual:
            if not messagebox.askyesno("Обновление", f"Установить версию {manifest['version']} и перезапустить Agentboard?", parent=self.window):
                self.pending = (manifest, (installer, signed_manifest), False)
                return
        try:
            backup_before_update(self.data_dir, VERSION)
            command = [*companion_command(), "--apply-update", "--installer", str(installer),
                       "--manifest", str(signed_manifest), "--wait-pid", str(os.getpid())]
            subprocess.Popen(command, cwd=ROOT, shell=False,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.close()
        except Exception as error:
            logging.exception("Update handoff failed")
            self.pending = None
            self.update_status.set(f"Не удалось установить обновление: {error}")

    def close(self):
        self.closed = True
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser(description="Локальный Agentboard для Windows")
    parser.add_argument("--data-dir", type=Path, default=personal_dir())
    parser.add_argument("--port", type=int)
    parser.add_argument("--headless", action="store_true", help="Run API without launcher or browser (diagnostics)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("Некорректный порт")
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(data_dir / "logs" / "desktop.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")])
    handle = acquire_mutex()
    if handle is None:
        if not args.no_browser and not args.headless:
            open_previous(data_dir)
        return
    server = thread = None
    try:
        server, thread, base_url = start_server(data_dir, args.port)
        if args.headless:
            while thread.is_alive():
                time.sleep(0.25)
        else:
            import tkinter as tk
            window = tk.Tk()
            Launcher(window, data_dir, base_url, server, thread)
            if not args.no_browser:
                window.after(250, lambda: webbrowser.open(base_url))
            window.mainloop()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        logging.exception("Desktop startup failed")
        if not args.headless:
            import tkinter as tk
            from tkinter import messagebox
            window = tk.Tk()
            window.withdraw()
            messagebox.showerror("Agentboard не запустился", f"{error}\n\nЖурнал: {data_dir / 'logs' / 'desktop.log'}", parent=window)
            window.destroy()
        raise SystemExit(1)
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=10)
        release_mutex(handle)


if __name__ == "__main__":
    main()
