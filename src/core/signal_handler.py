"""Signal handling for graceful shutdown with enhanced shutdown system.

Registers handlers for SIGINT/SIGTERM (and SIGBREAK on Windows) to allow the
application to trigger a coordinated shutdown of all managed processes using
the new ShutdownManager system.

Integrators should provide an object with an async ``stop_all()`` method –
compatible with the existing ProcessManager.
"""
from __future__ import annotations

import asyncio
import signal
import sys
import time
import os
import logging
from types import FrameType
from typing import Optional, Protocol

from .shutdown_logger import shutdown_logger
logger = shutdown_logger


class SupportsStopAll(Protocol):  # pragma: no cover - structural
    async def stop_all(self) -> None: ...  # noqa: D401,E701
    async def cleanup_resources(self) -> None: ...  # noqa: D401,E701


class SignalHandler:
    def __init__(self, manager: SupportsStopAll) -> None:
        self._manager = manager
        self._shutdown_started = False
        self._shutdown_manager = None  # Will be set by app if using new shutdown system
        self.signal_count = 0
        self.last_signal_time = 0

    def set_shutdown_manager(self, shutdown_manager) -> None:
        """Set the ShutdownManager for enhanced shutdown handling."""
        self._shutdown_manager = shutdown_manager

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
        current_time = time.time()
        
        # Handle multiple signals (force kill on 3rd signal)
        if current_time - self.last_signal_time < 1:
            self.signal_count += 1
        else:
            self.signal_count = 1
        
        self.last_signal_time = current_time
        
        if self.signal_count >= 3:
            # Emergency exit
            print("\n!!! Force exit !!!")
            os._exit(1)
        elif self.signal_count == 2:
            print("\nForce stopping... (press again for emergency exit)")
            if self._shutdown_manager and not self._shutdown_started:
                self._shutdown_started = True
                try:
                    asyncio.get_running_loop().create_task(
                        self._shutdown_manager.emergency_shutdown()
                    )
                except RuntimeError:
                    # Fallback to old method
                    self._fallback_shutdown()
            else:
                self._fallback_shutdown()
        else:
            print("\nGraceful shutdown... (press again to force)")
            if self._shutdown_manager and not self._shutdown_started:
                self._shutdown_started = True
                try:
                    asyncio.get_running_loop().create_task(
                        self._shutdown_manager.initiate_shutdown(f"signal_{signum}")
                    )
                except RuntimeError:
                    # Fallback to old method
                    self._fallback_shutdown()
            elif not self._shutdown_started:
                self._shutdown_started = True
                try:
                    asyncio.get_running_loop().create_task(self._graceful())
                except RuntimeError:
                    # Fallback to old method
                    self._fallback_shutdown()

    def _fallback_shutdown(self) -> None:
        """Fallback shutdown method when event loop is not available."""
        logger.warning("Using fallback shutdown method")
        try:
            # Try to run both stop_all and cleanup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._manager.stop_all())
                loop.run_until_complete(self._manager.cleanup_resources())
            finally:
                loop.close()
        except Exception:  # noqa: BLE001
            logger.exception("Fallback shutdown failed")
        finally:
            os._exit(1)

    async def _graceful(self) -> None:
        logger.info("Starting graceful shutdown")
        try:
            await self._manager.stop_all()
            await self._manager.cleanup_resources()
        except Exception:  # noqa: BLE001
            logger.exception("Graceful shutdown failed")


__all__ = ["SignalHandler"]
