"""Main Textual application (Phase 1)."""
from __future__ import annotations

import logging
from pathlib import Path
from textual.app import App

from src.core.process_manager import ProcessManager
from src.screens.selection import ProjectSelectionScreen


class NodeManagerApp(App):
    CSS_PATH = None
    TITLE = "Node Project Manager (Phase 1)"

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._manager = ProcessManager()

    def on_mount(self) -> None:  # type: ignore[override]
        self.push_screen(ProjectSelectionScreen(self._root, self._manager))

    async def on_shutdown_request(self) -> None:  # type: ignore[override]
        await self._manager.stop_all()


def run(root: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = NodeManagerApp(root)
    app.run()


__all__ = ["run", "NodeManagerApp"]
