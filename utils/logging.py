"""Optimized logging utilities for high-performance log management."""

import asyncio
import time
from collections import deque
from typing import Dict, Optional, List
import threading

try:
    from textual.widgets import RichLog
except ImportError:
    RichLog = None


class LogManager:
    """Optimized log manager with thread-safe operations."""
    
    def __init__(self, max_lines_per_project: int = 1000):
        self.max_lines = max_lines_per_project
        self.all_logs = deque(maxlen=max_lines_per_project * 10)
        self.project_logs: Dict[int, deque] = {}
        self.project_names: Dict[int, str] = {}
        self._lock = threading.RLock()  # Thread safety
    
    def add_project(self, project_idx: int, project_name: str) -> None:
        """Register a project."""
        with self._lock:
            self.project_logs[project_idx] = deque(maxlen=self.max_lines)
            self.project_names[project_idx] = project_name
    
    def add_log_line(self, project_idx: int, formatted_line: str) -> None:
        """Add log line efficiently."""
        with self._lock:
            # Add to project buffer if exists
            if project_idx in self.project_logs:
                self.project_logs[project_idx].append(formatted_line)
            
            # Add to all-logs buffer
            self.all_logs.append(formatted_line)
    
    def get_project_logs(self, project_idx: Optional[int] = None) -> List[str]:
        """Get logs for a project."""
        with self._lock:
            if project_idx is None:
                return list(self.all_logs)
            return list(self.project_logs.get(project_idx, []))
    
    def remove_project(self, project_idx: int) -> None:
        """Remove a project's logs."""
        with self._lock:
            self.project_logs.pop(project_idx, None)
            self.project_names.pop(project_idx, None)


class LogBuffer:
    """High-performance log buffer with batching."""
    
    def __init__(
        self, 
        log_widget: RichLog, 
        flush_interval: float = 0.2, 
        max_buffer: int = 10
    ):
        self.log_widget = log_widget
        self.buffer: List[str] = []
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    async def add_line(self, line: str) -> None:
        """Add line with async safety."""
        async with self._lock:
            self.buffer.append(line)
            
            if len(self.buffer) >= self.max_buffer:
                await self._flush_now_internal()
            else:
                self._schedule_flush()
    
    def add_line_sync(self, line: str) -> None:
        """Synchronous add for compatibility."""
        self.buffer.append(line)
        
        if len(self.buffer) >= self.max_buffer:
            self.flush_now()
        else:
            self._schedule_flush()
    
    def _schedule_flush(self) -> None:
        """Schedule flush if not pending."""
        if not self._flush_task or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())
    
    async def _delayed_flush(self) -> None:
        """Delayed flush."""
        await asyncio.sleep(self.flush_interval)
        async with self._lock:
            await self._flush_now_internal()
    
    async def _flush_now_internal(self) -> None:
        """Internal flush without lock."""
        if self.buffer and self.log_widget:
            # Batch write all lines
            text = '\n'.join(self.buffer)
            self.log_widget.write(text)
            self.buffer.clear()
    
    def flush_now(self) -> None:
        """Synchronous flush."""
        if self.buffer and self.log_widget:
            text = '\n'.join(self.buffer)
            self.log_widget.write(text)
            self.buffer.clear()


class MultiLogBuffer:
    """Optimized multi-output log buffer."""
    
    def __init__(
        self,
        all_log_widget: RichLog,
        project_log_widget: Optional[RichLog] = None,
        flush_interval: float = 0.2,
        max_buffer: int = 10
    ):
        self.all_log_widget = all_log_widget
        self.project_log_widget = project_log_widget
        self.buffer: List[str] = []
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self._flush_task: Optional[asyncio.Task] = None
        self._last_flush = time.monotonic()
    
    def add_line(self, line: str) -> None:
        """Add line to buffer."""
        self.buffer.append(line)
        
        # Force flush on buffer full or time elapsed
        if len(self.buffer) >= self.max_buffer:
            self.flush_now()
        elif time.monotonic() - self._last_flush > self.flush_interval:
            self.flush_now()
        else:
            self._schedule_flush()
    
    def _schedule_flush(self) -> None:
        """Schedule async flush."""
        if not self._flush_task or self._flush_task.done():
            try:
                self._flush_task = asyncio.create_task(self._delayed_flush())
            except RuntimeError:
                # No event loop, flush synchronously
                self.flush_now()
    
    async def _delayed_flush(self) -> None:
        """Delayed flush."""
        remaining = self.flush_interval - (time.monotonic() - self._last_flush)
        if remaining > 0:
            await asyncio.sleep(remaining)
        self.flush_now()
    
    def flush_now(self) -> None:
        """Immediate flush to all widgets."""
        if not self.buffer:
            return
        
        # Join all lines for single write
        text = '\n'.join(self.buffer)
        
        # Write to both widgets
        if self.all_log_widget:
            self.all_log_widget.write(text)
        
        if self.project_log_widget:
            self.project_log_widget.write(text)
        
        self.buffer.clear()
        self._last_flush = time.monotonic()
        
        # Cancel pending flush
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()