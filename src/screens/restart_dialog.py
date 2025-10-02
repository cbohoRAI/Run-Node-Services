"""Restart dialog screen - Select projects to restart."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static
from textual.containers import Container
from textual import events
from typing import List, Dict, Callable, Awaitable

from src.models.status import ProjectStatus


class RestartDialog(ModalScreen[List[str]]):
    """Modal dialog for selecting projects to restart."""
    
    BINDINGS = [
        ("q", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel"),
        ("enter", "restart_selected", "Restart Selected"),
        ("e", "toggle_select", "Toggle"),
        ("space", "toggle_select", "Toggle"),
    ]

    DEFAULT_CSS = """
    RestartDialog {
        align: center middle;
    }
    
    #dialog-container {
        width: 80;
        height: auto;
        max-height: 30;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }
    
    #dialog-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }
    
    #restart-table {
        height: auto;
        max-height: 30;
        width: 100%;
    }
    
    #restart-table .datatable--cursor {
        background: $accent;
        color: $text;
    }
    
    #instructions {
        width: 100%;
        padding: 1 0 0 0;
        text-style: italic;
        color: $text-muted;
    }
    """

    # Symbols
    CHECKED_MARK = "[X]"
    UNCHECKED_MARK = "[ ]"

    def __init__(
        self, 
        projects: Dict[str, Dict[str, any]]
    ) -> None:
        """Initialize restart dialog.
        
        Args:
            projects: Dict mapping project name to project info dict with 'status', 'port', 'branch'
        """
        super().__init__()
        self._projects = projects
        self._selected: Dict[str, bool] = {}
        self._row_keys: Dict[int, str] = {}  # row_index -> project_name

    def compose(self) -> ComposeResult:
        with Container(id="dialog-container"):
            yield Static("Select Projects to Restart", id="dialog-title")
            self._table = DataTable(zebra_stripes=True, id="restart-table")
            self._table.cursor_type = "row"
            yield self._table
            yield Static(
                "Use ↑/↓ or W/S to navigate, Space/E to toggle, Enter to restart, Q/Esc to cancel",
                id="instructions"
            )

    def on_mount(self) -> None:
        self._table.add_columns("Select", "Project", "Status", "Port", "Branch")
        
        for idx, (name, info) in enumerate(sorted(self._projects.items())):
            status = info.get('status', ProjectStatus.RUNNING)
            port = info.get('port')
            branch = info.get('branch')
            
            port_display = str(port) if port else "-"
            branch_display = branch if branch else "-"
            status_display = status.value.capitalize()
            
            self._table.add_row(
                self.UNCHECKED_MARK,
                name,
                status_display,
                port_display,
                branch_display
            )
            self._row_keys[idx] = name
        
        # Add restart row
        self._restart_row_idx = len(self._projects)
        self._table.add_row("→", "Restart Selected Projects", "", "", "")
        
        self._table.refresh()
        self._table.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for navigation."""
        if event.key in ("w", "W", "up"):
            if not self._table.has_focus:
                self._table.focus()
            self._table.action_cursor_up()
            event.prevent_default()
        elif event.key in ("s", "S", "down"):
            if not self._table.has_focus:
                self._table.focus()
            self._table.action_cursor_down()
            event.prevent_default()

    def action_toggle_select(self) -> None:
        """Toggle selection for current row."""
        if self._table.cursor_row is None:
            return
        
        row_index = self._table.cursor_row
        
        # Restart row triggers restart action
        if row_index == self._restart_row_idx:
            self.action_restart_selected()
            return
        
        # Toggle selection for project row
        if row_index in self._row_keys:
            project_name = self._row_keys[row_index]
            current = self._selected.get(project_name, False)
            self._selected[project_name] = not current
            self._rebuild_table_rows(self._table.cursor_row)

    def _rebuild_table_rows(self, cursor_before: int | None) -> None:
        """Rebuild table rows with current selection state."""
        self._table.clear()
        
        for idx, (name, info) in enumerate(sorted(self._projects.items())):
            sel_mark = self.CHECKED_MARK if self._selected.get(name, False) else self.UNCHECKED_MARK
            status = info.get('status', ProjectStatus.RUNNING)
            port = info.get('port')
            branch = info.get('branch')
            
            port_display = str(port) if port else "-"
            branch_display = branch if branch else "-"
            status_display = status.value.capitalize()
            
            self._table.add_row(
                sel_mark,
                name,
                status_display,
                port_display,
                branch_display
            )
        
        # Re-add restart row
        self._table.add_row("→", "Restart Selected Projects", "", "", "")
        
        # Restore cursor
        if cursor_before is not None and cursor_before < (len(self._projects) + 1):
            self._table.cursor_coordinate = (cursor_before, 0)
        self._table.refresh()

    def action_restart_selected(self) -> None:
        """Restart selected projects and close dialog."""
        chosen = [name for name, selected in self._selected.items() if selected]
        
        # If nothing selected, use the current row
        if not chosen and self._table.cursor_row is not None:
            row_index = self._table.cursor_row
            if row_index in self._row_keys:
                chosen = [self._row_keys[row_index]]
        
        # Dismiss with selected project names
        self.dismiss(chosen)

    def action_cancel(self) -> None:
        """Cancel and close dialog without restarting."""
        self.dismiss([])


__all__ = ["RestartDialog"]
