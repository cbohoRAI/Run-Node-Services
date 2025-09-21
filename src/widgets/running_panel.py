"""Collapsible running projects panel (Phase 3)."""
from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button
from typing import Dict
from src.models.status import ProjectStatus, STATUS_COLOR

class RunningPanel(Widget):
    collapsed = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self._statuses: Dict[str, ProjectStatus] = {}
        self._ports: Dict[str, int | None] = {}
        self._branches: Dict[str, str | None] = {}

    def set_project(self, name: str, status: ProjectStatus, port: int | None, branch: str | None) -> None:
        self._statuses[name] = status
        self._ports[name] = port
        self._branches[name] = branch
        self.refresh()

    def update_status(self, name: str, status: ProjectStatus) -> None:
        if name in self._statuses:
            self._statuses[name] = status
            self.refresh()

    def compose(self) -> ComposeResult:  # type: ignore[override]
        header = Horizontal(
            Static(self._header_title(), id="rp-title"),
            Button("[+]" if self.collapsed else "[−]", id="rp-toggle"),
            id="rp-header",
        )
        yield header
        if not self.collapsed:
            body = Vertical(id="rp-body")
            for name in sorted(self._statuses.keys()):
                status = self._statuses[name]
                color = STATUS_COLOR.get(status, "white")
                port = self._ports.get(name)
                branch = self._branches.get(name) or "-"
                body.mount(Static(f"[bold]{name}[/bold] [#{color}]{status.value}[/] :{port or '-'} {branch}"))
            yield body

    def _header_title(self) -> str:
        running = sum(1 for s in self._statuses.values() if s == ProjectStatus.RUNNING)
        return f"Running Projects ({running} active)"

    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        if event.button.id == "rp-toggle":
            self.collapsed = not self.collapsed
            self.refresh(recompose=True)

__all__ = ["RunningPanel"]
