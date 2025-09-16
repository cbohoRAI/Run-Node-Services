"""Process management for running Node.js projects."""

import asyncio
import contextlib
import os
import shutil
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.runner import NodeProjectRunnerApp

try:
    from models.data import RunningProject
    from utils.logging import MultiLogBuffer
    from utils.port import PortUtils
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


class ProcessManager:
    """Mixin class containing process management methods."""
    
    def _is_command_available(self: 'NodeProjectRunnerApp', cmd: str) -> bool:
        """Check if a command is available in PATH."""
        return shutil.which(cmd) is not None

    async def _start_project(self: 'NodeProjectRunnerApp', idx: int) -> None:
        """Start a single project and create its log tab."""
        proj = self.projects[idx]
        path = proj.path
        
        # Register project with log manager
        self.log_manager.add_project(idx, proj.name)
        
        # Create tab for this project
        self._add_project_tab(idx, proj.name)
        
        # Validate directory
        if not os.path.isdir(path):
            if self._log:
                self._log.write(f"[red]{proj.name}[/red]: Directory missing → {path}")
            return
        
        # Check for package.json
        pkg = os.path.join(path, 'package.json')
        if not os.path.exists(pkg):
            if self._log:
                self._log.write(f"[yellow]{proj.name}[/yellow]: package.json not found (continuing)")

        # Try to find port from .env file or package.json
        project_port = PortUtils.detect_project_port(path)
        if project_port:
            if self._log:
                self._log.write(f"[blue]{proj.name}[/blue]: Detected port {project_port}")
        else:
            if self._log:
                self._log.write(f"[yellow]{proj.name}[/yellow]: No port detected in .env or package.json")

        # Try external terminals first
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

        if cmd:
            try:
                term_proc = await asyncio.create_subprocess_exec(*cmd)
                self.processes[idx] = term_proc
                self.running_projects[idx] = RunningProject(
                    name=proj.name,
                    path=path,
                    pid=term_proc.pid,
                    status="External Terminal",
                    start_time=datetime.now(),
                    port=project_port
                )
                if self._log:
                    self._log.write(f"[green]{proj.name}[/green]: Started in external terminal (PID {term_proc.pid})")
                return
            except Exception as e:
                if self._log:
                    self._log.write(f"[red]{proj.name} external start failed:[/red] {e}. Falling back to in-app process.")
                # Fall through to internal start

        # Fallback to in-app process with log streaming
        try:
            proc = await asyncio.create_subprocess_exec(
                'npm', 'run', 'dev',
                cwd=path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self.processes[idx] = proc
            self.running_projects[idx] = RunningProject(
                name=proj.name,
                path=path,
                pid=proc.pid,
                status="Running",
                start_time=datetime.now(),
                port=project_port
            )
            if self._log:
                self._log.write(f"[cyan]{proj.name}[/cyan]: Started (PID {proc.pid})")
            self.log_tasks[idx] = asyncio.create_task(self._stream_logs(idx, proj.name, proc))
        except FileNotFoundError:
            if self._log:
                self._log.write(f"[red]{proj.name}[/red]: npm not found in PATH")
        except Exception as e:
            if self._log:
                self._log.write(f"[red]{proj.name}[/red]: Start error → {e}")

    async def _stream_logs(self: 'NodeProjectRunnerApp', idx: int, name: str, proc: asyncio.subprocess.Process) -> None:
        """Stream logs with tabbed output support."""
        if not proc.stdout:
            return
        
        colors = ["blue", "green", "yellow", "magenta", "cyan"]
        color = colors[idx % len(colors)]
        
        # Get both log widgets
        all_log_widget = self._log  # Main "All Logs" widget
        project_log_widget = self._project_log_widgets.get(idx)
        
        # Use the multi-output log buffer
        log_buffer = MultiLogBuffer(
            all_log_widget, 
            project_log_widget, 
            flush_interval=0.3, 
            max_buffer=15
        )
        
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                
                text = line.decode(errors='replace').rstrip('\n')
                if text.strip():
                    formatted_line = f"[bold {color}][{name}][/bold {color}] {text}"
                    log_buffer.add_line(formatted_line)
                    # Also add to log manager for persistence
                    self.log_manager.add_log_line(idx, formatted_line)
            
            # Ensure final flush
            log_buffer.flush_now()
            
            rc = await proc.wait()
            if idx in self.running_projects:
                self.running_projects[idx].status = f"Exited ({rc})"
            if self._log:
                exit_message = f"[magenta]{name}[/magenta]: Exited with code {rc}"
                self._log.write(exit_message)
                # Also write exit message to project tab
                if project_log_widget:
                    project_log_widget.write(exit_message)
                
        except asyncio.CancelledError:
            log_buffer.flush_now()  # Flush before canceling
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
            if idx in self.running_projects:
                self.running_projects[idx].status = "Terminated"
        except Exception as e:
            log_buffer.flush_now()
            error_message = f"[red]{name} log error:[/red] {e}"
            if self._log:
                self._log.write(error_message)
            # Also write error to project tab
            if project_log_widget:
                project_log_widget.write(error_message)
            if idx in self.running_projects:
                self.running_projects[idx].status = "Error"

    async def _cleanup_processes(self: 'NodeProjectRunnerApp') -> None:
        """Clean up running processes and log the shutdown."""
        if self._cleanup_started:
            return
        self._cleanup_started = True

        # Log shutdown info
        try:
            with open("shutdown.log", "a") as f:
                f.write(f"Shutdown at {datetime.now()}\n")
                if self.processes:
                    for idx, proc in self.processes.items():
                        proj = self.projects[idx] if idx < len(self.projects) else None
                        name = proj.name if proj else f"Unknown-{idx}"
                        pid = getattr(proc, "pid", None)
                        
                        # Get port info if available
                        running_proj = self.running_projects.get(idx)
                        port = running_proj.port if running_proj else None
                        
                        f.write(f"  Attempting to kill: {name} (PID: {pid}, Port: {port})\n")
                else:
                    f.write("  No processes to kill.\n")
        except Exception as e:
            # If logging fails, ignore to not block shutdown
            pass

        # Cancel log tasks
        for task in self.log_tasks.values():
            task.cancel()
        
        # Remove all project tabs
        for idx in list(self.running_projects.keys()):
            self._remove_project_tab(idx)
            self.log_manager.remove_project(idx)
        
        # First, try to kill processes by port (more effective for Node.js)
        ports_killed = set()
        for idx, running_proj in self.running_projects.items():
            if running_proj.port and running_proj.port not in ports_killed:
                if self._log:
                    self._log.write(f"[yellow]Killing processes on port {running_proj.port}[/yellow]")
                
                success = PortUtils.kill_processes_by_port(running_proj.port)
                ports_killed.add(running_proj.port)
                
                if success:
                    if self._log:
                        self._log.write(f"[green]Successfully killed processes on port {running_proj.port}[/green]")
                else:
                    if self._log:
                        self._log.write(f"[red]Failed to kill some processes on port {running_proj.port}[/red]")
        
        # Wait a moment for port-based kills to take effect
        await asyncio.sleep(1.0)
        
        # Then terminate direct child processes (npm processes)
        for proc in self.processes.values():
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
        
        # Give them time to terminate
        await asyncio.sleep(0.5)
        
        # Force kill remaining processes if needed
        for proc in self.processes.values():
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass