"""Health checker for monitoring project health via HTTP endpoints."""
from __future__ import annotations

import asyncio
import aiohttp
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Set
from enum import Enum
import time
import logging

from src.models.status import ProjectStatus

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Internal health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNRESPONSIVE = "unresponsive"
    NOT_READY = "not_ready"  # Server not yet listening


@dataclass
class ProjectHealth:
    """Health information for a project."""
    project_name: str
    base_url: str
    health_path: str
    port: Optional[int] = None
    last_check: float = 0.0
    consecutive_failures: int = 0
    status: HealthStatus = HealthStatus.NOT_READY
    # Track if we're in a known restart state
    restarting: bool = False
    # Track process existence separately
    process_running: bool = False


class HealthChecker:
    """Periodic health checker for Node.js projects."""
    
    def __init__(
        self,
        check_interval: float = 5.0,
        startup_grace_period: float = 15.0,
        timeout: float = 3.0,
        failure_threshold: int = 3,
    ):
        """Initialize health checker.
        
        Args:
            check_interval: Seconds between health checks
            startup_grace_period: Seconds to wait before first check after registration
            timeout: HTTP request timeout in seconds
            failure_threshold: Consecutive failures before marking unhealthy
        """
        self._check_interval = check_interval
        self._startup_grace_period = startup_grace_period
        self._timeout = timeout
        self._failure_threshold = failure_threshold
        
        self._projects: Dict[str, ProjectHealth] = {}
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
        self._callbacks: Set[Callable[[str, ProjectStatus], None]] = set()
        self._session: Optional[aiohttp.ClientSession] = None
    
    def register_callback(self, callback: Callable[[str, ProjectStatus], None]) -> None:
        """Register a callback for health status changes.
        
        Callback signature: (project_name: str, status: ProjectStatus) -> None
        """
        self._callbacks.add(callback)
    
    def unregister_callback(self, callback: Callable[[str, ProjectStatus], None]) -> None:
        """Unregister a callback."""
        self._callbacks.discard(callback)
    
    def register_project(
        self,
        project_name: str,
        port: int,
        health_path: str = "/ping",
    ) -> None:
        """Register a project for health checking.
        
        Args:
            project_name: Project identifier
            port: Port the project is running on
            health_path: HTTP path for health endpoint (default: /ping)
        """
        base_url = f"http://localhost:{port}"
        self._projects[project_name] = ProjectHealth(
            project_name=project_name,
            base_url=base_url,
            health_path=health_path,
            port=port,
            last_check=time.time(),  # Start grace period now
            process_running=True,
        )
        logger.info(f"Registered health check for {project_name} at {base_url}{health_path}")
    
    def unregister_project(self, project_name: str) -> None:
        """Unregister a project from health checking."""
        if project_name in self._projects:
            del self._projects[project_name]
            logger.info(f"Unregistered health check for {project_name}")
    
    def mark_restarting(self, project_name: str) -> None:
        """Mark a project as restarting (gives it grace period)."""
        if project_name in self._projects:
            health = self._projects[project_name]
            health.restarting = True
            health.consecutive_failures = 0
            health.last_check = time.time()
            health.status = HealthStatus.NOT_READY
            # Notify callbacks immediately
            self._notify_status_change(project_name, ProjectStatus.RESTARTING)
    
    def mark_stopped(self, project_name: str) -> None:
        """Mark a project as intentionally stopped."""
        if project_name in self._projects:
            health = self._projects[project_name]
            health.process_running = False
            health.restarting = False
            self._notify_status_change(project_name, ProjectStatus.STOPPED)
    
    def mark_process_running(self, project_name: str, running: bool) -> None:
        """Update whether the process is running (from process manager)."""
        if project_name in self._projects:
            self._projects[project_name].process_running = running
    
    async def start(self) -> None:
        """Start the health checker."""
        if self._running:
            return
        
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._timeout)
        )
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("Health checker started")
    
    async def stop(self) -> None:
        """Stop the health checker."""
        self._running = False
        
        if self._check_task and not self._check_task.done():
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info("Health checker stopped")
    
    async def _check_loop(self) -> None:
        """Main health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_all_projects()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}", exc_info=True)
    
    async def _check_all_projects(self) -> None:
        """Check health of all registered projects."""
        if not self._session:
            return
        
        tasks = []
        for project_name in list(self._projects.keys()):
            tasks.append(self._check_project(project_name))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_project(self, project_name: str) -> None:
        """Check health of a single project."""
        if project_name not in self._projects:
            return
        
        health = self._projects[project_name]
        now = time.time()
        
        # Check if we're still in grace period
        time_since_start = now - health.last_check
        if health.status == HealthStatus.NOT_READY:
            if time_since_start < self._startup_grace_period:
                # Still in grace period, try the check but don't penalize failures
                success = await self._perform_health_check(health)
                if success:
                    health.status = HealthStatus.HEALTHY
                    health.consecutive_failures = 0
                    self._notify_status_change(project_name, ProjectStatus.RUNNING)
                # If it fails, just wait - we're still in grace period
                return
            elif health.restarting:
                # Grace period over but still restarting - likely a problem
                health.restarting = False
                health.consecutive_failures += 1
        
        # Perform health check
        success = await self._perform_health_check(health)
        
        previous_status = health.status
        
        if success:
            # Health check passed
            health.consecutive_failures = 0
            health.status = HealthStatus.HEALTHY
            health.restarting = False
            
            # Only notify if status changed
            if previous_status != HealthStatus.HEALTHY:
                self._notify_status_change(project_name, ProjectStatus.RUNNING)
        else:
            # Health check failed
            health.consecutive_failures += 1
            
            # Determine new status based on failure count and process state
            if not health.process_running:
                # Process is down
                new_status = HealthStatus.UNHEALTHY
                project_status = ProjectStatus.CRASHED
            elif health.consecutive_failures >= self._failure_threshold:
                # Multiple failures - unresponsive
                new_status = HealthStatus.UNRESPONSIVE
                project_status = ProjectStatus.UNRESPONSIVE
            else:
                # First few failures - might be temporary
                new_status = HealthStatus.UNHEALTHY
                project_status = ProjectStatus.UNHEALTHY
            
            if health.status != new_status:
                health.status = new_status
                self._notify_status_change(project_name, project_status)
    
    async def _perform_health_check(self, health: ProjectHealth) -> bool:
        """Perform actual HTTP health check.
        
        Returns:
            True if health check succeeded, False otherwise
        """
        if not self._session:
            return False
        
        url = f"{health.base_url}{health.health_path}"
        
        try:
            async with self._session.get(url) as response:
                # Accept any 2xx status as healthy
                if 200 <= response.status < 300:
                    return True
                else:
                    logger.debug(f"Health check for {health.project_name} returned {response.status}")
                    return False
        except asyncio.TimeoutError:
            logger.debug(f"Health check timeout for {health.project_name}")
            return False
        except aiohttp.ClientError as e:
            logger.debug(f"Health check error for {health.project_name}: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking {health.project_name}: {e}")
            return False
    
    def _notify_status_change(self, project_name: str, status: ProjectStatus) -> None:
        """Notify all callbacks of a status change."""
        for callback in self._callbacks:
            try:
                callback(project_name, status)
            except Exception as e:
                logger.error(f"Error in health status callback: {e}", exc_info=True)
    
    def get_status(self, project_name: str) -> Optional[ProjectStatus]:
        """Get current status for a project.
        
        Returns:
            ProjectStatus or None if project not registered
        """
        if project_name not in self._projects:
            return None
        
        health = self._projects[project_name]
        
        if health.restarting:
            return ProjectStatus.RESTARTING
        
        if not health.process_running:
            return ProjectStatus.STOPPED
        
        status_map = {
            HealthStatus.HEALTHY: ProjectStatus.RUNNING,
            HealthStatus.NOT_READY: ProjectStatus.STARTING,
            HealthStatus.UNHEALTHY: ProjectStatus.UNHEALTHY,
            HealthStatus.UNRESPONSIVE: ProjectStatus.UNRESPONSIVE,
        }
        
        return status_map.get(health.status, ProjectStatus.RUNNING)


__all__ = ["HealthChecker", "HealthStatus", "ProjectHealth"]
