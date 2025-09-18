"""Basic asynchronous process management for Phase 1.

Responsibilities:
- Start a Node.js project using npm/yarn/pnpm (simple heuristic)
- Capture stdout/stderr lines asynchronously
- Provide stop capability

Phase 1 keeps this intentionally simple; Phase 2 will introduce
port-based tracking and robust tree termination.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, AsyncIterator, Callable, List
import asyncio
import sys
import logging

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunningProcess:
    project_name: str
    path: Path
    process: asyncio.subprocess.Process


class ProcessManager:
    def __init__(self) -> None:
        self._processes: Dict[str, RunningProcess] = {}
        self._lock = asyncio.Lock()

    async def start_project(
        self,
        name: str,
        path: Path,
        on_output: Optional[Callable[[str, str], None]] = None,
        command: Optional[List[str]] = None,
    ) -> bool:
        """Start a project if not already running.

        Parameters
        ----------
        name: Project identifier.
        path: Project directory.
        on_output: Callback invoked with (project_name, line).
        """
        async with self._lock:
            if name in self._processes:
                logger.info("Project %s already running", name)
                return False

            cmd = command or self._command_for_project(path)
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                logger.error("Failed to start %s: %s", name, exc)
                return False

            rp = RunningProcess(project_name=name, path=path, process=process)
            self._processes[name] = rp
            logger.info("Started project %s (pid=%s)", name, process.pid)

            # Spawn readers
            if process.stdout:
                asyncio.create_task(self._read_stream(name, process.stdout, on_output))
            if process.stderr:
                asyncio.create_task(self._read_stream(name, process.stderr, on_output))
            return True

    async def stop_project(self, name: str) -> bool:
        async with self._lock:
            rp = self._processes.get(name)
            if not rp:
                return False
            proc = rp.process
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning("Force killing %s", name)
                    proc.kill()
            del self._processes[name]
            logger.info("Stopped project %s", name)
            return True

    async def stop_all(self) -> None:
        async with self._lock:
            names = list(self._processes.keys())
        for n in names:
            try:
                await self.stop_project(n)
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping %s", n)

    def list_running(self) -> List[str]:
        return list(self._processes.keys())

    async def _read_stream(
        self,
        name: str,
        stream: asyncio.StreamReader,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        try:
            while not stream.at_eof():
                line = await stream.readline()
                if not line:
                    break
                try:
                    decoded = line.decode(errors="replace").rstrip()
                except Exception:  # noqa: BLE001
                    decoded = repr(line)
                if on_output:
                    on_output(name, decoded)
        except Exception:  # noqa: BLE001
            logger.exception("Stream reader crashed for %s", name)

    def _command_for_project(self, path: Path) -> List[str]:
        # Simple heuristic: prefer npm
        if sys.platform == "win32":
            return ["npm", "start"]
        return ["npm", "start"]


__all__ = ["ProcessManager"]
