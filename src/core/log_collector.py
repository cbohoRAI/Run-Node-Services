"""Asynchronous log collection with per-project ring buffers (Phase 3)."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Deque, Dict, Callable, List, Optional
from datetime import datetime
import re

# Pattern to detect nodemon restart messages
NODEMON_RESTART_PATTERN = re.compile(
    r"\[nodemon\]\s+(restarting|starting)",
    re.IGNORECASE
)

# Pattern to detect nodemon crash messages (real crashes, not restarts)
NODEMON_CRASH_PATTERN = re.compile(
    r"\[nodemon\]\s+app\s+crashed",
    re.IGNORECASE
)

class LogCollector:
    def __init__(self, max_lines_per_project: int = 1000) -> None:
        self._max = max_lines_per_project
        self._buffers: Dict[str, Deque[str]] = {}
        self._callbacks: List[Callable[[str, str], None]] = []
        self._locks: Dict[str, asyncio.Lock] = {}
        # Callbacks for restart/crash detection
        self._restart_callbacks: List[Callable[[str], None]] = []
        self._crash_callbacks: List[Callable[[str], None]] = []

    def register_callback(self, cb: Callable[[str, str], None]) -> None:
        self._callbacks.append(cb)

    def unregister_callback(self, cb):
        """Remove a previously registered callback."""
        try:
            if cb in self._callbacks: 
                self._callbacks.remove(cb)
        except Exception:
            pass
    
    def register_restart_callback(self, cb: Callable[[str], None]) -> None:
        """Register a callback for nodemon restart detection.
        
        Callback signature: (project_name: str) -> None
        """
        self._restart_callbacks.append(cb)
    
    def register_crash_callback(self, cb: Callable[[str], None]) -> None:
        """Register a callback for nodemon crash detection.
        
        Callback signature: (project_name: str) -> None
        Note: This is for nodemon-reported crashes only, not all crashes.
        """
        self._crash_callbacks.append(cb)

    def get_buffer(self, project: str) -> List[str]:
        buf = self._buffers.get(project)
        if not buf:
            return []
        return list(buf)

    async def add_line(self, project: str, line: str) -> None:
        if project not in self._buffers:
            self._buffers[project] = deque(maxlen=self._max)
            self._locks[project] = asyncio.Lock()
        
        # Check for nodemon patterns before processing
        # Note: These are supplementary to health checks, not the only crash detection method
        if NODEMON_RESTART_PATTERN.search(line):
            # Nodemon is restarting - notify restart callbacks
            for cb in self._restart_callbacks:
                try:
                    cb(project)
                except Exception:
                    pass  # Don't let callback errors break log collection
        elif NODEMON_CRASH_PATTERN.search(line):
            # Nodemon reports a crash - notify crash callbacks
            # Note: This won't catch all crashes, only those nodemon explicitly reports
            for cb in self._crash_callbacks:
                try:
                    cb(project)
                except Exception:
                    pass
        
        async with self._locks[project]:
            ts = datetime.utcnow().strftime("%H:%M:%S")
            entry = f"{ts} {line}"
            self._buffers[project].append(entry)
        for cb in self._callbacks:
            cb(project, entry)

__all__ = ["LogCollector"]
