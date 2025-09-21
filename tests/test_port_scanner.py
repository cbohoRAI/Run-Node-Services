import asyncio
import socket
from pathlib import Path

from src.core.port_scanner import find_process_by_port, kill_process_tree
import psutil


def _open_ephemeral_server()->tuple[int,int]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    return s.fileno(), port  # keep socket open via FD; process will own it


def test_find_process_by_port_self():
    # Create a listening socket in this process and verify discovery
    fd, port = _open_ephemeral_server()
    pids = find_process_by_port(port)
    assert psutil.Process().pid in pids


def test_kill_process_tree(tmp_path: Path):
    # Spawn a subprocess that sleeps; ensure kill terminates it
    import subprocess, sys
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])  # noqa: S603,S607
    try:
        assert proc.poll() is None
        kill_process_tree(proc.pid)
        proc.wait(timeout=5)
        assert proc.returncode is not None
    finally:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
