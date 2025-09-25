# Complete Shutdown System Rewrite Plan

## Problem Statement

### Current Issues
1. **AsyncIO Event Loop Error**: `RuntimeError: Event loop is closed` when pressing 'q' due to subprocess transports attempting cleanup after loop closure
2. **Node.js Process Leaks**: Node processes started via npm/yarn/pnpm create child processes that aren't killed when the parent process terminates
3. **Port Binding Issues**: Ports remain bound even after attempting to stop projects, requiring manual `ss -tulnp` and kill commands
4. **Race Conditions**: Cleanup operations happen in undefined order, causing resource conflicts

## Architecture Overview

```
ShutdownManager (Orchestrator)
├── ResourceRegistry (Tracking)
│   ├── ProcessTracker
│   │   ├── Wrapper processes (npm/yarn/pnpm)
│   │   └── Actual Node.js processes (found via port)
│   ├── TaskTracker (asyncio tasks)
│   ├── TransportTracker (pipes/streams)
│   └── PortTracker (bound ports)
├── ShutdownSequencer (Phases)
│   ├── Phase 1: Stop accepting new operations
│   ├── Phase 2: Cancel asyncio tasks
│   ├── Phase 3: Terminate Node.js processes
│   ├── Phase 4: Kill wrapper processes
│   ├── Phase 5: Close transports/pipes
│   └── Phase 6: Close event loop
└── ErrorRecovery
    ├── TimeoutHandler
    ├── ForceKiller
    └── EmergencyExit
```

## Detailed Implementation Plan

### Phase 1: Core Infrastructure

#### 1.1 Create Resource Registry (`src/core/resource_registry.py`)

```python
class ResourceRegistry:
    """Central registry for all managed resources"""
    
    def __init__(self):
        self.processes = {}  # name -> ProcessInfo
        self.tasks = {}      # name -> set of asyncio.Task
        self.transports = {} # name -> set of transports
        self.ports = {}      # name -> port number
        self.node_pids = {}  # name -> set of actual Node.js PIDs
    
    def register_process(self, name: str, wrapper_process, port: int = None)
    def register_node_pids(self, name: str, pids: Set[int])
    def register_task(self, name: str, task: asyncio.Task)
    def register_transport(self, name: str, transport)
    def get_all_resources(self, name: str) -> ResourceBundle
    def clear_resources(self, name: str)
```

#### 1.2 Create Shutdown Manager (`src/core/shutdown_manager.py`)

```python
class ShutdownManager:
    """Orchestrates graceful shutdown of all components"""
    
    def __init__(self, registry: ResourceRegistry, process_manager):
        self.registry = registry
        self.process_manager = process_manager
        self.shutdown_in_progress = False
        self.shutdown_event = asyncio.Event()
    
    async def initiate_shutdown(self, reason: str = "user_request")
    async def execute_shutdown_sequence(self)
    async def emergency_shutdown(self)
    def get_shutdown_status(self) -> ShutdownStatus
```

### Phase 2: Node.js Process Management Enhancement

#### 2.1 Enhance Process Discovery (`src/core/process_manager.py`)

**Modified Functions:**
- `start_project()` - Track both wrapper and actual Node.js processes
  - After starting npm/yarn/pnpm, wait for port to be bound
  - Use port scanner to find actual Node.js PIDs
  - Register all PIDs in ResourceRegistry
  
- `_wait_and_map_port()` - Enhanced to properly track Node processes
  - Use `ss -tulnp` or `lsof` to find processes on port
  - Track entire process tree, not just direct children
  - Store mapping of wrapper PID → Node.js PIDs

**New Functions:**
- `_discover_node_processes(port: int) -> Set[int]`
  - Platform-specific process discovery
  - Linux: Parse `/proc/net/tcp` and `/proc/*/fd/*`
  - macOS: Use `lsof -i :port`
  - Windows: Use `netstat -ano | findstr :port`
  
- `_get_process_tree(pid: int) -> Set[int]`
  - Recursively find all child processes
  - Include processes that have been reparented

#### 2.2 Create Node Process Killer (`src/core/node_killer.py`)

```python
class NodeProcessKiller:
    """Specialized killer for Node.js process trees"""
    
    async def kill_node_project(self, name: str, port: int, wrapper_pid: int):
        # Step 1: Find all Node.js processes on the port
        node_pids = await self.find_node_processes(port)
        
        # Step 2: Send SIGTERM to Node processes first
        for pid in node_pids:
            self.terminate_process(pid)
        
        # Step 3: Wait briefly for graceful shutdown
        await asyncio.sleep(1)
        
        # Step 4: Force kill any remaining Node processes
        remaining = await self.find_node_processes(port)
        for pid in remaining:
            self.force_kill_process(pid)
        
        # Step 5: Kill the wrapper process
        self.kill_process_tree(wrapper_pid)
        
        # Step 6: Verify port is released
        await self.wait_for_port_release(port, timeout=5)
```

