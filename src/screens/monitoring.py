"""Monitoring screen (Phase 3)."""
from __future__ import annotations

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Footer
from textual import events
from textual.containers import Vertical
from typing import Dict, List

from src.widgets.running_panel import RunningPanel
from src.widgets.log_viewer import TabbedLogViewer
from src.models.status import ProjectStatus
from src.core.process_manager import ProcessManager
from src.core.log_collector import LogCollector

class MonitoringScreen(Screen):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_panel", "Panel"),
        ("r", "restart", "Restart"),
        ("R", "restart_all", "Restart All"),
        ("s", "stop", "Stop"),
        ("tab", "next_tab", "Next Tab"),
        ("1", "tab_1", "Tab1"),
        ("2", "tab_2", "Tab2"),
        ("3", "tab_3", "Tab3"),
        ("4", "tab_4", "Tab4"),
        ("5", "tab_5", "Tab5"),
        ("6", "tab_6", "Tab6"),
        ("7", "tab_7", "Tab7"),
        ("8", "tab_8", "Tab8"),
        ("9", "tab_9", "Tab9"),
    ]

    def __init__(self, manager: ProcessManager, log_collector: LogCollector, projects: List[str]) -> None:
        super().__init__()
        self._manager = manager
        self._log_collector = log_collector
        self._projects = projects

    def compose(self) -> ComposeResult:  # type: ignore[override]
        self._panel = RunningPanel()
        self._logs = TabbedLogViewer()
        yield Vertical(self._panel, self._logs)
        yield Footer()

    def on_mount(self) -> None:  # type: ignore[override]
        for proj in self._projects:
            self._panel.set_project(proj, ProjectStatus.RUNNING, None, None)
            self._logs.add_project(proj)
        self._log_collector.register_callback(self._on_log_line)

    def _on_log_line(self, project: str, line: str) -> None:
        self._logs.write_line(project, line)

    # Actions ---------------------------------------------------------------
    def action_quit(self) -> None:  # type: ignore[override]
        self.app.exit()

    def action_toggle_panel(self) -> None:
        self._panel.collapsed = not self._panel.collapsed
        self._panel.refresh(recompose=True)

    async def action_restart(self) -> None:
        # Basic: restart all currently tracked projects
        for name in list(self._projects):
            await self._manager.restart_project(name)
            self._panel.update_status(name, ProjectStatus.RESTARTING)

    async def action_restart_all(self) -> None:
        await self.action_restart()

    async def action_stop(self) -> None:
        for name in list(self._projects):
            await self._manager.stop_project(name)
            self._panel.update_status(name, ProjectStatus.STOPPED)

    def action_next_tab(self) -> None:
        # Move to next tab (Textual's TabbedContent provides action_next_tab normally)
        try:
            self._logs.action_next_tab()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    # Numbered tab switching (1 always maps to 'all')
    def _switch_index(self, idx: int) -> None:
        try:
            panes = list(self._logs.panes)
            if not panes:
                return
            if idx == 1:
                target = "all"
            else:
                # idx 2 -> first project pane, etc.
                project_offset = idx - 2
                project_ids = [p.id for p in panes if p.id != "all"]
                if project_offset < 0 or project_offset >= len(project_ids):
                    return
                target = project_ids[project_offset]
            self._logs.active = target  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def action_tab_1(self) -> None: self._switch_index(1)  # noqa: D401,E701
    def action_tab_2(self) -> None: self._switch_index(2)  # noqa: D401,E701
    def action_tab_3(self) -> None: self._switch_index(3)  # noqa: D401,E701
    def action_tab_4(self) -> None: self._switch_index(4)  # noqa: D401,E701
    def action_tab_5(self) -> None: self._switch_index(5)  # noqa: D401,E701
    def action_tab_6(self) -> None: self._switch_index(6)  # noqa: D401,E701
    def action_tab_7(self) -> None: self._switch_index(7)  # noqa: D401,E701
    def action_tab_8(self) -> None: self._switch_index(8)  # noqa: D401,E701
    def action_tab_9(self) -> None: self._switch_index(9)  # noqa: D401,E701

__all__ = ["MonitoringScreen"]
