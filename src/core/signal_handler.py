"""Signal handling for graceful shutdown (Phase 2).

Registers handlers for SIGINT/SIGTERM (and SIGBREAK on Windows) to allow the
application to trigger a coordinated shutdown of all managed processes.

Integrators should provide an object with an async ``stop_all()`` method –
compatible with the existing ProcessManager.
"""
from __future__ import annotations

import asyncio
import signal
import sys
import logging
from types import FrameType
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class SupportsStopAll(Protocol):  # pragma: no cover - structural
    async def stop_all(self) -> None: ...  # noqa: D401,E701


class SignalHandler:
    def __init__(self, manager: SupportsStopAll) -> None:
        self._manager = manager
        self._shutdown_started = False

    def install(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                logger.exception("Failed to register handler for %s", sig)
        if sys.platform == "win32":  # SIGBREAK available on Windows
            try:
                signal.signal(signal.SIGBREAK, self._handle_signal)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                logger.exception("Failed to register SIGBREAK handler")

    def _handle_signal(self, signum: int, frame: Optional[FrameType]) -> None:  # noqa: D401
        if self._shutdown_started:
            logger.debug("Shutdown already in progress (signal %s)", signum)
            return
        self._shutdown_started = True
        logger.info("Received signal %s – initiating graceful shutdown", signum)
        try:
            asyncio.get_running_loop().create_task(self._graceful())
        except RuntimeError:
            # No running loop – fallback to synchronous stop
            logger.warning("No running event loop; performing synchronous stop")
            try:
                asyncio.run(self._manager.stop_all())
            except Exception:  # noqa: BLE001
                logger.exception("Synchronous stop_all failed after signal")

    async def _graceful(self) -> None:
        try:
            await self._manager.stop_all()
        except Exception:  # noqa: BLE001
            logger.exception("Error during graceful shutdown")

__all__ = ["SignalHandler"]
