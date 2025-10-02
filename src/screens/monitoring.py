"""Monitoring screen (Phase 3) - Enhanced version with health checking."""
from __future__ import annotations

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Footer, Header
from textual import events
from textual.containers import Vertical, Container
from typing import Dict, List, Optional
from rich.text import Text
import asyncio
import os

from src.widgets.running_panel import RunningPanel
from src.widgets.simple_log_viewer import SimpleLogViewer   # CHANGE: debug viewer
from src.models.status import ProjectStatus
from src.core.process_manager import ProcessManager
from src.core.log_collector import LogCollector
from src.core.project_discovery import NodeProject
from src.core.shutdown_manager import ShutdownManager, ShutdownPhase
from src.core.resource_registry import ResourceRegistry
from src.core.health_checker import HealthChecker
from src.screens.restart_dialog import RestartDialog

class MonitoringScreen(Screen):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_panel", "Toggle Panel"),
        ("r", "restart", "Restart"),
        ("s", "stop_all", "Stop All"),
        ("a", "show_all_logs", "All Logs"),
    ]

    DEFAULT_CSS = """
    MonitoringScreen {
        background: $background;
    }
    #monitoring-container {
        layout: vertical;        /* CHANGE: explicit */
        height: 100%;
        width: 100%;
    }
    RunningPanel {
        height: 8;
        min-height: 5;
        max-height: 12;          /* Keep small so log area is obvious */
    }
    SimpleLogViewer {
        border: solid $primary;
        height: 1fr;             /* Fills remaining space */
        min-height: 10;
    }
    Header {
        background: $background;
    }
    
    Footer {
        background: $background;
    }
    """

    def __init__(
        self, 
        manager: ProcessManager, 
        log_collector: LogCollector, 
        projects: List[Dict[str, any]]
    ) -> None:
        """Initialize monitoring screen.
        
        Args:
            manager: Process manager instance
            log_collector: Log collector instance  
            projects: List of project dictionaries with 'name', 'port', 'branch' keys
        """
        super().__init__()
        self._manager = manager
        self._log_collector = log_collector
        self._projects = projects
        self._panel: Optional[RunningPanel] = None
        self._logs: Optional[SimpleLogViewer] = None
        
        # Initialize health checker
        self._health_checker = HealthChecker(
            check_interval=5.0,
            startup_grace_period=15.0,
            timeout=3.0,
            failure_threshold=3,
        )
        
        # Ensure manager has a resource registry
        if not hasattr(manager, 'registry') or manager.registry is None:
            manager.registry = ResourceRegistry()
        
        # Map project name -> short nickname (or fallback to name) for log prefixes
        self._name_to_short: Dict[str, str] = {}
        # Map project name -> color style name
        self._project_colors: Dict[str, str] = {}
        # Simple deterministic palette (cycled if more projects than colors)
        self._color_palette: List[str] = [
            "cyan",
            "magenta",
            "yellow",
            "green",
            "blue",
            "bright_magenta",
            "bright_cyan",
            "bright_yellow",
            "bright_green",
        ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Use a Vertical container to enforce vertical stacking
        with Vertical(id="monitoring-container"):  # CHANGE: Vertical instead of generic Container
            self._panel = RunningPanel()
            yield self._panel
            # Replace TabbedLogViewer with SimpleLogViewer
            self._logs = SimpleLogViewer()          # CHANGE
            yield self._logs
        yield Footer()

    def on_mount(self) -> None:
        # Populate panel and register projects for health checking
        for idx, proj_info in enumerate(self._projects):
            if isinstance(proj_info, dict):
                name = proj_info.get('name')
                port = proj_info.get('port')
                branch = proj_info.get('branch')
                health_path = proj_info.get('healthPath', '/ping')
                # Prefer explicit short_name, then short, then alias
                short = proj_info.get('short_name') or proj_info.get('short') or proj_info.get('alias')
            else:
                name = getattr(proj_info, 'name', str(proj_info))
                port = getattr(proj_info, 'port', None)
                branch = getattr(proj_info, 'git_branch', None)
                health_path = getattr(proj_info, 'health_path', '/ping')
                short = getattr(proj_info, 'short_name', None)
            
            # Build nickname mapping (fallback to full name if missing)
            if name:
                self._name_to_short[name] = (short or name)[:10]  # trim overly long nicknames
                # Assign color deterministically if not already set
                if name not in self._project_colors:
                    self._project_colors[name] = self._color_palette[idx % len(self._color_palette)]
            
            # Set initial status to STARTING
            self._panel.set_project(name, ProjectStatus.STARTING, port, branch)
            
            # Register project for health checking if we have a port
            if port and name:
                self._health_checker.register_project(name, port, health_path)
        
        # Initialize log viewer project registry (for completeness)
        if self._logs:
            self._logs.set_projects(list(self._name_to_short.keys()))
        
        # Register health status callback
        self._health_checker.register_callback(self._on_health_status_change)
        
        # Register log callback
        self._log_collector.register_callback(self._on_log_line)
        
        # Register nodemon restart detection callback
        self._log_collector.register_restart_callback(self._on_nodemon_restart)
        
        # Register nodemon crash detection callback (supplementary to health checks)
        self._log_collector.register_crash_callback(self._on_nodemon_crash)
        
        # Start health checker
        asyncio.create_task(self._health_checker.start())
        
        # DEBUG: emit a test line to verify viewer path
        # if self._logs:
        #     self._logs.add_log("system", Text("(debug) Monitoring screen mounted", style="italic dim"))
        self._panel.refresh(recompose=True)

    def _on_log_line(self, project: str, line: str) -> None:
        # DEBUG instrumentation (also goes to terminal)
        print(f"[DEBUG monitor cb] {project}: {line}")
        short = self._name_to_short.get(project, project)
        color = self._project_colors.get(project, "white")
        if self._logs:
            try:
                txt = Text()
                txt.append("[", style="dim")
                txt.append(short, style=f"bold {color}")
                txt.append("] ", style="dim")
                txt.append(line.rstrip("\r\n"))
                self._logs.add_log(project=project, text=txt)
            except Exception as e:
                print(f"[DEBUG monitor cb ERROR] {e}")
    
    def _on_health_status_change(self, project: str, status: ProjectStatus) -> None:
        """Handle health status changes from the health checker."""
        if self._panel:
            self._panel.update_status(project, status)
        
        # Log status changes
        # if self._logs:
        #     status_messages = {
        #         ProjectStatus.RUNNING: f"[green]✓[/green] {project} is healthy",
        #         ProjectStatus.UNHEALTHY: f"[orange1]⚠[/orange1] {project} health check failed",
        #         ProjectStatus.UNRESPONSIVE: f"[dark_orange]◯[/dark_orange] {project} is unresponsive",
        #         ProjectStatus.CRASHED: f"[red]✖[/red] {project} has crashed",
        #         ProjectStatus.RESTARTING: f"[magenta]◆[/magenta] {project} is restarting",
        #     }
        #     message = status_messages.get(status, f"{project} status: {status.value}")
        #     self._logs.add_log("HEALTH", Text(message))
    
    def _on_nodemon_restart(self, project: str) -> None:
        """Handle nodemon restart detection from log output."""
        # Mark project as restarting in health checker
        self._health_checker.mark_restarting(project)
        
        # Update UI panel
        if self._panel:
            self._panel.update_status(project, ProjectStatus.RESTARTING)
        
        # Log the restart
        if self._logs:
            self._logs.add_log("NODEMON", Text(f"[magenta]◆[/magenta] {project} detected nodemon restart"))
    
    def _on_nodemon_crash(self, project: str) -> None:
        """Handle nodemon crash detection from log output.
        
        Note: This is supplementary - health checks are the primary crash detection.
        """
        # Mark process as not running (but health checker will do its own detection too)
        self._health_checker.mark_process_running(project, False)
        
        # Log the crash
        if self._logs:
            self._logs.add_log("NODEMON", Text(f"[red]✖[/red] {project} nodemon reported crash"))

    # Actions ---------------------------------------------------------------
    async def action_quit(self) -> None:
        """Quit the application using enhanced shutdown system."""
        try:
            # Stop health checker first
            await self._health_checker.stop()
            
            # Create shutdown manager
            shutdown_manager = ShutdownManager(
                self._manager.registry,
                self._manager,
                graceful_timeout=10.0,
                emergency_timeout=15.0
            )
            
            # Set up progress callbacks
            shutdown_manager.on_phase_change = self._on_shutdown_phase_change
            shutdown_manager.on_progress_update = self._on_shutdown_progress
            
            # Show shutdown notification
            if self._logs:
                self._logs.add_log("SYSTEM", "[bold yellow]Initiating graceful shutdown...[/bold yellow]")
            
            # Execute shutdown
            await shutdown_manager.initiate_shutdown("user_quit")
            
            # Update UI to show projects are stopped
            for proj_info in self._projects:
                name = proj_info.get('name') if isinstance(proj_info, dict) else proj_info
                if self._panel:
                    self._panel.update_status(name, ProjectStatus.STOPPED)
                    
        except Exception as e:
            # Emergency exit on failure
            if self._logs:
                self._logs.add_log("SYSTEM", f"[bold red]Shutdown failed: {e}[/bold red]")
                self._logs.add_log("SYSTEM", "[bold red]Performing emergency exit...[/bold red]")
            await asyncio.sleep(1)
            os._exit(1)
        
        # Now exit the application
        self.app.exit()
    
    def _on_shutdown_phase_change(self, phase: ShutdownPhase, message: str) -> None:
        """Handle shutdown phase changes for UI feedback."""
        if self._logs:
            phase_colors = {
                ShutdownPhase.STOPPING_OPERATIONS: "blue",
                ShutdownPhase.CANCELLING_TASKS: "cyan", 
                ShutdownPhase.TERMINATING_NODE: "yellow",
                ShutdownPhase.KILLING_WRAPPERS: "magenta",
                ShutdownPhase.CLOSING_TRANSPORTS: "green",
                ShutdownPhase.CLEANING_LOOP: "white",
                ShutdownPhase.COMPLETE: "bright_green",
                ShutdownPhase.EMERGENCY: "bright_red"
            }
            color = phase_colors.get(phase, "white")
            self._logs.add_log("SHUTDOWN", f"[{color}]{message}[/{color}]")
    
    def _on_shutdown_progress(self, status) -> None:
        """Handle shutdown progress updates."""
        if self._logs and status.total_projects > 0:
            progress = (status.projects_processed / status.total_projects) * 100
            self._logs.add_log("SHUTDOWN", 
                f"[dim]Progress: {status.projects_processed}/{status.total_projects} projects ({progress:.0f}%)[/dim]")

    def action_toggle_panel(self) -> None:
        """Toggle the running panel collapsed state."""
        if self._panel:
            self._panel.collapsed = not self._panel.collapsed
            self._panel.refresh(recompose=True)

    def action_restart(self) -> None:
        """Show restart dialog to select projects to restart."""
        # Build project info dict for dialog
        project_info = {}
        for proj_info in self._projects:
            name = proj_info.get('name') if isinstance(proj_info, dict) else proj_info
            if name and name in self._panel._statuses:
                project_info[name] = {
                    'status': self._panel._statuses[name],
                    'port': self._panel._ports.get(name),
                    'branch': self._panel._branches.get(name),
                }
        
        # Show dialog with callback
        def handle_restart_selection(selected_projects: List[str]) -> None:
            """Handle restart dialog result."""
            if selected_projects:
                asyncio.create_task(self._restart_projects(selected_projects))
        
        self.app.push_screen(RestartDialog(project_info), handle_restart_selection)
    
    async def _restart_projects(self, project_names: List[str]) -> None:
        """Restart specified projects.
        
        Args:
            project_names: List of project names to restart
        """
        for name in project_names:
            # Mark as restarting in both panel and health checker
            if self._panel:
                self._panel.update_status(name, ProjectStatus.RESTARTING)
            self._health_checker.mark_restarting(name)
            
            success = await self._manager.restart_project(name)
            
            # Health checker will update status based on health checks
            # But if restart failed immediately, mark as crashed
            if not success:
                if self._panel:
                    self._panel.update_status(name, ProjectStatus.CRASHED)
                self._health_checker.mark_process_running(name, False)

    async def action_stop_all(self) -> None:
        """Stop all running projects."""
        for proj_info in self._projects:
            name = proj_info.get('name') if isinstance(proj_info, dict) else proj_info
            await self._manager.stop_project(name)
            self._panel.update_status(name, ProjectStatus.STOPPED)
            self._health_checker.mark_stopped(name)

    # New actions -----------------------------------------------------------
    def action_show_all_logs(self) -> None:
        # Clear selection in both panel and log viewer so UI stays consistent
        if self._panel:
            self._panel.set_selected(None)
        if self._logs:
            # Direct call ensures refresh even if selection was already None
            self._logs.set_active_project(None)

    # Message handlers ------------------------------------------------------
    def on_running_panel_project_selected(self, message: RunningPanel.ProjectSelected) -> None:  # type: ignore[override]
        if self._logs:
            self._logs.set_active_project(message.project)
    
    async def on_running_panel_restart_project(self, message: RunningPanel.RestartProject) -> None:  # type: ignore[override]
        """Handle restart request from running panel."""
        if message.project:
            await self._restart_projects([message.project])

__all__ = ["MonitoringScreen"]