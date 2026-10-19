"""Native paths and Unix lifetime locks are part of safe runtime upgrades."""
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from desktop import runtime


def test_macos_data_and_companion_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'runtime' / 'Agentboard'))
    assert runtime.personal_dir() == tmp_path / 'Library/Application Support/Agentboard'
    assert runtime.companion_command() == [str(tmp_path / 'runtime/AgentboardMCP')]
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))
    assert runtime.personal_dir() == tmp_path / 'Local/Agentboard'
    assert runtime.binary_name('AgentboardMCP') == 'AgentboardMCP.exe'


@pytest.mark.skipif(os.name == 'nt', reason='Native flock requires macOS/Unix')
def test_unix_exclusive_server_and_multiple_mcp_sessions(tmp_path):
    desktop = runtime.acquire_mutex(data_dir=tmp_path)
    first = second = None
    try:
        assert desktop is not None
        assert runtime.acquire_mutex(data_dir=tmp_path) is None
        assert not runtime.mcp_running(tmp_path)
        first = runtime.acquire_mutex('MCP', tmp_path)
        second = runtime.acquire_mutex('MCP', tmp_path)
        assert first is not None and second is not None
        assert runtime.mcp_running(tmp_path)
        assert not runtime.mcp_running(tmp_path / 'other-profile')
        runtime.release_mutex(first)
        first = None
        assert runtime.mcp_running(tmp_path)
        runtime.release_mutex(second)
        second = None
        assert not runtime.mcp_running(tmp_path)
    finally:
        for handle in (first, second, desktop):
            runtime.release_mutex(handle)
    new = runtime.acquire_mutex(data_dir=tmp_path)
    assert new is not None
    runtime.release_mutex(new)
    # A session starting during the exclusive health probe waits, then owns a shared lock.
    import fcntl
    entered = threading.Event()
    def connect():
        entered.set()
        return runtime.acquire_mutex('MCP', tmp_path)
    with ThreadPoolExecutor(max_workers=1) as worker:
        with (tmp_path / '.mcp.lock').open('a+b') as probe:
            fcntl.flock(probe, fcntl.LOCK_EX)
            pending = worker.submit(connect)
            assert entered.wait(3)
            assert not pending.done()
        session = pending.result(timeout=3)
        try:
            assert session is not None and runtime.mcp_running(tmp_path)
        finally:
            runtime.release_mutex(session)
