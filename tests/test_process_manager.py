import asyncio
from pathlib import Path
import pytest
from src.core.process_manager import ProcessManager

# These tests assume npm is installed; if not, they skip gracefully.

def has_npm() -> bool:
    import shutil
    return shutil.which("npm") is not None

@pytest.mark.asyncio
async def test_start_stop_no_package(tmp_path: Path) -> None:
    if not has_npm():
        pytest.skip("npm not available")
    # Create minimal package.json with start script that exits quickly
    (tmp_path / "package.json").write_text('{"name": "t","scripts":{"start":"node -e \"console.log(1)\""}}')
    mgr = ProcessManager()
    started = await mgr.start_project("t", tmp_path)
    assert started
    await asyncio.sleep(0.5)
    await mgr.stop_all()

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
