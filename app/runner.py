"""Main application class for the Node.js Project Runner."""

import asyncio
import contextlib
import os
import shutil
import signal
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import DataTable, Footer, Header, RichLog, TabbedContent, TabPane, Static
    
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
            min-height: 3;  /* Minimum height for header */
            border: round $primary;
            margin: 0 0 1 0;
            overflow-y: auto;  /* Allow scrolling if too many projects */
        }

        #running-panel.hidden {
            display: none;
        }

        .running-status-container {
            height: auto;
            padding: 0 1;
            min-height: 1;  /* Ensure minimum height */
        }

        .status-item {
            height: 1;
            margin: 0;
            padding: 0 1;
            display: block;  /* Ensure proper display */
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
        self.current_log_tab: Optional[int] = None  # None = "All", int = specific project
        
        # UI components
        self._table: Optional[DataTable] = None
        self._log: Optional[RichLog] = None
        self._log_panel: Optional[Vertical] = None
        self._project_selection_panel: Optional[Vertical] = None
        self._running_panel: Optional[CollapsibleRunningPanel] = None
        self._log_tabs: Optional[TabbedContent] = None
        self._project_log_widgets: Dict[int, RichLog] = {}
        
        # Performance and activity tracking
        self._update_interval_timer = None
        self._current_update_interval = 5.0
        self._last_activity_time = time.time()
        
        # Add debouncing for key actions
        self._last_toggle_time = 0
        self._last_quit_time = 0
        self._cleanup_started = False  # Prevent duplicate cleanup
        
        # Graceful exit for SIGINT
        signal.signal(signal.SIGINT, self._sigint_handler)

    # ========================== Activity and Performance Management ==========================
    
    def _adjust_update_interval(self):
        """Dynamically adjust update frequency based on activity."""
        current_time = time.time()
        time_since_activity = current_time - self._last_activity_time
        
        # Slow down updates if no recent activity
        if time_since_activity > 30:  # 30 seconds of no activity
            new_interval = 10.0  # Update every 10 seconds
        elif time_since_activity > 60:  # 1 minute of no activity  
            new_interval = 30.0  # Update every 30 seconds
        else:
            new_interval = 5.0   # Normal update frequency
        
        # Only change if interval actually changed
        if new_interval != self._current_update_interval:
            self._current_update_interval = new_interval
            # Cancel old timer and start new one
            if self._update_interval_timer:
                self._update_interval_timer.cancel()
            self._update_interval_timer = self.set_interval(new_interval, self._update_status_display)
    
    def _mark_activity(self):
        """Mark that user activity occurred."""
        self._last_activity_time = time.time()
        self._adjust_update_interval()

    def _sigint_handler(self, *_) -> None:
        """Handle SIGINT (Ctrl+C)."""
        # Schedule async cleanup then exit. Signal handlers can't be async.
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._cleanup_processes())
        except RuntimeError:
            # Fallback: no loop, ignore
            pass
        self.exit(message="Interrupted - cleaning up...")

    # ========================== Lifecycle Methods ==========================
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        
        with Vertical(id="body"):
            # Project selection panel (shown before starting)
            with Vertical(id="project-selection-panel") as project_panel:
                yield Static("📋 Projects", classes="log-panel-header")
                
                table = DataTable(zebra_stripes=True, cursor_type="row")
                table.add_columns("#", "Selected", "Project", "Path", "Status")
                self._table = table
                yield table
                
                self._project_selection_panel = project_panel
            
            # Running projects panel (hidden initially, shown when running)
            self._running_panel = CollapsibleRunningPanel()
            self._running_panel.display = False
            yield self._running_panel
            
            # Log panel with tabs (hidden initially, shown when running)
            with TabbedContent(id="log-tabs") as tabs:
                with TabPane("All Logs", id="tab-all"):
                    self._log = RichLog(highlight=True, markup=True, wrap=True, auto_scroll=True)
                    yield self._log
                
                # Individual project tabs will be added dynamically
                self._log_tabs = tabs
                self._log_tabs.display = False  # Hidden initially
        
        yield Footer()

    async def on_mount(self) -> None:
        """Optimized initialization."""
        # Load projects asynchronously to not block UI
        await asyncio.sleep(0.01)  # Yield to UI
        
        loader = ProjectLoader(self.projects_file)
        self.projects = loader.load()
        
        await asyncio.sleep(0.01)  # Yield to UI
        
        self._populate_table()
        self._write_help_note()
        
        if self._table and self.projects:
            self._table.focus()
            self._table.cursor_coordinate = (0, 0)
        
        # Schedule periodic cleanup
        self.set_interval(60.0, self._cleanup_old_data)

    # ========================== Event Handlers ==========================
    
    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight events."""
        # Could update status bar or provide other feedback
        pass