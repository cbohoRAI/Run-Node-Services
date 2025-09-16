"""Action methods and UI management for the Node.js Project Runner."""

import asyncio
import time
from typing import Protocol, runtime_checkable
from functools import lru_cache

try:
    from textual.widgets import DataTable, Static, RichLog, TabPane, TabbedContent
    from textual.app import ComposeResult
    from utils.port import PortUtils
except ImportError as e:
    print("Missing dependency: textual. Install with: pip install textual")
    raise


@runtime_checkable
class AppActionsProtocol(Protocol):
    """Protocol for AppActions expectations."""
    started: bool
    selected: set
    running_projects: dict
    projects: list
    _log: object
    _table: object
    _running_panel: object
    _log_tabs: object
    _project_log_widgets: dict
    _project_selection_panel: object
    _cleanup_lock: asyncio.Lock
    
    def _debounce_action(self, name: str, interval: float) -> bool: ...
    def _mark_activity(self) -> None: ...
    def _switch_to_running_view(self) -> None: ...
    def _start_project(self, idx: int) -> None: ...
    def _cleanup_processes(self) -> None: ...
    def create_task(self, coro) -> asyncio.Task: ...
    def call_from_thread(self, fn, *args) -> None: ...
    def exit(self, **kwargs) -> None: ...
    def set_interval(self, interval: float, callback, **kwargs) -> None: ...
    def _update_loop(self) -> None: ...


