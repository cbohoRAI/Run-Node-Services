from __future__ import annotations

from typing import List, Optional, Tuple

from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Button
from textual.app import ComposeResult
from rich.text import Text

class SimpleLogViewer(Vertical):
    """Log viewer with a lightweight tab bar implemented using buttons.

    Tabs: "All Logs" plus one per project. Clicking (or using key bindings)
    filters visible log lines without discarding collected content.
    """

    DEFAULT_CSS = """
    SimpleLogViewer {
        layout: vertical;
    }
    SimpleLogViewer > .tab-bar {
        height: 1;
        padding: 0 1;
        background: $boost;
    }
    SimpleLogViewer Button.tab {
        padding: 0 1;
        background: $surface;
        border: none;
        text-style: none;
    }
    SimpleLogViewer Button.tab.-active {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    SimpleLogViewer Button.tab:hover {
        background: $accent-darken-1;
    }
    SimpleLogViewer RichLog {
        height: 1fr;
        border: none;
    }
    """

    def __init__(self) -> None:  # type: ignore[override]
        super().__init__()
        self._log = RichLog(highlight=True, markup=True, wrap=True, id="log")
        self._entries: List[Tuple[str, Text]] = []
        self._projects: List[str] = []
        self._active_project: Optional[str] = None
        self._tab_bar = Horizontal(id="tab-bar", classes="tab-bar")

    # Composition -----------------------------------------------------------
    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield self._tab_bar
        yield self._log

    # Public API ------------------------------------------------------------
    def set_projects(self, projects: List[str]) -> None:
        """Define project names (rebuilds tabs)."""
        previous = self._active_project
        self._projects = list(dict.fromkeys(projects))
        self._build_tabs()
        if previous and previous in self._projects:
            self._active_project = previous
        elif previous is not None and previous not in self._projects:
            self._active_project = None
        self._refresh_display()

    def add_log(self, project: str, text: Text | str) -> None:
        """Add a log line for a project."""
        text_obj = Text(text) if isinstance(text, str) else text
        self._entries.append((project, text_obj))
        if self._active_project is None or self._active_project == project:
            self._log.write(text_obj)

    def write(self, text: Text | str) -> None:  # type: ignore[override]
        self.add_log(project="unknown", text=text)

    # Keyboard support ------------------------------------------------------
    def next_tab(self) -> None:
        """Advance to next tab (wrap)."""
        order: List[Optional[str]] = [None] + self._projects  # None = All Logs
        try:
            idx = order.index(self._active_project)
        except ValueError:
            idx = 0
        idx = (idx + 1) % len(order)
        self._active_project = order[idx]
        self._refresh_display()

    def select_tab_index(self, index: int) -> None:
        """Select tab by zero-based index (0=All Logs, >=1 project tabs)."""
        if index <= 0:
            self._active_project = None
        else:
            proj_index = index - 1
            if 0 <= proj_index < len(self._projects):
                self._active_project = self._projects[proj_index]
        self._refresh_display()

    @property
    def tab_count(self) -> int:
        """Total tab count including 'All Logs'."""
        return 1 + len(self._projects)

    # Internal helpers ------------------------------------------------------
    def _build_tabs(self) -> None:
        self._tab_bar.remove_children()
        all_btn = Button("All Logs", id="tab-all", classes="tab")
        self._tab_bar.mount(all_btn)
        for proj in self._projects:
            btn = Button(proj, id=f"tab-{proj}", classes="tab")
            self._tab_bar.mount(btn)
        self._update_tab_styles()

    def _update_tab_styles(self) -> None:
        for button in self._tab_bar.query(Button):
            if button.id == "tab-all":
                if self._active_project is None:
                    button.add_class("-active")
                else:
                    button.remove_class("-active")
            elif button.id and button.id.startswith("tab-"):
                proj = button.id[4:]
                if self._active_project == proj:
                    button.add_class("-active")
                else:
                    button.remove_class("-active")

    def _refresh_display(self) -> None:
        self._log.clear()
        for proj, text in self._entries:
            if self._active_project is None or proj == self._active_project:
                self._log.write(text)
        self._update_tab_styles()

    # Events ----------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        button_id = event.button.id or ""
        if button_id == "tab-all":
            self._active_project = None
        elif button_id.startswith("tab-"):
            self._active_project = button_id[4:]
        self._refresh_display()

__all__ = ["SimpleLogViewer"]