import asyncio
from pathlib import Path
import pytest
import sys
import socket
from src.core.process_manager import ProcessManager
from src.core.port_scanner import find_process_by_port

# These tests assume npm is installed; if not, they skip gracefully.

def has_npm() -> bool:
    import shutil
    return shutil.which("npm") is not None

def _reserve_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _dummy_output(project: str, line: str):  # pragma: no cover - helper
    pass

@pytest.mark.asyncio
async def test_start_stop_with_port(tmp_path: Path):
    if not has_npm():
        pytest.skip("npm not available")
    proj = tmp_path / "proj"
    proj.mkdir()
    script = proj / "server.py"
    # Minimal TCP server that listens then sleeps
    script.write_text(
        "import socket, time, sys; s=socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen(1); print('LISTENING', flush=True); time.sleep(5)"
    )

    port = _reserve_port()
    pm = ProcessManager()
    started = await pm.start_project(
        name="demo", path=proj, command=[sys.executable, str(script), str(port)], port=port, on_output=_dummy_output
    )
    assert started
    await asyncio.sleep(0.5)
    # Port should be mapped
    pids = find_process_by_port(port)
    assert pids, "Expected a listener PID for the test server"
    assert "demo" in pm.list_running()
    stopped = await pm.stop_project("demo")
    assert stopped
    assert "demo" not in pm.list_running()

@pytest.mark.asyncio
async def test_restart(tmp_path: Path):
    proj = tmp_path / "proj2"
    proj.mkdir()
    script = proj / "server.py"
    script.write_text(
        "import socket, time, sys; s=socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen(1); print('UP', flush=True); time.sleep(2)"
    )
    port = _reserve_port()
    pm = ProcessManager()
    assert await pm.start_project(
        name="demo2", path=proj, command=[sys.executable, str(script), str(port)], port=port
    )
    await asyncio.sleep(0.4)
    assert await pm.restart_project("demo2")
    await asyncio.sleep(0.4)
    assert "demo2" in pm.list_running()
    await pm.stop_all()

@pytest.mark.asyncio
async def test_multiple_start_guard(tmp_path: Path) -> None:
    if not has_npm():
        pytest.skip("npm not available")
    (tmp_path / "package.json").write_text('{"name": "t2","scripts":{"start":"node -e \"setTimeout(()=>{},5000)\""}}')
    mgr = ProcessManager()
    first = await mgr.start_project("t2", tmp_path)
    second = await mgr.start_project("t2", tmp_path)
    assert first is True and second is False
    await mgr.stop_all()
