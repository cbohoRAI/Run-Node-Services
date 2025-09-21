"""Collapsible running projects panel (Phase 3) - Enhanced version."""
from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button
from textual import events
from typing import Dict, Optional
from rich.table import Table
from rich.console import Console
from rich.text import Text
from src.models.status import ProjectStatus, STATUS_COLOR

class RunningPanel(Widget):
    collapsed = reactive(False)

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
        padding: 1;
        margin: 0;
        background: $background;
        border: none;
        color: $text;
    }
    
    #rp-body {
        padding: 0 1;
        height: auto;
        background: $background;
    }
    
    #rp-table {
        background: $background;
        padding: 0;
    }
    """

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

    def compose(self) -> ComposeResult:
        with Horizontal(id="rp-header"):
            yield Static(self._get_header_text(), id="rp-title")
            yield Static(self._get_toggle_text(), id="rp-toggle")
        
        if not self.collapsed:
            with Vertical(id="rp-body"):
                yield Static(self._get_projects_table(), id="rp-table")

    def _get_header_text(self) -> str:
        if self.collapsed:
            running = sum(1 for s in self._statuses.values() if s == ProjectStatus.RUNNING)
            return f"Running Projects ({running} active)"
        return "Running Projects"

    def _get_toggle_text(self) -> str:
        return "[+]" if self.collapsed else "[-]"

    def _get_projects_table(self) -> str:
        """Generate a simple formatted string of running projects."""
        if not self._statuses:
            return "No projects running"
        
        lines = []
        for name in sorted(self._statuses.keys()):
            status = self._statuses[name]
            port = self._ports.get(name)
            branch = self._branches.get(name)
            
            # Status icon
            icon = self._get_status_icon(status)
            
            # Port display
            port_text = f":{port}" if port else ":−"
            
            # Branch display - truncate if too long
            branch_text = branch or "−"
            if len(branch_text) > 20:
                branch_text = branch_text[:17] + "..."
            
            # Format as a simple string with fixed spacing
            color = STATUS_COLOR.get(status, "white")
            status_formatted = f"[{color}]{icon} {status.value.capitalize()}[/{color}]"
            
            # Build the line with proper spacing
            line = f"  {name:<35} {status_formatted:<20} {port_text:<8} {branch_text}"
            lines.append(line)
        
        return "\n".join(lines)

    def _get_status_icon(self, status: ProjectStatus) -> str:
        icons = {
            ProjectStatus.RUNNING: "●",
            ProjectStatus.STOPPED: "■",
            ProjectStatus.CRASHED: "✖",
            ProjectStatus.RESTARTING: "◆",
            ProjectStatus.STARTING: "◌",
        }
        return icons.get(status, "·")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rp-toggle":
            self.collapsed = not self.collapsed
            self.refresh(recompose=True)
    
    def on_click(self, event: events.Click) -> None:
        """Handle clicks on the toggle button."""
        if event.target.id == "rp-toggle":
            self.collapsed = not self.collapsed
            self.refresh(recompose=True)

__all__ = ["RunningPanel"]