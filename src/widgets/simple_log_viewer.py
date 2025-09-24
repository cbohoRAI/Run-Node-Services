from __future__ import annotations

from typing import List, Optional, Tuple

from textual.containers import Vertical
from textual.widgets import RichLog, Static
from textual.app import ComposeResult
from rich.text import Text

class SimpleLogViewer(Vertical):
    """Project log viewer without tabs.

    Maintains an in-memory list of (project, Text) entries and renders either
    all logs (default) or only those belonging to the currently selected
    project, controlled externally via ``set_active_project``.
    """

    DEFAULT_CSS = """
    SimpleLogViewer {
        layout: vertical;
    }
    SimpleLogViewer Static#log-status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $boost;
    }
    SimpleLogViewer RichLog {
        height: 1fr;
        border: none;
    }
    """

    def __init__(self, *, max_entries: Optional[int] = None) -> None:  # type: ignore[override]
        super().__init__()
        self._log = RichLog(highlight=True, markup=True, wrap=True, id="log")
        self._status = Static("All Logs", id="log-status")
        self._entries: List[Tuple[str, Text]] = []
        self._projects: List[str] = []  # kept for possible external awareness
        self._active_project: Optional[str] = None
        self._max_entries: Optional[int] = max_entries
        # For simple testability we keep last rendered count
        self._last_rendered: int = 0

    # Composition -----------------------------------------------------------
    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield self._status
        yield self._log

    # Public API ------------------------------------------------------------
    def set_projects(self, projects: List[str]) -> None:
        """Record project names (no UI side-effects).

        Keeping this to avoid changing callers yet.
        """
        self._projects = list(dict.fromkeys(projects))

    def set_active_project(self, project: Optional[str]) -> None:
        """Select a project to filter logs (``None`` = all)."""
        if project == self._active_project:
            return
        self._active_project = project
        self._refresh_display()

    def get_active_project(self) -> Optional[str]:
        return self._active_project

    def clear(self) -> None:
        """Clear all stored log entries."""
        self._entries.clear()
        self._refresh_display()

    def add_log(self, project: str, text: Text | str) -> None:
        """Add a log line for a project.

        Applies retention policy if ``max_entries`` was supplied.
        """
        text_obj = Text(text) if isinstance(text, str) else text
        self._entries.append((project, text_obj))
        if self._max_entries is not None and len(self._entries) > self._max_entries:
            # Drop oldest extra entries
            overflow = len(self._entries) - self._max_entries
            if overflow > 0:
                self._entries = self._entries[overflow:]
                # Full refresh since indexes changed
                self._refresh_display()
                return
        # Fast-path append if visible
        if self._active_project is None or self._active_project == project:
            self._log.write(text_obj)
            self._last_rendered += 1

    def write(self, text: Text | str) -> None:  # type: ignore[override]
        self.add_log(project="unknown", text=text)

    # Internal helpers ------------------------------------------------------
    def _refresh_display(self) -> None:
        self._log.clear()
        rendered = 0
        for proj, text in self._entries:
            if self._active_project is None or proj == self._active_project:
                self._log.write(text)
                rendered += 1
        self._last_rendered = rendered
        if self._active_project is None:
            self._status.update("All Logs")
        else:
            self._status.update(f"Project: [bold]{self._active_project}[/] — Press 'a' for all")

__all__ = ["SimpleLogViewer"]

__all__ = ["SimpleLogViewer"]