### Phase 3: Shutdown Sequence Implementation

#### 3.1 Shutdown Phases (`src/core/shutdown_manager.py`)

```python
async def execute_shutdown_sequence(self):
    """Execute ordered shutdown sequence"""
    
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
```

#### 3.2 Phase Implementations

**Phase 1: Stop Accepting New Operations**
- Set shutdown flag
- Prevent new project starts
- Disable UI interactions

**Phase 2: Cancel Tasks**
- Cancel all reader tasks
- Cancel health monitoring tasks
- Wait for task completion with timeout

**Phase 3: Terminate Node.js Processes**
```python
async def _phase3_terminate_node_processes(self):
    for name in self.registry.processes:
        port = self.registry.ports.get(name)
        if port:
            # Find and terminate Node.js processes
            node_pids = find_process_by_port(port)
            for pid in node_pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
    
    # Wait for graceful termination
    await asyncio.sleep(2)
    
    # Force kill remaining processes
    for name in self.registry.processes:
        port = self.registry.ports.get(name)
        if port:
            remaining = find_process_by_port(port)
            for pid in remaining:
                kill_process_tree(pid)
```

**Phase 4: Kill Wrapper Processes**
```python
async def _phase4_kill_wrappers(self):
    for name, process_info in self.registry.processes.items():
        wrapper = process_info.wrapper_process
        if wrapper.returncode is None:
            wrapper.terminate()
            try:
                await asyncio.wait_for(wrapper.wait(), timeout=2)
            except asyncio.TimeoutError:
                wrapper.kill()
                await wrapper.wait()
```

**Phase 5: Close Transports**
```python
async def _phase5_close_transports(self):
    for name, transports in self.registry.transports.items():
        for transport in transports:
            # Drain pipes first
            if hasattr(transport, 'get_pipe_transport'):
                pipe = transport.get_pipe_transport(0)
                if pipe and not pipe.is_closing():
                    pipe.close()
            
            # Close transport
            if not transport.is_closing():
                transport.close()
    
    # Give event loop time to process close callbacks
    await asyncio.sleep(0.1)
```

**Phase 6: Event Loop Cleanup**
```python
async def _phase6_cleanup_loop(self):
    # Cancel any remaining tasks
    tasks = [t for t in asyncio.all_tasks() 
             if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Stop the event loop (but don't close it yet)
    loop = asyncio.get_running_loop()
    loop.stop()
```

### Phase 4: Signal Handler Enhancement

#### 4.1 Update Signal Handler (`src/core/signal_handler.py`)

```python
class SignalHandler:
    def __init__(self, shutdown_manager: ShutdownManager):
        self.shutdown_manager = shutdown_manager
        self.signal_count = 0
        self.last_signal_time = 0
    
    def _handle_signal(self, signum: int, frame):
        current_time = time.time()
        
        # Handle multiple signals (force kill on 3rd signal)
        if current_time - self.last_signal_time < 1:
            self.signal_count += 1
        else:
            self.signal_count = 1
        
        self.last_signal_time = current_time
        
        if self.signal_count >= 3:
            # Emergency exit
            print("\n!!! Force exit !!!")
            os._exit(1)
        elif self.signal_count == 2:
            print("\nForce stopping... (press again for emergency exit)")
            asyncio.create_task(self.shutdown_manager.emergency_shutdown())
        else:
            print("\nGraceful shutdown... (press again to force)")
            asyncio.create_task(self.shutdown_manager.initiate_shutdown())
```

### Phase 5: UI Integration

#### 5.1 Update Monitoring Screen (`src/screens/monitoring.py`)

```python
async def action_quit(self):
    """Initiate graceful shutdown"""
    # Show shutdown progress
    self.show_shutdown_overlay()
    
    try:
        # Use shutdown manager
        shutdown_manager = ShutdownManager(
            self.app.resource_registry,
            self._manager
        )
        
        # Register UI callback for progress updates
        shutdown_manager.on_phase_change = self.update_shutdown_progress
        
        # Execute shutdown
        await shutdown_manager.initiate_shutdown("user_quit")
        
    except Exception as e:
        # Emergency exit on failure
        self.show_error(f"Shutdown failed: {e}")
        await asyncio.sleep(1)
        os._exit(1)
    
    finally:
        self.app.exit()
```

### Phase 6: Platform-Specific Handlers

#### 6.1 Create Platform Utilities (`src/utils/platform_cleanup.py`)

