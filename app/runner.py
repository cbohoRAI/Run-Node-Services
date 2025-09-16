"""Main application class for the Node.js Project Runner."""

import asyncio
import contextlib
import os
import shutil
import signal
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from weakref import WeakSet

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import DataTable, Footer, Header, RichLog, TabbedContent, TabPane, Static
    from textual.reactive import reactive
    
    from models.data import Project, RunningProject
    from utils.loader import ProjectLoader
    from utils.logging import LogManager, MultiLogBuffer
    from utils.port import PortUtils
    from ui.widgets import CollapsibleRunningPanel
    from app.actions import AppActions, UIManagement
    from app.process_manager import ProcessManager
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


class NodeProjectRunnerApp(App, AppActions, UIManagement, ProcessManager):
    """A Textual app to run multiple Node.js projects."""
    
    # Use reactive properties for better performance
    is_running = reactive(False)
    selected_count = reactive(0)
    
    CSS = """
        Screen {
            layout: vertical;
        }

        #body {
            height: 1fr;
            layout: vertical;
        }

        /* Panel header styles */
        .panel-header {
            content-align: center middle;
            height: 1;
            background: $boost;
            color: $text;
            text-style: bold;
            border-bottom: solid $accent;
        }
        .running-panel-header {
            content-align: left middle;
            height: 2;
            background: $primary;
            color: $text;
            text-style: bold;
            border-bottom: solid $accent;
            padding: 0 1;
        }
        .running-panel-header:hover {
            background: $primary-darken-1;
            text-style: bold;
        }
        .log-panel-header {
            content-align: center middle;
            height: 1;
            background: $boost;
            color: $text;
            text-style: bold;
            border-bottom: solid $accent;
        }

        #running-panel {
            height: auto;
            max-height: 50%;
            min-height: 3;
            border: round $primary;
            margin: 0 0 1 0;
            overflow-y: auto;
        }

        #running-panel.hidden {
            display: none;
        }

        .running-status-container {
            height: auto;
            padding: 0 1;
            min-height: 1;
        }

        .status-item {
            height: 1;
            margin: 0;
            padding: 0 1;
            display: block;
        }

        .status-name { width: 1fr; }
        .status-pid { width: 20; text-align: right; }
        .status-runtime { width: 20; text-align: right; }

        #log-tabs {
            height: 1fr;
            border: round $accent;
        }

        #log-tabs > Tabs {
            dock: top;
            height: 3;
            background: $surface;
        }

        #log-tabs TabPane {
            padding: 0;
        }

        #log-tabs RichLog {
            height: 1fr;
            padding: 0 1;
            overflow-y: auto;
        }

        DataTable {
            height: 1fr;
        }

        DataTable > .datatable--cursor {
            background: $boost;
        }

        RichLog {
            height: 1fr;
            padding: 0 1;
            overflow-y: auto;
        }

        .status-name { 
            width: 1fr; 
        }

        .status-pid { 
            width: 25; text-align: right; 
        }

        .status-runtime { 
            width: 20; 
            text-align: right; 
        }
        """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "select_all", "Select All"),
        Binding("c", "clear_selection", "Clear"),
        Binding("r", "toggle_running_panel", "Toggle Running"),
        Binding("s", "start_selected", "Start Selected"),
        Binding("e", "toggle_or_start", "Select/Start"),
        Binding("ctrl+k", "kill_by_ports", "Kill by Ports", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("1,2,3,4,5,6,7,8,9", "switch_to_project_tab", "Project Tab", show=False),
        Binding("0", "switch_to_all_logs", "All Logs", show=False),
        Binding("tab", "next_log_tab", "Next Tab", show=False),
        Binding("shift+tab", "prev_log_tab", "Prev Tab", show=False),
    ]

    def __init__(self, projects_file: str = "projects.txt"):
        super().__init__()
        self.projects_file = projects_file
        
        # Core data
        self.projects: List[Project] = []
        self.selected: Set[int] = set()
        self.started: bool = False
        self.processes: Dict[int, asyncio.subprocess.Process] = {}
        self.running_projects: Dict[int, RunningProject] = {}
        self.log_tasks: Dict[int, asyncio.Task] = {}
        self.log_manager: LogManager = LogManager()
        self.current_log_tab: Optional[int] = None
        
        # UI components with type hints
        self._table: Optional[DataTable] = None
        self._log: Optional[RichLog] = None
        self._log_panel: Optional[Vertical] = None
        self._project_selection_panel: Optional[Vertical] = None
        self._running_panel: Optional[CollapsibleRunningPanel] = None
        self._log_tabs: Optional[TabbedContent] = None
        self._project_log_widgets: Dict[int, RichLog] = {}
        
        # Performance optimizations
        self._update_timer: Optional[asyncio.Task] = None
        self._update_interval = 5.0
        self._last_activity = time.time()
        self._status_update_pending = False
        self._batch_log_updates: List[tuple] = []
        self._log_batch_timer: Optional[asyncio.Task] = None
        
        # Debouncing
        self._action_timestamps: Dict[str, float] = {}
        self._cleanup_lock = asyncio.Lock()
        self._cleanup_started = False
        
        # Track active async tasks for cleanup
        self._active_tasks: WeakSet = WeakSet()
        
        # Graceful exit
        signal.signal(signal.SIGINT, self._sigint_handler)

    # ========================== Performance Optimizations ==========================
    
    def _debounce_action(self, action_name: str, min_interval: float = 0.3) -> bool:
        """Check if action should be debounced."""
        current = time.time()
        last = self._action_timestamps.get(action_name, 0)
        if current - last < min_interval:
            return True
        self._action_timestamps[action_name] = current
        return False
    
    def _mark_activity(self) -> None:
        """Mark user activity for dynamic update intervals."""
        self._last_activity = time.time()
        # Resume normal update frequency on activity
        if self._update_interval > 5.0:
            self._update_interval = 5.0
            self._restart_update_timer()
    
    def _restart_update_timer(self) -> None:
        """Restart the update timer with new interval."""
        if self._update_timer and not self._update_timer.done():
            self._update_timer.cancel()
        if self.started and self.running_projects:
            self._update_timer = self.create_task(self._update_loop())
    
    async def _update_loop(self) -> None:
        """Efficient update loop with adaptive intervals."""
        while self.started and self.running_projects:
            try:
                # Dynamic interval based on activity
                time_since_activity = time.time() - self._last_activity
                if time_since_activity > 60:
                    self._update_interval = 30.0
                elif time_since_activity > 30:
                    self._update_interval = 10.0
                else:
                    self._update_interval = 5.0
                
                # Batch status updates
                if self._running_panel and self._running_panel.display:
                    self.call_from_thread(self._running_panel.update_status, self.running_projects)
                
                await asyncio.sleep(self._update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5.0)

    def _sigint_handler(self, *_) -> None:
        """Handle SIGINT (Ctrl+C)."""
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._cleanup_processes())
        except RuntimeError:
            pass
        self.exit(message="Interrupted - cleaning up...")
    
    def create_task(self, coro) -> asyncio.Task:
        """Create a task and track it for cleanup."""
        task = asyncio.create_task(coro)
        self._active_tasks.add(task)
        return task

    # ========================== Lifecycle Methods ==========================
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        
        with Vertical(id="body"):
            # Project selection panel
            with Vertical(id="project-selection-panel") as project_panel:
                yield Static("📋 Projects", classes="log-panel-header")
                
                table = DataTable(zebra_stripes=True, cursor_type="row")
                table.add_columns("#", "Selected", "Project", "Path", "Status")
                # Enable caching for better performance
                table.fixed_columns = 2  # First two columns are fixed width
                self._table = table
                yield table
                
                self._project_selection_panel = project_panel
            
            # Running projects panel
            self._running_panel = CollapsibleRunningPanel()
            self._running_panel.display = False
            yield self._running_panel
            
            # Log panel with tabs
            with TabbedContent(id="log-tabs") as tabs:
                with TabPane("All Logs", id="tab-all"):
                    self._log = RichLog(
                        highlight=True, 
                        markup=True, 
                        wrap=True, 
                        auto_scroll=True,
                        max_lines=5000  # Limit buffer for performance
                    )
                    yield self._log
                
                self._log_tabs = tabs
                self._log_tabs.display = False
        
        yield Footer()

    async def on_mount(self) -> None:
        """Optimized initialization."""
        # Load projects synchronously first to ensure they're available
        loader = ProjectLoader(self.projects_file)
        self.projects = loader.load()
        
        # Now populate the table with the loaded projects
        self._populate_table()
        self._write_help_note()
        
        if self._table and self.projects:
            self._table.focus()
            self._table.cursor_coordinate = (0, 0)
        
        # Set up efficient periodic cleanup
        self.set_interval(120.0, self._cleanup_old_data, pause=True)

    # ========================== Event Handlers ==========================
    
    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight events."""
        # Minimal processing for snappy response
        self._mark_activity()
    
    def watch_selected_count(self, count: int) -> None:
        """React to selection count changes."""
        if self._table and not self.started:
            self._update_start_row_count()
    
    def _populate_table(self) -> None:
        """Populate table efficiently."""
        if not self._table:
            return
        
        # Debug: log how many projects we have
        if self._log:
            self._log.write(f"[dim]Loading {len(self.projects)} projects...[/dim]")
        
        # Batch all rows at once
        rows = []
        for idx, proj in enumerate(self.projects):
            rows.append((str(idx + 1), "", proj.name, proj.path, "Ready"))
        
        # Add separator and start row
        rows.append(("─" * 3, "─" * 8, "─" * 20, "─" * 30, "─" * 10))
        rows.append((
            "▶", "", 
            "[bold green]START SELECTED PROJECTS[/bold green]",
            f"[dim]{len(self.selected)} selected[/dim]", 
            ""
        ))
        
        # Clear and add all at once
        self._table.clear()
        for row in rows:
            self._table.add_row(*row)