class AppActions:
    """Mixin class containing all action methods."""
    
    def action_toggle_running_panel(self: AppActionsProtocol) -> None:
        """Toggle running panel with debouncing."""
        if self._debounce_action('toggle_panel', 0.2):
            return
        
        self._mark_activity()
        if self.started and self._running_panel:
            self._running_panel.toggle_collapse()
    
    async def action_quit(self: AppActionsProtocol) -> None:
        """Quit with debouncing."""
        if self._debounce_action('quit', 0.5):
            return
        
        await self._cleanup_processes()
        self.exit()

    async def action_kill_by_ports(self: AppActionsProtocol) -> None:
        """Emergency kill by ports."""
        if self._debounce_action('kill_ports', 1.0):
            return
        
        self._mark_activity()
        
        if not self.running_projects:
            if self._log:
                self._log.write("[yellow]No running projects[/yellow]")
            return
        
        # Run port kills in parallel
        ports = {p.port for p in self.running_projects.values() if p.port}
        if ports:
            kill_tasks = [
                asyncio.get_event_loop().run_in_executor(
                    None, PortUtils.kill_processes_by_port, port
                )
                for port in ports
            ]
            results = await asyncio.gather(*kill_tasks, return_exceptions=True)
            
            for port, result in zip(ports, results):
                if isinstance(result, Exception):
                    if self._log:
                        self._log.write(f"[red]Failed to kill port {port}[/red]")
                else:
                    if self._log:
                        self._log.write(f"[green]Killed port {port}[/green]")

    def action_switch_to_project_tab(self: AppActionsProtocol, key: str) -> None:
        """Instant tab switching by number."""
        self._mark_activity()
        
        if not self._log_tabs or not self._log_tabs.display:
            return
        
        try:
            # Direct tab access without iteration
            tab_num = int(key) - 1
            active_projects = sorted(self.running_projects.keys())
            
            if 0 <= tab_num < len(active_projects):
                tab_id = f"tab-{active_projects[tab_num]}"
                # Direct assignment for instant switch
                self._log_tabs.active = tab_id
        except (ValueError, IndexError, KeyError):
            pass

    def action_switch_to_all_logs(self: AppActionsProtocol) -> None:
        """Instant switch to All Logs."""
        self._mark_activity()
        
        if self._log_tabs and self._log_tabs.display:
            self._log_tabs.active = "tab-all"

    def action_next_log_tab(self: AppActionsProtocol) -> None:
        """Fast next tab."""
        self._mark_activity()
        
        if self._log_tabs and self._log_tabs.display:
            # Use native method for speed
            self._log_tabs.action_next_tab()

    def action_prev_log_tab(self: AppActionsProtocol) -> None:
        """Fast previous tab."""
        self._mark_activity()
        
        if self._log_tabs and self._log_tabs.display:
            # Use native method for speed
            self._log_tabs.action_previous_tab()

    def action_toggle_or_start(self: AppActionsProtocol) -> None:
        """Toggle selection or start."""
        if self._debounce_action('toggle_start', 0.1):
            return
        
        self._mark_activity()
        
        if not self._table or not self.projects or not self._table.display:
            return
        
        cursor_row = self._table.cursor_row
        if cursor_row is None:
            return
        
        start_row = len(self.projects) + 1
        if cursor_row == start_row:
            # Async start without blocking
            self.create_task(self.action_start_selected())
        elif cursor_row < len(self.projects):
            self._toggle_index(cursor_row)

    def action_select_all(self: AppActionsProtocol) -> None:
        """Select all projects."""
        if self.started:
            return
        
        self.selected = set(range(len(self.projects)))
        # Batch update
        self._batch_refresh_selection()

    def action_clear_selection(self: AppActionsProtocol) -> None:
        """Clear selection."""
        if self.started:
            return
        
        old_selected = self.selected.copy()
        self.selected.clear()
        # Batch update for efficiency
        for idx in old_selected:
            self._refresh_selection_cell(idx)
        self._update_start_row_count()

    def action_cursor_down(self: AppActionsProtocol) -> None:
        """Move cursor down."""
        if self._table and self._table.display:
            self._table.action_cursor_down()

    def action_cursor_up(self: AppActionsProtocol) -> None:
        """Move cursor up."""
        if self._table and self._table.display:
            self._table.action_cursor_up()

    async def action_start_selected(self: AppActionsProtocol) -> None:
        """Start selected projects asynchronously."""
        if not self.selected:
            if self._log:
                self._log.write("[bold red]No projects selected[/bold red]")
            return
        
        if self.started:
            if self._log:
                self._log.write("[yellow]Already started[/yellow]")
            return
        
        self.started = True
        
        # Fast UI switch
        self.call_from_thread(self._switch_to_running_view)
        
        if self._log:
            self._log.write(f"[green]Starting {len(self.selected)} project(s)...[/green]")
        
        # Start projects in parallel for speed
        start_tasks = [
            self._start_project(idx) 
            for idx in sorted(self.selected)
        ]
        await asyncio.gather(*start_tasks, return_exceptions=True)
        
        # Start update timer
        self.create_task(self._update_loop())