```python
class PlatformCleaner:
    @staticmethod
    def get_cleaner():
        if sys.platform == "win32":
            return WindowsCleaner()
        else:
            return UnixCleaner()

class WindowsCleaner:
    def cleanup_event_loop(self, loop):
        # ProactorEventLoop specific cleanup
        if hasattr(loop, '_proactor'):
            loop._proactor.close()
    
    def find_processes_on_port(self, port):
        # Use netstat on Windows
        cmd = f"netstat -ano | findstr :{port}"
        # Parse output to get PIDs

class UnixCleaner:
    def cleanup_event_loop(self, loop):
        # Unix selector cleanup
        if hasattr(loop, '_selector'):
            loop._selector.close()
    
    def find_processes_on_port(self, port):
        # Use ss or lsof on Unix
        cmd = f"ss -tulnp | grep :{port}"
        # Parse output to get PIDs
```

### Phase 7: Testing Strategy

#### 7.1 Test Files to Create/Update

1. **`tests/test_shutdown_manager.py`**
   - Test each shutdown phase independently
   - Test phase ordering
   - Test timeout handling
   - Test emergency shutdown

2. **`tests/test_node_killer.py`**
   - Test Node.js process discovery
   - Test process tree killing
   - Test port release verification

3. **`tests/test_resource_registry.py`**
   - Test resource registration
   - Test resource cleanup
   - Test orphan detection

4. **`tests/integration/test_full_shutdown.py`**
   - Start multiple Node.js projects
   - Trigger shutdown
   - Verify all processes killed
   - Verify all ports released
   - Verify no asyncio errors

### Phase 8: Configuration

#### 8.1 Create Shutdown Configuration (`src/config/shutdown.yaml`)

```yaml
shutdown:
  graceful_timeout: 5.0
  force_kill_timeout: 2.0
  emergency_exit_timeout: 10.0
  
  node_process:
    discovery_timeout: 2.0
    termination_timeout: 3.0
    port_release_timeout: 5.0
  
  asyncio:
    task_cancel_timeout: 2.0
    transport_close_timeout: 1.0
    loop_cleanup_timeout: 0.5
  
  ui:
    show_progress: true
    progress_update_interval: 0.5
```

## Implementation Order

### Week 1: Foundation
1. Create `ResourceRegistry` class
2. Create `ShutdownManager` class
3. Create `NodeProcessKiller` class
4. Update `ProcessManager` to use registry

### Week 2: Shutdown Sequence
1. Implement shutdown phases
2. Integrate with signal handler
3. Add platform-specific handlers
4. Update UI quit actions

### Week 3: Testing & Refinement
1. Write unit tests
2. Write integration tests
3. Test on all platforms (Windows, macOS, Linux)
4. Fix edge cases

## Success Criteria

1. **No AsyncIO Errors**: Pressing 'q' should never produce "Event loop is closed" errors
2. **Complete Process Cleanup**: All Node.js processes must be terminated
3. **Port Release**: All ports must be released within 5 seconds of shutdown
4. **Graceful Degradation**: System should handle partial failures gracefully
5. **User Feedback**: Clear progress indication during shutdown
6. **Emergency Exit**: Force exit available if graceful shutdown fails
7. **Cross-Platform**: Works on Windows, macOS, and Linux

## Monitoring & Logging

### Shutdown Logs Should Include:
```
[INFO] Shutdown initiated: user_quit
[INFO] Phase 1: Stopping new operations
[INFO] Phase 2: Cancelling 5 tasks
[INFO] Phase 3: Terminating Node processes - Project A (PIDs: 1234, 1235)
[INFO] Phase 3: Terminating Node processes - Project B (PIDs: 2234, 2235)
[INFO] Phase 4: Killing wrapper processes
[INFO] Phase 5: Closing transports (10 active)
[INFO] Phase 6: Event loop cleanup
[INFO] Shutdown complete in 3.2s
```

## Error Recovery Matrix

| Failure Point | Recovery Action | Timeout | Fallback |
|--------------|-----------------|---------|-----------|
| Task cancellation fails | Force cancel | 2s | Continue |
| Node process won't SIGTERM | SIGKILL | 3s | Kill process tree |
| Port won't release | Kill all on port | 5s | Log warning |
| Transport won't close | Force close | 1s | Abandon |
| Event loop won't stop | os._exit(1) | 10s | Force exit |

## Future Enhancements

1. **Shutdown Profiles**: Different shutdown strategies for development vs production
2. **Partial Shutdown**: Ability to stop specific projects during shutdown
3. **Shutdown Hooks**: Allow plugins to register cleanup callbacks
4. **State Persistence**: Save project state before shutdown for recovery
5. **Metrics Collection**: Track shutdown performance and failures
6. **Graceful Restart**: Restart without full shutdown when possible