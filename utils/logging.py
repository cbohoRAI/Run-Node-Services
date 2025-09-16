"""Logging utilities for managing and buffering log output."""

import asyncio
import time
from collections import deque
from typing import Dict, Optional

try:
    from textual.widgets import RichLog
except ImportError:
    RichLog = None  # For type checking when textual isn't available


class LogManager:
    """Manages multiple log streams for different projects."""
    
    def __init__(self, max_lines_per_project: int = 1000):
        self.max_lines = max_lines_per_project
        self.all_logs = deque(maxlen=max_lines_per_project * 10)  # Larger buffer for "All"
        self.project_logs: Dict[int, deque] = {}  # project_idx -> log lines
        self.project_names: Dict[int, str] = {}  # project_idx -> project name
    
    def add_project(self, project_idx: int, project_name: str) -> None:
        """Register a new project for logging."""
        self.project_logs[project_idx] = deque(maxlen=self.max_lines)
        self.project_names[project_idx] = project_name
    
    def add_log_line(self, project_idx: int, formatted_line: str) -> None:
        """Add a log line to both the all-logs buffer and project-specific buffer."""
        # Add to project-specific buffer
        if project_idx in self.project_logs:
            self.project_logs[project_idx].append(formatted_line)
        
        # Add to all-logs buffer
        self.all_logs.append(formatted_line)
    
    def get_project_logs(self, project_idx: Optional[int] = None) -> list:
        """Get logs for a specific project, or all logs if project_idx is None."""
        if project_idx is None:
            return list(self.all_logs)
        
        return list(self.project_logs.get(project_idx, []))
    
    def remove_project(self, project_idx: int) -> None:
        """Remove a project's log buffer when it stops."""
        self.project_logs.pop(project_idx, None)
        self.project_names.pop(project_idx, None)


class LogBuffer:
    """Efficient log buffer with automatic flushing."""
    
    def __init__(self, log_widget: RichLog, flush_interval: float = 0.5, max_buffer: int = 20):
        self.log_widget = log_widget
        self.buffer = []
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self.last_flush = time.time()
        self._flush_task = None
    
    def add_line(self, line: str):
        """Add a line to the buffer."""
        self.buffer.append(line)
        
        # Force flush if buffer is full
        if len(self.buffer) >= self.max_buffer:
            self.flush_now()
        else:
            # Schedule a flush if not already scheduled
            self._schedule_flush()
    
    def _schedule_flush(self):
        """Schedule a flush if one isn't already pending."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())
    
    async def _delayed_flush(self):
        """Flush after a delay."""
        await asyncio.sleep(self.flush_interval)
        self.flush_now()
    
    def flush_now(self):
        """Immediately flush all buffered logs."""
        if self.buffer and self.log_widget:
            # Write all lines at once
            for line in self.buffer:
                self.log_widget.write(line)
            self.buffer.clear()
            self.last_flush = time.time()


class MultiLogBuffer:
    """Efficient log buffer that writes to multiple RichLog widgets."""
    
    def __init__(self, all_log_widget: RichLog, project_log_widget: Optional[RichLog] = None, 
                 flush_interval: float = 0.5, max_buffer: int = 20):
        self.all_log_widget = all_log_widget
        self.project_log_widget = project_log_widget
        self.buffer = []
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self.last_flush = time.time()
        self._flush_task = None
    
    def add_line(self, line: str):
        """Add a line to the buffer."""
        self.buffer.append(line)
        
        if len(self.buffer) >= self.max_buffer:
            self.flush_now()
        else:
            self._schedule_flush()
    
    def _schedule_flush(self):
        """Schedule a flush if one isn't already pending."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())
    
    async def _delayed_flush(self):
        """Flush after a delay."""
        await asyncio.sleep(self.flush_interval)
        self.flush_now()
    
    def flush_now(self):
        """Immediately flush all buffered logs to both widgets."""
        if self.buffer:
            for line in self.buffer:
                # Write to "All Logs" tab
                if self.all_log_widget:
                    self.all_log_widget.write(line)
                
                # Write to project-specific tab
                if self.project_log_widget:
                    self.project_log_widget.write(line)
            
            self.buffer.clear()
            self.last_flush = time.time()