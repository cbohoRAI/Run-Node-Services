"""Platform-specific cleanup utilities.

This module provides platform-specific implementations for cleanup operations
that differ between Windows and Unix-like systems.
"""
from __future__ import annotations

import sys
import subprocess
import logging
from typing import List, Set
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PlatformCleaner(ABC):
    """Abstract base class for platform-specific cleanup operations."""
    
    @abstractmethod
    def cleanup_event_loop(self, loop) -> None:
        """Perform platform-specific event loop cleanup."""
        pass
    
    @abstractmethod
    def find_processes_on_port(self, port: int) -> List[int]:
        """Find processes listening on a specific port."""
        pass
    
    @staticmethod
    def get_cleaner() -> 'PlatformCleaner':
        """Get the appropriate cleaner for the current platform."""
        if sys.platform == "win32":
            return WindowsCleaner()
        else:
            return UnixCleaner()


class WindowsCleaner(PlatformCleaner):
    """Windows-specific cleanup operations."""
    
    def cleanup_event_loop(self, loop) -> None:
        """Windows ProactorEventLoop specific cleanup."""
        try:
            # Close the proactor to prevent resource leaks
            if hasattr(loop, '_proactor') and loop._proactor:
                loop._proactor.close()
        except Exception as e:
            logger.warning("Error during Windows event loop cleanup: %s", e)
    
    def find_processes_on_port(self, port: int) -> List[int]:
        """Use netstat to find processes on Windows."""
        try:
            # Use netstat to find processes listening on the port
            cmd = ["netstat", "-ano"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                logger.warning("netstat command failed: %s", result.stderr)
                return []
            
            pids = []
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    # Parse PID from the last column
                    parts = line.strip().split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            pids.append(pid)
                        except (ValueError, IndexError):
                            continue
            
            return pids
            
        except Exception as e:
            logger.warning("Error using netstat to find processes on port %s: %s", port, e)
            return []


class UnixCleaner(PlatformCleaner):
    """Unix/Linux/macOS-specific cleanup operations."""
    
    def cleanup_event_loop(self, loop) -> None:
        """Unix selector event loop cleanup."""
        try:
            # Close the selector to prevent resource leaks
            if hasattr(loop, '_selector') and loop._selector:
                loop._selector.close()
        except Exception as e:
            logger.warning("Error during Unix event loop cleanup: %s", e)
    
    def find_processes_on_port(self, port: int) -> List[int]:
        """Use ss or lsof to find processes on Unix."""
        # Try ss first (more modern)
        pids = self._try_ss(port)
        if pids:
            return pids
        
        # Fallback to lsof
        return self._try_lsof(port)
    
    def _try_ss(self, port: int) -> List[int]:
        """Try using ss command."""
        try:
            cmd = ["ss", "-tulnp"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return []
            
            pids = []
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTEN" in line:
                    # Parse PID from the process info
                    # ss output format: ... users:(("process_name",pid=123,fd=4))
                    if "pid=" in line:
                        try:
                            # Extract PID using string manipulation
                            pid_start = line.find("pid=") + 4
                            pid_end = line.find(",", pid_start)
                            if pid_end == -1:
                                pid_end = line.find(")", pid_start)
                            
                            if pid_end > pid_start:
                                pid = int(line[pid_start:pid_end])
                                pids.append(pid)
                        except (ValueError, IndexError):
                            continue
            
            return pids
            
        except Exception as e:
            logger.debug("ss command failed: %s", e)
            return []
    
    def _try_lsof(self, port: int) -> List[int]:
        """Try using lsof command."""
        try:
            cmd = ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return []
            
            pids = []
            for line in result.stdout.strip().splitlines():
                try:
                    pid = int(line.strip())
                    pids.append(pid)
                except ValueError:
                    continue
            
            return pids
            
        except Exception as e:
            logger.debug("lsof command failed: %s", e)
            return []


# Global instance for easy access
platform_cleaner = PlatformCleaner.get_cleaner()