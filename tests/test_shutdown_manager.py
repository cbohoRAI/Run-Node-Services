"""Tests for ShutdownManager."""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.core.shutdown_manager import ShutdownManager, ShutdownPhase, ShutdownStatus
from src.core.resource_registry import ResourceRegistry, ProcessInfo


class MockProcessManager:
    """Mock ProcessManager for testing."""
    def __init__(self):
        self._shutdown_flag = False
    
    async def stop_all(self):
        pass
    
    async def cleanup_resources(self):
        pass


class TestShutdownManager:
    
    @pytest.fixture
    async def registry(self):
        """Create a ResourceRegistry instance."""
        return ResourceRegistry()
    
    @pytest.fixture
    def process_manager(self):
        """Create a mock ProcessManager."""
        return MockProcessManager()
    
    @pytest.fixture
    def shutdown_manager(self, registry, process_manager):
        """Create a ShutdownManager instance."""
        return ShutdownManager(
            registry=registry,
            process_manager=process_manager,
            graceful_timeout=5.0,
            emergency_timeout=10.0
        )
    
    async def test_shutdown_status_properties(self):
        """Test ShutdownStatus properties."""
        status = ShutdownStatus()
        
        assert status.phase == ShutdownPhase.IDLE
        assert status.elapsed_time == 0.0
        assert not status.is_complete
        
        status.phase = ShutdownPhase.COMPLETE
        assert status.is_complete
    
    async def test_initiate_shutdown_success(self, shutdown_manager):
        """Test successful shutdown initiation."""
        # Mock the execute_shutdown_sequence to complete quickly
        shutdown_manager.execute_shutdown_sequence = AsyncMock()
        
        await shutdown_manager.initiate_shutdown("test_reason")
        
        assert shutdown_manager.shutdown_in_progress
        assert shutdown_manager.status.phase == ShutdownPhase.COMPLETE
        assert shutdown_manager.status.start_time is not None
        shutdown_manager.execute_shutdown_sequence.assert_called_once()
    
    async def test_initiate_shutdown_already_in_progress(self, shutdown_manager):
        """Test shutdown when already in progress."""
        shutdown_manager.shutdown_in_progress = True
        
        # Should return immediately without doing anything
        await shutdown_manager.initiate_shutdown("test_reason")
        
        # Status should still be idle since no actual shutdown occurred
        assert shutdown_manager.status.phase == ShutdownPhase.IDLE
    
    async def test_initiate_shutdown_with_exception(self, shutdown_manager):
        """Test shutdown when execute_shutdown_sequence raises an exception."""
        # Mock execute_shutdown_sequence to raise an exception
        shutdown_manager.execute_shutdown_sequence = AsyncMock(side_effect=Exception("Test error"))
        shutdown_manager.emergency_shutdown = AsyncMock()
        
        await shutdown_manager.initiate_shutdown("test_reason")
        
        shutdown_manager.emergency_shutdown.assert_called_once()
        assert "Shutdown failed: Test error" in shutdown_manager.status.errors
    
    @patch('os._exit')
    async def test_emergency_shutdown(self, mock_exit, shutdown_manager, registry):
        """Test emergency shutdown procedure."""
        # Add some mock resources
        mock_process = Mock()
        mock_process.pid = 1234
        await registry.register_process("test-project", mock_process, port=3000)
        await registry.register_node_pids("test-project", {5678})
        
        # Mock the node killer
        shutdown_manager.node_killer.kill_all_on_port = AsyncMock()
        
        with patch('os.kill') as mock_kill:
            await shutdown_manager.emergency_shutdown()
        
        assert shutdown_manager.status.phase == ShutdownPhase.EMERGENCY
        assert shutdown_manager.status.emergency_mode
        
        # Should try to kill processes on port
        shutdown_manager.node_killer.kill_all_on_port.assert_called_with(3000)
        
        # Should try to kill wrapper process
        mock_kill.assert_called_with(1234, 9)  # SIGKILL
        
        # Should exit
        mock_exit.assert_called_once_with(1)
    
    async def test_phase1_stop_accepting(self, shutdown_manager):
        """Test phase 1 - stop accepting operations."""
        await shutdown_manager._phase1_stop_accepting()
        
        assert shutdown_manager.status.phase == ShutdownPhase.STOPPING_OPERATIONS
        assert shutdown_manager.process_manager._shutdown_flag
    
    async def test_phase2_cancel_tasks(self, shutdown_manager, registry):
        """Test phase 2 - cancel asyncio tasks."""
        # Create some mock tasks
        task1 = asyncio.create_task(asyncio.sleep(10))
        task2 = asyncio.create_task(asyncio.sleep(10))
        
        await registry.register_task("project1", task1)
        await registry.register_task("project2", task2)
        
        await shutdown_manager._phase2_cancel_tasks()
        
        assert shutdown_manager.status.phase == ShutdownPhase.CANCELLING_TASKS
        assert task1.cancelled()
        assert task2.cancelled()
    
    async def test_phase3_terminate_node_processes(self, shutdown_manager, registry):
        """Test phase 3 - terminate Node.js processes."""
        # Add mock process info
        mock_process = Mock()
        mock_process.pid = 1234
        await registry.register_process("test-project", mock_process, port=3000)
        await registry.register_node_pids("test-project", {5678})
        
        # Mock the node killer
        shutdown_manager.node_killer.kill_node_project = AsyncMock(return_value=True)
        
        await shutdown_manager._phase3_terminate_node_processes()
        
        assert shutdown_manager.status.phase == ShutdownPhase.TERMINATING_NODE
        shutdown_manager.node_killer.kill_node_project.assert_called_once_with(
            name="test-project",
            port=3000,
            known_node_pids={5678}
        )
        assert shutdown_manager.status.projects_processed == 1
    
    async def test_phase4_kill_wrappers(self, shutdown_manager, registry):
        """Test phase 4 - kill wrapper processes."""
        # Create mock wrapper process
        mock_wrapper = AsyncMock()
        mock_wrapper.returncode = None
        mock_wrapper.wait = AsyncMock()
        
        process_info = ProcessInfo(
            wrapper_process=mock_wrapper,
            wrapper_pid=1234
        )
        await registry.register_process("test-project", mock_wrapper, port=3000)
        
        await shutdown_manager._phase4_kill_wrappers()
        
        assert shutdown_manager.status.phase == ShutdownPhase.KILLING_WRAPPERS
        mock_wrapper.terminate.assert_called_once()
    
    async def test_phase5_close_transports(self, shutdown_manager, registry):
        """Test phase 5 - close transports."""
        # Create mock transport
        mock_transport = Mock()
        mock_transport.is_closing.return_value = False
        
        await registry.register_transport("test-project", mock_transport)
        
        # Create mock subprocess
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.stdin.is_closing.return_value = False
        mock_process.stdout.is_closing.return_value = False
        mock_process.stderr.is_closing.return_value = False
        
        await registry.register_process("test-project", mock_process)
        
        await shutdown_manager._phase5_close_transports()
        
        assert shutdown_manager.status.phase == ShutdownPhase.CLOSING_TRANSPORTS
        mock_transport.close.assert_called_once()
        mock_process.stdin.close.assert_called_once()
        mock_process.stdout.close.assert_called_once()
        mock_process.stderr.close.assert_called_once()
    
    async def test_phase6_cleanup_loop(self, shutdown_manager):
        """Test phase 6 - cleanup event loop."""
        # Create a mock task
        mock_task = Mock()
        mock_task.cancel = Mock()
        
        with patch('asyncio.all_tasks', return_value=[mock_task]), \
             patch('asyncio.current_task', return_value=None), \
             patch('asyncio.gather', new=AsyncMock()) as mock_gather:
            
            await shutdown_manager._phase6_cleanup_loop()
        
        assert shutdown_manager.status.phase == ShutdownPhase.CLEANING_LOOP
        mock_task.cancel.assert_called_once()
        mock_gather.assert_called_once()
    
    async def test_callbacks(self, shutdown_manager):
        """Test phase change and progress callbacks."""
        phase_changes = []
        progress_updates = []
        
        def on_phase_change(phase, message):
            phase_changes.append((phase, message))
        
        def on_progress_update(status):
            progress_updates.append(status)
        
        shutdown_manager.on_phase_change = on_phase_change
        shutdown_manager.on_progress_update = on_progress_update
        
        shutdown_manager._notify_phase_change(ShutdownPhase.STOPPING_OPERATIONS, "Test message")
        shutdown_manager._notify_progress()
        
        assert len(phase_changes) == 1
        assert phase_changes[0] == (ShutdownPhase.STOPPING_OPERATIONS, "Test message")
        
        assert len(progress_updates) == 1
        assert progress_updates[0] is shutdown_manager.status