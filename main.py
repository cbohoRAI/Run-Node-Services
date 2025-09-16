#!/usr/bin/env python3
"""Main entry point for the Textual-based Node.js Project Runner."""

import argparse
from datetime import datetime
from app.runner import NodeProjectRunnerApp


def main():
    """Main entry point for the application."""
    # Log startup to a file
    with open("startup.log", "a") as f:
        f.write(f"Script started at {datetime.now()}\n")
    
    parser = argparse.ArgumentParser(description="Textual-based Node.js Project Runner")
    parser.add_argument(
        "-f", "--file",
        default="projects.txt",
        help="Path to projects configuration file (default: projects.txt)"
    )
    args = parser.parse_args()
    
    app = NodeProjectRunnerApp(projects_file=args.file)
    app.run()


if __name__ == "__main__":
    main()