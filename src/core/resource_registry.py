"""Resource Registry for tracking all managed resources during shutdown.

This module provides centralized tracking of all resources that need cleanup
during shutdown: processes, tasks, transports, and ports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any
import asyncio
# import logging

# logger = logging.getLogger(__name__)

from .shutdown_logger import shutdown_logger
logger = shutdown_logger

@dataclass
class ProcessInfo:
    """Information about a managed process."""
    wrapper_process: asyncio.subprocess.Process
    wrapper_pid: int
    node_pids: Set[int] = field(default_factory=set)
    port: Optional[int] = None
    path: Optional[str] = None
    command: list[str] = field(default_factory=list)


@dataclass
class ResourceBundle:
    """Bundle of all resources for a single project."""
    process_info: Optional[ProcessInfo] = None
    tasks: Set[asyncio.Task] = field(default_factory=set)
    transports: Set[Any] = field(default_factory=set)  # asyncio transports
    port: Optional[int] = None


class ResourceRegistry:
    """Central registry for all managed resources."""
    
    def __init__(self) -> None:
        self.processes: Dict[str, ProcessInfo] = {}
        self.tasks: Dict[str, Set[asyncio.Task]] = {}
        self.transports: Dict[str, Set[Any]] = {}
        self.ports: Dict[str, int] = {}
        self.node_pids: Dict[str, Set[int]] = {}
        self._lock = asyncio.Lock()
    
    async def register_process(
        self, 
        name: str, 
        wrapper_process: asyncio.subprocess.Process,
        port: Optional[int] = None,
        path: Optional[str] = None,
        command: Optional[list[str]] = None
    ) -> None:
        """Register a wrapper process."""
        async with self._lock:
            self.processes[name] = ProcessInfo(
                wrapper_process=wrapper_process,
                wrapper_pid=wrapper_process.pid or 0,
                port=port,
                path=path,
                command=command or []
            )
            if port:
                self.ports[name] = port
            logger.debug("Registered process %s (wrapper_pid=%s, port=%s)", 
                        name, wrapper_process.pid, port)
    
    async def register_node_pids(self, name: str, pids: Set[int]) -> None:
        """Register actual Node.js process PIDs for a project."""
        async with self._lock:
            self.node_pids[name] = pids
            if name in self.processes:
                self.processes[name].node_pids = pids
            logger.debug("Registered Node.js PIDs for %s: %s", name, pids)
    
    async def register_task(self, name: str, task: asyncio.Task) -> None:
        """Register an asyncio task for a project."""
        async with self._lock:
            if name not in self.tasks:
                self.tasks[name] = set()
            self.tasks[name].add(task)
            logger.debug("Registered task for %s: %s", name, task)
    
    async def register_transport(self, name: str, transport: Any) -> None:
        """Register a transport/pipe for a project."""
        async with self._lock:
            if name not in self.transports:
                self.transports[name] = set()
            self.transports[name].add(transport)
            logger.debug("Registered transport for %s: %s", name, transport)
    
    async def get_all_resources(self, name: str) -> ResourceBundle:
        """Get all resources for a project."""
        async with self._lock:
            return ResourceBundle(
                process_info=self.processes.get(name),
                tasks=self.tasks.get(name, set()).copy(),
                transports=self.transports.get(name, set()).copy(),
                port=self.ports.get(name)
            )
    
    async def clear_resources(self, name: str) -> None:
        """Clear all resources for a project."""
        async with self._lock:
            self.processes.pop(name, None)
            self.tasks.pop(name, None)
            self.transports.pop(name, None)
            self.ports.pop(name, None)
            self.node_pids.pop(name, None)
            logger.debug("Cleared all resources for %s", name)
    
    async def get_all_project_names(self) -> Set[str]:
        """Get all project names with registered resources."""
        async with self._lock:
            names = set()
            names.update(self.processes.keys())
            names.update(self.tasks.keys())
            names.update(self.transports.keys())
            names.update(self.ports.keys())
            names.update(self.node_pids.keys())
            return names
    
    async def get_all_tasks(self) -> Set[asyncio.Task]:
        """Get all registered tasks."""
        async with self._lock:
            all_tasks = set()
            for task_set in self.tasks.values():
                all_tasks.update(task_set)
            return all_tasks
    
    async def remove_task(self, name: str, task: asyncio.Task) -> None:
        """Remove a specific task from tracking."""
        async with self._lock:
            if name in self.tasks:
                self.tasks[name].discard(task)
                if not self.tasks[name]:
                    del self.tasks[name]