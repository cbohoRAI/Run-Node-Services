"""Per-project control buttons (Phase 3)."""
from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Button
from textual.message import Message
from textual.app import ComposeResult

class ProjectRestartRequest(Message):
    def __init__(self, project_name: str) -> None:
        self.project_name = project_name
        super().__init__()

class ProjectStopRequest(Message):
    def __init__(self, project_name: str) -> None:
        self.project_name = project_name
        super().__init__()

class ProjectControls(Horizontal):
    def __init__(self, project_name: str) -> None:
        super().__init__()
        self.project_name = project_name

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Button("↻", id=f"restart-{self.project_name}", variant="warning")
        yield Button("■", id=f"stop-{self.project_name}", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        bid = event.button.id or ""
        if bid.startswith("restart-"):
            self.post_message(ProjectRestartRequest(self.project_name))
        elif bid.startswith("stop-"):
            self.post_message(ProjectStopRequest(self.project_name))

__all__ = ["ProjectControls", "ProjectRestartRequest", "ProjectStopRequest"]
