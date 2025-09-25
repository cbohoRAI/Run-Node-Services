"""Node.js Process Killer - Specialized termination for Node.js process trees.

This module handles the complex task of properly terminating Node.js applications
that are started via npm/yarn/pnpm wrappers, ensuring both the wrapper processes
and the actual Node.js processes are killed and ports are released.
"""
from __future__ import annotations

import asyncio
import os
import signal
import time
from typing import Set, Optional
# import logging

from .port_scanner import find_process_by_port, kill_process_tree

# logger = logging.getLogger(__name__)

from .shutdown_logger import shutdown_logger
logger = shutdown_logger

class NodeProcessKiller:
    """Specialized killer for Node.js process trees."""
    
    def __init__(self, graceful_timeout: float = 3.0, force_timeout: float = 2.0):
        self.graceful_timeout = graceful_timeout
        self.force_timeout = force_timeout
    
    async def kill_node_project(
        self, 
        name: str, 
        port: Optional[int] = None,
        wrapper_pid: Optional[int] = None,
        known_node_pids: Optional[Set[int]] = None
    ) -> bool:
        """Kill a Node.js project including wrapper and actual Node processes.
        
        Args:
            name: Project name (for logging)
            port: Port the project is listening on
            wrapper_pid: PID of wrapper process (npm/yarn/pnpm)
            known_node_pids: Set of known Node.js PIDs
            
        Returns:
            True if all processes were terminated successfully
        """
        logger.info("Killing Node.js project %s (port=%s, wrapper_pid=%s)", 
                   name, port, wrapper_pid)
        
        success = True
        
        # Step 1: Find all Node.js processes on the port
        node_pids = set()
        if port:
            try:
                found_pids = find_process_by_port(port)
                node_pids.update(found_pids)
                logger.debug("Found %d processes on port %s: %s", 
                           len(found_pids), port, found_pids)
            except Exception as e:
                logger.warning("Failed to find processes on port %s: %s", port, e)
                success = False
        
        # Add any known Node.js PIDs
        if known_node_pids:
            node_pids.update(known_node_pids)
        
        # Step 2: Send SIGTERM to Node processes first (graceful)
        if node_pids:
            logger.debug("Sending SIGTERM to Node.js processes: %s", node_pids)
            for pid in node_pids:
                await self._terminate_process_graceful(pid)
            
            # Step 3: Wait briefly for graceful shutdown
            await asyncio.sleep(1.0)
            
            # Step 4: Force kill any remaining Node processes
            remaining = await self._check_remaining_processes(port)
            if remaining:
                logger.warning("Force killing remaining Node.js processes: %s", remaining)
                for pid in remaining:
                    await self._kill_process_force(pid)
                success = False
        
        # Step 5: Kill the wrapper process
        if wrapper_pid:
            logger.debug("Killing wrapper process: %s", wrapper_pid)
            try:
                kill_process_tree(wrapper_pid)
            except Exception as e:
                logger.warning("Failed to kill wrapper process %s: %s", wrapper_pid, e)
                success = False
        
        # Step 6: Verify port is released
        if port:
            port_released = await self._wait_for_port_release(port, timeout=5.0)
            if not port_released:
                logger.error("Port %s is still bound after killing project %s", port, name)
                success = False
            else:
                logger.debug("Port %s successfully released", port)
        
        if success:
            logger.info("Successfully killed Node.js project %s", name)
        else:
            logger.warning("Node.js project %s kill completed with issues", name)
        
        return success
    
    async def _terminate_process_graceful(self, pid: int) -> bool:
        """Send SIGTERM to a process for graceful shutdown."""
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            # Process already dead
            return True
        except PermissionError:
            logger.warning("Permission denied terminating process %s", pid)
            return False
        except Exception as e:
            logger.warning("Error terminating process %s: %s", pid, e)
            return False
    
    async def _kill_process_force(self, pid: int) -> bool:
        """Force kill a process."""
        try:
            kill_process_tree(pid)
            return True
        except Exception as e:
            logger.warning("Error force killing process %s: %s", pid, e)
            return False
    
    async def _check_remaining_processes(self, port: Optional[int]) -> Set[int]:
        """Check which processes are still bound to the port."""
        if not port:
            return set()
        
        try:
            return set(find_process_by_port(port))
        except Exception as e:
            logger.warning("Error checking remaining processes on port %s: %s", port, e)
            return set()
    
    async def _wait_for_port_release(self, port: int, timeout: float = 5.0) -> bool:
        """Wait for a port to be released (no longer bound)."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                pids = find_process_by_port(port)
                if not pids:
                    return True
                logger.debug("Port %s still bound by: %s", port, pids)
                await asyncio.sleep(0.5)
            except Exception:
                # Error checking port likely means it's free
                return True
        
        return False
    
    async def kill_all_on_port(self, port: int) -> bool:
        """Kill all processes bound to a specific port."""
        logger.info("Killing all processes on port %s", port)
        
        try:
            pids = find_process_by_port(port)
            if not pids:
                return True
            
            # First try graceful termination
            for pid in pids:
                await self._terminate_process_graceful(pid)
            
            await asyncio.sleep(1.0)
            
            # Then force kill remaining
            remaining = find_process_by_port(port)
            for pid in remaining:
                await self._kill_process_force(pid)
            
            # Verify port is released
            return await self._wait_for_port_release(port)
            
        except Exception as e:
            logger.error("Error killing processes on port %s: %s", port, e)
            return False
    
    async def discover_node_processes(self, port: int) -> Set[int]:
        """Discover Node.js processes listening on a port."""
        try:
            pids = find_process_by_port(port)
            logger.debug("Discovered %d processes on port %s: %s", len(pids), port, pids)
            return set(pids)
        except Exception as e:
            logger.warning("Failed to discover processes on port %s: %s", port, e)
            return set()