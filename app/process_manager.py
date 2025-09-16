"""Process management for running Node.js projects."""

import asyncio
import contextlib
import os
import shutil
from datetime import datetime
from typing import Protocol, runtime_checkable
from weakref import WeakValueDictionary

try:
    from models.data import RunningProject
    from utils.logging import MultiLogBuffer
    from utils.port import PortUtils
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


@runtime_checkable
class ProcessManagerProtocol(Protocol):
    """Protocol defining the interface that ProcessManager expects."""
    projects: list
    processes: dict
    running_projects: dict
    log_tasks: dict
    log_manager: object
    _log: object
    _cleanup_started: bool
    _cleanup_lock: asyncio.Lock
    _project_log_widgets: dict
    _active_tasks: set
    
    def _add_project_tab(self, idx: int, name: str) -> None: ...
    def _remove_project_tab(self, idx: int) -> None: ...
    def create_task(self, coro) -> asyncio.Task: ...


class ProcessManager:
    """Mixin class containing process management methods."""
    
    # Cache for command availability checks
    _command_cache: dict = {}
    
    def _is_command_available(self: ProcessManagerProtocol, cmd: str) -> bool:
        """Check if a command is available in PATH (cached)."""
        if cmd not in self._command_cache:
            self._command_cache[cmd] = shutil.which(cmd) is not None
        return self._command_cache[cmd]

    async def _start_project(self: ProcessManagerProtocol, idx: int) -> None:
        """Start a single project and create its log tab."""
        proj = self.projects[idx]
        path = proj.path
        
        # Quick validation
        if not os.path.isdir(path):
            if self._log:
                self._log.write(f"[red]{proj.name}[/red]: Directory missing → {path}")
            return
        
        # Register with log manager
        self.log_manager.add_project(idx, proj.name)
        
        # Add tab asynchronously to not block
        self._add_project_tab(idx, proj.name)
        
        # Check for package.json (non-blocking)
        pkg = os.path.join(path, 'package.json')
        has_package = os.path.exists(pkg)
        
        if not has_package and self._log:
            self._log.write(f"[yellow]{proj.name}[/yellow]: package.json not found")
        
        # Detect port asynchronously
        project_port = await asyncio.get_event_loop().run_in_executor(
            None, PortUtils.detect_project_port, path
        )
        
        if project_port and self._log:
            self._log.write(f"[blue]{proj.name}[/blue]: Port {project_port}")
        
        # Try external terminal first (faster startup)
        external_started = await self._try_external_terminal(
            self, idx, proj, path, project_port
        )
        
        if not external_started:
            # Fallback to internal process
            await self._start_internal_process(
                self, idx, proj, path, project_port
            )

    async def _try_external_terminal(
        self: ProcessManagerProtocol, 
        idx: int, 
        proj: object, 
        path: str, 
        port: int
    ) -> bool:
        """Try to start in external terminal."""
        cmd = None
        
        if self._is_command_available('gnome-terminal'):
            cmd = [
                'gnome-terminal', '--tab', '--title', proj.name, '--', 'bash', '-c',
                f"cd '{path}' && npm run dev; exec bash"
            ]
        elif self._is_command_available('xterm'):
            cmd = [
                'xterm', '-T', proj.name, '-e',
                f"bash -c 'cd \"{path}\" && npm run dev; exec bash'"
            ]
        
        if not cmd:
            return False
        
        try:
            proc = await asyncio.create_subprocess_exec(*cmd)
            self.processes[idx] = proc
            self.running_projects[idx] = RunningProject(
                name=proj.name,
                path=path,
                pid=proc.pid,
                status="External Terminal",
                start_time=datetime.now(),
                port=port
            )
            if self._log:
                self._log.write(f"[green]{proj.name}[/green]: External terminal (PID {proc.pid})")
            return True
        except Exception:
            return False

    async def _start_internal_process(
        self: ProcessManagerProtocol,
        idx: int,
        proj: object,
        path: str,
        port: int
    ) -> None:
        """Start process internally with log streaming."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'npm', 'run', 'dev',
                cwd=path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                # Use smaller buffer for faster response
                limit=1024 * 64  # 64KB buffer
            )
            
            self.processes[idx] = proc
            self.running_projects[idx] = RunningProject(
                name=proj.name,
                path=path,
                pid=proc.pid,
                status="Running",
                start_time=datetime.now(),
                port=port
            )
            
            if self._log:
                self._log.write(f"[cyan]{proj.name}[/cyan]: Started (PID {proc.pid})")
            
            # Create log streaming task
            task = self.create_task(
                self._stream_logs_optimized(idx, proj.name, proc)
            )
            self.log_tasks[idx] = task
            
        except FileNotFoundError:
            if self._log:
                self._log.write(f"[red]{proj.name}[/red]: npm not found")
        except Exception as e:
            if self._log:
                self._log.write(f"[red]{proj.name}[/red]: Error → {e}")

    async def _stream_logs_optimized(
        self: ProcessManagerProtocol,
        idx: int,
        name: str,
        proc: asyncio.subprocess.Process
    ) -> None:
        """Optimized log streaming with batching."""
        if not proc.stdout:
            return
        
        colors = ["blue", "green", "yellow", "magenta", "cyan"]
        color = colors[idx % len(colors)]
        
        # Get log widgets
        all_log = self._log
        project_log = self._project_log_widgets.get(idx)
        
        # Use smaller buffer for faster updates
        log_buffer = MultiLogBuffer(
            all_log,
            project_log,
            flush_interval=0.2,  # Faster flush
            max_buffer=10  # Smaller buffer
        )
        
        try:
            # Use readline with timeout for responsiveness
            while True:
                try:
                    # Read with timeout to ensure responsiveness
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=0.5
                    )
                    
                    if not line_bytes:
                        break
                    
                    text = line_bytes.decode(errors='replace').rstrip('\n')
                    if text.strip():
                        formatted = f"[bold {color}][{name}][/bold {color}] {text}"
                        log_buffer.add_line(formatted)
                        self.log_manager.add_log_line(idx, formatted)
                        
                except asyncio.TimeoutError:
                    # Flush any pending logs on timeout
                    log_buffer.flush_now()
                    continue
            
            # Final flush
            log_buffer.flush_now()
            
            # Handle process exit
            rc = await proc.wait()
            if idx in self.running_projects:
                self.running_projects[idx].status = f"Exited ({rc})"
            
            exit_msg = f"[magenta]{name}[/magenta]: Exited with code {rc}"
            if all_log:
                all_log.write(exit_msg)
            if project_log:
                project_log.write(exit_msg)
                
        except asyncio.CancelledError:
            log_buffer.flush_now()
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
            if idx in self.running_projects:
                self.running_projects[idx].status = "Terminated"
        except Exception as e:
            log_buffer.flush_now()
            if self._log:
                self._log.write(f"[red]{name} error:[/red] {e}")
            if idx in self.running_projects:
                self.running_projects[idx].status = "Error"

    async def _cleanup_processes(self: ProcessManagerProtocol) -> None:
        """Clean up running processes efficiently."""
        async with self._cleanup_lock:
            if self._cleanup_started:
                return
            self._cleanup_started = True
            
            # Cancel all log tasks first
            tasks_to_cancel = list(self.log_tasks.values())
            for task in tasks_to_cancel:
                task.cancel()
            
            # Wait for cancellation with timeout
            if tasks_to_cancel:
                await asyncio.wait(
                    tasks_to_cancel,
                    timeout=1.0,
                    return_when=asyncio.ALL_COMPLETED
                )
            
            # Kill by ports (most effective)
            ports_killed = set()
            kill_tasks = []
            
            for idx, proj in self.running_projects.items():
                if proj.port and proj.port not in ports_killed:
                    ports_killed.add(proj.port)
                    # Kill ports in parallel
                    kill_tasks.append(
                        asyncio.get_event_loop().run_in_executor(
                            None, PortUtils.kill_processes_by_port, proj.port
                        )
                    )
            
            if kill_tasks:
                await asyncio.gather(*kill_tasks, return_exceptions=True)
            
            # Quick termination of remaining processes
            for proc in self.processes.values():
                if proc.returncode is None:
                    try:
                        proc.terminate()
                    except ProcessLookupError:
                        pass
            
            # Force kill after short wait
            await asyncio.sleep(0.5)
            for proc in self.processes.values():
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
            
            # Clean up UI
            for idx in list(self.running_projects.keys()):
                self._remove_project_tab(idx)
                self.log_manager.remove_project(idx)