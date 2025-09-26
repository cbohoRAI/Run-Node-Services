"""Project selection screen (Phase 1) - Enhanced to pass project details."""
from __future__ import annotations

from textual.app import ComposeResult
import asyncio
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static
from textual import events
from pathlib import Path
from typing import List, Dict

from src.core.project_discovery import discover_projects, NodeProject
from src.core.process_manager import ProcessManager
from src.core.log_collector import LogCollector
from src.core.log_tap import attach_file_sink
from src.screens.monitoring import MonitoringScreen


class ProjectSelectionScreen(Screen):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("enter", "start_selected", "Start Selected"),
        ("e", "toggle_select", "Toggle"),
        ("space", "toggle_select", "Toggle"),
        ("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    ProjectSelectionScreen {
        layout: vertical;
    }
    ProjectSelectionScreen DataTable {
        height: 1fr;
    }
    ProjectSelectionScreen Footer {
        dock: bottom;
    }
    #projects-table {
        height: 1fr;
    }
    #projects-table .datatable--cursor {
        background: $accent;
        color: $text;
    }
    """

    # Symbols defined at class-level
    CHECKED_MARK = "[X]"
    UNCHECKED_MARK = "[ ]"

    def __init__(self, root: Path, manager: ProcessManager, log_collector: LogCollector | None = None) -> None:
        super().__init__()
        self._root = root
        self._manager = manager
        self._projects: List[NodeProject] = []
        self._selected: Dict[int, bool] = {}
        self._log: List[str] = []
        self._log_collector = log_collector or LogCollector()
        self._row_keys = {}

    def compose(self) -> ComposeResult:
        self._table = DataTable(zebra_stripes=True, id="project-table")
        self._table.cursor_type = "row"
        yield self._table
        self._log_widget = Static("", id="log")
        self._log_widget.display = False
        yield self._log_widget
        yield Footer()

    def on_mount(self) -> None:
        self._logs_active = False
        # DIAGNOSTIC: attach file sink once (idempotent assumption: single on_mount)
        # try:
        #     attach_file_sink(self._log_collector, "logs/stream_capture.log")  # CHANGE: adds file logging
        # except Exception:
        #     pass
        self._table.add_columns("Select", "Short", "Name", "Port", "Branch")
        self.refresh_projects()
        self.set_focus(self._table)

    def refresh_projects(self) -> None:
        self._projects = discover_projects(self._root)
        self._selected.clear()
        self._row_keys.clear()
        self._table.clear()
        
        for idx, p in enumerate(self._projects):
            nickname = getattr(p, "short_name", None) or "-"
            port_display = str(p.port) if p.port else "-"
            branch_display = p.git_branch if p.git_branch else "-"
            
            row_key = self._table.add_row(
                self.UNCHECKED_MARK, 
                nickname, 
                p.name, 
                port_display,
                branch_display
            )
            self._row_keys[idx] = row_key
        
        # Add special start row
        self._start_row_key = self._table.add_row("→", "", "Start Selected Projects", "", "")
        self._table.refresh()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for navigation."""
        if event.key in ("space", "e", "E"):
            self.action_toggle_select()
            event.prevent_default()
        elif event.key in ("w", "W"):
            if not self._table.has_focus:
                self.set_focus(self._table)
            self._table.action_cursor_up()
            event.prevent_default()
        elif event.key in ("s", "S"):
            if not self._table.has_focus:
                self.set_focus(self._table)
            self._table.action_cursor_down()
            event.prevent_default()
        elif event.key == "enter":
            asyncio.create_task(self.action_start_selected())
            event.prevent_default()

    def action_refresh(self) -> None:
        self.refresh_projects()

    def action_toggle_select(self) -> None:
        if self._table.cursor_row is None:
            return
        row_index = self._table.cursor_row
        
        # Start row triggers start action
        if row_index == len(self._projects):
            asyncio.create_task(self.action_start_selected())
            return
        
        row_key = self._row_keys.get(row_index)
        if row_key is None:
            return
        
        current = self._selected.get(row_index, False)
        self._selected[row_index] = not current
        self._rebuild_table_rows(self._table.cursor_row)

    def _rebuild_table_rows(self, cursor_before: int | None) -> None:
        """Rebuild table rows with current selection state."""
        self._table.clear()
        self._row_keys.clear()
        
        for idx, p in enumerate(self._projects):
            sel_mark = self.CHECKED_MARK if self._selected.get(idx, False) else self.UNCHECKED_MARK
            nickname = getattr(p, "short_name", None) or "-"
            port_display = str(p.port) if p.port else "-"
            branch_display = p.git_branch if p.git_branch else "-"

            row_key_new = self._table.add_row(
                sel_mark, 
                nickname, 
                p.name, 
                port_display,
                branch_display
            )
            self._row_keys[idx] = row_key_new
        
        # Re-add start row
        self._start_row_key = self._table.add_row("→", "", "Start Selected Projects", "", "")
        
        # Restore cursor
        if cursor_before is not None and cursor_before < (len(self._projects) + 1):
            self._table.cursor_coordinate = (cursor_before, 0)
        self._table.refresh()

    async def action_start_selected(self) -> None:
        """Start selected projects and switch to monitoring screen."""
        chosen = [self._projects[i] for i, sel in self._selected.items() if sel]
        
        # If nothing selected, use the current row
        if not chosen and self._table.cursor_row is not None and self._table.cursor_row < len(self._projects):
            chosen = [self._projects[self._table.cursor_row]]
        
        if not chosen:
            return
        
        self._append_log(f"Starting {len(chosen)} project(s)... switching to monitoring view")

        # Start each project
        started_projects = []
        for project in chosen:
            success = await self._manager.start_project(
                project.name,
                project.path,
                lambda pn, line: self._enqueue_log(pn, line),
                command=project.start_command,
                port=project.port,
            )
            
            if success:
                # Create project info dict with all details
                project_info = {
                    'name': project.name,
                    'port': project.port,
                    'branch': project.git_branch,
                    'short_name': getattr(project, 'short_name', None),
                    'healthPath': getattr(project, 'health_path', '/ping'),
                }
                started_projects.append(project_info)

        if started_projects:
            # Switch to monitoring screen with full project details
            self.app.push_screen(
                MonitoringScreen(
                    self._manager,
                    self._log_collector,
                    started_projects,
                )
            )

    def _enqueue_log(self, project_name: str, line: str) -> None:
        """Queue log line for display."""
        asyncio.create_task(self._log_collector.add_line(project_name, line))
        self._append_log(f"[{project_name}] {line}")

    def _append_log(self, line: str) -> None:
        """Append log line to display buffer."""
        self._log.append(line)
        self._log = self._log[-200:]
        
        if not self._logs_active:
            self._log_widget.display = True
            self._logs_active = True
        
        self._log_widget.update("\n".join(self._log))

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()

__all__ = ["ProjectSelectionScreen"]