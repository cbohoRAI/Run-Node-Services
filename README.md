# Node Manager - Terminal-Based Node.js Project Manager

## Project Overview

A Python-based terminal UI application for managing multiple Node.js projects simultaneously. The app provides an interactive interface to start, stop, and monitor Node projects with real-time log viewing and process management.

## Core Features

### 1. Interactive Project Selection
- Display discovered Node projects with details (name, port, git branch)
- Multi-select interface using checkboxes
- No CLI arguments - launch directly into interactive mode

### 2. Process Monitoring Dashboard
- Real-time status of running projects
- Collapsible panel to maximize log viewing space
- Visual indicators for process states (running, stopped, crashed, restarting)
- Port and git branch information display

### 3. Tabbed Log Viewer
- Combined log view showing all projects with color-coded prefixes
- Individual project log tabs
- Keyboard navigation between tabs (Tab key, number keys 1-9)
- Scrollable log history with configurable buffer size

### 4. Robust Process Management
- Graceful shutdown handling
- Port-based process discovery (handles npm/node PID chain issues)
- Cross-platform support (Windows, Linux, macOS)
- Clean cleanup on application exit

## Technical Stack

- **Python 3.8+** - Core language
- **Textual** - Terminal UI framework
- **asyncio** - Asynchronous process management
- **psutil** - Cross-platform process monitoring
- **Rich** - Terminal formatting and colors
- **Pydantic** - Configuration validation
- **TOML/JSON** - Configuration files

## Project Configuration (Config-Driven Discovery)

Phase 1 now supports explicit, configuration-based project discovery. Instead of (or before) recursively scanning for every `package.json`, the application will load user-defined project entries if a configuration file is present in the root directory you launch the app against.

Discovery precedence (first match wins):
1. `projects.json`
2. `projects.txt` (legacy/simple format)
3. Recursive scan fallback (original behavior)

### 1. `projects.json` Format (Recommended)
Provide an array of project objects:

```jsonc
[
    {
        "name": "api-service",              // Required: display name
        "path": "~/dev/api-service",       // Required: absolute or ~ path to project root
        "port": 4000,                       // Optional: overrides .env PORT if present
        "start_command": ["npm", "run", "dev"] // Optional: defaults to ["npm", "start"]
    },
    {
        "name": "frontend",
        "path": "/work/apps/frontend",
        "start_command": ["npm", "start"]
    }
]
```

Field rules:
- `name` (string, required): Unique label shown in the UI
- `short_name` / `short` / `alias` (string, optional): Shorthand displayed in parentheses after the full name (e.g. `very-long-service (svc)`)
- `path` (string, required): Directory containing the Node project
- `port` (int, optional): 1–65535; if omitted, the tool attempts `.env` extraction
- `start_command` (list[str], optional): Exact argv executed; if omitted uses `npm start`

Git branch is still auto-detected if the path is a git repository. If `port` is not supplied and `.env` has `PORT=XXXX`, that value is used.

### 2. `projects.txt` Format (Simple Alternative)
Each non-empty, non-comment line:

```
# name | path | port | command
api-service | ~/dev/api-service | 4000 | npm run dev
frontend | /work/apps/frontend |  | npm start
```

Parsing rules:
- Separator: `|`
- Minimum fields: `name|path`
- Empty or non-integer port field is ignored (falls back to `.env` / none)
- Command field is split on whitespace into an argument list; defaults to `npm start`

### 3. Fallback Recursive Scan
If neither config file exists or they contain no valid entries, the original scan walks all subdirectories for `package.json` (skipping any `node_modules` paths).

### Why Config-Driven?
Explicit configuration offers:
- Faster startup for large monorepos
- Ability to customize start commands per project
- Stable ordering independent of filesystem layout
- Clear, versionable source of truth committed to your repo or shared among team members

### Migration From Scanning
1. Create a `projects.json` at the root you pass to the app.
2. Add project objects as shown above.
3. Launch the tool; only listed projects will appear.
4. Remove `projects.json` (or rename) to revert to scan mode.

> Tip: Keep a `projects.example.json` checked in and add `projects.json` to `.gitignore` if paths are user-specific.

## Phase 2 Progress (In Repository)

Initial components of Phase 2 have been implemented:

1. Port-Based Process Discovery:
    - Added `src/core/port_scanner.py` with `find_process_by_port` and `kill_process_tree` utilities.
    - Uses `psutil` primarily with lightweight fallbacks (`lsof`/`ss` on Unix, `netstat` on Windows) when needed.

2. Enhanced Process Manager:
    - `ProcessManager` now records the wrapper spawn PID and (optionally) the real listener PIDs discovered via the project port.
    - Supports `restart_project(name)` which performs stop + start with port remapping.
    - Graceful shutdown attempts followed by forced termination of process trees bound to the port.

3. Signal Handling:
    - `src/core/signal_handler.py` provides coordinated shutdown on SIGINT/SIGTERM (and SIGBREAK on Windows) to avoid orphaned processes.

4. Tests Added:
    - `tests/test_port_scanner.py` validates port discovery and process tree termination.
    - Updated `tests/test_process_manager.py` to cover port-aware start/stop and restart flows.

5. Backward Compatibility:
    - Existing calls to `start_project(name, path, ...)` still work; callers can supply a `port` arg to enable full Phase 2 tracking.

Upcoming (not yet implemented in repo):
    - Automatic periodic reconciliation of listener PIDs
    - Health monitoring loop & auto-restart policies
    - More detailed status states (CRASHED, RESTARTING) surfaced to UI layer

---

## Phase 3 Progress (Initial Implementation)

Implemented foundational monitoring UI components:

1. New Monitoring Screen (`screens/monitoring.py`):
    - Displays a collapsible running projects panel and a tabbed log viewer.
    - Keyboard shortcuts: `p` toggle panel, `r` restart selected (currently all), `R` restart all, `s` stop all, `tab` cycle tabs, `1-9` quick tab switch (1 = All Logs).

2. Log Collection (`core/log_collector.py`):
    - Async ring buffer per project with timestamped entries and callback hook into UI.

3. Widgets:
    - `widgets/running_panel.py` shows status, port, branch placeholders.
    - `widgets/log_viewer.py` simple tabbed content with an aggregate “All Logs” pane.
    - `widgets/project_controls.py` (scaffolding for per‑project buttons; not yet wired into panel).

4. Selection → Monitoring Transition:
    - After starting selected projects on the selection screen, app switches automatically to monitoring screen.

