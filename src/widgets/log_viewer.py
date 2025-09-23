"""Tabbed log viewer widget (working version).

Rewritten to:
- Avoid poking into private Textual internals.
- Queue project tabs added before on_mount.
- Provide write_line(project, line) API similar to the simple viewer.
- Wrap long lines by default.
"""
from __future__ import annotations

from textual.widgets import TabbedContent, TabPane, RichLog
from textual.app import ComposeResult
from typing import Dict, List


class TabbedLogViewer(TabbedContent):
    def __init__(
        self,
        *,
        wrap: bool = True,
        highlight: bool = True,
        markup: bool = True,
    ) -> None:
        super().__init__()
        self._wrap = wrap
        self._highlight = highlight
        self._markup = markup
        self._logs: Dict[str, RichLog] = {}      # project -> RichLog
        self._pending: List[str] = []            # projects requested pre-mount
        self._ready = False

    def compose(self) -> ComposeResult:  # type: ignore[override]
        # Create the "All" aggregate pane first.
        yield TabPane(
            "All",
            RichLog(
                highlight=self._highlight,
                markup=self._markup,
                wrap=self._wrap,
            ),
            id="all",
        )

    def on_mount(self) -> None:  # type: ignore[override]
        self._ready = True
        # Flush any queued project tabs.
        for name in self._pending:
            self._add_project_tab(name)
        self._pending.clear()

    def ensure_project(self, name: str) -> None:
        """Ensure a tab exists for the project."""
        if name == "all" or name in self._logs:
            return
        if not self._ready:
            if name not in self._pending:
                self._pending.append(name)
            return
        self._add_project_tab(name)

    def _add_project_tab(self, name: str) -> None:
        if name in self._logs:
            return
        log = RichLog(
            highlight=self._highlight,
            markup=self._markup,
            wrap=self._wrap,
        )
        self._logs[name] = log
        self.add_pane(TabPane(name, log, id=name))

    def write_line(self, project: str, line: str) -> None:
        """Write a line to the project's tab and the All tab."""
        self.ensure_project(project)

        # Write to project-specific log
        proj_log = self._logs.get(project)
        if proj_log is not None:
            proj_log.write(line)

        # Always write to All tab (prefixed)
        try:
            all_log = self.get_pane("all").query_one(RichLog)
            all_log.write(f"[{project}] {line}")
        except Exception:
            pass


__all__ = ["TabbedLogViewer"]
