"""Custom UI widgets for the Node.js Project Runner."""

from datetime import datetime
from typing import Dict, Optional

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Static
    
    from models.data import RunningProject
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


class StatusWidget(Horizontal):
    """A compact horizontal widget to display running project status."""
    
    def __init__(self, running_project: RunningProject, **kwargs):
        super().__init__(classes="status-item", **kwargs)
        self.running_project = running_project
        self._last_update = None
    
    def compose(self) -> ComposeResult:
        start_time_str = self.running_project.start_time.strftime("%I:%M %p")
        start_time_text = f"Started: {start_time_str}"

        name_status = f"[bold cyan]{self.running_project.name}[/bold cyan] [green]({self.running_project.status})[/green]"
        
        # Enhanced port/PID display
        if self.running_project.port:
            pid_text = f"PID: {self.running_project.pid if self.running_project.pid else 'External'} | [bold yellow]Port: {self.running_project.port}[/bold yellow]"
        else:
            pid_text = f"PID: {self.running_project.pid if self.running_project.pid else 'External'} | [dim]No Port[/dim]"

        yield Static(name_status, classes="status-name")
        yield Static(pid_text, classes="status-pid")
        yield Static(start_time_text, classes="status-runtime")


class CollapsibleRunningPanel(Vertical):
    """A collapsible panel showing running projects with a proper title bar."""
    
    def __init__(self, **kwargs):
        super().__init__(id="running-panel", **kwargs)
        self._collapsed = False
        self._status_container: Optional[Vertical] = None
        self._header: Optional[Static] = None
        self._last_project_count = 0
        self._project_hashes = {}  # Track actual changes, not just count
    
    def compose(self) -> ComposeResult:
        # Create the title bar with collapse indicator - use a regular Static widget
        title_text = "[bold]v Running Project List[/bold]"  # Down arrow when expanded
        self._header = Static(title_text, classes="running-panel-header")
        self._header.can_focus = True  # Make it focusable so it can handle clicks
        yield self._header

        self._status_container = Vertical(classes="running-status-container")
        yield self._status_container
    
    @property
    def collapsed(self) -> bool:
        return self._collapsed
    
    def toggle_collapse(self) -> None:
        """Toggle the collapsed state of the panel."""
        self._collapsed = not self._collapsed
        
        if self._collapsed:
            # Collapse: hide the status container and update header
            if self._status_container:
                self._status_container.display = False
            if self._header:
                count = len(self._project_hashes)
                if count > 0:
                    self._header.update(f"[bold]> Running Project List ({count})[/bold]")
                else:
                    self._header.update("[bold]> Running Project List[/bold]")
            self.styles.height = 3  # Just enough for the header
        else:
            # Expand: show the status container and update header
            if self._status_container:
                self._status_container.display = True
            if self._header:
                self._header.update("[bold]v Running Project List[/bold]")  # Down arrow when expanded
            # Let it auto-size when expanded
            self.styles.height = "auto"
    
    def update_status(self, running_projects: Dict[int, RunningProject]) -> None:
        """Update only when projects actually change."""
        if not self._status_container:
            return
        
        # Create hash of current project states
        current_hashes = {}
        for idx, proj in running_projects.items():
            # Hash based on name, status, and runtime minute (not second)
            runtime_minutes = int((datetime.now() - proj.start_time).total_seconds() // 60)
            current_hashes[idx] = hash((proj.name, proj.status, runtime_minutes))
        
        # Only update if hashes changed
        if current_hashes == self._project_hashes:
            return
        
        self._project_hashes = current_hashes
        self._status_container.remove_children()
        
        if not running_projects:
            self._status_container.mount(
                Static("[dim]No projects running[/dim]", classes="no-projects")
            )
            return
        
        # Mount each status widget (they will self-compose)
        for idx, running in running_projects.items():
            self._status_container.mount(StatusWidget(running))
        
        # Update header to show project count when collapsed
        if self._collapsed and self._header:
            count_text = f"[bold]> Running Project List ({len(running_projects)})[/bold]"
            self._header.update(count_text)
        elif not self._collapsed and self._header:
            # Make sure expanded header is correct
            self._header.update("[bold]v Running Project List[/bold]")
        
        # Don't manually set height - let the CSS and auto-sizing handle it
        # Remove the manual height calculation that was causing issues
    
    def on_click(self, event) -> None:
        """Handle click events on the header."""
        # Check if the click was on the header
        if event.widget == self._header:
            self.toggle_collapse()
            event.stop()  # Prevent event propagation