5. Status Model:
    - `models/status.py` defines `ProjectStatus` enum with basic color mapping.

Limitations / Next Steps:
    - Per-project restart/stop buttons not yet embedded in running panel rows.
    - Project ports/branches not fed live (needs integration with discovery metadata and manager mapping).
    - No crash detection or dynamic status changes yet (will come with health monitoring in later phases).
    - Log level coloring / search / filtering pending Phase 4 work.

---


## Project Structure

```
node-manager/
├── src/
│   ├── __main__.py           # Entry point
│   ├── app.py                # Main Textual application
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── selection.py      # Project selection screen
│   │   └── monitoring.py     # Main monitoring screen
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── project_list.py   # Project selection list widget
│   │   ├── running_panel.py  # Collapsible running projects panel
│   │   └── log_viewer.py     # Tabbed log viewer widget
│   ├── core/
│   │   ├── __init__.py
│   │   ├── process_manager.py # Process spawning and management
│   │   ├── port_scanner.py    # Port-based process discovery
│   │   ├── log_collector.py   # Async log collection
│   │   └── project_discovery.py # Find Node projects
│   ├── models/
│   │   ├── __init__.py
│   │   ├── project.py        # Project dataclass
│   │   └── config.py         # Configuration models
│   └── utils/
│       ├── __init__.py
│       ├── platform.py       # OS-specific implementations
│       └── git.py            # Git branch detection
├── config/
│   └── settings.toml         # Default configuration
├── tests/
│   └── ...
├── requirements.txt
├── pyproject.toml
└── README.md
```

## UI/UX Design Mockups

### Initial State - Project Selection Screen
When the user first runs the application, they see a clean project selection interface:

```
┌─────────────────────────────────────────────────────┐
│  Node Project Manager - Select Projects             │
├─────────────────────────────────────────────────────┤
│                                                      │
│  [ ] my-api-server         :3000    main           │
│  [ ] frontend-app          :3001    develop        │
│  [x] auth-service         :4000    feature/auth   │
│  [x] worker-queue         :5000    main           │
│  [ ] admin-dashboard      :5001    staging        │
│                                                      │
│  ──────────────────────────────────────────────    │
│  Space: Toggle  Enter: Start Selected  Q: Quit      │
└─────────────────────────────────────────────────────┘
```

### Running State - Monitoring Screen (Panel Expanded)
After starting projects, the UI switches to the monitoring screen:

```
┌─────────────────────────────────────────────────────┐
│  Running Projects                              [─]  │
├─────────────────────────────────────────────────────┤
│  auth-service    ● Running  :4000  feature/auth    │
│  worker-queue    ● Running  :5000  main            │
├─────────────────────────────────────────────────────┤
│ [All Logs] │ auth-service │ worker-queue │         │
├─────────────────────────────────────────────────────┤
│ [auth-service] Server started on port 4000         │
│ [worker-queue] Connected to Redis                  │
│ [auth-service] Watching for file changes...        │
│ [worker-queue] Processing job #1234                │
│ [auth-service] GET /api/auth/login 200 45ms       │
│ [worker-queue] Job #1234 completed                 │
│ [auth-service] POST /api/users 201 123ms          │
│                                                     │
├─────────────────────────────────────────────────────┤
│ Tab/1-9: Switch Logs  S: Stop All  R: Restart  Q: Quit │
└─────────────────────────────────────────────────────┘
```

### Running State - Monitoring Screen (Panel Collapsed)
User can collapse the panel for more log viewing space:

```
┌─────────────────────────────────────────────────────┐
│  Running Projects (2 active)                   [+]  │
├─────────────────────────────────────────────────────┤
│ [All Logs] │ auth-service │ worker-queue │         │
├─────────────────────────────────────────────────────┤
│ [auth-service] Server started on port 4000         │
│ [worker-queue] Connected to Redis                  │
│ [auth-service] Watching for file changes...        │
│ [worker-queue] Processing job #1234                │
│ [auth-service] GET /api/auth/login 200 45ms       │
│ [worker-queue] Job #1234 completed                 │
│ [auth-service] POST /api/users 201 123ms          │
│ [worker-queue] New job received #1235              │
│ [auth-service] WebSocket client connected          │
│ [worker-queue] Processing job #1235                │
│ [auth-service] Database query executed (23ms)      │
│                                                     │
├─────────────────────────────────────────────────────┤
│ P: Toggle Panel  Tab: Switch Logs  S: Stop  Q: Quit │
└─────────────────────────────────────────────────────┤
```

### Error States Display
When projects crash or have issues:

```
┌─────────────────────────────────────────────────────┐
│  Running Projects                              [─]  │
├─────────────────────────────────────────────────────┤
│  auth-service    ✖ Crashed  :4000  feature/auth   │
│  worker-queue    ◆ Restarting  :5000  main        │
│  frontend-app    ● Running  :3001  develop        │
├─────────────────────────────────────────────────────┤
│ [All Logs] │ ! auth-service │ worker-queue │ frontend │
├─────────────────────────────────────────────────────┤
│ [auth-service] ERROR: Connection refused           │
│ [auth-service] Process exited with code 1          │
│ [worker-queue] Attempting restart (attempt 2/5)    │
│ [frontend-app] Compiled successfully               │
└─────────────────────────────────────────────────────┘
```

### Running State with Restart Controls
```
┌─────────────────────────────────────────────────────┐
│  Running Projects                              [─]  │
├─────────────────────────────────────────────────────┤
│  auth-service    ● Running  :4000  feature/auth  [↻][■] │
│  worker-queue    ◆ Restarting  :5000  main       [↻][■] │
├─────────────────────────────────────────────────────┤
│ [All Logs] │ auth-service │ worker-queue │         │
├─────────────────────────────────────────────────────┤
│ [auth-service] Server shutting down...             │
│ [auth-service] Process terminated                  │
│ [auth-service] Starting server...                  │
│ [auth-service] Server started on port 4000         │
└─────────────────────────────────────────────────────┤
```

## Implementation Phases

### Phase 1: Core Foundation (MVP)
**Goal:** Create the basic infrastructure for discovering and launching Node.js projects with a simple terminal interface.

**What we'll build:**
- Project discovery system that scans directories for package.json files
- Basic process spawning using Python's asyncio subprocess
- Simple terminal UI showing a list of discovered projects
- Ability to start a single project and see its output
- Cross-platform command execution (npm on Windows vs Unix)

**Detailed Steps:**

