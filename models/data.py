"""Data structures and models for the Node.js Project Runner."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    """Represents a Node.js project configuration."""
    name: str
    path: str


@dataclass
class RunningProject:
    """Represents a currently running project with its runtime information."""
    name: str
    path: str
    pid: Optional[int]
    status: str
    start_time: datetime
    port: Optional[int] = None  # Track the port this project is running on