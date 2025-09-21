"""Main Textual application (Phase 3)."""
from __future__ import annotations

import logging
from pathlib import Path
from textual.app import App

from src.core.process_manager import ProcessManager
from src.core.log_collector import LogCollector
from src.screens.selection import ProjectSelectionScreen


class NodeManagerApp(App):
    CSS_PATH = None
    TITLE = "Node Project Manager (Phase 3)"

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._manager = ProcessManager()
        self._log_collector = LogCollector()

    def on_mount(self) -> None:  # type: ignore[override]
        self.push_screen(ProjectSelectionScreen(self._root, self._manager, self._log_collector))

    async def on_shutdown_request(self) -> None:  # type: ignore[override]
        await self._manager.stop_all()


def run(root: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = NodeManagerApp(root)
    app.run()


__all__ = ["run", "NodeManagerApp"]
