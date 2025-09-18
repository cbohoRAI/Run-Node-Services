"""Project discovery for Node.js projects.

Phase 1 implementation: basic scanning for package.json files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import json
import re
import subprocess

_PORT_ENV_PATTERN = re.compile(r"^PORT\s*=\s*(\d{2,5})\s*$")


@dataclass(slots=True)
class NodeProject:
    """Represents a configured Node.js project.

    Attributes
    ----------
    name: Display name.
    path: Absolute path to the project root.
    port: Optional static port defined by user (overrides .env detection when set).
    git_branch: Current git branch name if repo, else None.
    start_command: Command list to launch the project (default: ["npm", "start"]).
    """
    name: str
    path: Path
    port: Optional[int]
    git_branch: Optional[str]
    start_command: List[str]
    short_name: Optional[str] = None


def _read_package_name(package_file: Path) -> Optional[str]:
    try:
        data = json.loads(package_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _extract_port_from_env(project_path: Path) -> Optional[int]:
    env_file = project_path / ".env"
    if not env_file.is_file():
        return None
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            m = _PORT_ENV_PATTERN.match(line.strip())
            if m:
                try:
                    port = int(m.group(1))
                except ValueError:
                    return None
                if 0 < port < 65536:
                    return port
                return None
    except OSError:
        return None
    return None


def _get_git_branch(project_path: Path) -> Optional[str]:
    git_dir = project_path / ".git"
    if not git_dir.exists():
        return None
    # Lightweight approach (avoid importing gitpython in Phase 1)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch or None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _load_from_config(config_file: Path) -> List[NodeProject]:
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    projects: List[NodeProject] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        path_raw = entry.get("path")
        if not name or not path_raw:
            continue
        path = Path(path_raw).expanduser().resolve()
        # Accept alias keys for short name
        short_name_val = entry.get("short_name") or entry.get("short") or entry.get("alias")
        short_name: Optional[str] = None
        if isinstance(short_name_val, str) and short_name_val.strip():
            short_name = short_name_val.strip()
        port_val = entry.get("port")
        port: Optional[int] = None
        if isinstance(port_val, int) and 0 < port_val < 65536:
            port = port_val
        start_cmd = entry.get("start_command")
        if isinstance(start_cmd, list) and all(isinstance(c, str) for c in start_cmd):
            start_command: List[str] = [c for c in start_cmd if c]
        else:
            start_command = ["npm", "start"]
        git_branch = _get_git_branch(path)
        if port is None:  # fallback to .env extraction
            port = _extract_port_from_env(path)
        projects.append(
            NodeProject(
                name=name,
                path=path,
                port=port,
                git_branch=git_branch,
                start_command=start_command,
                short_name=short_name,
            )
        )
    projects.sort(key=lambda p: p.name.lower())
    return projects


def _scan_fallback(root_dir: Path) -> List[NodeProject]:
    projects: List[NodeProject] = []
    for package_file in root_dir.rglob("package.json"):
        if "node_modules" in package_file.parts:
            continue
        project_path = package_file.parent
        name = _read_package_name(package_file) or project_path.name
        port = _extract_port_from_env(project_path)
        branch = _get_git_branch(project_path)
        projects.append(
            NodeProject(
                name=name,
                path=project_path,
                port=port,
                git_branch=branch,
                start_command=["npm", "start"],
                short_name=None,
            )
        )
    projects.sort(key=lambda p: p.name.lower())
    return projects


def discover_projects(root_dir: Path) -> List[NodeProject]:
    """Discover projects using configuration file if present.

    Order of precedence:
    1. projects.json in root directory (list of project dicts)
    2. projects.txt legacy flat file (name|path|port|command)
    3. Fallback recursive scan (original behaviour)
    """
    root_dir = root_dir.expanduser().resolve()
    if not root_dir.is_dir():
        return []

    config_json = root_dir / "projects.json"
    if config_json.exists():
        loaded = _load_from_config(config_json)
        if loaded:
            return loaded

    # Optional simple text format: name|path|port|command...
    config_txt = root_dir / "projects.txt"
    if config_txt.exists():
        entries: List[NodeProject] = []
        try:
            for raw in config_txt.read_text(encoding="utf-8").splitlines():
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = [p.strip() for p in stripped.split("|")]
                if len(parts) < 2:
                    continue
                name, path_raw = parts[0], parts[1]
                if not name or not path_raw:
                    continue
                path = Path(path_raw).expanduser().resolve()
                port: Optional[int] = None
                if len(parts) >= 3 and parts[2].isdigit():
                    p_int = int(parts[2])
                    if 0 < p_int < 65536:
                        port = p_int
                start_command: List[str] = ["npm", "start"]
                if len(parts) >= 4 and parts[3]:
                    start_command = parts[3].split()
                branch = _get_git_branch(path)
                if port is None:
                    port = _extract_port_from_env(path)
                # short name not supported in txt format for simplicity (could extend with 5th column later)
                entries.append(
                    NodeProject(
                        name=name,
                        path=path,
                        port=port,
                        git_branch=branch,
                        start_command=start_command,
                        short_name=None,
                    )
                )
        except OSError:
            entries = []
        if entries:
            entries.sort(key=lambda p: p.name.lower())
            return entries

    return _scan_fallback(root_dir)


__all__ = ["NodeProject", "discover_projects"]
