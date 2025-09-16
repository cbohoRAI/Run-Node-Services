"""Action methods and UI management for the Node.js Project Runner."""

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.runner import NodeProjectRunnerApp

try:
    from textual.widgets import DataTable, Static
    from utils.port import PortUtils
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


class AppActions:
    """Mixin class containing all action methods for the NodeProjectRunnerApp."""
    
    def action_toggle_running_panel(self: 'NodeProjectRunnerApp') -> None:
        """Toggle running projects panel collapse state with debouncing."""
        self._mark_activity()
        current_time = time.time()
        
        # Debounce: ignore if pressed within 0.3 seconds
        if current_time - self._last_toggle_time < 0.3:
            return
        
        self._last_toggle_time = current_time
        
        if not self.started or not self._running_panel:
            return  # Only works when running
        self._running_panel.toggle_collapse()
    
    async def action_quit(self: 'NodeProjectRunnerApp') -> None:
        """Quit the application with debouncing."""
        current_time = time.time()
        
        # Debounce: ignore if pressed within 0.5 seconds
        if current_time - self._last_quit_time < 0.5:
            return
        
        self._last_quit_time = current_time
        
        await self._cleanup_processes()
        self.exit()

    async def action_kill_by_ports(self: 'NodeProjectRunnerApp') -> None:
        """Emergency kill all processes by their ports."""
        self._mark_activity()
        
        if not self.running_projects:
            if self._log:
                self._log.write("[yellow]No running projects to kill[/yellow]")
            return
        
        if self._log:
            self._log.write("[red]Emergency port-based cleanup initiated...[/red]")
        
        ports_killed = set()
        for idx, running_proj in self.running_projects.items():
            if running_proj.port and running_proj.port not in ports_killed:
                if self._log:
                    self._log.write(f"[yellow]Force killing processes on port {running_proj.port}[/yellow]")
                
                success = PortUtils.kill_processes_by_port(running_proj.port)
                ports_killed.add(running_proj.port)
                
                if success:
                    if self._log:
                        self._log.write(f"[green]Killed processes on port {running_proj.port}[/green]")
                    running_proj.status = "Terminated (Port Kill)"
                else:
                    if self._log:
                        self._log.write(f"[red]Failed to kill processes on port {running_proj.port}[/red]")
        
        if self._log:
            self._log.write("[green]Emergency cleanup complete[/green]")

    def action_switch_to_project_tab(self: 'NodeProjectRunnerApp', key: str) -> None:
        """Switch to a specific project tab (1-9)."""
        self._mark_activity()
        
        if not self._log_tabs or not self._log_tabs.display:
            return
        
        try:
            tab_number = int(key) - 1  # Convert to 0-based index
            # Get list of active project indices
            active_projects = sorted(self.running_projects.keys())
            
            if 0 <= tab_number < len(active_projects):
                project_idx = active_projects[tab_number]
                tab_id = f"tab-{project_idx}"
                self._log_tabs.active = tab_id
        except (ValueError, IndexError):
            pass

    def action_switch_to_all_logs(self: 'NodeProjectRunnerApp') -> None:
        """Switch to the 'All Logs' tab."""
        self._mark_activity()
        
        if self._log_tabs and self._log_tabs.display:
            self._log_tabs.active = "tab-all"

    def action_next_log_tab(self: 'NodeProjectRunnerApp') -> None:
        """Switch to the next log tab."""
        self._mark_activity()
        
        if self._log_tabs and self._log_tabs.display:
            self._log_tabs.action_next_tab()

    def action_prev_log_tab(self: 'NodeProjectRunnerApp') -> None:
        """Switch to the previous log tab."""
        self._mark_activity()
        
        if self._log_tabs and self._log_tabs.display:
            self._log_tabs.action_previous_tab()

    def action_toggle_or_start(self: 'NodeProjectRunnerApp') -> None:
        """Toggle selection on project rows, or start if on the start row."""
        self._mark_activity()
        if not self._table or not self.projects:
            return
        
        # Only works if table is visible (not in running mode)
        if not self._table.display:
            return
        
        cursor_row = self._table.cursor_row
        if cursor_row is None:
            return
            
        # Check if we're on the start row (last row)
        start_row_idx = len(self.projects) + 1
        if cursor_row == start_row_idx:
            # Start the selected projects
            self.app.call_later(self.action_start_selected)
        elif cursor_row < len(self.projects):
            # Toggle selection for project rows
            self._toggle_index(cursor_row)

    def action_select_all(self: 'NodeProjectRunnerApp') -> None:
        """Select all projects."""
        if self.started:
            return  # Don't allow selection changes after starting
        self.selected = set(range(len(self.projects)))
        for idx in self.selected:
            self._refresh_selection_cell(idx)

    def action_clear_selection(self: 'NodeProjectRunnerApp') -> None:
        """Clear all selections."""
        if self.started:
            return  # Don't allow selection changes after starting
        old_selected = list(self.selected)
        self.selected.clear()
        for idx in old_selected:
            self._refresh_selection_cell(idx)
        self._update_start_row_count()

    def action_cursor_down(self: 'NodeProjectRunnerApp') -> None:
        """Move cursor down (j key)."""
        if self._table and self._table.display:
            self._table.action_cursor_down()

    def action_cursor_up(self: 'NodeProjectRunnerApp') -> None:
        """Move cursor up (k key)."""
        if self._table and self._table.display:
            self._table.action_cursor_up()

    async def action_start_selected(self: 'NodeProjectRunnerApp') -> None:
        """Start all selected projects."""
        if not self.selected:
            if self._log:
                self._log.write("[bold red]No projects selected.[/bold red]")
            return
        
        if self.started:
            if self._log:
                self._log.write("[yellow]Already started. Restart not implemented in this session.[/yellow]")
            return
        
        self.started = True
        
        # Switch to running view
        self._switch_to_running_view()
        
        if self._log:
            self._log.write(f"[green]Starting {len(self.selected)} project(s)...[/green]")
        
        for idx in sorted(self.selected):
            await self._start_project(idx)
        
        # Start periodic status updates
        self.set_interval(5.0, self._update_status_display)