#### Step 1.1: Project Discovery Implementation
- Recursively scan specified directories for Node.js projects
- Parse package.json files to extract project metadata
- Detect port numbers from .env files (PORT=xxxx format)
- Extract git branch information for each project
- Filter out node_modules directories and other irrelevant paths
- Cache discovered projects for faster subsequent launches

```python
# src/core/project_discovery.py
import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class NodeProject:
    name: str
    path: Path
    port: int
    start_command: str
    git_branch: Optional[str]
    
def extract_port_from_env(project_path: Path) -> Optional[int]:
    """Extract PORT variable from .env file"""
    env_file = project_path / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                match = re.match(r'^\s*PORT\s*=\s*(\d+)', line)
                if match:
                    return int(match.group(1))
    return None

def get_git_branch(project_path: Path) -> Optional[str]:
    """Get current git branch for project"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None
    
def discover_projects(root_dir: Path) -> List[NodeProject]:
    """Scan directory tree for Node.js projects"""
    projects = []
    for package_json in root_dir.rglob("package.json"):
        if "node_modules" in package_json.parts:
            continue
            
        with open(package_json) as f:
            data = json.load(f)
        
        project_path = package_json.parent
        
        # Try to get port from .env file, fallback to default
        port = extract_port_from_env(project_path) or 3000
        
        project = NodeProject(
            name=data.get("name", project_path.name),
            path=project_path,
            port=port,
            start_command=data.get("scripts", {}).get("start", "node index.js"),
            git_branch=get_git_branch(project_path)
        )
        projects.append(project)
    
    return projects
```

