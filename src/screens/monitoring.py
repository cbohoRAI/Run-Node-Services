"""Monitoring screen (Phase 3) - Enhanced version."""
from __future__ import annotations

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Footer, Header
from textual import events
from textual.containers import Vertical, Container
from typing import Dict, List, Optional

from src.widgets.running_panel import RunningPanel
from src.widgets.log_viewer import TabbedLogViewer
from src.models.status import ProjectStatus
from src.core.process_manager import ProcessManager
from src.core.log_collector import LogCollector
from src.core.project_discovery import NodeProject

class MonitoringScreen(Screen):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_panel", "Toggle Panel"),
        ("r", "restart", "Restart"),
        ("shift+r", "restart_all", "Restart All"),
        ("s", "stop_all", "Stop All"),
        ("tab", "next_tab", "Switch Logs"),
        ("1", "tab_1", "All Logs"),
        ("2", "tab_2", "Tab 2"),
        ("3", "tab_3", "Tab 3"),
        ("4", "tab_4", "Tab 4"),
        ("5", "tab_5", "Tab 5"),
        ("6", "tab_6", "Tab 6"),
        ("7", "tab_7", "Tab 7"),
        ("8", "tab_8", "Tab 8"),
        ("9", "tab_9", "Tab 9"),
    ]

    DEFAULT_CSS = """
    MonitoringScreen {
        background: $background;
    }
    
    #monitoring-container {
        width: 100%;
        height: 100%;
        padding: 0;
        background: $background;
    }
    
    RunningPanel {
        width: 100%;
        height: auto;
        min-height: 5;
        max-height: 50%;
        margin-bottom: 1;
        background: $background;
    }
    
    TabbedLogViewer {
        width: 100%;
        height: 1fr;
        border: solid $primary;
        background: $background;
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
        self._logs: Optional[TabbedLogViewer] = None

    def compose(self) -> ComposeResult:
        # Add a header for better visual structure
        yield Header(show_clock=True)
        
        with Container(id="monitoring-container"):
            self._panel = RunningPanel()
            yield self._panel
            
            self._logs = TabbedLogViewer()
            yield self._logs
        
        yield Footer()

    def on_mount(self) -> None:
        """Initialize projects when screen mounts."""
        # Set up each project in the panel with proper details
        for proj_info in self._projects:
            if isinstance(proj_info, dict):
                name = proj_info.get('name')
                port = proj_info.get('port')
                branch = proj_info.get('branch')
            elif isinstance(proj_info, str):
                # Fallback for string-only project names
                name = proj_info
                port = None
                branch = None
            else:
                # Handle NodeProject objects
                name = getattr(proj_info, 'name', str(proj_info))
                port = getattr(proj_info, 'port', None)
                branch = getattr(proj_info, 'git_branch', None)
            
            self._panel.set_project(name, ProjectStatus.RUNNING, port, branch)
            self._logs.add_project(name)
        
        # Register callback for log updates
        self._log_collector.register_callback(self._on_log_line)
        
        # Force a refresh to ensure the panel displays correctly
        self._panel.refresh(recompose=True)

    def _on_log_line(self, project: str, line: str) -> None:
        """Handle new log line from a project."""
        # Strip timestamp if it's already in the line (avoid duplication)
        if len(line) > 8 and line[2] == ':' and line[5] == ':':
            # Line likely starts with HH:MM:SS format
            display_line = line[9:].strip()
        else:
            display_line = line
        
        self._logs.write_line(project, display_line)

    # Actions ---------------------------------------------------------------
    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def action_toggle_panel(self) -> None:
        """Toggle the running panel collapsed state."""
        if self._panel:
            self._panel.collapsed = not self._panel.collapsed
            self._panel.refresh(recompose=True)

    async def action_restart(self) -> None:
        """Restart selected project (currently restarts all)."""
        for proj_info in self._projects:
            name = proj_info.get('name') if isinstance(proj_info, dict) else proj_info
            self._panel.update_status(name, ProjectStatus.RESTARTING)
            success = await self._manager.restart_project(name)
            if success:
                self._panel.update_status(name, ProjectStatus.RUNNING)
            else:
                self._panel.update_status(name, ProjectStatus.CRASHED)

    async def action_restart_all(self) -> None:
        """Restart all running projects."""
        await self.action_restart()

    async def action_stop_all(self) -> None:
        """Stop all running projects."""
        for proj_info in self._projects:
            name = proj_info.get('name') if isinstance(proj_info, dict) else proj_info
            await self._manager.stop_project(name)
            self._panel.update_status(name, ProjectStatus.STOPPED)

    def action_next_tab(self) -> None:
        """Switch to next log tab."""
        try:
            if hasattr(self._logs, 'action_next_tab'):
                self._logs.action_next_tab()
        except Exception:
            pass

    # Tab switching actions
    def _switch_to_tab(self, idx: int) -> None:
        """Switch to specific tab by index."""
        try:
            if not self._logs:
                return
                
            panes = list(self._logs.panes) if hasattr(self._logs, 'panes') else []
            if not panes:
                return
                
            if idx == 1:
                # Tab 1 is always "All Logs"
                self._logs.active = "all"
            else:
                # Map other numbers to project tabs
                project_panes = [p for p in panes if p.id != "all"]
                tab_idx = idx - 2
                if 0 <= tab_idx < len(project_panes):
                    self._logs.active = project_panes[tab_idx].id
        except Exception:
            pass

    def action_tab_1(self) -> None: self._switch_to_tab(1)
    def action_tab_2(self) -> None: self._switch_to_tab(2)
    def action_tab_3(self) -> None: self._switch_to_tab(3)
    def action_tab_4(self) -> None: self._switch_to_tab(4)
    def action_tab_5(self) -> None: self._switch_to_tab(5)
    def action_tab_6(self) -> None: self._switch_to_tab(6)
    def action_tab_7(self) -> None: self._switch_to_tab(7)
    def action_tab_8(self) -> None: self._switch_to_tab(8)
    def action_tab_9(self) -> None: self._switch_to_tab(9)

__all__ = ["MonitoringScreen"]