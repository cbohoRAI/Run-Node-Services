"""Asynchronous log collection with per-project ring buffers (Phase 3)."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Deque, Dict, Callable, List
from datetime import datetime

class LogCollector:
    def __init__(self, max_lines_per_project: int = 1000) -> None:
        self._max = max_lines_per_project
        self._buffers: Dict[str, Deque[str]] = {}
        self._callbacks: List[Callable[[str, str], None]] = []
        self._locks: Dict[str, asyncio.Lock] = {}

    def register_callback(self, cb: Callable[[str, str], None]) -> None:
        self._callbacks.append(cb)

    def get_buffer(self, project: str) -> List[str]:
        buf = self._buffers.get(project)
        if not buf:
            return []
        return list(buf)

    async def add_line(self, project: str, line: str) -> None:
        if project not in self._buffers:
            self._buffers[project] = deque(maxlen=self._max)
            self._locks[project] = asyncio.Lock()
        async with self._locks[project]:
            ts = datetime.utcnow().strftime("%H:%M:%S")
            entry = f"{ts} {line}"
            self._buffers[project].append(entry)
        for cb in self._callbacks:
            cb(project, entry)

__all__ = ["LogCollector"]
