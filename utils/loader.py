"""Project configuration loader utility."""

import os
import sys
from typing import List

from models.data import Project


class ProjectLoader:
    """Load projects from a config file."""

    def __init__(self, projects_file: str = "projects.txt"):
        self.projects_file = projects_file

    def ensure_exists_or_example(self) -> None:
        """Create an example config file if it doesn't exist."""
        if os.path.exists(self.projects_file):
            return
        
        example_content = """# Node.js Projects Configuration
# Format: Project Name: /path/to/project
# Lines starting with # are comments

# Example projects (update with your actual paths):
Frontend: /mnt/c/projects/frontend-app
API Server: /mnt/c/projects/api-server
Admin Dashboard: /mnt/c/projects/admin-dashboard
Mobile Backend: /mnt/c/projects/mobile-backend
"""
        with open(self.projects_file, "w") as f:
            f.write(example_content)
        print(f"Created example '{self.projects_file}'. Please edit it and re-run.")
        sys.exit(0)

    def load(self) -> List[Project]:
        """Load and parse projects from the configuration file."""
        self.ensure_exists_or_example()
        projects: List[Project] = []
        
        with open(self.projects_file, "r") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#'):  # Skip blank/comment
                    continue
                
                if ': ' in s:
                    name, path = s.split(': ', 1)
                    name, path = name.strip(), path.strip()
                    
                    if not name or not path:
                        continue
                    
                    # Windows path conversion to WSL style
                    if len(path) >= 2 and path[1] == ':':
                        drive = path[0].lower()
                        rest = path[2:].replace('\\', '/')
                        path = f"/mnt/{drive}{rest}"
                    
                    projects.append(Project(name=name, path=path))
        
        if not projects:
            print(f"No valid projects found in '{self.projects_file}'.")
            sys.exit(1)
        
        return projects