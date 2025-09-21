"""Project status enumeration for UI (Phase 3)."""
from __future__ import annotations

from enum import Enum

class ProjectStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    RESTARTING = "restarting"

STATUS_COLOR = {
    ProjectStatus.STARTING: "yellow",
    ProjectStatus.RUNNING: "green",
    ProjectStatus.STOPPED: "grey50",
    ProjectStatus.CRASHED: "red",
    ProjectStatus.RESTARTING: "magenta",
}

__all__ = ["ProjectStatus", "STATUS_COLOR"]
