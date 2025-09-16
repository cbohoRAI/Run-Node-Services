"""Custom UI widgets optimized for performance."""

from datetime import datetime
from typing import Dict, Optional
import time

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Static
    from textual.reactive import reactive
    
    from models.data import RunningProject
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


class StatusWidget(Horizontal):
    """Optimized status widget with caching."""
    
    def __init__(self, running_project: RunningProject, **kwargs):
        super().__init__(classes="status-item", **kwargs)
        self.running_project = running_project
        self._name_widget: Optional[Static] = None
        self._pid_widget: Optional[Static] = None
        self._time_widget: Optional[Static] = None
        self._last_update_minute = -1
    
    def compose(self) -> ComposeResult:
        """Compose with references for updates."""
        name_status = f"[bold cyan]{self.running_project.name}[/bold cyan] [green]({self.running_project.status})[/green]"
        
        if self.running_project.port:
            pid_text = f"PID: {self.running_project.pid or 'External'} | [bold yellow]Port: {self.running_project.port}[/bold yellow]"
        else:
            pid_text = f"PID: {self.running_project.pid or 'External'} | [dim]No Port[/dim]"
        
        start_time_str = self.running_project.start_time.strftime("%I:%M %p")
        time_text = f"Started: {start_time_str}"
        
        self._name_widget = Static(name_status, classes="status-name")
        self._pid_widget = Static(pid_text, classes="status-pid")
        self._time_widget = Static(time_text, classes="status-runtime")
        
        yield self._name_widget
        yield self._pid_widget
        yield self._time_widget
    
    def update_if_changed(self) -> bool:
        """Update only if status changed. Returns True if updated."""
        if not self._name_widget:
            return False
        
        # Check if status changed
        new_status = f"[bold cyan]{self.running_project.name}[/bold cyan] [green]({self.running_project.status})[/green]"
        if self._name_widget.renderable != new_status:
            self._name_widget.update(new_status)
            return True
        
        return False


class CollapsibleRunningPanel(Vertical):
    """Optimized collapsible panel with efficient updates."""
    
    # Use reactive for automatic UI updates
    is_collapsed = reactive(False)
    project_count = reactive(0)
    
    def __init__(self, **kwargs):
        super().__init__(id="running-panel", **kwargs)
        self._status_container: Optional[Vertical] = None
        self._header: Optional[Static] = None
        self._status_widgets: Dict[int, StatusWidget] = {}
        self._last_update_hash = None
    
    def compose(self) -> ComposeResult:
        """Compose the panel."""
        self._header = Static(
            "[bold]v Running Project List[/bold]",
            classes="running-panel-header"
        )
        self._header.can_focus = True
        yield self._header
        
        self._status_container = Vertical(classes="running-status-container")
        yield self._status_container
    
    def watch_is_collapsed(self, collapsed: bool) -> None:
        """React to collapse state changes."""
        if not self._header or not self._status_container:
            return
        
        if collapsed:
            self._status_container.display = False
            count = self.project_count
            header_text = f"[bold]> Running Project List{f' ({count})' if count > 0 else ''}[/bold]"
            self._header.update(header_text)
            self.styles.height = 3
        else:
            self._status_container.display = True
            self._header.update("[bold]v Running Project List[/bold]")
            self.styles.height = "auto"
    
    def toggle_collapse(self) -> None:
        """Toggle collapse state."""
        self.is_collapsed = not self.is_collapsed
    
    def update_status(self, running_projects: Dict[int, RunningProject]) -> None:
        """Efficient status update with diffing."""
        if not self._status_container:
            return
        
        # Create efficient hash of current state
        current_hash = tuple(
            (idx, p.name, p.status, int((datetime.now() - p.start_time).total_seconds() // 60))
            for idx, p in running_projects.items()
        )
        
        # Skip if nothing changed
        if current_hash == self._last_update_hash:
            return
        
        self._last_update_hash = current_hash
        self.project_count = len(running_projects)
        
        # Diff and update
        current_indices = set(running_projects.keys())
        existing_indices = set(self._status_widgets.keys())
        
        # Remove widgets for stopped projects
        for idx in existing_indices - current_indices:
            widget = self._status_widgets.pop(idx)
            widget.remove()
        
        # Add widgets for new projects
        for idx in current_indices - existing_indices:
            widget = StatusWidget(running_projects[idx])
            self._status_widgets[idx] = widget
            self._status_container.mount(widget)
        
        # Update existing widgets if needed
        for idx in current_indices & existing_indices:
            widget = self._status_widgets[idx]
            widget.running_project = running_projects[idx]
            widget.update_if_changed()
        
        # Handle empty state
        if not running_projects and not self._status_widgets:
            self._status_container.mount(
                Static("[dim]No projects running[/dim]", classes="no-projects")
            )
    
    def on_click(self, event) -> None:
        """Handle header clicks."""
        if event.widget == self._header:
            self.toggle_collapse()
            event.stop()