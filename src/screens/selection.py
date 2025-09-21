"""Project selection screen (Phase 1)."""
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
from src.screens.monitoring import MonitoringScreen


class ProjectSelectionScreen(Screen):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("enter", "start_selected", "Start Selected"),
        ("e", "toggle_select", "Toggle"),
        ("r", "refresh", "Refresh"),
    ]

    # Symbols defined at class-level (easy to theme later)
    CHECKED_MARK = "[X]"  # could be replaced with "☑" / "✔" in later polish phase
    UNCHECKED_MARK = "[ ]"

    def __init__(self, root: Path, manager: ProcessManager, log_collector: LogCollector | None = None) -> None:
        super().__init__()
        self._root = root
        self._manager = manager
        self._projects: List[NodeProject] = []
        self._selected: Dict[int, bool] = {}
        self._log: List[str] = []
        self._log_collector = log_collector or LogCollector()
        # Map visible row index -> DataTable row key (RowKey)
        self._row_keys = {}  # type: Dict[int, object]

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
        self._selected.clear()  # reset selection on full refresh (could preserve later)
        # Build rows fresh
        self._row_keys.clear()
        self._table.clear()
        for idx, p in enumerate(self._projects):
            nickname = getattr(p, "short_name", None) or "-"
            row_key = self._table.add_row(self.UNCHECKED_MARK, nickname, p.name, str(p.port or "-"), p.git_branch or "-")
            self._row_keys[idx] = row_key
        # Add special start row (non-selectable marker row index == len(projects))
        self._start_row_key = self._table.add_row("→", "", "Start Selected Projects", "", "")
        self._table.refresh()

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
        elif event.key == "enter":
            # Fallback: trigger same as binding if not already handled
            # Start selected if on normal row or start row
            asyncio.create_task(self.action_start_selected())
            event.prevent_default()

    def action_refresh(self) -> None:
        self.refresh_projects()

    def action_toggle_select(self) -> None:
        if self._table.cursor_row is None:
            return
        row_index = self._table.cursor_row
        # Hitting toggle on the special last row triggers start
        if row_index == len(self._projects):
            # Use async path identical to pressing enter
            asyncio.create_task(self.action_start_selected())
            return
        row_key = self._row_keys.get(row_index)
        if row_key is None:
            return  # safety
        current = self._selected.get(row_index, False)
        self._selected[row_index] = not current
        self._rebuild_table_rows(self._table.cursor_row)

    def _apply_selection_marks(self) -> None:
        """Re-apply visual selection markers for current _selected mapping."""
        self._rebuild_table_rows(self._table.cursor_row)

    def _rebuild_table_rows(self, cursor_before: int | None) -> None:
        """Rebuild all table rows using documented remove_row / add_row pattern."""
        # Remove existing rows using their keys
        # Remove + rebuild: per Textual docs clear() removes data, then re-add
        self._table.clear()
        self._row_keys.clear()
        # Re-add rows with current selection state
        for idx, p in enumerate(self._projects):
            sel_mark = self.CHECKED_MARK if self._selected.get(idx, False) else self.UNCHECKED_MARK
            nickname = getattr(p, "short_name", None) or "-"
            row_key_new = self._table.add_row(sel_mark, nickname, p.name, str(p.port or "-"), p.git_branch or "-")
            self._row_keys[idx] = row_key_new
        # Add special start row again
        self._start_row_key = self._table.add_row("→", "", "Start Selected Projects", "", "")
        # Restore cursor
        if cursor_before is not None and cursor_before < (len(self._projects) + 1):
            self._table.cursor_coordinate = (cursor_before, 0)
        self._table.refresh()

    async def action_start_selected(self) -> None:
        chosen = [self._projects[i] for i, sel in self._selected.items() if sel]
        if not chosen and self._table.cursor_row is not None:
            chosen = [self._projects[self._table.cursor_row]]
        if not chosen:
            return
        self._append_log(f"Starting {len(chosen)} project(s)... switching to monitoring view")

        async def cb_start(project: NodeProject) -> None:
            await self._manager.start_project(
                project.name,
                project.path,
                lambda pn, line: self._enqueue_log(pn, line),
                command=project.start_command,
                port=project.port,
            )

        for project in chosen:
            await cb_start(project)

        # Push monitoring screen with list of started project names
        self.app.push_screen(
            MonitoringScreen(
                self._manager,
                self._log_collector,
                [p.name for p in chosen],
            )
        )

    def _enqueue_log(self, project_name: str, line: str) -> None:
        # Add to collector (async safe) — fire and forget
        asyncio.create_task(self._log_collector.add_line(project_name, line))
        # Maintain legacy short log display until screen switch
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