class UIManagement:
    """Mixin class containing UI management methods."""
    
    def _populate_table(self: 'NodeProjectRunnerApp') -> None:
        """Populate the data table with projects."""
        if not self._table:
            return
            
        self._table.clear()
        for idx, proj in enumerate(self.projects):
            self._table.add_row(
                str(idx + 1), "", proj.name, proj.path, "Ready"
            )
        
        # Add a separator and start option at the bottom
        self._table.add_row(
            "─" * 3, "─" * 8, "─" * 20, "─" * 30, "─" * 10
        )
        self._table.add_row(
            "▶", "", "[bold green]START SELECTED PROJECTS[/bold green]", 
            f"[dim]{len(self.selected)} selected[/dim]", ""
        )

    def _switch_to_running_view(self: 'NodeProjectRunnerApp') -> None:
        """Switch the UI to show running status and logs."""
        # Hide project selection panel
        if self._project_selection_panel:
            self._project_selection_panel.display = False
        
        # Show running panel and log tabs
        if self._running_panel:
            self._running_panel.display = True
        
        if self._log_tabs:
            self._log_tabs.display = True
        
        # Update the status display
        self._update_status_display()

    def _update_status_display(self: 'NodeProjectRunnerApp') -> None:
        """Update the running projects status display."""
        if self._running_panel and self.running_projects:
            # Only update if we have running projects and the panel is visible
            if self._running_panel.display:
                self._running_panel.update_status(self.running_projects)

    def _add_project_tab(self: 'NodeProjectRunnerApp', project_idx: int, project_name: str) -> None:
        """Add a new tab for a project."""
        if not self._log_tabs:
            return
        
        from textual.app import ComposeResult
        from textual.widgets import RichLog, TabPane
        
        tab_id = f"tab-{project_idx}"
        project_log = RichLog(highlight=True, markup=True, wrap=True, auto_scroll=True)
        
        # Create a custom TabPane class that composes the log widget
        class ProjectTabPane(TabPane):
            def compose(self) -> ComposeResult:
                yield project_log
        
        # Create and add the tab pane
        tab_pane = ProjectTabPane(project_name, id=tab_id)
        self._log_tabs.add_pane(tab_pane)
        
        # Store reference for writing logs
        self._project_log_widgets[project_idx] = project_log

    def _remove_project_tab(self: 'NodeProjectRunnerApp', project_idx: int) -> None:
        """Remove a project's tab when it stops."""
        if not self._log_tabs:
            return
        
        tab_id = f"tab-{project_idx}"
        try:
            self._log_tabs.remove_pane(tab_id)
            self._project_log_widgets.pop(project_idx, None)
        except Exception:
            pass  # Tab might not exist

    def _write_help_note(self: 'NodeProjectRunnerApp') -> None:
        """Write initial help text to the log."""
        if self._log:
            self._log.write(
                "[dim]Press [bold]E[/bold] to select/deselect projects, "
                "[bold]S[/bold] or select START row to run. "
                "[bold]A[/bold]=All [bold]C[/bold]=Clear "
                "[bold]R[/bold]=Toggle Running Panel [bold]Ctrl+K[/bold]=Emergency Port Kill [bold]Q[/bold]=Quit[/dim]"
            )
            self._log.write(
                "[dim]Tab Navigation: [bold]1-9[/bold]=Project Tabs [bold]0[/bold]=All Logs "
                "[bold]Tab/Shift+Tab[/bold]=Next/Prev Tab[/dim]"
            )

    def _toggle_index(self: 'NodeProjectRunnerApp', idx: int) -> None:
        """Toggle selection state for a project."""
        if idx < 0 or idx >= len(self.projects):
            return
            
        if idx in self.selected:
            self.selected.discard(idx)
        else:
            self.selected.add(idx)
        self._refresh_selection_cell(idx)

    def _refresh_selection_cell(self: 'NodeProjectRunnerApp', idx: int) -> None:
        """Update the selection indicator in the table."""
        if not self._table or idx < 0 or idx >= len(self.projects):
            return
        try:
            mark = "✓" if idx in self.selected else ""
            # Update using row index and column index (1 for "Selected" column)
            self._table.update_cell_at((idx, 1), mark)
            # Also update the start row to show count
            self._update_start_row_count()
        except (IndexError, KeyError, Exception):
            # Silently ignore if update fails
            pass
    
    def _update_start_row_count(self: 'NodeProjectRunnerApp') -> None:
        """Update the count display in the start row."""
        if not self._table:
            return
        try:
            # The start row is at index len(projects) + 1 (after separator)
            start_row_idx = len(self.projects) + 1
            count_text = f"[dim]{len(self.selected)} selected[/dim]"
            self._table.update_cell_at((start_row_idx, 3), count_text)
        except:
            pass

    def _set_status(self: 'NodeProjectRunnerApp', idx: int, text: str) -> None:
        """Update the status column for a project."""
        if not self._table or idx < 0 or idx >= len(self.projects):
            return
        try:
            # Update using row index and column index (4 for "Status" column)
            self._table.update_cell_at((idx, 4), text)
        except (IndexError, KeyError, Exception):
            # Silently ignore if update fails
            pass
    
    def _cleanup_old_data(self: 'NodeProjectRunnerApp'):
        """Periodically clean up old data to prevent memory leaks."""
        current_time = time.time()
        
        # Clean up finished processes from dictionaries
        finished_processes = []
        for idx, running_proj in list(self.running_projects.items()):
            if running_proj.status.startswith("Exited") or running_proj.status == "Terminated":
                # Keep for 5 minutes after exit, then clean up
                if (current_time - running_proj.start_time.timestamp()) > 300:
                    finished_processes.append(idx)
        
        for idx in finished_processes:
            # Clean up all references
            self.running_projects.pop(idx, None)
            self.processes.pop(idx, None)
            if idx in self.log_tasks:
                self.log_tasks[idx].cancel()
                self.log_tasks.pop(idx, None)