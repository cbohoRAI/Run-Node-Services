"""Process management (Phase 2).

Enhancements over Phase 1:
* Track processes by logical project name AND intended port (if known)
* Port-based verification after spawn to map to the "real" Node (child) PID
* Graceful stop that also terminates any remaining listeners on the port
* Optional restart routine
* Internal readers remain lightweight / backpressure-aware

Backward compatibility: The original ``ProcessManager`` API (start_project, stop_project,
stop_all, list_running) is preserved. Callers may pass a ``port`` argument to
``start_project`` to enable port tracking; otherwise behaviour degrades to
simple PID management.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Callable, List, Set
import asyncio
import sys
import logging
import time

from .port_scanner import find_process_by_port, kill_process_tree

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ManagedProcess:
    project_name: str
    path: Path
    spawn_process: asyncio.subprocess.Process
    start_command: List[str]
    requested_port: Optional[int] = None
    # PIDs discovered to actually own the listening port (may include node, ts-node, etc.)
    listener_pids: Set[int] = field(default_factory=set)
    started_at: float = field(default_factory=time.time)
    restarting: bool = False


class ProcessManager:
    def __init__(self) -> None:
        self._processes: Dict[str, ManagedProcess] = {}
        self._lock = asyncio.Lock()
        # Wait parameters
        self._port_wait_interval = 0.3
        self._port_wait_timeout = 12.0

    async def start_project(
        self,
        name: str,
        path: Path,
        on_output: Optional[Callable[[str, str], None]] = None,
        command: Optional[List[str]] = None,
        port: Optional[int] = None,
    ) -> bool:
        """Start a project if not already running.

        If ``port`` is provided we will attempt to wait until that port is
        observed in a listening state and then capture the real listener pids.
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

            mp = ManagedProcess(
                project_name=name,
                path=path,
                spawn_process=process,
                start_command=cmd,
                requested_port=port,
            )
            self._processes[name] = mp
            logger.info(
                "Started project %s (wrapper pid=%s, port=%s)",
                name,
                process.pid,
                port,
            )

            # Spawn readers immediately
            if process.stdout:
                asyncio.create_task(self._read_stream(name, process.stdout, on_output))
            if process.stderr:
                asyncio.create_task(self._read_stream(name, process.stderr, on_output))

        # Outside lock: optionally wait for port
        if port:
            await self._wait_and_map_port(name, port)
        return True

    async def stop_project(self, name: str) -> bool:
        async with self._lock:
            mp = self._processes.get(name)
            if not mp:
                return False
            proc = mp.spawn_process
            listener_pids = set(mp.listener_pids)
            port = mp.requested_port
        # operate outside lock for termination
        if proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Force killing wrapper for %s", name)
                proc.kill()

        # Kill any tracked listener pids (they may remain if wrapper exited)
        for pid in listener_pids:
            kill_process_tree(pid)

        # If we know the port, double‑check nothing remains
        if port:
            for pid in find_process_by_port(port):
                kill_process_tree(pid)

        async with self._lock:
            self._processes.pop(name, None)
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

    async def restart_project(
        self, name: str, on_output: Optional[Callable[[str, str], None]] = None
    ) -> bool:
        """Restart a running project.

        Returns True if restart succeeded.
        """
        async with self._lock:
            mp = self._processes.get(name)
            if not mp:
                logger.warning("Restart requested for unknown project %s", name)
                return False
            if mp.restarting:
                logger.info("Project %s already restarting", name)
                return False
            mp.restarting = True
            path = mp.path
            cmd = list(mp.start_command)
            port = mp.requested_port

        # Stop outside lock
        await self.stop_project(name)

        # Start again
        ok = await self.start_project(
            name=name, path=path, on_output=on_output, command=cmd, port=port
        )
        async with self._lock:
            mp_new = self._processes.get(name)
            if mp_new:
                mp_new.restarting = False
        return ok

    def list_running(self) -> List[str]:
        return list(self._processes.keys())

    async def _wait_and_map_port(self, name: str, port: int) -> None:
        """Wait until the given port is listening and record listener PIDs.

        Non-fatal on timeout; best effort.
        """
        deadline = time.time() + self._port_wait_timeout
        captured: Set[int] = set()
        while time.time() < deadline:
            pids = find_process_by_port(port)
            if pids:
                captured.update(pids)
                break
            await asyncio.sleep(self._port_wait_interval)
        if not captured:
            logger.warning(
                "Timeout waiting for port %s for project %s", port, name
            )
        async with self._lock:
            mp = self._processes.get(name)
            if mp:
                mp.listener_pids = captured

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
