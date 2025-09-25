"""Shutdown Manager - Orchestrates graceful shutdown of all components.

This module provides the main orchestration logic for shutting down the application
in a controlled manner, ensuring all resources are cleaned up properly and avoiding
the "Event loop is closed" errors.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import signal
from enum import Enum
from typing import Optional, Callable, Set, Dict, Any

from .resource_registry import ResourceRegistry, ResourceBundle
from .node_killer import NodeProcessKiller
from pathlib import Path

from .shutdown_logger import shutdown_logger
logger = shutdown_logger

class ShutdownPhase(Enum):
    """Phases of the shutdown process."""
    IDLE = "idle"
    STOPPING_OPERATIONS = "stopping_operations"
    CANCELLING_TASKS = "cancelling_tasks"
    TERMINATING_NODE = "terminating_node"
    KILLING_WRAPPERS = "killing_wrappers"
    CLOSING_TRANSPORTS = "closing_transports"
    CLEANING_LOOP = "cleaning_loop"
    COMPLETE = "complete"
    EMERGENCY = "emergency"


class ShutdownStatus:
    """Status information about the shutdown process."""
    
    def __init__(self):
        self.phase = ShutdownPhase.IDLE
        self.start_time: Optional[float] = None
        self.current_operation = ""
        self.projects_processed = 0
        self.total_projects = 0
        self.errors: list[str] = []
        self.emergency_mode = False
    
    @property
    def elapsed_time(self) -> float:
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
    
    @property
    def is_complete(self) -> bool:
        return self.phase in (ShutdownPhase.COMPLETE, ShutdownPhase.EMERGENCY)

class ShutdownManager:
    """Orchestrates graceful shutdown of all components."""
    
    def __init__(
        self, 
        registry: ResourceRegistry, 
        process_manager: Any,  # ProcessManager
        graceful_timeout: float = 10.0,
        emergency_timeout: float = 15.0,
        log_dir: Optional[Path] = None
    ):
        self.registry = registry
        self.process_manager = process_manager
        self.graceful_timeout = graceful_timeout
        self.emergency_timeout = emergency_timeout
        
        self.shutdown_in_progress = False
        self.shutdown_event = asyncio.Event()
        self.status = ShutdownStatus()
        self.node_killer = NodeProcessKiller()
        
        # Initialize the file logger
        logger.initialize(log_file="last_run.txt", log_dir=log_dir)
        
        # Callback for UI updates
        self.on_phase_change: Optional[Callable[[ShutdownPhase, str], None]] = None
        self.on_progress_update: Optional[Callable[[ShutdownStatus], None]] = None
        
        logger.info("ShutdownManager initialized")
        logger.debug(f"Graceful timeout: {graceful_timeout}s, Emergency timeout: {emergency_timeout}s")
    
    async def initiate_shutdown(self, reason: str = "user_request") -> None:
        """Initiate graceful shutdown process."""
        if self.shutdown_in_progress:
            logger.info("Shutdown already in progress")
            return
        
        self.shutdown_in_progress = True
        self.status.start_time = time.time()
        
        logger.info("=" * 60)
        logger.info(f"SHUTDOWN INITIATED: {reason}")
        logger.info("=" * 60)
        self._notify_phase_change(ShutdownPhase.STOPPING_OPERATIONS, f"Starting shutdown: {reason}")
        
        try:
            # Set up emergency timeout
            emergency_task = asyncio.create_task(self._emergency_timeout_handler())
            
            # Execute shutdown sequence
            await self.execute_shutdown_sequence()
            
            # Cancel emergency timeout
            emergency_task.cancel()
            
            self.status.phase = ShutdownPhase.COMPLETE
            elapsed = self.status.elapsed_time
            logger.info("=" * 60)
            logger.info(f"SHUTDOWN COMPLETED SUCCESSFULLY in {elapsed:.2f} seconds")
            logger.info("=" * 60)
            
            # Restore terminal before completing
            self._restore_terminal()
            
            # Mark logger as complete
            logger.complete()
            
        except Exception as e:
            logger.error(f"SHUTDOWN FAILED: {e}")
            logger.error("Starting emergency shutdown...")
            self.status.errors.append(f"Shutdown failed: {e}")
            await self.emergency_shutdown()
        finally:
            self.shutdown_event.set()
            logger.flush()
            logger.complete()
    
    async def execute_shutdown_sequence(self) -> None:
        """Execute the ordered shutdown sequence."""
        try:
            # Get list of all projects to track progress
            project_names = await self.registry.get_all_project_names()
            self.status.total_projects = len(project_names)
            
            # Phase 1: Stop accepting new operations
            await self._phase1_stop_accepting()
            
            # Phase 2: Cancel asyncio tasks (but not cleanup tasks)
            await self._phase2_cancel_tasks()
            
            # Phase 3: Terminate Node.js processes gracefully
            await self._phase3_terminate_node_processes()
            
            # Phase 4: Kill wrapper processes
            await self._phase4_kill_wrappers()
            
            # Phase 5: Drain and close pipes/transports
            await self._phase5_close_transports()
            
            # Phase 6: Final event loop cleanup
            await self._phase6_cleanup_loop()
            
        except Exception as e:
            logger.error("Error in shutdown sequence: %s", e)
            raise
    
    async def emergency_shutdown(self) -> None:
        """Perform emergency shutdown when graceful shutdown fails."""
        logger.warning("Performing emergency shutdown")
        self.status.phase = ShutdownPhase.EMERGENCY
        self.status.emergency_mode = True
        self._notify_phase_change(ShutdownPhase.EMERGENCY, "Emergency shutdown in progress")
        
        # Restore terminal state before exiting
        self._restore_terminal()
        
        # Create a task that will force exit after a very short timeout
        force_exit_task = asyncio.create_task(self._force_exit_after_delay(2.0))
        
        try:
            # Try to kill all processes quickly WITHOUT waiting
            project_names = await self.registry.get_all_project_names()
            
            # Collect all kill operations but don't wait for them
            kill_tasks = []
            
            for name in project_names:
                try:
                    bundle = await self.registry.get_all_resources(name)
                    
                    # Kill operations without waiting
                    if bundle.port:
                        kill_tasks.append(
                            asyncio.create_task(self.node_killer.kill_all_on_port(bundle.port))
                        )
                    
                    if bundle.process_info and bundle.process_info.wrapper_pid:
                        try:
                            os.kill(bundle.process_info.wrapper_pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            pass
                            
                except Exception as e:
                    logger.warning("Error in emergency kill of %s: %s", name, e)
            
            # Wait for kill tasks with a short timeout
            if kill_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*kill_tasks, return_exceptions=True),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Kill operations timed out")
            
            # Cancel all remaining asyncio tasks
            tasks = [t for t in asyncio.all_tasks() 
                    if t is not asyncio.current_task() 
                    and t is not force_exit_task]
            
            for task in tasks:
                task.cancel()
            
        except Exception as e:
            logger.error("Error in emergency shutdown: %s", e)
        
        finally:
            # Force exit immediately
            logger.critical("Forcing exit NOW")
            self._restore_terminal()  # One more time to be sure
            os._exit(1)

    def _restore_terminal(self) -> None:
        """Restore terminal to normal state before exit."""
        try:
            # Reset terminal to sane state
            if sys.platform != "win32":
                import subprocess
                try:
                    # Use stty to reset terminal
                    subprocess.run(['stty', 'sane'], check=False, timeout=1)
                except Exception:
                    pass
            
            # Ensure cursor is visible
            sys.stdout.write('\033[?25h')  # Show cursor
            sys.stdout.flush()
            
        except Exception as e:
            logger.debug("Error restoring terminal: %s", e)
    
    async def _force_exit_after_delay(self, delay: float) -> None:
        """Force exit after a delay as a safety net."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        
        logger.critical("Force exit timer expired - terminating process")
        os._exit(1)
    
    async def _emergency_timeout_handler(self) -> None:
        """Handle emergency timeout for shutdown."""
        try:
            await asyncio.sleep(self.emergency_timeout)
            logger.critical("Emergency timeout reached - forcing exit")
            
            # Try multiple methods to ensure exit
            try:
                # Method 1: Force kill via os._exit (most direct)
                import os
                os._exit(1)
            except:
                pass
            
            try:
                # Method 2: sys.exit 
                import sys
                sys.exit(1)
            except:
                pass
            
            try:
                # Method 3: Raise SystemExit
                raise SystemExit(1)
            except:
                pass
            
            # Method 4: If we're still here, cancel all tasks and stop the loop
            try:
                loop = asyncio.get_running_loop()
                
                # Cancel ALL tasks including ourselves
                for task in asyncio.all_tasks(loop):
                    task.cancel()
                
                # Stop the loop
                loop.stop()
                
                # Close the loop
                loop.close()
            except:
                pass
                
        except asyncio.CancelledError:
            # Normal case - shutdown completed before timeout
            logger.debug("Emergency timeout cancelled - normal shutdown completed")
            pass
    
    async def _phase1_stop_accepting(self) -> None:
        """Phase 1: Stop accepting new operations."""
        self.status.phase = ShutdownPhase.STOPPING_OPERATIONS
        self._notify_phase_change(ShutdownPhase.STOPPING_OPERATIONS, "Stopping new operations")
        
        # Set flags to prevent new project starts
        # The ProcessManager should check these flags
        if hasattr(self.process_manager, '_shutdown_flag'):
            self.process_manager._shutdown_flag = True
        
        logger.info("Phase 1: Stopped accepting new operations")
    
    async def _phase2_cancel_tasks(self) -> None:
        """Phase 2: Cancel asyncio tasks."""
        self.status.phase = ShutdownPhase.CANCELLING_TASKS
        self._notify_phase_change(ShutdownPhase.CANCELLING_TASKS, "Cancelling tasks")
        
        all_tasks = await self.registry.get_all_tasks()
        if not all_tasks:
            logger.info("Phase 2: No tasks to cancel")
            return
        
        logger.info("Phase 2: Cancelling %d tasks", len(all_tasks))
        
        # Cancel all tasks
        for task in all_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for task completion with timeout
        if all_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some tasks did not complete within timeout")
        
        logger.info("Phase 2: Task cancellation complete")
    
    async def _phase3_terminate_node_processes(self) -> None:
        """Phase 3: Terminate Node.js processes gracefully."""
        self.status.phase = ShutdownPhase.TERMINATING_NODE
        self._notify_phase_change(ShutdownPhase.TERMINATING_NODE, "Terminating Node.js processes")
        
        project_names = await self.registry.get_all_project_names()
        
        for name in project_names:
            try:
                bundle = await self.registry.get_all_resources(name)
                if bundle.process_info:
                    logger.info("Phase 3: Terminating Node processes - %s", name)
                    
                    success = await self.node_killer.kill_node_project(
                        name=name,
                        port=bundle.port,
                        known_node_pids=bundle.process_info.node_pids
                    )
                    
                    if not success:
                        self.status.errors.append(f"Failed to cleanly terminate {name}")
                
                self.status.projects_processed += 1
                self._notify_progress()
                
            except Exception as e:
                logger.error("Error terminating Node processes for %s: %s", name, e)
                self.status.errors.append(f"Error terminating {name}: {e}")
        
        logger.info("Phase 3: Node.js process termination complete")
    
    async def _phase4_kill_wrappers(self) -> None:
        """Phase 4: Kill wrapper processes."""
        self.status.phase = ShutdownPhase.KILLING_WRAPPERS
        self._notify_phase_change(ShutdownPhase.KILLING_WRAPPERS, "Killing wrapper processes")
        
        project_names = await self.registry.get_all_project_names()
        logger.info("Phase 4: Killing wrapper processes for %d projects", len(project_names))
        
        # Kill all processes concurrently with timeout
        kill_tasks = []
        
        for name in project_names:
            kill_tasks.append(self._kill_single_wrapper(name))
        
        # Execute all kills concurrently with overall timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*kill_tasks, return_exceptions=True),
                timeout=5.0  # Overall timeout for all wrapper kills
            )
        except asyncio.TimeoutError:
            logger.error("Phase 4: Timeout killing wrapper processes")
            self.status.errors.append("Timeout killing wrapper processes")
        
        logger.info("Phase 4: Wrapper process termination complete")
    
    async def _kill_single_wrapper(self, name: str) -> None:
        """Kill a single wrapper process (helper for concurrent execution)."""
        try:
            bundle = await self.registry.get_all_resources(name)
            
            # Check if we have process info
            if not bundle.process_info:
                logger.debug("No process info for %s, skipping", name)
                return
                
            # Get the wrapper PID from the stored value
            wrapper_pid = bundle.process_info.wrapper_pid
            if not wrapper_pid or wrapper_pid == 0:
                logger.debug("No wrapper PID for %s, skipping", name)
                return
            
            logger.info("Attempting to kill wrapper process for %s (pid=%s)", name, wrapper_pid)
            
            # Try to kill using psutil first
            try:
                import psutil
                try:
                    proc = psutil.Process(wrapper_pid)
                    if proc.is_running():
                        logger.debug("Process %s (pid=%s) is still running, terminating", name, wrapper_pid)
                        
                        # Try graceful termination first
                        proc.terminate()
                        
                        # Wait for graceful termination with timeout
                        try:
                            proc.wait(timeout=1.0)  # Reduced from 2.0
                            logger.info("Wrapper process %s (pid=%s) terminated gracefully", name, wrapper_pid)
                            return
                        except psutil.TimeoutExpired:
                            logger.warning("Wrapper process %s (pid=%s) did not terminate, force killing", name, wrapper_pid)
                            proc.kill()
                            
                            # Wait briefly for kill to take effect
                            try:
                                proc.wait(timeout=0.5)  # Reduced from 1.0
                                logger.info("Wrapper process %s (pid=%s) force killed", name, wrapper_pid)
                            except psutil.TimeoutExpired:
                                logger.error("Failed to kill wrapper process %s (pid=%s)", name, wrapper_pid)
                                self.status.errors.append(f"Failed to kill wrapper {name} (pid={wrapper_pid})")
                    else:
                        logger.debug("Process %s (pid=%s) is not running", name, wrapper_pid)
                        
                except psutil.NoSuchProcess:
                    logger.debug("Process %s (pid=%s) does not exist", name, wrapper_pid)
                    return
                    
            except ImportError:
                # Fallback if psutil is not available - use OS kill directly
                logger.debug("psutil not available, using OS kill for %s (pid=%s)", name, wrapper_pid)
                
                try:
                    # Check if process exists by sending signal 0
                    os.kill(wrapper_pid, 0)
                    
                    # Process exists, try to terminate it
                    logger.debug("Sending SIGTERM to %s (pid=%s)", name, wrapper_pid)
                    os.kill(wrapper_pid, signal.SIGTERM)
                    
                    # Wait a bit for graceful termination (non-blocking)
                    await asyncio.sleep(0.5)  # Reduced from 2.0
                    
                    # Check if still exists
                    try:
                        os.kill(wrapper_pid, 0)
                        # Still exists, force kill
                        logger.warning("Process %s (pid=%s) still exists after SIGTERM, sending SIGKILL", name, wrapper_pid)
                        os.kill(wrapper_pid, signal.SIGKILL)
                        
                        # Wait briefly (non-blocking)
                        await asyncio.sleep(0.2)  # Reduced from 1.0
                        
                        # Final check
                        try:
                            os.kill(wrapper_pid, 0)
                            logger.error("Process %s (pid=%s) refuses to die!", name, wrapper_pid)
                            self.status.errors.append(f"Failed to kill wrapper {name} (pid={wrapper_pid})")
                        except (ProcessLookupError, PermissionError):
                            logger.info("Process %s (pid=%s) killed", name, wrapper_pid)
                            
                    except (ProcessLookupError, PermissionError):
                        logger.info("Process %s (pid=%s) terminated after SIGTERM", name, wrapper_pid)
                        
                except ProcessLookupError:
                    logger.debug("Process %s (pid=%s) already gone", name, wrapper_pid)
                    return
                except PermissionError as e:
                    logger.error("Permission denied killing %s (pid=%s): %s", name, wrapper_pid, e)
                    self.status.errors.append(f"Permission denied killing {name} (pid={wrapper_pid})")
                    return
                    
            # Also try to kill using the subprocess object if available
            if bundle.process_info.wrapper_process:
                wrapper = bundle.process_info.wrapper_process
                if wrapper.returncode is None:
                    try:
                        wrapper.terminate()
                    except (ProcessLookupError, Exception):
                        pass
                        
        except Exception as e:
            logger.error("Error killing wrapper for %s: %s", name, e)
            self.status.errors.append(f"Error processing wrapper for {name}: {e}")
    
    async def _phase5_close_transports(self) -> None:
        """Phase 5: Close transports and pipes."""
        self.status.phase = ShutdownPhase.CLOSING_TRANSPORTS
        self._notify_phase_change(ShutdownPhase.CLOSING_TRANSPORTS, "Closing transports")
        
        project_names = await self.registry.get_all_project_names()
        transport_count = 0
        
        for name in project_names:
            try:
                bundle = await self.registry.get_all_resources(name)
                
                # Close subprocess pipes and transports
                if bundle.process_info and bundle.process_info.wrapper_process:
                    self._close_subprocess_safely(bundle.process_info.wrapper_process)
                
                # Close any registered transports
                for transport in bundle.transports:
                    try:
                        if hasattr(transport, 'close') and not getattr(transport, 'is_closing', lambda: True)():
                            transport.close()
                            transport_count += 1
                    except Exception as e:
                        logger.warning("Error closing transport: %s", e)
                        
            except Exception as e:
                logger.error("Error closing transports for %s: %s", name, e)
        
        # Give event loop time to process close callbacks
        await asyncio.sleep(0.1)
        
        logger.info("Phase 5: Closed %d transports", transport_count)
    
    async def _phase6_cleanup_loop(self) -> None:
        """Phase 6: Final event loop cleanup."""
        self.status.phase = ShutdownPhase.CLEANING_LOOP
        self._notify_phase_change(ShutdownPhase.CLEANING_LOOP, "Cleaning event loop")
        
        # Cancel any remaining tasks (excluding current task)
        tasks = [t for t in asyncio.all_tasks() 
                if t is not asyncio.current_task()]
        
        if tasks:
            logger.info("Phase 6: Cancelling %d remaining tasks", len(tasks))
            for task in tasks:
                task.cancel()
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Don't stop the event loop here - let the app do it
        logger.info("Phase 6: Event loop cleanup complete")
    
    def _close_subprocess_safely(self, proc: asyncio.subprocess.Process) -> None:
        """Safely close subprocess to prevent event loop errors."""
        try:
            # Close pipes explicitly
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
            if proc.stdout and not proc.stdout.is_closing():
                proc.stdout.close()
            if proc.stderr and not proc.stderr.is_closing():
                proc.stderr.close()
            
            # Close the underlying transport
            transport = getattr(proc, '_transport', None)
            if transport and hasattr(transport, 'close'):
                try:
                    transport.close()
                except Exception:
                    pass
                    
        except Exception:
            # Ignore errors during cleanup
            pass
    
    def _notify_phase_change(self, phase: ShutdownPhase, message: str) -> None:
        """Notify about phase changes."""
        self.status.current_operation = message
        if self.on_phase_change:
            try:
                self.on_phase_change(phase, message)
            except Exception as e:
                logger.warning("Error in phase change callback: %s", e)
    
    def _notify_progress(self) -> None:
        """Notify about progress updates."""
        if self.on_progress_update:
            try:
                self.on_progress_update(self.status)
            except Exception as e:
                logger.warning("Error in progress update callback: %s", e)
    
    def get_shutdown_status(self) -> ShutdownStatus:
        """Get current shutdown status."""
        return self.status