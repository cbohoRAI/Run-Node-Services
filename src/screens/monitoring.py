"""Monitoring screen (Phase 3) - Enhanced version."""
from __future__ import annotations

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Footer, Header
from textual import events
from textual.containers import Vertical, Container
from typing import Dict, List, Optional
from rich.text import Text

from src.widgets.running_panel import RunningPanel
from src.widgets.simple_log_viewer import SimpleLogViewer   # CHANGE: debug viewer
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
        # Populate panel
        for idx, proj_info in enumerate(self._projects):
            if isinstance(proj_info, dict):
                name = proj_info.get('name')
                port = proj_info.get('port')
                branch = proj_info.get('branch')
                # Prefer explicit short_name, then short, then alias
                short = proj_info.get('short_name') or proj_info.get('short') or proj_info.get('alias')
            else:
                name = getattr(proj_info, 'name', str(proj_info))
                port = getattr(proj_info, 'port', None)
                branch = getattr(proj_info, 'git_branch', None)
                short = getattr(proj_info, 'short_name', None)
            # Build nickname mapping (fallback to full name if missing)
            if name:
                self._name_to_short[name] = (short or name)[:10]  # trim overly long nicknames
                # Assign color deterministically if not already set
                if name not in self._project_colors:
                    self._project_colors[name] = self._color_palette[idx % len(self._color_palette)]
            self._panel.set_project(name, ProjectStatus.RUNNING, port, branch)
        # Initialize log viewer tabs
        if self._logs:
            self._logs.set_projects(list(self._name_to_short.keys()))
        # Register callback
        self._log_collector.register_callback(self._on_log_line)
        # DEBUG: emit a test line to verify viewer path
        if self._logs:
            self._logs.add_log("system", Text("(debug) Monitoring screen mounted", style="italic dim"))
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
        if self._logs:
            self._logs.next_tab()

    def _switch_to_tab(self, idx: int) -> None:
        """Switch to tab by number key (1=All Logs, 2+=projects)."""
        if not self._logs:
            return
        # SimpleLogViewer expects zero-based (0 = All Logs)
        self._logs.select_tab_index(idx - 1)

    def action_tab_1(self) -> None:
        self._switch_to_tab(1)

    def action_tab_2(self) -> None:
        self._switch_to_tab(2)

    def action_tab_3(self) -> None:
        self._switch_to_tab(3)

    def action_tab_4(self) -> None:
        self._switch_to_tab(4)

    def action_tab_5(self) -> None:
        self._switch_to_tab(5)

    def action_tab_6(self) -> None:
        self._switch_to_tab(6)

    def action_tab_7(self) -> None:
        self._switch_to_tab(7)

    def action_tab_8(self) -> None:
        self._switch_to_tab(8)

    def action_tab_9(self) -> None:
        self._switch_to_tab(9)

__all__ = ["MonitoringScreen"]