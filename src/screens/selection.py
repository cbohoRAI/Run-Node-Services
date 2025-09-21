"""Project selection screen (Phase 1)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static
from textual import events
from pathlib import Path
from typing import List, Callable, Dict

from src.core.project_discovery import discover_projects, NodeProject
from src.core.process_manager import ProcessManager


class ProjectSelectionScreen(Screen):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("enter", "start_selected", "Start Selected"),
        ("e", "toggle_select", "Toggle"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, root: Path, manager: ProcessManager) -> None:
        super().__init__()
        self._root = root
        self._manager = manager
        self._projects: List[NodeProject] = []
        self._selected: Dict[int, bool] = {}
        self._log: List[str] = []

    def compose(self) -> ComposeResult:
        self._table = DataTable(zebra_stripes=True)
        self._table.cursor_type = "row"
        yield self._table
        self._log_widget = Static("", id="log")  # created but not shown yet
        self._log_widget.display = False
        yield self._log_widget
        yield Footer()

    def on_mount(self) -> None:
        self._logs_active = False
        self._table.add_columns("Select", "Nickname", "Name", "Port", "Branch")
        self.refresh_projects()
        # Ensure table is focused immediately so movement keys work on first press
        self.set_focus(self._table)

    def refresh_projects(self) -> None:
        self._projects = discover_projects(self._root)
        self._table.clear()
        self._selected.clear()
        for idx, p in enumerate(self._projects):
            nickname = getattr(p, "short_name", None) or "-"
            self._table.add_row("[ ]", nickname, p.name, str(p.port or "-"), p.git_branch or "-")

    def on_key(self, event: events.Key) -> None:
        """Handle key events directly for immediate response."""
        # Handle W/S keys for navigation
        if event.key in ("w", "W"):
            # Focus the table if not focused
            if not self._table.has_focus:
                self.set_focus(self._table)
            # Use the DataTable's built-in action
            self._table.action_cursor_up()
            event.prevent_default()
        elif event.key in ("s", "S"):
            # Focus the table if not focused
            if not self._table.has_focus:
                self.set_focus(self._table)
            # Use the DataTable's built-in action
            self._table.action_cursor_down()
            event.prevent_default()

    def action_refresh(self) -> None:
        self.refresh_projects()

    def action_toggle_select(self) -> None:
        if self._table.cursor_row is None:
            return
        row = self._table.cursor_row
        current = self._selected.get(row, False)
        self._selected[row] = not current
        mark = "[x]" if not current else "[ ]"
        row_data = list(self._table.get_row(row))
        row_data[0] = mark
        self._table.update_row(row, *row_data)

    async def action_start_selected(self) -> None:
        chosen = [self._projects[i] for i, sel in self._selected.items() if sel]
        if not chosen and self._table.cursor_row is not None:
            chosen = [self._projects[self._table.cursor_row]]
        if not chosen:
            return
        self._append_log(f"Starting {len(chosen)} project(s)...")
        for project in chosen:
            await self._manager.start_project(
                project.name,
                project.path,
                self._on_output,
                command=project.start_command,
            )

    def _on_output(self, project_name: str, line: str) -> None:
        self._append_log(f"[{project_name}] {line}")

    def _append_log(self, line: str) -> None:
        # Only reveal log widget after first real output
        self._log.append(line)
        self._log = self._log[-200:]
        if not self._logs_active:
            self._log_widget.display = True
            self._logs_active = True
            if not self._log_widget.renderable:
                pass
        self._log_widget.update("\n".join(self._log))

    def action_quit(self) -> None:  # type: ignore[override]
        self.app.exit()