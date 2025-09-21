"""Port-based process discovery and process tree termination (Phase 2).

This module provides utility functions for discovering which processes are
listening on a given TCP port and for terminating a process tree reliably
across platforms.

Strategies:
- Primary: use psutil.net_connections() (portable, though may require root for some
  platforms to see all connections). We filter for LISTEN state.
- Fallback: attempt lsof/ss (Unix) or netstat (Windows) if psutil provides
  insufficient data (kept simple for initial Phase 2; can be expanded later).

The goal is to map service identity to its bound port(s) rather than trust the
initial npm wrapper PID.
"""
from __future__ import annotations

from typing import List, Set
import psutil
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

__all__ = ["find_process_by_port", "kill_process_tree"]


def find_process_by_port(port: int) -> List[int]:
    """Return a list of PIDs listening on the given TCP port.

    We first try psutil which is cross-platform. If we get no result, we attempt
    a lightweight platform-specific fallback.
    """
    pids: Set[int] = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port:
                status = getattr(conn, "status", None)
                # Only consider LISTEN / NONE (some platforms omit status)
                if status in (psutil.CONN_LISTEN, None, "LISTEN"):
                    if conn.pid is not None:
                        pids.add(conn.pid)
    except Exception:  # noqa: BLE001
        logger.exception("psutil.net_connections failed")

    if pids:
        return list(pids)

    # Fallbacks (best-effort, minimal parsing) ---------------------------------
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                target = f":{port}"
                for line in result.stdout.splitlines():
                    if target in line and "LISTEN" in line.upper():
                        parts = line.split()
                        if parts:
                            try:
                                pid = int(parts[-1])
                            except ValueError:
                                continue
                            pids.add(pid)
        else:
            # Prefer 'ss' first (user request) then fall back to lsof
            ss_attempted = False
            try:
                ss_attempted = True
                result = subprocess.run(
                    ["ss", "-tulnp"], capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    target = f":{port}"
                    for line in result.stdout.splitlines():
                        if target in line:
                            if "pid=" in line:
                                for seg in line.split():
                                    if "pid=" in seg:
                                        for piece in seg.split(","):
                                            if piece.startswith("pid="):
                                                val = piece[4:].strip().rstrip(")")
                                                try:
                                                    pids.add(int(val))
                                                except ValueError:
                                                    pass
            except FileNotFoundError:
                ss_attempted = False  # not available

            if not pids:  # lsof fallback only if ss absent or produced nothing
                try:
                    result = subprocess.run(
                        ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-Pn", "-F", "p"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    if result.returncode == 0:
                        for token in result.stdout.split("p"):
                            token = token.strip()
                            if not token:
                                continue
                            try:
                                pids.add(int(token))
                            except ValueError:
                                pass
                except FileNotFoundError:
                    # neither ss nor lsof available produced results
                    if ss_attempted:
                        logger.debug("'ss' executed but no listeners found for port %s", port)
                    else:
                        logger.debug("Neither 'ss' nor 'lsof' available for port scan")
    except Exception:  # noqa: BLE001
        logger.exception("Fallback port scan failed")

    return list(pids)


def kill_process_tree(pid: int, timeout: float = 3.0) -> None:
    """Terminate a process and all its children.

    Attempts graceful termination first, then force kill.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    children = parent.children(recursive=True)

    # Terminate children first
    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("Failed to terminate child %s", child.pid)

    try:
        parent.terminate()
    except psutil.NoSuchProcess:
        return
    except Exception:  # noqa: BLE001
        logger.exception("Failed to terminate parent %s", pid)

    gone, alive = psutil.wait_procs(children + [parent], timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("Failed to kill process %s", p.pid)

