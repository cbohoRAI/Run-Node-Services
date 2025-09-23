from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Callable, Optional, TextIO

_FILE_HEADER = "# Streaming log capture\n# Format: ISO-8601(ms) | project | line\n"

def attach_file_sink(log_collector, file_path: str | Path) -> Callable[[], None]:
    """
    Attach a file sink to an existing LogCollector.
    
    Args:
        log_collector: The shared LogCollector instance.
        file_path: Destination log file path (will be created; parent dirs ensured).
    
    Returns:
        detach() function to remove the sink later.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fh: Optional[TextIO] = path.open("a", encoding="utf-8", buffering=1)
    if path.stat().st_size == 0:
        fh.write(_FILE_HEADER)

    def _callback(project: str, line: str) -> None:
        # Keep callback lean; avoid heavy formatting
        try:
            timestamp = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
            # Normalize newlines
            clean = line.rstrip("\n\r")
            fh.write(f"{timestamp} | {project} | {clean}\n")
        except Exception:
            pass  # Silent; this is diagnostic only

    log_collector.register_callback(_callback)

    def detach() -> None:
        try:
            log_collector.unregister_callback(_callback)  # Add this if not present; else ignore
        except Exception:
            pass
        try:
            if fh and not fh.closed:
                fh.flush()
                fh.close()
        except Exception:
            pass

    return detach