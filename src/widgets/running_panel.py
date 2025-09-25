"""Collapsible running projects panel (Phase 3) - Enhanced version."""
from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button
from textual import events
from typing import Dict, Optional, Iterable
from textual.message import Message
from rich.table import Table
from rich.console import Console
from rich.text import Text
from src.models.status import ProjectStatus, STATUS_COLOR

class RunningPanel(Widget):
    collapsed = reactive(False)
    selected: Optional[str] = reactive(None)

    DEFAULT_CSS = """
    RunningPanel {
        height: auto;
        border: solid $primary;
        padding: 0;
        background: $background;
    }
    
    #rp-header {
        background: $background;
        padding: 0 1;
        height: 3;
        border-bottom: solid $primary;
        layout: horizontal;
        align: center middle;
    }
    
    #rp-title {
        width: 1fr;
        padding: 1 0;
        background: $background;
    }
    
    #rp-toggle {
        width: 5;
        height: 3;
        padding: 0 1;
        margin: 0;
        background: $background;
        border: none;
        color: $text;
    }
    
    #rp-body {
        padding: 0 0;
        height: auto;
        background: $background;
    }
    
    RunningPanel Button.project-line {
        layout: horizontal;
        width: 100%;
        height: 1;
        padding: 0 1;
        border: none;
        background: $background;
        color: $text;
        text-align: left;
    }
    RunningPanel Button.project-line:hover {
        background: $boost;
    }
    RunningPanel Button.project-line.-selected {
        background: $accent-darken-1;
        color: $text;
    }
    """

    class ProjectSelected(Message):
        """Message emitted when a project selection changes.

        Attribute ``project`` is the newly selected project or ``None`` for all.
        """
        def __init__(self, project: Optional[str]):
            self.project = project
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self._statuses: Dict[str, ProjectStatus] = {}
        self._ports: Dict[str, Optional[int]] = {}
        self._branches: Dict[str, Optional[str]] = {}

    def set_project(self, name: str, status: ProjectStatus, port: Optional[int], branch: Optional[str]) -> None:
        self._statuses[name] = status
        self._ports[name] = port
        self._branches[name] = branch
        self.refresh(recompose=True)  # Force recompose to update display

    def update_status(self, name: str, status: ProjectStatus) -> None:
        if name in self._statuses:
            self._statuses[name] = status
            self.refresh(recompose=True)  # Force recompose to update display

    def on_resize(self, event: events.Resize) -> None:  # type: ignore[override]
        """Handle terminal resize events by refreshing the display."""
        self.refresh(recompose=True)

    def watch_selected(self, old: Optional[str], new: Optional[str]) -> None:  # type: ignore[override]
        # When selection changes, update button highlighting without full recompose
        for btn in self.query(Button).results(Button):
            if btn.id and btn.id.startswith("proj-"):
                proj_name = btn.id[5:]
                btn.label = self._format_project_line(proj_name)
                if proj_name == new:
                    btn.add_class("-selected")
                else:
                    btn.remove_class("-selected")

    def compose(self) -> ComposeResult:
        with Horizontal(id="rp-header"):
            yield Static(self._get_header_text(), id="rp-title")
            yield Button(self._get_toggle_text(), id="rp-toggle")

        if not self.collapsed:
            with Vertical(id="rp-body"):
                for name in sorted(self._statuses.keys()):
                    yield Button(self._format_project_line(name), id=f"proj-{name}", classes="project-line")

    def _get_header_text(self) -> str:
        if self.collapsed:
            running = sum(1 for s in self._statuses.values() if s == ProjectStatus.RUNNING)
            return f"Running Projects ({running} active)"
        return "Running Projects"

    def _get_toggle_text(self) -> str:
        return "[+]" if self.collapsed else "[-]"

    def _format_project_line(self, name: str) -> str:
        status = self._statuses[name]
        port = self._ports.get(name)
        branch = self._branches.get(name)
        icon = self._get_status_icon(status)
        port_text = f":{port}" if port else ":-"
        branch_text = branch or "-"
        color = STATUS_COLOR.get(status, "white")
        status_formatted = f"[{color}]{icon} {status.value.capitalize()}[/{color}]"
        prefix = "▶" if name == self.selected else " "
        
        # Calculate available space for branch text
        # Account for: prefix(1) + space(1) + name(26) + space(1) + status(24) + space(1) + port(8) + space(1) = 63
        terminal_width = self.app.size.width if hasattr(self, 'app') and self.app.size else 80
        available_branch_width = max(1, terminal_width - 63)  # Minimum 1 char for branch
        
        # Truncate branch text if needed
        if len(branch_text) > available_branch_width:
            if available_branch_width > 1:
                branch_text = branch_text[:available_branch_width-1] + "…"
            else:
                branch_text = "…"
        
        return f"{prefix} {name:<26} {status_formatted:<24} {port_text:<8} {branch_text}"

    def _get_status_icon(self, status: ProjectStatus) -> str:
        icons = {
            ProjectStatus.RUNNING: "●",
            ProjectStatus.STOPPED: "■",
            ProjectStatus.CRASHED: "✖",
            ProjectStatus.RESTARTING: "◆",
            ProjectStatus.STARTING: "◌",
        }
        return icons.get(status, "·")

    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        bid = event.button.id or ""
        if bid == "rp-toggle":
            self.collapsed = not self.collapsed
            self.refresh(recompose=True)
            return
        if bid.startswith("proj-"):
            name = bid[5:]
            if name in self._statuses:
                self.toggle_selected(name)
                # Update all project button labels & classes
                for btn in self.query(Button).results(Button):
                    if btn.id and btn.id.startswith("proj-"):
                        proj_name = btn.id[5:]
                        btn.label = self._format_project_line(proj_name)
                        if proj_name == self.selected:
                            btn.add_class("-selected")
                        else:
                            btn.remove_class("-selected")

    # Selection API ---------------------------------------------------------
    def set_selected(self, project: Optional[str]) -> None:
        if project == self.selected:
            return
        self.selected = project
        # Emit message so listeners can react
        self.post_message(self.ProjectSelected(self.selected))
        self.refresh(recompose=True)

    def toggle_selected(self, project: str) -> None:
        if self.selected == project:
            self.set_selected(None)
        else:
            self.set_selected(project)

    def get_selected(self) -> Optional[str]:
        return self.selected

    def cycle(self, *, direction: int = 1) -> None:
        names = sorted(self._statuses.keys())
        if not names:
            return
        if self.selected not in names:
            next_name = names[0 if direction > 0 else -1]
        else:
            idx = names.index(self.selected)
            next_name = names[(idx + direction) % len(names)]
        self.set_selected(next_name)

    def key_up(self) -> None:  # type: ignore[override]
        self.cycle(direction=-1)

    def key_down(self) -> None:  # type: ignore[override]
        self.cycle(direction=1)

    def key_enter(self) -> None:  # type: ignore[override]
        # Toggle current row or pick first if none
        if self.selected is None:
            names = sorted(self._statuses.keys())
            if names:
                self.set_selected(names[0])
        else:
            self.set_selected(None)

__all__ = ["RunningPanel"]