#### Step 1.2: Basic Process Management Implementation
- Create ProcessManager class to handle subprocess lifecycle
- Implement platform-specific command execution (Windows cmd vs Unix shell)
- Track spawned processes (even though PIDs won't be accurate yet)
- Basic start/stop functionality
- Simple output capture to verify processes are running
```python
# src/core/process_manager.py
import asyncio
import sys
from typing import Dict, Optional

class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        
    async def start_project(self, project: NodeProject):
        """Start a Node.js project"""
        # Platform-specific command
        if sys.platform == "win32":
            cmd = ["cmd", "/c", "npm", "start"]
        else:
            cmd = ["npm", "start"]
            
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project.path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=asyncio.subprocess.CREATE_NEW_PROCESS_GROUP 
                if sys.platform == "win32" else 0
        )
        
        self.processes[project.name] = process
        return process
```

#### Step 1.3: Simple Terminal UI Implementation
- Build a basic Textual application with a single screen
- Display discovered projects in a selectable list
- Show project name, port, and path for each project  
- Implement keyboard navigation (arrow keys to move, space to select)
- Add a footer showing available commands
- Handle the Enter key to start selected projects

```python
# src/screens/selection.py
from textual.app import Screen
from textual.widgets import DataTable, Footer

class ProjectSelectionScreen(Screen):
    def compose(self):
        table = DataTable()
        table.add_columns("Select", "Project", "Port", "Path")
        
        for project in self.discovered_projects:
            table.add_row("[ ]", project.name, str(project.port), str(project.path))
            
        yield table
        yield Footer()
```

**Deliverables for Phase 1:**
- Working project discovery that finds all Node projects in a directory
- Ability to start a Node project and see its output in the terminal
- Basic UI that shows available projects and allows selection
- Cross-platform support for Windows and Unix systems

---

### Phase 2: Port-Based Process Management
**Goal:** Implement robust process tracking using ports as the source of truth, solving the PID chain problem we identified.

**What we'll build:**
- Port scanning system to find actual Node.js processes
- Process discovery that handles the npm → shell → node chain
- Reliable process termination that kills all related processes
- Cross-platform implementation for Windows and Unix
- Signal handling for graceful shutdown
- Fallback mechanisms when primary methods fail

#### Step 2.1: Port Scanner Implementation Details
- Implement Windows port scanning using netstat command
- Implement Unix port scanning using lsof, with fallback to ss
- Use psutil as a cross-platform fallback option
- Create unified interface that works on all platforms
- Cache port scan results to avoid excessive system calls
- Handle permission issues gracefully (some commands need elevated privileges)
```python
# src/core/port_scanner.py
import psutil
import subprocess
import sys
from typing import List, Optional

def find_process_by_port(port: int) -> List[int]:
    """Find all PIDs using a specific port"""
    pids = []
    
    if sys.platform == "win32":
        # Windows: Use netstat
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True
        )
        for line in result.stdout.split('\n'):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        pids.append(int(parts[-1]))
                    except ValueError:
                        pass
    else:
        # Unix: Use lsof or ss
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.stdout:
                pids = [int(pid) for pid in result.stdout.strip().split('\n')]
        except FileNotFoundError:
            # Fallback to ss
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.pid:
                    pids.append(conn.pid)
    
    return pids

def kill_process_tree(pid: int):
    """Kill a process and all its children"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # Terminate children first
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        
        # Then parent
        parent.terminate()
        
        # Wait and force kill if needed
        gone, alive = psutil.wait_procs(children + [parent], timeout=3)
        for p in alive:
            p.kill()
            
    except psutil.NoSuchProcess:
        pass
```

#### Step 2.2: Process Tree Management

- Implement process tree discovery (finding all child processes)
- Create kill_process_tree function that terminates parent and all children
- Handle zombie processes and process groups
- Implement graceful shutdown with SIGTERM, followed by SIGKILL if needed
- Add timeout mechanisms for stubborn processes

#### Step 2.3: Enhanced Process Manager with Port Tracking

- Refactor ProcessManager to use ports as primary identifier
- Implement "wait for port" functionality after starting a process
- Map ports to projects for reliable tracking
- Store both spawn PIDs and actual service PIDs
- Add retry logic for finding processes that take time to bind to ports
```python
# src/core/process_manager.py (updated)
class EnhancedProcessManager:
    def __init__(self):
        self.processes = {}
        self.port_mapping = {}  # port -> project_name
        
    async def start_project(self, project):
        # Start the process
        process = await self._spawn_process(project)
        
        # Wait for port to become active
        await self._wait_for_port(project.port, timeout=10)
        
        # Find actual PIDs on the port
        actual_pids = find_process_by_port(project.port)
        
        self.processes[project.name] = {
            'spawn_process': process,
            'actual_pids': actual_pids,
            'port': project.port
        }
        self.port_mapping[project.port] = project.name
        
    async def stop_project(self, project_name):
        if project_name not in self.processes:
            return
            
        info = self.processes[project_name]
        
        # Try graceful shutdown of spawn process
        if info['spawn_process'].returncode is None:
            info['spawn_process'].terminate()
        
        # Kill all processes on the port
        for pid in find_process_by_port(info['port']):
            kill_process_tree(pid)
        
        del self.processes[project_name]
        del self.port_mapping[info['port']]
    
    async def restart_project(self, project_name: str, graceful_timeout: int = 5):
        """Restart a specific project with proper cleanup"""
        if project_name not in self.processes:
            raise ValueError(f"Project {project_name} is not running")
        
        project_config = self.get_project_config(project_name)
        
        # Update status to restarting
        await self.notify_status_change(project_name, ProjectStatus.RESTARTING)
        
        try:
            # Step 1: Gracefully stop the project
            await self.stop_project(project_name, timeout=graceful_timeout)
            
            # Step 2: Wait for port to be released
            await asyncio.sleep(1)
            
            # Step 3: Start the project again
            await self.start_project(project_config)
            
            # Track restart count
            if project_name not in self.restart_counts:
                self.restart_counts[project_name] = 0
            self.restart_counts[project_name] += 1
            
            await self.notify_status_change(project_name, ProjectStatus.RUNNING)
            
        except Exception as e:
            await self.notify_status_change(project_name, ProjectStatus.CRASHED)
            raise Exception(f"Failed to restart {project_name}: {e}")
```

#### Step 2.4: Signal Handling Implementation

- Register signal handlers for graceful shutdown
- Handle Ctrl+C (SIGINT) to stop all projects before exiting
- Implement cleanup on SIGTERM for system shutdowns
- Ensure all child processes are terminated on app exit
- Save application state before emergency shutdown

```py
# src/core/signal_handler.py
import signal
import asyncio
import sys

class SignalHandler:
    def __init__(self, app):
        self.app = app
        self.shutdown_in_progress = False
        
    def register_handlers(self):
        """Register signal handlers for graceful shutdown"""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)
            
        # Windows-specific signal handling
        if sys.platform == "win32":
            signal.signal(signal.SIGBREAK, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        if self.shutdown_in_progress:
            return  # Prevent multiple shutdown attempts
            
        self.shutdown_in_progress = True
        
        # Schedule graceful shutdown
        asyncio.create_task(self._graceful_shutdown())
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown"""
        try:
            # Notify user
            self.app.notify("Shutting down all processes...")
            
            # Stop all running projects
            await self.app.process_manager.stop_all()
            
            # Save state
            self.app.save_state()
            
            # Exit app
            self.app.exit()
        except Exception as e:
            # Emergency exit
            sys.exit(1)
```

### Deliverables for Phase 2:

- Reliable process discovery that finds the actual Node.js processes
- Cross-platform port scanning that works on Windows, Mac, and Linux
- Robust cleanup that ensures no orphaned processes
- Signal handling for graceful shutdown
- Improved reliability when dealing with complex Node.js toolchains (nodemon, ts-node, etc.)

### Phase 3: Enhanced UI and Monitoring
**Goal:** Implement the dual-screen interface with the collapsible running projects panel and tabbed log viewer as designed in our mockups.

**What we'll build:**
- Screen transition from project selection to monitoring view
- Collapsible panel showing running project status
- Tabbed interface for viewing logs (All Logs + individual project tabs)
- Color-coded log output for better readability
- Real-time status indicators (running, stopped, crashed)
- Log streaming architecture with proper backpressure handling

#### Step 3.1: Collapsible Running Panel Implementation
- Create a custom Textual widget that can expand and collapse
- Show full project details when expanded (name, status, port, git branch)
- Show summary when collapsed (number of active projects)
- Animate the collapse/expand transition smoothly
- Save collapse state to user preferences
- Implement keyboard shortcut (P key) to toggle panel

```python
# src/widgets/running_panel.py
from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive

class CollapsibleRunningPanel(Vertical):
    is_collapsed = reactive(False)
    
    def compose(self):
        with Horizontal(id="panel-header"):
            yield Static(self.get_title())
            yield Button("[−]" if not self.is_collapsed else "[+]")
        
        if not self.is_collapsed:
            yield Vertical(id="panel-content")
    
    def toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        self.refresh(recompose=True)
```

#### Step 3.2: Tabbed Log Viewer Implementation

- Build custom tabbed container for log views
- Implement "All Logs" tab that shows interleaved output from all projects
- Create individual tabs for each running project
- Add project name prefixes with unique colors in the combined view
- Support keyboard navigation (Tab key, number keys 1-9 for quick switching)
- Implement scrollable log buffer with configurable history size
- Add log level detection and color coding (errors in red, warnings in yellow)

```py
# src/widgets/log_viewer.py
from textual.widgets import TabbedContent, Tab, RichLog
from collections import deque

class TabbedLogViewer(TabbedContent):
    def __init__(self):
        super().__init__()
        self.log_buffers = {}  # project_name -> deque
        self.add_tab(Tab("All Logs", id="all"))
    
    def add_project_tab(self, project_name: str):
        self.log_buffers[project_name] = deque(maxlen=1000)
        self.add_tab(Tab(project_name, id=project_name))
    
    def append_log(self, project_name: str, line: str):
        # Add to project buffer
        if project_name in self.log_buffers:
            self.log_buffers[project_name].append(line)
        
        # Add to "All Logs" with color coding
        all_logs = self.get_tab("all").get_child()
        all_logs.write(f"[{project_name}] {line}")
```

#### Step 3.3: Log Streaming Architecture

- Connect subprocess stdout/stderr pipes to async readers
- Implement task manager to coordinate multiple log collection tasks
- Handle backpressure when logs arrive faster than UI can display
- Process incomplete UTF-8 sequences and binary output gracefully
- Manage concurrent log streams without blocking

```py
# src/core/log_stream_manager.py
import asyncio
from typing import Dict, Set
import codecs

class LogStreamManager:
    def __init__(self, log_collector):
        self.log_collector = log_collector
        self.active_tasks: Dict[str, Set[asyncio.Task]] = {}
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        
    async def start_log_stream(self, project_name: str, process):
        """Start streaming logs from a process"""
        if project_name not in self.active_tasks:
            self.active_tasks[project_name] = set()
        
        # Create tasks for stdout and stderr
        stdout_task = asyncio.create_task(
            self._stream_output(project_name, process.stdout, 'stdout')
        )
        stderr_task = asyncio.create_task(
            self._stream_output(project_name, process.stderr, 'stderr')
        )
        
        self.active_tasks[project_name].add(stdout_task)
        self.active_tasks[project_name].add(stderr_task)
        
    async def _stream_output(self, project_name: str, stream, stream_type: str):
        """Stream output with backpressure handling"""
        buffer = b''
        
        try:
            while True:
                # Read chunk with timeout to prevent blocking
                try:
                    chunk = await asyncio.wait_for(
                        stream.read(4096), 
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue
                    
                if not chunk:
                    break  # Stream closed
                
                buffer += chunk
                
                # Process complete lines
                lines = buffer.split(b'\n')
                buffer = lines[-1]  # Keep incomplete line in buffer
                
                for line_bytes in lines[:-1]:
                    # Handle encoding properly
                    try:
                        line = line_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        # Use incremental decoder for broken UTF-8
                        line = self.decoder.decode(line_bytes, False)
                    
                    await self.log_collector.add_log(
                        project_name, 
                        line, 
                        stream_type
                    )
                    
                    # Implement backpressure
                    if self.log_collector.is_buffer_full(project_name):
                        await asyncio.sleep(0.01)  # Small delay
                        
        except Exception as e:
            await self.log_collector.add_log(
                project_name,
                f"Stream error: {e}",
                'error'
            )
        finally:
            # Clean up task reference
            if project_name in self.active_tasks:
                self.active_tasks[project_name].discard(asyncio.current_task())
    
    async def stop_log_stream(self, project_name: str):
        """Stop all log streaming tasks for a project"""
        if project_name in self.active_tasks:
            for task in self.active_tasks[project_name]:
                task.cancel()
            
            # Wait for tasks to complete
            await asyncio.gather(
                *self.active_tasks[project_name], 
                return_exceptions=True
            )
            
            del self.active_tasks[project_name]
```

#### Step 3.4: Screen Transition System
- Implement smooth transition from selection screen to monitoring screen
- Pass selected projects data between screens
- Start processes during transition with progress indicator
- Handle startup failures gracefully
- Show loading state while projects initialize

#### Step 3.5: Individual Project Controls and Selective Restart
- Add restart buttons for each running project in the UI
- Implement keyboard shortcuts for quick restart (R key)
- Handle graceful restart with proper port release timing
- Show restart status in the UI (◆ Restarting indicator)
- Limit consecutive restart attempts to prevent loops
- Support batch restart for multiple selected projects

```python
# src/widgets/project_controls.py
from textual.widgets import Button
from textual.containers import Horizontal
from textual.message import Message

class ProjectRestartRequest(Message):
    """Message sent when user requests project restart"""
    def __init__(self, project_name: str):
        self.project_name = project_name
        super().__init__()

class ProjectControls(Horizontal):
    """Individual project control buttons in the running panel"""
    
    def __init__(self, project_name: str):
        super().__init__()
        self.project_name = project_name
        
    def compose(self):
        yield Button("↻", id=f"restart-{self.project_name}", variant="warning")
        yield Button("■", id=f"stop-{self.project_name}", variant="error")
        
    def on_button_pressed(self, event):
        button_id = event.button.id
        if button_id.startswith("restart-"):
            self.post_message(ProjectRestartRequest(self.project_name))
```

### Updated Keyboard Shortcuts:

- R: Restart selected/highlighted project
- Shift+R: Restart all running projects
- S: Stop selected projects
- P: Toggle panel collapse
- Tab/1-9: Switch between log tabs
- Q: Quit application (with confirmation if projects running)

### Deliverables for Phase 3:

- Fully functional dual-screen interface matching our mockups
- Collapsible panel that remembers user preference
- Tabbed log viewer with color-coded output
- Robust log streaming with proper encoding and backpressure handling
- Real-time status monitoring with visual indicators
- Individual project restart controls
- Smooth user experience with keyboard navigation

---

### Phase 4: Log Collection and Optimization
**Goal:** Build an efficient async log collection system that can handle high-throughput logging from multiple projects without impacting UI performance.

**What we'll build:**
- Async log collectors for each project's stdout/stderr
- Ring buffers to limit memory usage
- Rate limiting for UI updates
- Log parsing for better formatting
- Search and filter capabilities

#### Step 4.1: Async Log Collector Implementation
- Create LogCollector class with async stream reading
- Implement non-blocking readline operations
- Handle different character encodings gracefully
- Parse ANSI color codes from terminal output
- Detect and tag error messages for special handling
- Buffer management with configurable limits per project

```python
# src/core/log_collector.py
import asyncio
from collections import deque
from datetime import datetime
from typing import Callable

class LogCollector:
    def __init__(self, max_lines_per_project=1000):
        self.max_lines = max_lines_per_project
        self.buffers = {}
        self.callbacks = []
        
    def add_callback(self, callback: Callable):
        """Register callback for new log lines"""
        self.callbacks.append(callback)
    
    async def collect_output(self, project_name: str, stream):
        """Collect output from a process stream"""
        if project_name not in self.buffers:
            self.buffers[project_name] = deque(maxlen=self.max_lines)
            
        async for line in stream:
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            
            line = line.rstrip()
            entry = {
                'timestamp': datetime.now(),
                'project': project_name,
                'content': line
            }
            
            self.buffers[project_name].append(entry)
            
            # Notify callbacks
            for callback in self.callbacks:
                await callback(entry)
```

#### Step 4.2: UI Update Rate Limiting
- Implement batching system that groups multiple log updates
- Set maximum UI refresh rate (e.g., 30 FPS)
- Queue updates when they come in faster than the refresh rate
- Use Textual's set_interval for periodic updates instead of per-line updates
- Measure and optimize render performance

#### Step 4.3: Log Parsing and Enhancement
- Strip ANSI escape codes for cleaner display
- Detect log levels (ERROR, WARN, INFO, DEBUG) and apply colors
- Parse JSON logs from structured loggers
- Extract and highlight HTTP status codes and response times
- Add timestamp formatting options

#### Step 4.4: Search and Filter Implementation
- Add search functionality with regex support
- Implement filters by log level, project, or time range
- Highlight search matches in the log view
- Add "follow mode" toggle to auto-scroll to new logs
- Clear log buffer command for individual projects

**Deliverables for Phase 4:**
- Smooth, lag-free log viewing even with high output rates
- Memory-efficient buffering system
- Search and filter capabilities
- Better log formatting and highlighting
- Performance metrics showing throughput and resource usage

---

### Phase 5: Configuration and Persistence
**Goal:** Add user customization options and persist settings between sessions.

**What we'll build:**
- Configuration file system for app settings
- Per-project configuration overrides
- User preferences (theme, panel state, buffer sizes)
- Project bookmarks and groups
- Command history and recent projects
```python
# src/utils/optimization.py
import asyncio
from functools import lru_cache
from typing import Dict, Any

class RateLimiter:
    """Limit UI update frequency"""
    def __init__(self, max_per_second=30):
        self.max_per_second = max_per_second
        self.last_update = 0
        self.pending_updates = {}
        
    async def update(self, key: str, data: Any):
        current_time = asyncio.get_event_loop().time()
        
        if current_time - self.last_update < 1.0 / self.max_per_second:
            # Queue the update
            self.pending_updates[key] = data
            return
            
        # Perform update
        self.last_update = current_time
        await self._do_update(key, data)
        
        # Flush pending updates
        if self.pending_updates:
            for k, v in self.pending_updates.items():
                await self._do_update(k, v)
            self.pending_updates.clear()

@lru_cache(maxsize=128)
def parse_ansi_codes(text: str) -> str:
    """Cache parsed ANSI code results"""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)
```

### Phase 5: Configuration and Persistence
**Goal:** User preferences and project configurations

#### Step 5.1: Configuration System
```python
# src/models/config.py
from pydantic import BaseModel
from pathlib import Path
from typing import List, Optional

class ProjectConfig(BaseModel):
    name: str
    path: Path
    port: int
    start_command: str = "npm start"
    env_vars: dict = {}
    auto_restart: bool = False
    
class AppConfig(BaseModel):
    projects_dir: Path = Path.home() / "projects"
    auto_discover: bool = True
    max_log_lines: int = 1000
    theme: str = "dark"
    panel_collapsed: bool = False
    
    class Config:
        json_encoders = {Path: str}

class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".nodemanager"
        self.config_file = self.config_dir / "config.toml"
        
    def load(self) -> AppConfig:
        if self.config_file.exists():
            import toml
            data = toml.load(self.config_file)
            return AppConfig(**data)
        return AppConfig()
    
    def save(self, config: AppConfig):
        self.config_dir.mkdir(exist_ok=True)
        import toml
        with open(self.config_file, 'w') as f:
            toml.dump(config.dict(), f)
```

### Phase 6: Advanced Features
**Goal:** Production-ready enhancements

#### Step 6.1: Git Integration Implementation
- Detect current git branch for each project

#### Step 6.2: Performance Metrics Dashboard
- Real-time CPU and memory usage per project
- Network I/O statistics
- Request/response metrics from log parsing
- Historical graphs using sparklines in terminal
- Export metrics to CSV for analysis
- Resource usage alerts and thresholds

#### Step 6.3: Advanced Debugging Tools
- Attach debugger to running Node processes
- Environment variable editor
- Port forwarding configuration
- Log export with filtering
- Process heap dumps and profiling
- Integration with Chrome DevTools for Node.js debugging

**Deliverables for Phase 6:**
- Complete health monitoring system with auto-restart
- Git integration showing project status
- Performance metrics and resource monitoring
- Advanced debugging capabilities
- Production-ready reliability features

---

## Performance Optimization Strategies

### 1. Efficient Log Handling
```python
# Circular buffer with fixed size
from collections import deque

class OptimizedLogBuffer:
    def __init__(self, max_size=1000, max_line_length=500):
        self.buffer = deque(maxlen=max_size)
        self.max_line_length = max_line_length
    
    def add(self, line: str):
        # Truncate long lines to prevent memory bloat
        if len(line) > self.max_line_length:
            line = line[:self.max_line_length] + "..."
        self.buffer.append(line)
```

### 2. Batch UI Updates
```python
class BatchedUIUpdater:
    def __init__(self, update_interval=0.1):  # 10 FPS
        self.update_interval = update_interval
        self.pending_updates = []
        self.last_update = 0
    
    async def add_update(self, update):
        self.pending_updates.append(update)
        
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_update >= self.update_interval:
            await self.flush()
    
    async def flush(self):
        if self.pending_updates:
            # Batch all pending updates into one UI refresh
            await self.ui.batch_update(self.pending_updates)
            self.pending_updates.clear()
            self.last_update = asyncio.get_event_loop().time()
```

### 3. Async Everything
- All I/O operations should be async (file reads, process communication, network requests)
- Use asyncio.gather() for parallel operations
- Implement connection pooling for health checks
- Non-blocking subprocess communication

### 4. Resource Management
```python
# Resource limits configuration
class ResourceLimits:
    MAX_LOG_LINES_PER_PROJECT = 1000
    MAX_LOG_LINE_LENGTH = 500
    UI_UPDATE_RATE = 10  # Hz
    HEALTH_CHECK_INTERVAL = 5  # seconds
    PROCESS_STAT_CACHE_TIME = 1  # second
    MAX_CONCURRENT_STARTS = 5  # Limit simultaneous project starts
    LOG_ROTATION_SIZE = 10000  # Lines before rotation
```

### 5. Lazy Loading and Virtualization
- Load log content only when tab is actively viewed
- Virtualize long lists (only render visible items)
- Defer expensive operations until needed
- Cache frequently accessed data

### 6. Memory Optimization
```python
import gc

class MemoryOptimizer:
    @staticmethod
    def cleanup_old_logs(log_buffers, inactive_threshold=300):
        """Clean up logs from inactive projects"""
        current_time = time.time()
        for project_name, buffer in list(log_buffers.items()):
            if buffer.last_access < current_time - inactive_threshold:
                # Project inactive for 5 minutes, reduce buffer
                buffer.reduce_size(100)  # Keep only last 100 lines
        
        # Force garbage collection if memory usage is high
        if psutil.Process().memory_percent() > 50:
            gc.collect()
```

### 7. Efficient Process Monitoring
```python
class CachedProcessMonitor:
    def __init__(self, cache_duration=1.0):
        self.cache = {}
        self.cache_duration = cache_duration
    
    async def get_process_stats(self, pid):
        if pid in self.cache:
            cached_data, timestamp = self.cache[pid]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        # Fetch fresh data
        try:
            process = psutil.Process(pid)
            stats = {
                'cpu_percent': process.cpu_percent(),
                'memory_mb': process.memory_info().rss / 1024 / 1024,
                'status': process.status(),
                'num_threads': process.num_threads()
            }
            self.cache[pid] = (stats, time.time())
            return stats
        except psutil.NoSuchProcess:
            return None
```

### 8. Platform-Specific Optimizations

#### Windows Optimizations
```python
if sys.platform == "win32":
    # Disable quick edit mode in Windows console for better performance
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), 128)
    
    # Use Windows-specific high-performance counters
    from time import perf_counter as timer
else:
    from time import time as timer
```

#### Unix Optimizations
```python
if sys.platform != "win32":
    # Use epoll/kqueue for better async performance
    import selectors
    selector = selectors.DefaultSelector()
    
    # Increase file descriptor limits for many projects
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
```

## Testing Strategy

### Unit Tests
```python
# tests/test_project_discovery.py
import pytest
from pathlib import Path
from src.core.project_discovery import discover_projects

def test_discover_projects_finds_valid_projects(tmp_path):
    # Create mock project structure
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    
    package_json = project_dir / "package.json"
    package_json.write_text('{"name": "test", "scripts": {"start": "node index.js"}}')
    
    projects = discover_projects(tmp_path)
    assert len(projects) == 1
    assert projects[0].name == "test"

def test_discover_projects_ignores_node_modules(tmp_path):
    # Create project in node_modules (should be ignored)
    node_modules = tmp_path / "node_modules" / "some_package"
    node_modules.mkdir(parents=True)
    
    package_json = node_modules / "package.json"
    package_json.write_text('{"name": "should_be_ignored"}')
    
    projects = discover_projects(tmp_path)
    assert len(projects) == 0
```

### Integration Tests
```python
# tests/test_process_management.py
import asyncio
import pytest
from src.core.process_manager import ProcessManager

@pytest.mark.asyncio
async def test_start_stop_project():
    manager = ProcessManager()
    
    # Start a simple Node server
    test_project = NodeProject(
        name="test",
        path=Path("./test_fixtures/simple_server"),
        port=3333,
        start_command="node server.js"
    )
    
    await manager.start_project(test_project)
    
    # Wait for port to be active
    await asyncio.sleep(2)
    
    # Check if process is running on port
    pids = find_process_by_port(3333)
    assert len(pids) > 0
    
    # Stop the project
    await manager.stop_project("test")
    
    # Verify it's stopped
    await asyncio.sleep(1)
    pids = find_process_by_port(3333)
    assert len(pids) == 0
```

### Performance Tests
```python
# tests/test_performance.py
import time
import asyncio
from src.core.log_collector import LogCollector

@pytest.mark.asyncio
async def test_log_collector_performance():
    collector = LogCollector()
    
    # Simulate high-throughput logging
    start_time = time.time()
    lines_processed = 0
    
    async def generate_logs():
        for i in range(10000):
            await collector.add_log("test_project", f"Log line {i}")
            lines_processed += 1
    
    await generate_logs()
    elapsed = time.time() - start_time
    
    throughput = lines_processed / elapsed
    assert throughput > 1000  # Should handle >1000 lines/second
    
    # Check memory usage
    import sys
    buffer_size = sys.getsizeof(collector.buffers["test_project"])
    assert buffer_size < 1_000_000  # Less than 1MB for 10k lines
```

### End-to-End Tests
```python
# tests/test_e2e.py
from textual.testing import AppTest
from src.app import NodeManagerApp

async def test_full_workflow():
    async with AppTest.run_async(NodeManagerApp()) as pilot:
        # Check initial screen shows project list
        assert "Select Projects" in pilot.screen.title
        
        # Select a project (simulate spacebar)
        await pilot.press("space")
        
        # Start selected projects (simulate enter)
        await pilot.press("enter")
        
        # Should transition to monitoring screen
        await pilot.pause()
        assert "Running Projects" in pilot.screen.title
        
        # Test panel collapse
        await pilot.press("p")
        await pilot.pause()
        assert pilot.screen.query_one("#running-panel").is_collapsed
        
        # Test tab switching
        await pilot.press("tab")
        await pilot.pause()
        # Verify tab changed
        
        # Test quit
        await pilot.press("q")
        # Verify cleanup happened
```

## Common Issues and Solutions

### Issue: NPM Process PID Mismatch
**Problem:** The PID we track is for npm, not the actual Node.js process.
**Solution:** Use port-based discovery as primary identification method.

### Issue: Orphaned Processes on Windows
**Problem:** Processes don't terminate properly on Windows.
**Solution:** Use Windows job objects to group processes:
```python
if sys.platform == "win32":
    import win32job
    job = win32job.CreateJobObject(None, "")
    extended_info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    extended_info['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, extended_info)
    win32job.AssignProcessToJobObject(job, process._handle)
```

### Issue: High CPU Usage with Many Projects
**Problem:** Monitoring many projects causes high CPU usage.
**Solution:** Implement adaptive polling - reduce check frequency for stable projects.

### Issue: Terminal Resizing Breaks Layout
**Problem:** UI doesn't handle terminal resize properly.
**Solution:** Textual handles this automatically, but ensure all widgets have proper resize handlers.

## Future Enhancements

1. **Remote Monitoring**: SSH into remote servers to manage Node.js projects
2. **Metrics Dashboard**: CPU, Memory, Network graphs using terminal charts
3. **Log Persistence**: Save logs to files with rotation and compression
4. **Project Templates**: Quick project creation with boilerplate
5. **Plugin System**: Allow custom extensions for specific workflows
6. **Web UI**: Optional web interface that mirrors the terminal UI
7. **Docker Support**: Manage containerized Node applications
8. **Cluster Mode**: Manage PM2 clusters or Node.js worker threads
9. **Notifications**: Desktop/mobile notifications for crashes
10. **CI/CD Integration**: Trigger deployments from the UI

## Development Workflow

1. **Start with Phase 1 MVP** - Get basic process launching working first
2. **Test on all platforms** after each phase - Windows, Mac, Linux
3. **Profile performance** with 5, 10, 20+ projects running
4. **Get user feedback** early - Don't wait until Phase 6
5. **Document platform quirks** as you discover them
6. **Keep dependencies minimal** - Each dependency adds complexity
7. **Write tests as you go** - Especially for platform-specific code

## Key Technical Decisions

1. **Port as Identity**: Use ports as the primary identifier for processes, not PIDs
2. **Async First**: Build on asyncio from the start for scalability
3. **Textual for UI**: Provides the rich, interactive experience needed
4. **Graceful Degradation**: Always have fallback methods for process management
5. **Configuration over Convention**: Make everything configurable but provide smart defaults
6. **Cross-platform from Day 1**: Test on Windows, Mac, and Linux throughout development
7. **Performance Budgets**: Set limits for memory usage and UI responsiveness Implementation
- Monitor process health using port availability checks
- Implement exponential backoff for restart attempts
- Optional HTTP health endpoint checking
- CPU and memory usage monitoring per process
- Alert system for crashes and high resource usage
- Configurable restart policies (always, on-failure, never)
```py
def get_git_branch(project_path: Path) -> Optional[str]:
    """Get current git branch for a project"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None

def get_git_status(project_path: Path) -> dict:
    """Get git status summary"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            return {
                'modified': len([l for l in lines if l.startswith(' M')]),
                'untracked': len([l for l in lines if l.startswith('??')]),
                'staged': len([l for l in lines if l[0] in 'MADRC'])
            }
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return {}
```

#### Step 6.2: Auto-restart and Health Monitoring
```python
# src/core/health_monitor.py
import asyncio
import aiohttp
from datetime import datetime, timedelta

class HealthMonitor:
    def __init__(self, process_manager):
        self.process_manager = process_manager
        self.health_status = {}
        self.restart_counts = {}
        
    async def monitor_loop(self):
        """Main monitoring loop"""
        while True:
            for project_name, info in self.process_manager.processes.items():
                await self.check_project_health(project_name, info)
            await asyncio.sleep(5)  # Check every 5 seconds
    
    async def check_project_health(self, project_name, info):
        port = info['port']
        
        # Check if process is alive
        pids = find_process_by_port(port)
        if not pids:
            await self.handle_crashed_project(project_name)
            return
        
        # Optional: HTTP health check
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/health", 
                                      timeout=2) as response:
                    self.health_status[project_name] = response.status == 200
        except:
            self.health_status[project_name] = None  # Unknown/No endpoint
    
    async def handle_crashed_project(self, project_name):
        """Handle crashed project with restart logic"""
        if project_name not in self.restart_counts:
            self.restart_counts[project_name] = 0
            
        self.restart_counts[project_name] += 1
        
        # Exponential backoff
        wait_time = min(2 ** self.restart_counts[project_name], 60)
        await asyncio.sleep(wait_time)
        
        # Restart if configured
        project = self.get_project_config(project_name)
        if project.auto_restart and self.restart_counts[project_name] < 5:
            await self.process_manager.start_project(project)
```

## Cross-Platform Considerations

### Windows-Specific Implementation
```python
# src/utils/platform.py
import sys
import os
import subprocess

class PlatformUtils:
    @staticmethod
    def get_npm_command():
        """Get platform-specific npm command"""
        if sys.platform == "win32":
            return ["cmd", "/c", "npm"]
        return ["npm"]
    
    @staticmethod
    def create_process_kwargs():
        """Get platform-specific subprocess kwargs"""
        kwargs = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
        }
        
        if sys.platform == "win32":
            # Windows specific flags
            kwargs['creationflags'] = (
                subprocess.CREATE_NEW_PROCESS_GROUP |
                subprocess.CREATE_NO_WINDOW
            )
            # Prevent console windows
            kwargs['startupinfo'] = subprocess.STARTUPINFO()
            kwargs['startupinfo'].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        else:
            # Unix: new session
            kwargs['start_new_session'] = True
            
        return kwargs
    
    @staticmethod
    def kill_process(pid: int):
        """Platform-specific process termination"""
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], 
                         capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
```

### Terminal Compatibility
```python
# src/app.py
from textual.app import App
import os

class NodeManagerApp(App):
    def __init__(self):
        super().__init__()
        
        # Windows terminal setup
        if sys.platform == "win32":
            # Enable ANSI colors in Windows terminal
            os.system("")  # Triggers ANSI support
            
            # Set console code page to UTF-8
            subprocess.run(["chcp", "65001"], shell=True, capture_output=True)
```

## Performance Optimization Strategies

### 1. Efficient Log Handling
- Use circular buffers with fixed size (deque with maxlen)
- Batch UI updates (update every 100ms instead of per line)
- Implement log level filtering to reduce noise
- Compress old logs in memory

### 2. Async Everything
- All I/O operations should be async
- Use asyncio.gather() for parallel operations
- Implement connection pooling for health checks
- Non-blocking subprocess communication

### 3. Resource Management
```python
# Resource limits
MAX_LOG_LINES_PER_PROJECT = 1000
MAX_LOG_LINE_LENGTH = 500
UI_UPDATE_RATE = 10  # Hz
HEALTH_CHECK_INTERVAL = 5  # seconds
PROCESS_STAT_CACHE_TIME = 1  # second
```

### 4. Lazy Loading
- Don't load all project logs at once
- Load log content only when tab is viewed
- Virtualize long lists (only render visible items)

### 5. Caching Strategy
```python
from functools import lru_cache, cached_property
from time import time

class CachedMetrics:
    def __init__(self, ttl=1.0):
        self.ttl = ttl
        self._cache = {}
        self._timestamps = {}
    
    def get(self, key, factory):
        now = time()
        if key in self._cache and now - self._timestamps[key] < self.ttl:
            return self._cache[key]
        
        value = factory()
        self._cache[key] = value
        self._timestamps[key] = now
        return value
```

## Testing Strategy

### Unit Tests
- Test process discovery in mock file systems
- Test port scanning with mock network states
- Test log parsing with various formats

### Integration Tests
- Test starting/stopping real Node processes
- Test cross-platform compatibility
- Test UI responsiveness under load

### Stress Tests
- Handle 20+ simultaneous projects
- Process 1000+ log lines per second
- Rapid start/stop cycles

## Future Enhancements

1. **Remote Monitoring**: SSH into remote servers
2. **Metrics Dashboard**: CPU, Memory, Network graphs
3. **Log Persistence**: Save logs to files with rotation
4. **Project Templates**: Quick project creation
5. **Plugin System**: Extend functionality
6. **Web UI**: Optional web interface alongside TUI
7. **Docker Support**: Manage containerized Node apps
8. **Cluster Mode**: Manage multiple instances per project

## Development Workflow

1. Start with Phase 1 MVP - get basic process launching working
2. Add UI progressively - don't over-engineer early
3. Test on all platforms after each phase
4. Profile performance with multiple projects
5. Get user feedback early and iterate

## Key Technical Decisions

1. **Port as Identity**: Use ports as the primary identifier for processes, not PIDs
2. **Async First**: Build on asyncio from the start
3. **Textual for UI**: Provides the rich, interactive experience needed
4. **Graceful Degradation**: Always have fallback methods for process management
5. **Configuration over Convention**: Make everything configurable but provide smart defaults