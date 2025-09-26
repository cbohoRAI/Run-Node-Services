"""Project status enumeration for UI (Phase 3)."""
from __future__ import annotations

from enum import Enum

class ProjectStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    RESTARTING = "restarting"
    UNHEALTHY = "unhealthy"      # Process running but health check fails
    UNRESPONSIVE = "unresponsive" # Health check timing out

STATUS_COLOR = {
    ProjectStatus.STARTING: "yellow",
    ProjectStatus.RUNNING: "green",
    ProjectStatus.STOPPED: "grey50",
    ProjectStatus.CRASHED: "red",
    ProjectStatus.RESTARTING: "magenta",
    ProjectStatus.UNHEALTHY: "orange1",
    ProjectStatus.UNRESPONSIVE: "dark_orange",
}

__all__ = ["ProjectStatus", "STATUS_COLOR"]