class UIManagement:
    """Mixin for UI management methods."""
    
    def _populate_table(self: AppActionsProtocol) -> None:
        """Populate table efficiently."""
        if not self._table:
            return
        
        # Debug log
        if self._log:
            self._log.write(f"[dim]Loading {len(self.projects)} projects...[/dim]")
        
        # Clear table
        self._table.clear()
        
        # Add project rows
        for idx, proj in enumerate(self.projects):
            self._table.add_row(
                str(idx + 1), "", proj.name, proj.path, "Ready"
            )
        
        # Add separator and start row
        self._table.add_row(
            "─" * 3, "─" * 8, "─" * 20, "─" * 30, "─" * 10
        )
        self._table.add_row(
            "▶", "", 
            "[bold green]START SELECTED PROJECTS[/bold green]",
            f"[dim]{len(self.selected)} selected[/dim]", 
            ""
        )

    def _switch_to_running_view(self: AppActionsProtocol) -> None:
        """Fast UI switch to running view."""
        # Hide/show in batch
        if self._project_selection_panel:
            self._project_selection_panel.display = False
        
        if self._running_panel:
            self._running_panel.display = True
        
        if self._log_tabs:
            self._log_tabs.display = True

    def _update_status_display(self: AppActionsProtocol) -> None:
        """Update status display if visible."""
        if self._running_panel and self._running_panel.display and self.running_projects:
            self._running_panel.update_status(self.running_projects)

    def _add_project_tab(self: AppActionsProtocol, project_idx: int, project_name: str) -> None:
        """Add project tab efficiently."""
        if not self._log_tabs:
            return
        
        tab_id = f"tab-{project_idx}"
        
        # Create log widget with performance settings
        project_log = RichLog(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            max_lines=2000  # Limit for performance
        )
        
        # Simple tab pane
        class ProjectTab(TabPane):
            def compose(self) -> ComposeResult:
                yield project_log
        
        tab = ProjectTab(project_name, id=tab_id)
        self._log_tabs.add_pane(tab)
        self._project_log_widgets[project_idx] = project_log

    def _remove_project_tab(self: AppActionsProtocol, project_idx: int) -> None:
        """Remove project tab."""
        if not self._log_tabs:
            return
        
        tab_id = f"tab-{project_idx}"
        try:
            self._log_tabs.remove_pane(tab_id)
            self._project_log_widgets.pop(project_idx, None)
        except Exception:
            pass

    def _write_help_note(self: AppActionsProtocol) -> None:
        """Write help text."""
        if self._log:
            self._log.write(
                "[dim]Press [bold]E[/bold] to select, "
                "[bold]S[/bold] to start. "
                "[bold]A[/bold]=All [bold]C[/bold]=Clear "
                "[bold]R[/bold]=Toggle Panel [bold]Q[/bold]=Quit[/dim]"
            )
            self._log.write(
                "[dim]Tabs: [bold]1-9[/bold]=Projects "
                "[bold]0[/bold]=All [bold]Tab[/bold]=Next/Prev[/dim]"
            )

    def _toggle_index(self: AppActionsProtocol, idx: int) -> None:
        """Toggle project selection."""
        if idx < 0 or idx >= len(self.projects):
            return
        
        if idx in self.selected:
            self.selected.discard(idx)
        else:
            self.selected.add(idx)
        
        self._refresh_selection_cell(idx)

    def _refresh_selection_cell(self: AppActionsProtocol, idx: int) -> None:
        """Update selection cell."""
        if not self._table or idx < 0 or idx >= len(self.projects):
            return
        
        try:
            mark = "✓" if idx in self.selected else ""
            self._table.update_cell_at((idx, 1), mark)
            self._update_start_row_count()
        except Exception:
            pass

    def _batch_refresh_selection(self: AppActionsProtocol) -> None:
        """Batch refresh all selections."""
        if not self._table:
            return
        
        for idx in range(len(self.projects)):
            mark = "✓" if idx in self.selected else ""
            try:
                self._table.update_cell_at((idx, 1), mark)
            except Exception:
                pass
        
        self._update_start_row_count()

    def _update_start_row_count(self: AppActionsProtocol) -> None:
        """Update start row count."""
        if not self._table:
            return
        
        try:
            start_row = len(self.projects) + 1
            count_text = f"[dim]{len(self.selected)} selected[/dim]"
            self._table.update_cell_at((start_row, 3), count_text)
        except Exception:
            pass

    def _set_status(self: AppActionsProtocol, idx: int, text: str) -> None:
        """Update status column."""
        if not self._table or idx < 0 or idx >= len(self.projects):
            return
        
        try:
            self._table.update_cell_at((idx, 4), text)
        except Exception:
            pass

    def _cleanup_old_data(self: AppActionsProtocol) -> None:
        """Periodic cleanup of old data."""
        current = time.time()
        to_remove = []
        
        for idx, proj in list(self.running_projects.items()):
            if proj.status.startswith("Exited") or proj.status == "Terminated":
                age = current - proj.start_time.timestamp()
                if age > 300:  # 5 minutes
                    to_remove.append(idx)
        
        for idx in to_remove:
            self.running_projects.pop(idx, None)
            self.processes.pop(idx, None)
            if idx in self.log_tasks:
                task = self.log_tasks.pop(idx, None)
                if task:
                    task.cancel()