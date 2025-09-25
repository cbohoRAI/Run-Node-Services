"""Main Textual application (Phase 3) - Enhanced with new shutdown system."""
from __future__ import annotations

import logging
from pathlib import Path
from textual.app import App

from src.core.process_manager import ProcessManager
from src.core.log_collector import LogCollector
from src.core.resource_registry import ResourceRegistry
from src.core.shutdown_manager import ShutdownManager
from src.core.signal_handler import SignalHandler
from src.screens.selection import ProjectSelectionScreen


class NodeManagerApp(App):
    CSS_PATH = None
    TITLE = "Node Project Manager (Phase 3)"

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        # Create resource registry first
        self._resource_registry = ResourceRegistry()
        # Create process manager with registry
        self._manager = ProcessManager(self._resource_registry)
        self._log_collector = LogCollector()
        
        # Create shutdown manager
        self._shutdown_manager = ShutdownManager(
            self._resource_registry,
            self._manager,
            graceful_timeout=10.0,
            emergency_timeout=15.0
        )
        
        # Create signal handler with enhanced shutdown
        self._signal_handler = SignalHandler(self._manager)
        self._signal_handler.set_shutdown_manager(self._shutdown_manager)
        
        # Install signal handlers
        self._signal_handler.install()

    def on_mount(self) -> None:  # type: ignore[override]
        self.push_screen(ProjectSelectionScreen(self._root, self._manager, self._log_collector))

    async def on_shutdown_request(self) -> None:  # type: ignore[override]
        """Handle app shutdown request using the new shutdown system."""
        try:
            await self._shutdown_manager.initiate_shutdown("app_shutdown")
        except Exception as e:
            logging.error("Error during app shutdown: %s", e)
            # Fallback to basic cleanup
            await self._manager.stop_all()
            await self._manager.cleanup_resources()


def run(root: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = NodeManagerApp(root)
    app.run()


__all__ = ["run", "NodeManagerApp"]
