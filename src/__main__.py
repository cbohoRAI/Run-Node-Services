from __future__ import annotations

from pathlib import Path
import argparse

from src.app import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Node Project Manager (Phase 1)")
    parser.add_argument(
        "root",
        nargs="?",
        default=Path.cwd(),
        type=Path,
        help="Root directory to scan for Node.js projects (default: current directory)",
    )
    args = parser.parse_args()
    run(args.root)


if __name__ == "__main__":  # pragma: no cover
    main()
