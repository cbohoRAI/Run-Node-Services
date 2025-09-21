"""Tabbed log viewer widget (Phase 3)."""
from __future__ import annotations

from textual.widgets import TabbedContent, TabPane, Tab
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import RichLog
from typing import Dict, List

class TabbedLogViewer(TabbedContent):
    active_project = reactive("all")

    def __init__(self) -> None:
        super().__init__()
        self._project_tabs: Dict[str, RichLog] = {}
        self._pending_projects: List[str] = []  # names queued before fully ready
        self._mounted = False  # on_mount called
        self._ready = False    # internal ContentTabs present

    def compose(self) -> ComposeResult:  # type: ignore[override]
        # TabPane expects label/title as first arg; avoid passing duplicate title kw
        yield TabPane("All Logs", RichLog(highlight=True, markup=True, wrap=False), id="all")

    def on_mount(self) -> None:  # type: ignore[override]
        self._mounted = True
        # Defer flushing until next refresh when ContentTabs is created
        self.call_after_refresh(self._flush_pending)

    def _flush_pending(self) -> None:
        # Verify internal ContentTabs now exists; set ready flag
        try:
            from textual.widgets._tabbed_content import ContentTabs  # type: ignore
            self.get_child_by_type(ContentTabs)
            self._ready = True
        except Exception:  # noqa: BLE001
            # Try again on next cycle if still not ready
            self.call_after_refresh(self._flush_pending)
            return
        # Now safe to add queued panes
        for name in list(self._pending_projects):
            self._really_add_project(name)
        self._pending_projects.clear()

    def add_project(self, name: str) -> None:
        if name in self._project_tabs:
            return
        if not self._ready:
            self._pending_projects.append(name)
            return
        self._really_add_project(name)

    def _really_add_project(self, name: str) -> None:
        if name in self._project_tabs:
            return
        log = RichLog(highlight=True, wrap=False, markup=True)
        self._project_tabs[name] = log
        self.add_pane(TabPane(name, log, id=name))

    def write_line(self, project: str, line: str) -> None:
        # Write to project's tab
        plog = self._project_tabs.get(project)
        if plog:
            plog.write(line)
        # Always write to all tab with prefixed project
        all_pane = self.get_pane("all") if self.has_pane("all") else None
        if all_pane is not None:
            try:
                all_log = all_pane.query_one(RichLog)
                all_log.write(f"[{project}] {line}")
            except Exception:
                pass

__all__ = ["TabbedLogViewer"]
