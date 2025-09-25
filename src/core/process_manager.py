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
# import logging
import time

from .port_scanner import find_process_by_port, kill_process_tree
from .resource_registry import ResourceRegistry
from .node_killer import NodeProcessKiller

# logger = logging.getLogger(__name__)

from .shutdown_logger import shutdown_logger
logger = shutdown_logger

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
    # Reader tasks for stdout / stderr so we can cancel them explicitly
    reader_tasks: Set[asyncio.Task] = field(default_factory=set)


class ProcessManager:
    def __init__(self, registry: Optional[ResourceRegistry] = None) -> None:
        self._processes: Dict[str, ManagedProcess] = {}
        self._lock = asyncio.Lock()
        self.registry = registry or ResourceRegistry()
        self.node_killer = NodeProcessKiller()
        self._shutdown_flag = False  # Flag to prevent new operations during shutdown
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
        # Check shutdown flag
        if self._shutdown_flag:
            logger.warning("Cannot start project %s: shutdown in progress", name)
            return False
        
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

            # Register the process with the resource registry
            await self.registry.register_process(
                name=name,
                wrapper_process=process,
                port=port,
                path=str(path),
                command=cmd
            )
            
            # Spawn readers immediately
            # Track reader tasks so they can be cancelled prior to loop shutdown
            if process.stdout:
                t = asyncio.create_task(self._read_stream(name, process.stdout, on_output))
                mp.reader_tasks.add(t)
                # Register task with registry
                await self.registry.register_task(name, t)
            if process.stderr:
                t = asyncio.create_task(self._read_stream(name, process.stderr, on_output))
                mp.reader_tasks.add(t)
                # Register task with registry
                await self.registry.register_task(name, t)

        # Outside lock: optionally wait for port
        if port:
            await self._wait_and_map_port(name, port)
        return True

    async def stop_project(self, name: str) -> bool:
        # Use the new NodeProcessKiller for better shutdown
        async with self._lock:
            mp = self._processes.get(name)
            if not mp:
                return False
            proc = mp.spawn_process
            listener_pids = set(mp.listener_pids)
            port = mp.requested_port
            reader_tasks = set(mp.reader_tasks)
        
        # Get resource bundle from registry
        bundle = await self.registry.get_all_resources(name)
        
        # Use NodeProcessKiller for comprehensive cleanup
        if bundle.process_info or port or listener_pids:
            await self.node_killer.kill_node_project(
                name=name,
                port=port,
                wrapper_pid=proc.pid,
                known_node_pids=listener_pids
            )
        
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
                # Give it a moment to actually die
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass
        # Cancel stream reader tasks before closing transports so they don't reschedule callbacks
        for t in reader_tasks:
            if not t.done():
                t.cancel()
                # Remove from registry
                await self.registry.remove_task(name, t)
        if reader_tasks:
            try:
                await asyncio.gather(*reader_tasks, return_exceptions=True)
            except Exception:  # noqa: BLE001
                pass
        
        # Safely close subprocess pipes to prevent event loop errors
        self._close_subprocess_safely(proc)

        # Kill any tracked listener pids (they may remain if wrapper exited)
        for pid in listener_pids:
            kill_process_tree(pid)

        # If we know the port, double‑check nothing remains
        if port:
            for pid in find_process_by_port(port):
                kill_process_tree(pid)

        async with self._lock:
            self._processes.pop(name, None)
        
        # Clear all resources from registry
        await self.registry.clear_resources(name)
        
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
    
    async def cleanup_resources(self) -> None:
        """Clean up all subprocess resources to prevent event loop errors on shutdown.
        
        Should be called before the event loop closes.
        """
        # Get all project names from both internal dict and registry
        project_names = set()
        async with self._lock:
            project_names.update(self._processes.keys())
        project_names.update(await self.registry.get_all_project_names())
        
        # Clean up each project
        for name in project_names:
            try:
                # Get resources from registry
                bundle = await self.registry.get_all_resources(name)
                
                # Cancel reader tasks
                for task in bundle.tasks:
                    if not task.done():
                        task.cancel()
                
                if bundle.tasks:
                    try:
                        await asyncio.gather(*bundle.tasks, return_exceptions=True)
                    except Exception:  # noqa: BLE001
                        pass
                
                # Clean up process if exists
                mp = self._processes.get(name)
                if mp:
                    proc = mp.spawn_process
                    # If process is still running, try one more terminate/kill
                    if proc.returncode is None:
                        try:
                            proc.terminate()
                            await asyncio.wait_for(proc.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            try:
                                proc.kill()
                                await asyncio.wait_for(proc.wait(), timeout=1.0)
                            except asyncio.TimeoutError:
                                pass  # Give up, but still clean up
                    
                    # Now safely close the subprocess
                    self._close_subprocess_safely(proc)
                
                # Clear resources from registry
                await self.registry.clear_resources(name)
                
            except Exception:
                # Ignore all errors during cleanup
                pass
        
        # Clear the processes dict
        async with self._lock:
            self._processes.clear()

        # Allow the loop a moment to run any callbacks generated by closing transports
        try:
            await asyncio.sleep(0)
        except RuntimeError:
            # Loop already closing/closed; ignore
            pass

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

    def _close_subprocess_safely(self, proc: asyncio.subprocess.Process) -> None:
        """Safely close subprocess and its transport to prevent event loop errors on shutdown."""
        try:
            logger.debug("Closing subprocess resources pid=%s returncode=%s", getattr(proc, 'pid', '?'), proc.returncode)
            # Close pipes explicitly before the event loop shuts down
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
            if proc.stdout and not proc.stdout.is_closing():
                proc.stdout.close()
            if proc.stderr and not proc.stderr.is_closing():
                proc.stderr.close()
            
            # Close the underlying transport to prevent BaseSubprocessTransport.__del__ errors
            # The transport is what actually causes the "Event loop is closed" error
            transport = getattr(proc, '_transport', None)
            if transport and hasattr(transport, 'close'):
                try:
                    transport.close()
                except Exception:
                    pass
                    
        except Exception:
            # Ignore errors during cleanup - we're shutting down anyway
            pass

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
        
        # Register discovered Node.js PIDs with the resource registry
        if captured:
            await self.registry.register_node_pids(name, captured)
            logger.debug("Registered Node.js PIDs for %s: %s", name, captured)

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
        except asyncio.CancelledError:  # Task cancelled during shutdown
            pass
        except Exception:  # noqa: BLE001
            logger.exception("Stream reader crashed for %s", name)

    def _command_for_project(self, path: Path) -> List[str]:
        # Simple heuristic: prefer npm
        if sys.platform == "win32":
            return ["npm", "start"]
        return ["npm", "start"]


__all__ = ["ProcessManager"]
